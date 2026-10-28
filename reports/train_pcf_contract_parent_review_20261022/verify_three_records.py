"""Independent same-transition check on three frozen TRAIN strata; read only."""
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from scipy.io import loadmat

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
ARCHIVE=ROOT.parent/'REFERENCE_FIX_FULL72_20261021_022342_313'
MANIFEST=ROOT/'reports/train_pcf_contract_reconstruction_20261022/stratified_sample_manifest.csv'
EXPECTED='4019aac3a23f1aef4a70f5d37b364d1ca09bfd1bcfe9ce39e486b3772af18b49'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):
            h.update(b)
    return h.hexdigest()


def z_axis(euler):
    r,p,y=euler
    return np.array([np.cos(y)*np.sin(p)*np.cos(r)+np.sin(y)*np.sin(r),
                     np.sin(y)*np.sin(p)*np.cos(r)-np.cos(y)*np.sin(r),np.cos(p)*np.cos(r)])


assert sha(MANIFEST)==EXPECTED
samples=pd.read_csv(MANIFEST)
checks=[]
for task,role,band in [('FIG8_3D','B','W00_W08'),('HELIX','POS_OFF','W09_W14'),('SQUARE','B','W15')]:
    record=samples.loc[(samples.task==task)&(samples.role==role)&(samples.wind_band==band)].iloc[0]
    sources={k:Path(record[k+'_path']).resolve() for k in ('raw','run_start','event_h5','cache')}
    before={}
    for kind,path in sources.items():
        assert any(path.is_relative_to(base.resolve()) for base in (ROOT,ARCHIVE))
        st=path.stat();before[kind]=(st.st_size,st.st_mtime_ns,sha(path))
        key='cache_sha256' if kind=='cache' else kind+'_path_sha256'
        assert before[kind][2]==record[key],(kind,path)
    rs=sources['run_start']
    option_flags={}
    if h5py.is_hdf5(rs):
        with h5py.File(rs,'r') as f:
            cfg=f['runStart/cfg']
            mass=float(np.asarray(cfg['plant/mass']).item());gravity=float(np.asarray(cfg['plant/g']).item())
            k1=np.asarray(cfg['control/bs/position/k1']).reshape(-1,1)
            k2=np.asarray(cfg['control/bs/position/k2']).reshape(-1,1)
            for name in ('physical_impulse_force_I','rbf_disturbance_diagnostic','state_perturbation'):
                key='runStart/opts/'+name+'/enabled'
                option_flags[name]={'enabled':bool(np.asarray(f[key]).item()) if key in f else False,
                                    'source':'explicit_runStart.opts' if key in f else 'absent_uses_source_default_false'}
    else:
        start=loadmat(rs,variable_names=['runStart'],simplify_cells=True)['runStart']
        cfg=start['cfg']
        mass=float(cfg['plant']['mass']);gravity=float(cfg['plant']['g'])
        k1=np.asarray(cfg['control']['bs']['position']['k1']).reshape(-1,1)
        k2=np.asarray(cfg['control']['bs']['position']['k2']).reshape(-1,1)
        for name in ('physical_impulse_force_I','rbf_disturbance_diagnostic','state_perturbation'):
            value=start.get('opts',{}).get(name,{})
            option_flags[name]={'enabled':bool(value.get('enabled',False)),
                                'source':'explicit_runStart.opts' if 'enabled' in value else 'absent_uses_source_default_false'}
    assert not any(v['enabled'] for v in option_flags.values()),option_flags
    with h5py.File(sources['raw'],'r') as f:
        log=f['log'];event=np.flatnonzero(np.asarray(log['position_event_flag']).reshape(-1)>0)
        guard_fields={}
        for field in ('physical_impulse_enabled','physical_impulse_force_I_N','diagnostic_external_force_I','state_perturbation_enabled'):
            if field in log:
                values=np.asarray(log[field],dtype=float)
                assert np.isfinite(values).all() and not np.any(values),field
                guard_fields[field]='present_zero_or_disabled'
            else:
                guard_fields[field]='absent; checked runStart.opts default'
        assert len(event)==1999
        get=lambda name:np.asarray(log[name],dtype=float)[:,event]
        x=get('state');e=get('reference/position')-x[:3];de=get('reference/velocity')-x[3:6]
        surface=de+k1*e
        a0=get('reference/acceleration')+k1*de+e+k2*surface
        u=get('position_compensation_applied_acceleration_mps2')
        req=get('position_commanded_force_N')/mass
        actual=get('realized_generalized')[0]*z_axis(x[6:9])/mass+get('wind_force_I')/mass
        actual[2]-=gravity
        af=get('requested_generalized')[0]*z_axis(get('filtered_attitude_reference'))/mass
        af[2]-=gravity
        rf=req-af
        y=actual-req
        mask=np.array([1.,1.,0.])[:,None]
        mixed=y+mask*rf
        mixed_rhs=actual-((1-mask)*req+mask*af)
        times=get('transition_time').reshape(-1)
        nominal=get('position_nominal_acceleration_mps2')
        logged_rf=get('stage1_position_pcf_r_f_mps2')
        arms=np.asarray(f['scene/arms/command'],dtype=float)[:,event]
        x14=np.vstack((e,surface,x[6:9],np.linalg.norm(a0+np.array([0.,0.,gravity])[:,None],axis=0),arms))
    with h5py.File(sources['event_h5'],'r') as f:
        event_y=np.asarray(f['target_raw'],dtype=float)
        h5_time=np.asarray(f['event_time_s'],dtype=float).reshape(-1)
        h5_index=np.asarray(f['plant_index']).reshape(-1)
        h5_event_index=np.asarray(f['event_index']).reshape(-1)
        h5_clip=np.asarray(f['target_clip'],dtype=float)
        h5_phase=np.asarray(f['phase_code']).reshape(-1)
        event_x=np.asarray(f['x14'],dtype=float)
        if event_y.shape==(1999,3):
            event_y=event_y.T
        if event_x.shape==(1999,14):
            event_x=event_x.T
        if h5_clip.shape==(3,1999):
            h5_clip=h5_clip.T
        assert event_y.shape==(3,1999) and event_x.shape==(14,1999)
    with np.load(sources['cache'],allow_pickle=False) as f:
        cache_y=np.asarray(f['raw'])
        cache_x=np.asarray(f['x14'])
        cache_plant=np.asarray(f['plant_index']).reshape(-1)
        cache_clip=np.asarray(f['y'])
        cache_phase=np.asarray(f['phase']).reshape(-1)
    errors={'nominal_replay_max_abs':float(np.max(np.abs(nominal-a0))),
            'req_vs_nominal_minus_u_max_abs':float(np.max(np.abs(req-(a0-u)))),
            'physical_Y_vs_event_H5_max_abs':float(np.max(np.abs(y-event_y))),
            'X14_vs_event_H5_max_abs':float(np.max(np.abs(x14-event_x))),
            'mixed_identity_max_abs':float(np.max(np.abs(mixed-mixed_rhs))),
            'event_time_max_abs':float(np.max(np.abs(times-h5_time)))}
    assert max(errors.values())<1e-9,errors
    assert np.array_equal(h5_index.astype(int),event+1)
    assert np.array_equal(h5_event_index.astype(int),np.arange(1,2000))
    assert np.array_equal(cache_plant.astype(int),event)
    assert np.array_equal(cache_phase,h5_phase.astype(cache_phase.dtype))
    assert np.array_equal(cache_y,np.float32(event_y.T))
    assert np.array_equal(cache_clip,np.float32(h5_clip))
    assert np.array_equal(cache_x,np.float32(event_x.T))
    for kind,path in sources.items():
        st=path.stat();assert before[kind]==(st.st_size,st.st_mtime_ns,sha(path))
    checks.append({'run_id':record.run_id,'task':task,'role':role,'band':band,'events':1999,**errors,
                   'cache_Y_float32_exact':True,'cache_X14_float32_exact':True,
                   'cache_plant_zero_based_exact':True,'cache_clipped_Y_exact':True,'cache_phase_code_exact':True,
                   'logged_stage1_rf_finite_count':int(np.isfinite(logged_rf).sum()),
                   'logged_stage1_rf_max_abs':float(np.max(np.abs(logged_rf[np.isfinite(logged_rf)]))) if np.isfinite(logged_rf).any() else None,
                   'reconstructed_rf_rms':float(np.sqrt(np.mean(rf**2))),
                   'sources_unchanged':True,'extra_input_options':option_flags,'extra_input_log_guards':guard_fields,
                   'source_sha256':{k:v[2] for k,v in before.items()}})
pd.DataFrame([{k:v for k,v in r.items() if k not in ('source_sha256','extra_input_options','extra_input_log_guards')} for r in checks]).to_csv(OUT/'three_records_checks.csv',index=False)
(OUT/'three_records_metadata.json').write_text(json.dumps({'status':'PASS_INDEPENDENT_THREE_TRAIN_RECORDS',
    'sample_manifest_sha256':EXPECTED,'script_sha256':sha(Path(__file__)),'records':checks,
    'optimizer_steps':0,'plant_calls':0,'GPU_used':False,'TEST_accessed':False,
    'scope':'Instantaneous target reconstruction on three fixed Teacher trajectories, not a closed-loop counterfactual.',
    'engineering_notes':['First audit attempt assumed component-major event H5 arrays and stopped at shape subtraction; corrected to explicit event-major/component-major adapter. No source data modified.']},indent=2,allow_nan=False)+'\n',encoding='utf8')
print(json.dumps(checks))
