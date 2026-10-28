"""Read-only independent CM18 SCREEN12 raw audit; run only after all 12 scenes are terminal."""
import argparse,datetime as dt,hashlib,json,os
from pathlib import Path
import h5py,numpy as np
ROOT=Path(__file__).resolve().parents[3]; REPORT=ROOT/'reports/attitude_cm18_a1_20261024'; OUTDIR=REPORT/'screen12_remaining_v1'
MANIFEST=REPORT/'CM18_A1_DEV_SCREEN12_v1.json'; RELEASE=OUTDIR/'ROOT_SCREEN12_REMAINING_RELEASE_v1.json'; LAUNCH=OUTDIR/'ROOT_BATCH_LAUNCH_v1.json'; PREP=OUTDIR/'SCREEN12_REMAINING_PREPARATION_RESULT_v1.json'
AUDIT=REPORT/'first_flight_preparation_v1/A1_FIRST_FLIGHT_LOG_AUDIT_v1.json'; FIRST_RELEASE=REPORT/'first_flight_preparation_v1/ROOT_A1_FIRST_FLIGHT_RELEASE_v1.json'
MODEL=ROOT/'experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json'; ENGINE=ROOT/'experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m'
PIN={'manifest':'fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923','release':'ac0f6625980ecfe44992d70c45e3de535a30a36df6ed345368e93071df79b360','prep':'0c4b82a00e2129fb9735979077a5912acd70408786943e565e6f7f0c1146b1dd','audit':'0fc04a79dc4dd790eb58b1908c3adda2fd28a5bb1060ae85e59410b84ca40d09','first_raw':'cb70eec663da6248d6291fb4b64bdf943cdf284a1d608313edb166c616d771f9','first_release':'0ab70f1ade1cacc04ac8db0fdb8b5efdeb3bf9158e5b53213d6c4d9df24016cd','model':'ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae','checkpoint':'105585385157da3f1b404ab24606d0717287638e4a1ca710790633cd16d233a4','engine':'4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a','runner':'4751636fb60dd5198877c4ec7977719220a6dbcc4e1909e6f6d9065b475dce1d','prepare':'746736995de8a6bdfd308f64fbede677ecedbc021e607bbbb3a4fca4aedad178'}
FIRST='DL1018_DEV_T1_C01_W15'; REMAINING=['DL1018_DEV_T1_C00_W03','DL1018_DEV_T1_C15_W14','DL1018_DEV_T1_C05_W06','DL1018_DEV_T2_C00_W04','DL1018_DEV_T2_C02_W15','DL1018_VAL_T2_C15_W09','DL1018_DEV_T2_C06_W07','DL1018_DEV_T3_C00_W05','DL1018_DEV_T3_C03_W15','DL1018_DEV_T3_C15_W14','DL1018_DEV_T3_C05_W02']
EVENT=np.arange(10,19991,10,dtype=np.int64); TOL=1e-10

def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def js(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def samepath(a,b): return os.path.normcase(os.path.normpath(str(a))).casefold()==os.path.normcase(os.path.normpath(str(b))).casefold()
def txt(d):
    if bool(d.attrs.get('MATLAB_empty',False)): return ''
    a=np.asarray(d)
    if a.dtype.kind in 'ui': return ''.join(chr(int(x)) for x in a.reshape(-1)).rstrip('\x00').rstrip()
    if a.dtype.kind in 'SU': return ''.join(x.decode() if isinstance(x,bytes) else str(x) for x in a.reshape(-1)).rstrip('\x00').rstrip()
    return str(a.reshape(-1)[0]).rstrip()
def sc(f,k): return np.asarray(f[k]).reshape(-1)[0].item()
def fl(f,k): return bool(sc(f,k))
def ma(f,k):
    a=np.asarray(f[k]); return a.T if a.ndim==2 else a
def vec(f,k): return np.asarray(ma(f,k),dtype=np.float64).reshape(-1)
def mx(a):
    a=np.asarray(a,dtype=np.float64); return float(np.max(np.abs(a))) if a.size else 0.0
def byaxis(a): return np.max(np.abs(np.asarray(a,dtype=np.float64)),axis=0).astype(float).tolist()
def runlen(mask,dt_s):
    m=np.asarray(mask,dtype=bool).reshape(-1); e=np.diff(np.r_[False,m,False].astype(np.int8)); s=np.flatnonzero(e==1); z=np.flatnonzero(e==-1)-1; r=(z-s+1)*dt_s
    return (float(r.max()) if r.size else 0.0,float(r[-1]) if r.size and m[-1] else 0.0)

def pins():
    expected=[(MANIFEST,'manifest'),(RELEASE,'release'),(PREP,'prep'),(AUDIT,'audit'),(FIRST_RELEASE,'first_release'),(MODEL,'model'),(ENGINE,'engine'),
      (ROOT/'experiments/attitude_cm18_a1_20261024/screen12_remaining_v1/run_cm18_screen12_remaining_v1.m','runner'),(ROOT/'experiments/attitude_cm18_a1_20261024/screen12_remaining_v1/prepare_cm18_screen12_remaining_v1.m','prepare')]
    for p,k in expected: need(p.is_file() and sha(p).lower()==PIN[k],f'{k} missing/SHA mismatch: {p}')
    m,r,p,model=js(MANIFEST),js(RELEASE),js(PREP),js(MODEL); launch,audit,fr=js(LAUNCH),js(AUDIT),js(FIRST_RELEASE)
    need(launch.get('schema')=='ROOT_SCREEN12_REMAINING_BATCH_LAUNCH_V1' and launch.get('release_sha256','').lower()==PIN['release'],'batch launch/release pin mismatch')
    need(m.get('schema')=='CM18_A1_FUTURE_DEVELOPMENT_SCREEN12_V1' and m.get('first_engineering_scene')==FIRST,'manifest identity mismatch')
    ids=[x['scene_id'] for x in m['scenes']]; rem=[x for x in m['scenes'] if x['scene_id']!=FIRST]
    need(len(ids)==12 and len(set(ids))==12 and [x['scene_id'] for x in rem]==REMAINING and launch.get('scene_ids')==REMAINING,'fixed scene list/order mismatch')
    need(r.get('schema')=='CM18_A1_SCREEN12_REMAINING_ROOT_RELEASE_V1' and r.get('state')=='APPROVED_CM18_A1_SCREEN12_REMAINING_V1' and r.get('decision')=='APPROVE_SCREEN12_REMAINING_11' and r.get('plant_authorized') is True and r.get('max_new_flights')==11 and r.get('allowed_scene_ids')==REMAINING and r.get('TEST_authorized') is False and r.get('training_authorized') is False,'release scope invalid')
    for key,pin in [('screen12_manifest_sha256','manifest'),('preparation_result_sha256','prep'),('first_flight_audit_sha256','audit'),('runner_sha256','runner'),('prepare_script_sha256','prepare'),('engine_sha256','engine'),('deployment_parameters_sha256','model')]: need(r.get(key,'').lower()==PIN[pin],f'release does not bind {key}')
    need(audit.get('schema')=='CM18_A1_FIRST_FLIGHT_LOG_AUDIT_V1' and audit.get('status')=='PASS' and audit.get('scene_id')==FIRST and audit.get('raw_sha256','').lower()==PIN['first_raw'] and audit.get('root_release_sha256','').lower()==PIN['first_release'],'first-flight audit is not pinned PASS')
    need(fr.get('schema')=='CM18_A1_FIRST_FLIGHT_ROOT_RELEASE_V1' and fr.get('scene_id')==FIRST and fr.get('engine_sha256','').lower()==PIN['engine'] and fr.get('deployment_parameters_sha256','').lower()==PIN['model'],'first-flight release identity mismatch')
    need(p.get('schema')=='CM18_A1_SCREEN12_REMAINING_PREPARATION_V1' and p.get('status')=='PREPARED_SCREEN12_REMAINING_NO_PLANT_V1' and p.get('scene_count')==11 and p.get('plant_calls')==0 and p.get('engine_called') is False and p.get('run_episode_called') is False and p.get('training_steps')==0 and p.get('optimizer_steps')==0 and p.get('TEST_accessed') is False,'prep result scope mismatch')
    pr={x['scene_id']:x for x in p['scene_rows']}; rb={x['scene_id']:x for x in r['scene_bindings']}
    need(set(pr)==set(REMAINING)==set(rb),'release/preparation scene set mismatch')
    for row in rem:
        q,b=pr[row['scene_id']],rb[row['scene_id']]
        need(q['baseline_C5_raw_sha256'].lower()==row['baseline_C5_raw_sha256'].lower() and b['baseline_C5_raw_sha256'].lower()==q['baseline_C5_raw_sha256'].lower() and b['prepared_snapshot_sha256'].lower()==q['prepared_snapshot_sha256'].lower(),f"{row['scene_id']}: baseline/snapshot binding mismatch")
    need(model.get('schema')=='CM18_A1_DEPLOYMENT_PARAMETERS_V1' and model['identity']['checkpoint_sha256'].lower()==PIN['checkpoint'] and model['identity']['selected_step']==30000,'model step/checkpoint mismatch')
    return m,r,p,model,{x['scene_id']:x for x in m['scenes']}

def paths(sid):
    base=ROOT/'experiments/attitude_cm18_a1_20261024'; sub='first_flight_preparation_v1' if sid==FIRST else 'screen12_remaining_v1'; d=base/sub/'runs'/sid/'attempt_01'
    return {k:d/v for k,v in {'raw':'raw_run.mat','status':'run_status.json','start':'run_start.mat','marker':'first_plant_step.marker'}.items()}
def preflight(ids):
    return [{'scene_id':sid,'artifact':k,'path':str(p)} for sid in ids for k,p in paths(sid).items() if not p.is_file()]
def forward(x,p):
    mu=np.asarray(p['input_mean'],float).reshape(18); sig=np.asarray(p['input_std'],float).reshape(18); rms=np.asarray(p['train_axis_rms_rad_s2'],float).reshape(3)
    h1=np.tanh(np.asarray(p['W1'],float)@((x-mu)/sig)+np.asarray(p['b1'],float).reshape(32)); h2=np.tanh(np.asarray(p['W2'],float)@h1+np.asarray(p['b2'],float).reshape(32))
    c=(np.asarray(p['W3'],float)@h2+np.asarray(p['b3'],float).reshape(24)).reshape(3,8)
    return (c@np.r_[x[11:15]/2.,x[7:11]])*rms
def close(a,b,tol=TOL): return np.shape(a)==np.shape(b) and mx(np.asarray(a,float)-np.asarray(b,float))<=tol

def audit_scene(sid,row,release,prep,model):
    q=paths(sid); raw,statusp,startp,marker=(q[k] for k in ('raw','status','start','marker')); st=js(statusp); first=sid==FIRST
    schema='CM18_A1_FIRST_FLIGHT_RUN_STATUS_V1' if first else 'CM18_A1_SCREEN12_REMAINING_RUN_STATUS_V1'
    need(st.get('schema')==schema and st.get('status')=='RUN_COMPLETE_PENDING_ROOT_AUDIT' and st.get('scene_id')==sid and st.get('log_status')=='STABLE' and st.get('safety_stop_reason')=='' and st.get('transitions')==20000 and st.get('state_samples')==20001 and st.get('raw_sha256','').lower()==sha(raw).lower() and st.get('run_start_sha256','').lower()==sha(startp).lower() and st.get('first_plant_step_confirmed') is True and st.get('plant_invocation_entered') is True and st.get('plant_calls')==1 and st.get('training_steps')==0 and st.get('optimizer_steps')==0 and st.get('TEST_accessed') is False,f'{sid}: run_status incomplete/identity mismatch')
    rsha=PIN['first_release'] if first else PIN['release']; psha=js(AUDIT)['preparation_result_sha256'] if first else PIN['prep']
    if first: need(st.get('raw_sha256','').lower()==PIN['first_raw'] and st.get('root_release_sha256','').lower()==rsha,'first-flight status SHA mismatch')
    else: need(st.get('cm18_events')==1999 and st.get('root_release_sha256','').lower()==rsha and st.get('preparation_result_sha256','').lower()==psha,'remaining run_status release/event mismatch')
    need(samepath(st.get('raw_path',''),raw) and samepath(st.get('first_plant_step_marker_path',''),marker) and 'first_plant_transition=1' in marker.read_text(encoding='utf-8-sig'),f'{sid}: raw/marker path mismatch')
    bytes_total=sum(x.stat().st_size for x in raw.parent.rglob('*') if x.is_file()); need(bytes_total<=100*1024**2 and st.get('output_directory_bytes',bytes_total)<=100*1024**2,f'{sid}: 100 MiB output cap exceeded')
    bsha=row['baseline_C5_raw_sha256'].lower()
    snapshot_raw_id=sid
    if sid!=FIRST:
        snaprow=next(x for x in prep['scene_rows'] if x['scene_id']==sid); snappath=Path(snaprow['prepared_snapshot_path'])
        need(sha(snappath).lower()==snaprow['prepared_snapshot_sha256'].lower(),f'{sid}: prepared snapshot SHA mismatch')
        with h5py.File(snappath,'r') as snapf:
            need(txt(snapf['sceneIdentity/scene_id'])==sid and txt(snapf['sceneIdentity/canonical_scene_id'])==sid,f'{sid}: prepared snapshot canonical scene mismatch')
            snapshot_raw_id=txt(snapf['sceneIdentity/raw_scene_id'])
    raw_file=raw
    with h5py.File(raw_file,'r') as f,h5py.File(startp,'r') as sf:
        need(all(k in f for k in ('log','scene','runStart','runIdentity')) and 'runStart' in sf,f'{sid}: missing raw/run_start groups')
        rs,ri,stand=f['runStart'],f['runIdentity'],sf['runStart']
        rschema='CM18_A1_FIRST_FLIGHT_RUN_START_V1' if first else 'CM18_A1_SCREEN12_REMAINING_RUN_START_V1'; ischema='CM18_A1_FIRST_FLIGHT_RUN_IDENTITY_V1' if first else 'CM18_A1_SCREEN12_REMAINING_RUN_IDENTITY_V1'
        need(txt(rs['schema'])==rschema and txt(ri['schema'])==ischema and txt(stand['schema'])==rschema,f'{sid}: run_start/run_identity schema mismatch')
        need(txt(f['scene/scene_id'])==sid and txt(rs['scene_id'])==sid and txt(ri['scene_id'])==sid and txt(rs['scene_identity/scene_id'])==sid and txt(ri['scene_identity/scene_id'])==sid and txt(rs['scene_identity/canonical_scene_id'])==sid and txt(ri['scene_identity/canonical_scene_id'])==sid and txt(rs['scene_identity/raw_scene_id'])==snapshot_raw_id and txt(ri['scene_identity/raw_scene_id'])==snapshot_raw_id,f'{sid}: scene identity mismatch')
        need(txt(stand['scene_id'])==sid and txt(stand['root_release_sha256']).lower()==rsha and txt(stand['preparation_result_sha256']).lower()==psha and txt(stand['deployment_parameters_sha256']).lower()==PIN['model'] and txt(stand['engine_sha256']).lower()==PIN['engine'] and txt(stand['scene_identity/scene_id'])==sid and txt(stand['model_identity/checkpoint_sha256']).lower()==PIN['checkpoint'] and float(sc(stand,'model_identity/selected_step'))==30000 and txt(rs['root_release_sha256']).lower()==rsha and txt(ri['root_release_sha256']).lower()==rsha and txt(rs['preparation_result_sha256']).lower()==psha and txt(ri['preparation_result_sha256']).lower()==psha and txt(rs['deployment_parameters_sha256']).lower()==PIN['model'] and txt(rs['engine_sha256']).lower()==PIN['engine'],f'{sid}: run identity does not bind release/model/engine')
        blkey='c5_raw_scene_sha256' if first else 'baseline_C5_raw_sha256'; bpkey='c5_raw_scene_path' if first else 'baseline_C5_raw_path'
        need(txt(rs[blkey]).lower()==bsha and samepath(txt(rs[bpkey]),row['baseline_C5_raw_path']),f'{sid}: run_start baseline does not match manifest')
        for ident in (rs,ri):
            need(txt(ident['model_identity/checkpoint_sha256']).lower()==PIN['checkpoint'] and float(sc(ident,'model_identity/selected_step'))==30000 and txt(ident['model_identity/normalizer_sha256']).lower()==model['identity']['normalizer_sha256'].lower(),f'{sid}: deployed model identity mismatch')
        need(int(sc(rs,'training_steps'))==0 and int(sc(rs,'optimizer_steps'))==0 and not fl(rs,'TEST_accessed') and int(sc(ri,'training_steps'))==0 and int(sc(ri,'optimizer_steps'))==0 and not fl(ri,'TEST_accessed'),f'{sid}: training/TEST scope invalid')
        for k in ('rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled'): need(not fl(rs,'opts/'+k),f'{sid}: RBF option {k} enabled')
        need(fl(rs,'opts/cm18_attitude_v1/enabled'),f'{sid}: CM18 disabled')
        rm=rs['opts/cm18_attitude_v1/model']
        for name,val in model['parameters'].items():
            actual=np.asarray(rm[name]); actual=actual.T if actual.ndim==2 else actual
            need(close(actual.reshape(-1),np.asarray(val,dtype=np.float64).reshape(-1),0.),f'{sid}: runtime model array {name} differs from deployment JSON')
        g=f['log']; n=20000; time=vec(f,'log/time'); trans=vec(f,'log/transition_time'); state=np.asarray(ma(f,'log/state'),float); ref=np.asarray(ma(f,'log/reference/position'),float)
        command=np.asarray(ma(f,'scene/arms/command'),float); logged_command=np.asarray(ma(f,'log/arms/command'),float); requested=np.asarray(ma(f,'log/requested_generalized'),float); nominal=np.asarray(ma(f,'log/attitude_bs_nominal_torque_Nm'),float)
        need(time.shape==(n+1,) and trans.shape==(n,) and state.shape==(n+1,12) and ref.shape==(n+1,3) and command.shape==(n+1,4) and logged_command.shape==command.shape and requested.shape==(n,4) and nominal.shape==(n,3),f'{sid}: event/state/output dimensions invalid')
        dt_s=float(sc(f,'runStart/cfg/plant/dt'))
        need(abs(dt_s-.001)<1e-15 and abs(time[0])<1e-12 and abs(time[-1]-20)<1e-12 and mx(np.diff(time)-dt_s)<1e-12 and mx(trans-time[:-1])<1e-12 and all(np.isfinite(x).all() for x in (time,trans,state,ref,command,requested,nominal)) and close(command,logged_command,0.),f'{sid}: timeline/finiteness/command mismatch')
        need(txt(g['status'])=='STABLE' and int(sc(f,'log/last_transition'))==n and txt(g['safety_stop_reason'])=='',f'{sid}: engine terminal status/safety stop mismatch')
        ev=np.asarray(g['cm18_event_flag'],bool).reshape(-1); ei=np.flatnonzero(ev)
        need(np.array_equal(ei,EVENT) and int(sc(f,'log/cm18_event_count'))==len(EVENT),f'{sid}: event schedule must be MATLAB 11:10:19991')
        need(fl(f,'log/cm18_attitude_enabled') and txt(g['cm18_model_profile'])=='CM18_A1_MLP32x32_TO24_FIXED_J0',f'{sid}: CM18 model profile mismatch')
        for k in ('cm18_rbf_attitude_runtime_enabled','cm18_rbf_attitude_output_enabled','cm18_rbf_attitude_update_enabled','attitude_fusion_enabled','attitude_head_enabled'): need(not fl(f,'log/'+k),f'{sid}: disabled branch {k} is active')
        for k in ('rbf_update_flag','rbf_attitude_output_limit_active'): need(not np.asarray(g[k],bool).any(),f'{sid}: {k} contains active entries')
        for k in ('rbf_update_dt','rbf_output_raw','rbf_output_unclipped','rbf_output_held','attitude_rbf_compensation_torque_Nm'): need(np.all(np.asarray(g[k])==0),f'{sid}: disabled RBF output {k} is nonzero')
        J0=np.asarray(ma(f,'log/cm18_fixed_inertia_J0_kgm2'),float); dmax=vec(f,'log/cm18_dmax_rad_s2'); tau=float(sc(f,'log/cm18_beta_rise_time_s'))
        need(J0.shape==(3,3) and np.isfinite(J0).all() and np.linalg.eigvalsh((J0+J0.T)/2).min()>0 and close(dmax,vec(f,'runStart/cfg/rbf/attitude/dmax'),0.) and abs(tau-float(sc(f,'runStart/cfg/rbf/attitude/beta_rise_time')))<1e-15,f'{sid}: J0/dmax/beta config mismatch')
        zlog=np.asarray(ma(f,'log/cm18_event_z_before_4'),float); ulog=np.asarray(ma(f,'log/cm18_event_u_current_4'),float); alog=np.asarray(ma(f,'log/cm18_event_a_previous_requested_torque_mean_Nm'),float)
        xlog=np.asarray(ma(f,'log/cm18_event_input_18'),float); rawlog=np.asarray(ma(f,'log/cm18_event_raw_acceleration_rad_s2'),float); cliplog=np.asarray(ma(f,'log/cm18_event_clipped_acceleration_rad_s2'),float); interval=vec(f,'log/cm18_event_interval_s')
        for name,a,w in [('X18',xlog,18),('z',zlog,4),('u',ulog,4),('aPrev',alog,3),('raw',rawlog,3),('clip',cliplog,3)]: need(a.shape==(n,w) and np.isfinite(a[ev]).all() and np.isnan(a[~ev]).all(),f'{sid}: {name} event-only shape/NaN mismatch')
        need(np.all(interval[~ev]==0) and close(interval[ev],np.full(len(EVENT),.01),1e-12),f'{sid}: event interval mismatch')
        mass=float(sc(f,'runStart/cfg/plant/mass')); p=model['parameters']; zall=np.vstack((np.zeros(4),np.cumsum(command[:-1]*dt_s,axis=0)))
        motor=np.asarray(ma(f,'log/motor_saturated'),bool); generalized=np.asarray(ma(f,'log/generalized_clipped'),bool); tiltlimited=np.asarray(g['tilt_limited'],bool).reshape(-1)
        need(motor.shape==(n,4) and generalized.shape==(n,4) and tiltlimited.shape==(n,),f'{sid}: saturation/limiter shapes mismatch')
        beta_log=vec(f,'log/cm18_beta_held'); heldacc_log=np.asarray(ma(f,'log/cm18_applied_acceleration_held_rad_s2'),float); heldtorque_log=np.asarray(ma(f,'log/cm18_compensation_torque_held_Nm'),float)
        complog=np.asarray(ma(f,'log/attitude_compensation_applied_torque_Nm'),float); clipheld_log=np.asarray(g['cm18_clip_flag_held'],bool).reshape(-1)
        heldacc=np.zeros((n,3)); heldbeta=np.zeros(n); heldtorque=np.zeros((n,3)); heldclipaxis=np.zeros((n,3),bool)
        acc=np.zeros(3); beta=0.; torque=np.zeros(3); axisclip=np.zeros(3,bool); records=[]; deltas={k:[] for k in ('x18','z','u','a_prev','alpha_inverse','forward','clip','nominal_minus_comp')}; event_clip=[]
        for i in range(n):
            if ev[i]:
                omega=state[i,9:12]; alpha=np.linalg.solve(J0,nominal[i]-np.cross(omega,J0@omega)); past=slice(i-10,i); weights=np.diff(time[i-10:i+1])
                aprev=np.sum(requested[past,1:4]*weights[:,None],axis=0)/weights.sum(); u=command[i]; x=np.r_[omega,alpha,requested[i,0]/mass,u,zall[i],aprev]
                raw=forward(x,p); clipped=np.clip(raw,-dmax,dmax); beta=min((i+1)*dt_s/tau,1.); acc=beta*clipped; torque=J0@acc; axisclip=raw!=clipped
                dx=xlog[i]-x; dz=zlog[i]-zall[i]; du=ulog[i]-u; da=alog[i]-aprev; dalpha=xlog[i,3:6]-alpha; draw=rawlog[i]-raw; dclip=cliplog[i]-clipped; dclose=requested[i,1:4]-(nominal[i]-torque)
                need(max(mx(v) for v in (dx,dz,du,da,dalpha,draw,dclip,dclose))<=TOL and abs(beta_log[i]-beta)<=1e-12,f'{sid}: independent event check failed at MATLAB transition {i+1}')
                for k,v in zip(deltas,(dx,dz,du,da,dalpha,draw,dclip,dclose)): deltas[k].append(v)
                event_clip.append(axisclip)
                records.append({'matlab_transition_index':i+1,'transition_time_s':float(trans[i]),'X18_reconstructed':x.tolist(),'X18_logged':xlog[i].tolist(),'X18_delta':dx.tolist(),'z_integral_reconstructed':zall[i].tolist(),'z_logged':zlog[i].tolist(),'u_current_reconstructed':u.tolist(),'u_logged':ulog[i].tolist(),'a_previous_10_requested_torque_mean_Nm_reconstructed':aprev.tolist(),'a_previous_logged':alog[i].tolist(),'alpha_BS_from_nominal_torque_inverse_rad_s2':alpha.tolist(),'forward_raw_reconstructed_rad_s2':raw.tolist(),'forward_raw_logged_rad_s2':rawlog[i].tolist(),'clipped_reconstructed_rad_s2':clipped.tolist(),'clipped_logged_rad_s2':cliplog[i].tolist(),'beta_reconstructed':float(beta),'beta_logged':float(beta_log[i]),'held_acceleration_reconstructed_rad_s2':acc.tolist(),'held_acceleration_logged_rad_s2':heldacc_log[i].tolist(),'J0_compensation_torque_reconstructed_Nm':torque.tolist(),'J0_compensation_torque_logged_Nm':heldtorque_log[i].tolist(),'clip_flag_held_logged':bool(clipheld_log[i]),'clip_by_output_axis':axisclip.tolist(),'generalized_clipped':generalized[i].tolist(),'motor_saturated_by_motor':motor[i].tolist(),'tilt_limited':bool(tiltlimited[i]),'nominal_torque_logged_Nm':nominal[i].tolist(),'requested_torque_logged_Nm':requested[i,1:4].tolist(),'nominal_minus_comp_delta_Nm':dclose.tolist(),'reconstruction_deltas':{'z':dz.tolist(),'u':du.tolist(),'a_previous':da.tolist(),'alpha_inverse':dalpha.tolist(),'forward':draw.tolist(),'clipped':dclip.tolist()}})
            heldacc[i]=acc; heldbeta[i]=beta; heldtorque[i]=torque; heldclipaxis[i]=axisclip
        need(heldacc_log.shape==(n,3) and heldtorque_log.shape==(n,3) and complog.shape==(n,3) and mx(heldacc_log-heldacc)<=TOL and mx(beta_log-heldbeta)<=1e-12 and mx(heldtorque_log-heldtorque)<=TOL and mx(complog-heldtorque)<=TOL and np.array_equal(clipheld_log,heldclipaxis.any(axis=1)) and mx(requested[:,1:4]-(nominal-heldtorque))<=TOL,f'{sid}: held forward/beta/J0/nominal-minus-comp closure mismatch')
        per_event={k:np.asarray(v,float) for k,v in deltas.items()}; clip_ev=np.asarray(event_clip,bool); evphase=trans[ei]<5.
        phases={}
        for name,tm,emask in [('PRE_0_5',trans<5.,evphase),('POST_5_20',trans>=5.,~evphase)]:
            phases[name]={'transition_count':int(tm.sum()),'event_count':int(emask.sum()),'event_X18_max_abs_delta_by_feature':byaxis(per_event['x18'][emask]),'forward_max_abs_delta_by_output_axis':byaxis(per_event['forward'][emask]),'clip_event_count_by_output_axis':np.count_nonzero(clip_ev[emask],axis=0).astype(int).tolist(),'clip_held_transition_count_by_output_axis':np.count_nonzero(heldclipaxis[tm],axis=0).astype(int).tolist(),'motor_saturated_transition_count_by_motor':np.count_nonzero(motor[tm],axis=0).astype(int).tolist(),'generalized_clipped_transition_count_by_axis':np.count_nonzero(generalized[tm],axis=0).astype(int).tolist(),'tilt_limited_transition_count':int(tiltlimited[tm].sum())}
        need(phases['PRE_0_5']['event_count']==499 and phases['POST_5_20']['event_count']==1500,f'{sid}: phase event count mismatch')
        poserr=np.linalg.norm(state[:n,:3]-ref[:n],axis=1); tilt=np.arccos(np.clip(np.cos(state[:n,6])*np.cos(state[:n,7]),-1.,1.)); rate=np.linalg.norm(state[:n,9:12],axis=1)
        pmax,ptail=runlen(poserr>1.,dt_s); tmax,ttail=runlen(tilt>np.pi/3,dt_s); rmax,rtail=runlen(rate>20.,dt_s)
        slog=[float(sc(f,'log/safety_position_error_persistence_s')),float(sc(f,'log/safety_tilt_persistence_s')),float(sc(f,'log/safety_body_rate_persistence_s'))]; tails=[ptail,ttail,rtail]
        need(pmax<.2 and tmax<.1 and rmax<.05 and mx(np.asarray(slog)-tails)<=1e-12,f'{sid}: safety persistence mismatch/threshold reached')
        resid={k:np.asarray(v,float) for k,v in deltas.items()}
        return {'scene_id':sid,'status':'PASS','raw_sha256':sha(raw_file),'transition_count':n,'state_sample_count':n+1,'event_count':len(records),'event_matlab_indices_first_step_last':[11,21,19991],
          'alpha_BS_note':'Recovered from logged nominal torque: solve(J0, nominal - cross(omega,J0*omega)); not an independent rerun of attitude_bs_step.',
          'J0_kgm2':J0.tolist(),'phase':phases,'per_output_axis':{'forward_max_abs_delta_rad_s2':byaxis(resid['forward']),'clip_event_count':clip_ev.sum(axis=0).astype(int).tolist(),'clip_held_transition_count':heldclipaxis.sum(axis=0).astype(int).tolist(),'held_acceleration_max_abs_delta_rad_s2':byaxis(heldacc_log-heldacc),'J0_torque_max_abs_delta_Nm':byaxis(heldtorque_log-heldtorque)},
          'motor_saturated_transition_count_by_motor':motor.sum(axis=0).astype(int).tolist(),'generalized_clipped_transition_count_by_axis':generalized.sum(axis=0).astype(int).tolist(),'tilt_limited_transition_count':int(tiltlimited.sum()),
          'safety':{'position_error_peak_m':float(poserr.max()),'position_error_max_consecutive_s':pmax,'tilt_peak_rad':float(tilt.max()),'tilt_max_consecutive_s':tmax,'body_rate_peak_rad_s':float(rate.max()),'body_rate_max_consecutive_s':rmax,'logged_trailing_persistence_s':slog},
          'max_abs_deltas':{k:mx(v) for k,v in resid.items()}|{'held_acceleration':mx(heldacc_log-heldacc),'held_beta':mx(beta_log-heldbeta),'held_torque':mx(heldtorque_log-heldtorque),'nominal_minus_comp':mx(requested[:,1:4]-(nominal-heldtorque))},'events':records}

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--output',type=Path,default=OUTDIR/'ROOT_SCREEN12_INDEPENDENT_RAW_AUDIT_v1.json'); args=ap.parse_args()
    manifest,release,prep,model,byid=pins(); ids=[FIRST]+REMAINING; missing=preflight(ids); out=args.output if args.output.is_absolute() else (ROOT/args.output).resolve()
    if missing:
        stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'); out=out.with_name(out.stem+'_INCOMPLETE_'+stamp+out.suffix)
        result={'schema':'ROOT_CM18_SCREEN12_INDEPENDENT_RAW_AUDIT_V1','status':'INCOMPLETE','reason':'A raw/status/run_start/marker is absent; no raw file was opened.','manifest_sha256':PIN['manifest'],'model_sha256':PIN['model'],'engine_sha256':PIN['engine'],'missing_artifacts':missing}
        need(not out.exists(),f'refusing to overwrite {out}'); out.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'status':'INCOMPLETE','missing_count':len(missing),'report':str(out)},indent=2)); return 2
    need(not out.exists(),f'refusing to overwrite {out}')
    rows=[]
    for sid in ids:
        try: rows.append(audit_scene(sid,byid[sid],release,prep,model))
        except Exception as exc: rows.append({'scene_id':sid,'status':'FAIL','error':f'{type(exc).__name__}: {exc}'})
    good=[np.asarray(x['J0_kgm2'],float) for x in rows if x.get('status')=='PASS']; j0delta=None
    if len(good)==12:
        j0delta=max(mx(x-good[0]) for x in good)
        if j0delta>1e-12: rows.append({'scene_id':'SCREEN12_GLOBAL','status':'FAIL','error':f'fixed J0 differs across scenes by {j0delta:.17g}'})
    passed=sum(x.get('status')=='PASS' for x in rows)
    result={'schema':'ROOT_CM18_SCREEN12_INDEPENDENT_RAW_AUDIT_V1','status':'PASS' if passed==12 and len(rows)==12 else 'FAIL','created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
      'scope':'Fixed first engineering scene plus released remaining 11; read-only raw audit, no Plant/training/TEST.','identity':{'manifest_sha256':PIN['manifest'],'remaining_root_release_sha256':PIN['release'],'first_flight_audit_sha256':PIN['audit'],'deployment_model_sha256':PIN['model'],'checkpoint_sha256':PIN['checkpoint'],'selected_step':30000,'engine_sha256':PIN['engine']},
      'method_note':'BS alpha is recovered from logged nominal torque using fixed logged J0 and omega cross term; this does not rerun attitude_bs_step. NumPy forward is independently evaluated from the pinned deployment JSON.',
      'fixed_J0_max_abs_cross_scene_delta_kgm2':j0delta,'completed_scene_count':passed,'rows':rows}
    need(not out.exists(),f'refusing to overwrite {out}'); out.write_text(json.dumps(result,separators=(',',':'),allow_nan=False),encoding='utf-8')
    print(json.dumps({'status':result['status'],'completed_scene_count':passed,'report':str(out),'fixed_J0_max_abs_cross_scene_delta_kgm2':j0delta},indent=2)); return 0 if result['status']=='PASS' else 1

if __name__=='__main__': raise SystemExit(main())


