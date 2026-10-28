from __future__ import annotations
import csv, hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
os.environ['MKL_NUM_THREADS']='1'
os.environ['NUMEXPR_NUM_THREADS']='1'
import h5py
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'C2_ON1_12_SCENE_FORCE_DECOMP_V2.json'
C2_LOCK = ROOT / 'experiments/position_beta_clock_c2_20261023/C2_SOURCE_LOCK.json'
C1_LOCK = ROOT / 'experiments/position_prior_calibration_c1_20261022_v9/C1_SOURCE_LOCK_v2.json'
RUNS_CSV = ROOT / 'experiments/position_prior_calibration_c1_20261022_v9/reports/C1_SCREEN_PER_RUN.csv'

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def ident(path: Path) -> dict:
    st=path.stat()
    return {'path':str(path.resolve()),'sha256':sha(path),'size_bytes':st.st_size,'mtime_ns':st.st_mtime_ns}

def body_z(euler: np.ndarray) -> np.ndarray:
    roll,pitch,yaw=euler.T
    return np.column_stack((np.cos(yaw)*np.sin(pitch)*np.cos(roll)+np.sin(yaw)*np.sin(roll),
                            np.sin(yaw)*np.sin(pitch)*np.cos(roll)-np.cos(yaw)*np.sin(roll),
                            np.cos(pitch)*np.cos(roll)))

def rms_axis(a: np.ndarray) -> dict:
    return {'ALL':float(np.sqrt(np.mean(np.sum(a*a,axis=1)))),
            'X':float(np.sqrt(np.mean(a[:,0]**2))),
            'Y':float(np.sqrt(np.mean(a[:,1]**2))),
            'Z':float(np.sqrt(np.mean(a[:,2]**2)))}

def band_rms(a: np.ndarray, dt: float) -> dict:
    n=len(a)
    assert abs(dt-0.01)<1e-12, f'expected the locked 100-Hz event clock, got {dt}'
    f=np.fft.rfftfreq(n,0.01); z=np.fft.rfft(a,axis=0)
    w=np.full(len(f),2.0); w[0]=1.0
    if n%2==0: w[-1]=1.0
    # The 1500-sample, 100-Hz window has df=1/15 Hz. Use exact bin
    # indices for the 1/5/50-Hz boundaries so floating comparisons cannot
    # drop a boundary bin or the Nyquist bin.
    k1=15; k5=75; k50=n//2
    assert n==1500 and f[k1]==1.0 and f[k5]==5.0 and f[k50]==50.0
    bins=np.arange(len(f))
    specs={'0_1_Hz_including_DC':bins<k1,
           '1_5_Hz':(bins>=k1)&(bins<k5),
           '5_50_Hz_including_Nyquist':(bins>=k5)&(bins<=k50)}
    assert np.array_equal(np.logical_or.reduce(list(specs.values())),np.ones(len(f),dtype=bool))
    out={}
    for name,mask in specs.items():
        power=(w[mask,None]*np.abs(z[mask])**2).sum(axis=0)/(n*n)
        out[name]={'ALL':float(np.sqrt(power.sum())),
                   'X':float(np.sqrt(power[0])),'Y':float(np.sqrt(power[1])),'Z':float(np.sqrt(power[2]))}
    one_sided_power=(w[:,None]*np.abs(z)**2).sum(axis=0)/(n*n)
    time_power=np.mean(a*a,axis=0)
    band_sum=np.sum([np.asarray([out[name][axis]**2 for axis in ('X','Y','Z')]) for name in specs],axis=0)
    parseval_axis=float(np.max(np.abs(one_sided_power-time_power)))
    parseval_bands=float(np.max(np.abs(band_sum-time_power)))
    out['_parseval']={'axis_power_max_abs':parseval_axis,
                      'band_sum_power_max_abs':parseval_bands,
                      'vector_power_max_abs':abs(float(np.sum(one_sided_power)-np.mean(np.sum(a*a,axis=1))))}
    assert parseval_axis<1e-12 and parseval_bands<1e-12 and out['_parseval']['vector_power_max_abs']<1e-12
    return out

def main():
    assert not OUT.exists(), f'refuse overwrite: {OUT}'
    c2lock=json.loads(C2_LOCK.read_text(encoding='utf-8-sig'))
    c1lock=json.loads(C1_LOCK.read_text(encoding='utf-8-sig'))
    cfgpin=c2lock['shared_c1_inputs']
    cfgpath=Path(cfgpin['effective_config_path'])
    assert sha(cfgpath)==cfgpin['effective_config_sha256']
    cfg=loadmat(cfgpath,simplify_cells=True)['cfg']['plant']
    mass=float(cfg['mass']); gravity=float(cfg['g'])
    assert mass>0 and gravity>0
    runtime=[x for x in c1lock['frozen_runtime_files'] if Path(x['path']).name=='run_dl1018_closed_loop.m']
    assert len(runtime)==1 and sha(Path(runtime[0]['path']))==runtime[0]['sha256']
    source_paths=[C2_LOCK,C1_LOCK,RUNS_CSV,cfgpath,Path(runtime[0]['path'])]
    source_before=[ident(p) for p in source_paths]
    with RUNS_CSV.open(encoding='utf-8-sig',newline='') as f:
        entries=[r for r in csv.DictReader(f) if r['condition']=='ON1']
    assert len(entries)==12 and len({r['scene_id'] for r in entries})==12
    assert all(r['status']=='STABLE' for r in entries)
    pre={r['scene_id']:ident(Path(r['raw_path'])) for r in entries}
    records=[]
    for meta in entries:
        path=Path(meta['raw_path']); expected=meta['raw_sha256'].lower()
        assert pre[meta['scene_id']]['sha256']==expected
        with h5py.File(path,'r') as f:
            g=f['log']
            def read(key):
                a=np.asarray(g[key])
                return a.T if a.ndim==2 else a
            ids=np.flatnonzero(read('stage1_position_event_inference_valid').ravel())
            assert np.array_equal(ids,np.arange(320,19991,10)),meta['scene_id']
            state=read('state')[ids]
            times=read('transition_time').ravel()[ids]
            assert np.max(np.abs(np.diff(times)-0.01))<1e-12
            late=(times>=5.0)&(times<20.0)
            assert int(late.sum())==1500
            Ract_z=body_z(state[:,6:9]); Rfilter_z=body_z(read('filtered_attitude_reference')[ids])
            raw_key='raw_outer_attitude' if 'raw_outer_attitude' in g else None
            Rraw_z=body_z(read(raw_key)[ids]) if raw_key else None
            req=read('requested_generalized')[ids]
            real=read('realized_generalized')[ids]
            wind=read('wind_force_I')[ids]
            thrust_req=req[:,0]; thrust_real=real[:,0]
            a_actual=Ract_z*thrust_real[:,None]/mass+wind/mass
            a_actual[:,2]-=gravity
            a_f=Rfilter_z*thrust_req[:,None]/mass
            a_f[:,2]-=gravity
            d=a_actual-a_f
            wind_term=wind/mass
            direction=(Ract_z-Rfilter_z)*thrust_req[:,None]/mass
            allocation=Ract_z*(thrust_real-thrust_req)[:,None]/mass
            terms={'logged_wind_force_I_over_mass':wind_term,'actual_vs_filtered_direction':direction,
                   'requested_vs_realized_thrust':allocation}
            if Rraw_z is not None:
                terms['actual_vs_raw_direction']=(Ract_z-Rraw_z)*thrust_req[:,None]/mass
                terms['raw_vs_filtered_direction']=(Rraw_z-Rfilter_z)*thrust_req[:,None]/mass
            rec=np.sum([v for k,v in terms.items() if k in ('logged_wind_force_I_over_mass','actual_vs_filtered_direction','requested_vs_realized_thrust')],axis=0)
            closure=float(np.max(np.abs(rec-d)))
            if Rraw_z is not None:
                split=terms['actual_vs_raw_direction']+terms['raw_vs_filtered_direction']
                split_closure=float(np.max(np.abs(split-direction)))
            else: split_closure=None
            assert closure<1e-12 and (split_closure is None or split_closure<1e-12)
            online=read('stage1_position_event_applied_acceleration_mps2')[ids]
            raw=read('stage1_position_event_raw_acceleration_mps2')[ids]
            beta=read('stage1_position_event_beta').ravel()[ids,None]
            online_check=float(np.max(np.abs(online-beta*np.clip(raw,-3,3))))
            assert online_check<1e-13
            e=online-d
            e_late=e[late]
            observed_dt=float(np.median(np.diff(times[late])))
            dt=0.01
            assert abs(observed_dt-dt)<1e-12
            rms={name:rms_axis(v[late]) for name,v in terms.items()}
            rms['physical_d']=rms_axis(d[late])
            rms['online_u_minus_d']=rms_axis(e_late)
            freqs=band_rms(e_late,dt)
            record={'scene_id':meta['scene_id'],'task':meta['task'],'wind_band':meta['wind_band'],
                    'raw_path':str(path.resolve()),'raw_sha256':expected,'events_all':len(ids),
                    'events_late_5_20':int(late.sum()),'late_time_s':[float(times[late][0]),float(times[late][-1])],
                    'dt_s_for_fft':dt,'observed_median_event_dt_s':observed_dt,'decomposition_closure_max_abs_mps2':closure,
                    'raw_attitude_split_available':Rraw_z is not None,
                    'raw_direction_split_closure_max_abs_mps2':split_closure,
                    'online_beta_clip_closure_max_abs_mps2':online_check,
                    'frequency_parseval_max_abs_power_error':freqs.pop('_parseval'),
                    'late_rms_mps2':rms,'online_u_minus_d_frequency_rms_mps2':freqs}
        raw_after=ident(path)
        assert raw_after==pre[meta['scene_id']],f'raw changed: {path}'
        record['raw_identity_before']=pre[meta['scene_id']]
        record['raw_identity_after']=raw_after
        record['raw_identity_before_after_equal']=True
        records.append(record)
    post={r['scene_id']:ident(Path(r['raw_path'])) for r in entries}
    assert pre==post
    groups={'ALL':lambda r:True,
            'HF_W09_W14':lambda r:r['wind_band'] in ('W09_W11','W12_W14'),
            'W15':lambda r:r['wind_band']=='W15'}
    aggregates=[]
    for name,pred in groups.items():
        s=[r for r in records if pred(r)]
        expected_n={'ALL':12,'HF_W09_W14':6,'W15':3}[name]
        assert len(s)==expected_n,(name,len(s))
        for metric in ['late_rms_mps2','online_u_minus_d_frequency_rms_mps2']:
            if metric=='late_rms_mps2':
                metric_names=list(s[0][metric])
                for component in metric_names:
                    aggregates.append({'group':name,'n_scenes':len(s),'metric':component,
                      'RMS_equal_scene_mean':{axis:math.fsum(r[metric][component][axis] for r in s)/len(s)
                                               for axis in ('ALL','X','Y','Z')}})
            else:
                for band in (b for b in s[0][metric] if b!='_parseval'):
                    aggregates.append({'group':name,'n_scenes':len(s),'metric':'online_u_minus_d:'+band,
                      'RMS_equal_scene_mean':{axis:math.fsum(r[metric][band][axis] for r in s)/len(s)
                                               for axis in ('ALL','X','Y','Z')}})
    source_after=[ident(p) for p in source_paths]
    assert source_before==source_after
    report={'schema':'C2_ON1_FORCE_DECOMPOSITION_V1','status':'PASS_OFFLINE_DESCRIPTIVE_NOT_CAUSAL',
      'created_utc':datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z'),
      'source_inputs_before_after':{'before':source_before,'after':source_after},
      'runtime_source_semantics':{'path':runtime[0]['path'],'sha256':runtime[0]['sha256'],
       'raw_outer_attitude_semantics':'The locked runtime sets raw=target and logs raw_outer_attitude from rawAtt; filtered_attitude_reference is logged from ir.euler returned by command_filter_step at the same event step.',
       'raw_attitude_reference_dataset_absent_but_raw_outer_attitude_present':True},
      'physical_contract':{'mass_kg':mass,'gravity_mps2':gravity,'d_definition':'d=a_actual-a_f; a_actual=R(actual Euler)e3*T_real/m + wind_force_I/m - g*e3; a_f=R(filtered attitude)e3*T_req/m - g*e3.',
       'terms_mps2':{'logged_wind_force_I_over_mass':'wind_force_I/m as logged; this is not separately asserted to be ambient wind only','actual_vs_filtered_direction':'(R_actual-R_filtered)e3*T_req/m','requested_vs_realized_thrust':'R_actual*e3*(T_real-T_req)/m'},
       'raw_split_if_available':['(R_actual-R_raw)e3*T_req/m','(R_raw-R_filtered)e3*T_req/m'],
       'instantaneous_not_RK4_interval_average':True},
      'scope':{'runs':12,'condition':'ON1','phase':'fixed event time 5.0 <= t < 20.0 s','events_per_run':1500,
       'groups':'ALL=12; HF_W09_W14=6 using W09_W11 or W12_W14; W15=3.',
       'rms_definition':'ALL=sqrt(mean_time(sum_xyz(component^2))) is vector-norm RMS; X/Y/Z are component RMS. Group values are equal-scene arithmetic means of per-run RMS. These ALL values are sqrt(3) larger than an elementwise component RMSE for isotropic errors and must not be mixed with it.',
       'aggregation':'For each run compute temporal RMS first; group values are equal-scene arithmetic means of those per-run RMS values. RMS components are not additive percentages.'},
      'frequency_method':{'signal':'online_applied_acceleration minus d','sample_interval_s_exact_for_fft':0.01,'observed_event_clock_tolerance_s':1e-12,'samples_per_run':1500,
       'bands_hz':{'0_1_Hz_including_DC':'0 <= f < 1','1_5_Hz':'1 <= f < 5','5_50_Hz_including_Nyquist':'5 <= f <= 50'},
       'boundary_bins':'1500 samples at 100 Hz use exact bin indices: 0..14, 15..74, 75..750; Nyquist bin 750 is included.',
       'method':'One-sided rFFT Parseval weights; each run/window transformed independently, no concatenated trajectories, detrending or lag search. Each run stores per-axis Parseval and band-power closure errors (<1e-12).'},
      'runs':records,'group_equal_scene_means':aggregates,
      'parseval_summary':{'max_axis_power_abs_error':max(r['frequency_parseval_max_abs_power_error']['axis_power_max_abs'] for r in records),
       'max_band_sum_axis_power_abs_error':max(r['frequency_parseval_max_abs_power_error']['band_sum_power_max_abs'] for r in records),
       'max_vector_power_abs_error':max(r['frequency_parseval_max_abs_power_error']['vector_power_max_abs'] for r in records)},
      'limits':['The 12 records are the original ON1 closed-loop states. This decomposes observed same-state forces, not counterfactual controller effects or a new rollout.',
        'The logged wind_force_I vector is used only as an offline force term; its nonzero value is not asserted to mean nonzero ambient wind, and it is not a deployment input.',
        'Frequency bands describe the logged 5-20 s error on the fixed 100-Hz event grid; no causal interpretation or tuning is implied.',
        'All raw/config/source path hashes and raw stat/hash before-after checks are retained.','Plant=0 new, training=0, optimizer=0, GPU=0, TEST=false.'],
      'script_sha256':sha(Path(__file__))}
    assert not OUT.exists()
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'output':str(OUT.resolve()),'sha256':sha(OUT),'runs':len(records),'group_rows':len(aggregates),
      'max_decomposition_closure':max(r['decomposition_closure_max_abs_mps2'] for r in records),
      'max_split_closure':max(r['raw_direction_split_closure_max_abs_mps2'] for r in records if r['raw_direction_split_closure_max_abs_mps2'] is not None),
      'max_online_closure':max(r['online_beta_clip_closure_max_abs_mps2'] for r in records),
      'parseval_summary':report['parseval_summary'],'source_and_raw_hashes_unchanged':True},indent=2))

if __name__=='__main__': main()
