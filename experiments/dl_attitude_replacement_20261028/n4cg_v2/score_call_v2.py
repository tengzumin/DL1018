"""Frozen per-scene score and event/hold action-chain replay; no Plant call."""
from pathlib import Path
import importlib.util
import json
import sys

import h5py
import numpy as np

from helper_parity_v2 import reference, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCENES = ['DL1018_DEV_T1_C00_W03','DL1018_DEV_T3_C09_W09','DL1018_DEV_T1_C11_W12']
SCORE_SOURCE = ROOT/'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py'
CONSTANTS = ROOT/'experiments/dl_attitude_replacement_20261026/mlp15_composite_dev_v3/RELEASE.json'
NPZ = HERE.parent/'causal_n4_gate_train24_acden_v2/CAUSAL_N4_GATE_TRAIN24_ACDEN_V2_PER_EVENT.npz'
TOL = 2e-10


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def data(log, name):
    return np.asarray(log[name][()], dtype=np.float64).T


def maxerr(x, y):
    return float(np.max(np.abs(np.asarray(x)-np.asarray(y))))


def main(scene):
    assert scene in SCENES
    ix = SCENES.index(scene)
    case = HERE/f'r{ix}'
    out = case/'SCORE_v2.json'
    if out.exists():
        raise RuntimeError('Refusing to overwrite score')
    release, lock = read(case/'RELEASE.json'), read(case/'SOURCE_LOCK_SINGLE_v2.json')
    assert release['fixed_scene_id'] == scene and sha(case/'SOURCE_LOCK_SINGLE_v2.json') == release['source_lock_sha256']
    for item in lock['files']:
        assert sha(Path(item['path'])) == item['sha256'], f"Locked source changed: {item['path']}"
    attempt = case/'runs'/scene/'attempt_01'
    raw, status_path = attempt/'raw_run.mat', attempt/'run_status.json'
    status = read(status_path)
    assert status['scene_id'] == scene and status['Plant_calls'] == 1 and status['raw_sha256'] == sha(raw)
    binding = read(case/'bindings'/f'{scene}.json')
    comparators = {'B':'b72_scoring', 'C5':'c5', 'parent':'parent'}
    paths = {'candidate':raw}
    for name, prefix in comparators.items():
        rp, sp = Path(binding[prefix+'_raw_path']), Path(binding[prefix+'_status_path'])
        assert sha(rp) == binding[prefix+'_raw_sha256'] and sha(sp) == binding[prefix+'_status_sha256']
        assert read(sp)['scene_id'] == scene
        paths[name] = rp
    spec = importlib.util.spec_from_file_location('frozen_score', SCORE_SOURCE)
    scorer = importlib.util.module_from_spec(spec); spec.loader.exec_module(scorer)
    c = read(CONSTANTS)
    scores = {name:scorer.score_raw(path, float(c['gravity_mps2']), float(c['max_tilt_rad']))
              for name,path in paths.items()}
    with h5py.File(raw,'r') as f:
        log = f['log']
        t = data(log,'transition_time').reshape(-1)
        event = data(log,'stage1_position_event').reshape(-1).astype(bool)
        valid = data(log,'stage1_position_event_inference_valid').reshape(-1).astype(bool)
        before = data(log,'stage1_position_event_applied_acceleration_mps2')
        u = data(log,'stage1_position_applied_static_n4_event_input_mps2')[event]
        n4 = data(log,'stage1_position_applied_static_n4_event_output_raw_mps2')[event]
        blend = data(log,'stage1_position_applied_static_n4_event_output_applied_mps2')[event]
        gate = data(log,'stage1_position_causal_n4_gate_diagnostics')[event]
        clips = data(log,'stage1_position_applied_static_n4_event_clip_active')[event].astype(bool)
        held = data(log,'stage1_position_held_applied_acceleration_mps2')
        force = data(log,'stage1_position_held_force_I_N')
        residual_arg = data(log,'stage1_position_injected_force_I_N')
        actual_force = data(log,'position_compensation_applied_force_N')
        state = data(log,'state')
        extra = float(data(log,'stage1_position_residual_gru_enabled').reshape(-1)[0])
        extra_events = float(data(log,'stage1_position_residual_gru_event_count').reshape(-1)[0])
    tt = t[event]
    assert t.size == 20000 and event.sum() == 1999 and valid[event].sum() == 1968
    assert np.all(~valid[event][:31]) and np.all(valid[event][31:])
    assert np.allclose(tt,np.arange(1,2000)*.01,atol=2e-8,rtol=0)
    assert u.shape == n4.shape == blend.shape == (1999,3) and gate.shape == (1999,5)
    event_before = before[event]
    parent_input = np.where(valid[event,None],event_before,0.)
    assert np.isfinite(u).all() and np.isfinite(gate).all() and np.isfinite(state).all()
    replay_out,replay_n4,replay_diag = reference(u,tt)
    sample_idx = np.cumsum(event)-1
    replay_hold = np.zeros_like(held)
    replay_hold[sample_idx>=0] = replay_out[sample_idx[sample_idx>=0]]
    unclipped = u+replay_diag[:,4,None]*(replay_n4-u)
    expected_clips = np.abs(unclipped-replay_out)>1e-12
    errors = {'input_from_C5':maxerr(u,parent_input), 'n4_raw':maxerr(n4,replay_n4),
              'gate_diagnostics':maxerr(gate,replay_diag), 'event_output':maxerr(blend,replay_out),
              'held_1ms':maxerr(held,replay_hold), 'position_bs_step_argument':maxerr(force,residual_arg),
              'reported_compensation':maxerr(residual_arg,actual_force)}
    checks = {'event_count_and_warmup':bool(event.sum()==1999 and valid[event].sum()==1968 and np.all(u[:31]==0)),
              'action_replay':bool(max(errors.values())<=TOL and np.array_equal(clips,expected_clips)),
              'no_extra_position_gru':bool(extra==0 and extra_events==0),
              'startup_gate_zero':bool(np.all(gate[tt<2,3:]==0)),
              'stable_20k_one_call':bool(status['state']=='COMPLETED' and status['status_value']=='STABLE' and
                  status['transitions']==20000 and status['state_samples']==20001 and status['first_plant_step_marker_created']),
              'Q_over_C5_le_1p05':bool(scores['candidate']['Q_m']<=1.05*scores['C5']['Q_m']),
              'safety_counters_zero':bool(all(v==0 for v in scores['candidate']['safety'].values())),
              'high_task_le_B':bool(ix==0 or scores['candidate']['task_SO3_rad']<=scores['B']['task_SO3_rad'])}
    with h5py.File(paths['parent'],'r') as f:
        parent_state = data(f['log'],'state')
        parent_action = data(f['log'],'stage1_position_held_applied_acceleration_mps2')
    parent_errors = {'state':maxerr(state,parent_state), 'held_action':maxerr(held,parent_action)}
    if ix==0:
        checks['low_gate_zero_and_parent_equivalence'] = bool(np.all(gate[:,4]==0) and max(parent_errors.values())<=TOL)
    with np.load(NPZ) as d:
        j = list(d['scene_ids']).index(scene)
        parent_ebp = d['action_Ebp_2_5'][j].copy()
        parent_gate = d['action_gate_ac'][j].copy()
    use = tt>=2
    ratio,g,gt = gate[:,2],gate[:,4],gate[:,3]
    windows = []
    for lo,hi in ((2,8),(8,14),(14,20)):
        m=(tt>=lo)&(tt<hi)
        windows.append({'time_s':[lo,hi], 'Ebp_mean':float(np.mean(gate[m,0])),
            'parent_Ebp_mean':float(np.mean(parent_ebp[m])), 'Elo_mean':float(np.mean(gate[m,1])),
            'ratio_mean':float(np.mean(ratio[m])), 'g_mean':float(np.mean(g[m]))})
    switches=lambda v,threshold:int(np.count_nonzero(np.diff((v>=threshold).astype(np.int8))))
    activation=np.flatnonzero(use & (g>.1))
    result={'status':'PASS_FIXED_CAUSAL_GATE_SCENE' if all(checks.values()) else 'FAIL_FIXED_CAUSAL_GATE_SCENE',
        'scene_id':scene, 'Plant_calls':1, 'raw_sha256':sha(raw), 'run_status_sha256':sha(status_path),
        'release_sha256':sha(case/'RELEASE.json'), 'source_lock_sha256':sha(case/'SOURCE_LOCK_SINGLE_v2.json'),
        'scores':scores, 'Q_over_C5':scores['candidate']['Q_m']/scores['C5']['Q_m'], 'criteria':checks,
        'action_chain_max_errors':errors, 'event_output_clip_count':int(clips.sum()),
        'parent_pointwise_max_abs_errors':parent_errors,
        'gate':{'event_count':int(event.sum()), 'ready_event_count':int(valid[event].sum()),
            'Ebp_mean':float(np.mean(gate[use,0])), 'Elo_mean':float(np.mean(gate[use,1])),
            'ratio_mean':float(np.mean(ratio[use])), 'ratio_median':float(np.median(ratio[use])),
            'g_mean':float(np.mean(g[use])), 'g_min':float(np.min(g)), 'g_max':float(np.max(g)),
            'g_above_0p1_fraction':float(np.mean(g[use]>.1)), 'g_ge_0p5_fraction':float(np.mean(g[use]>=.5)),
            'first_g_above_0p1_s':float(tt[activation[0]]) if len(activation) else None,
            'g_0p1_crossings':switches(g[use],.1), 'g_0p5_crossings':switches(g[use],.5),
            'target_0p5_crossings':switches(gt[use],.5), 'parent_g_mean':float(np.mean(parent_gate[use])),
            'time_windows':windows},
        'self_excitation_interpretation':'Time-window and parent comparisons are observational; they do not alone prove or disprove closed-loop self-excitation.',
        'score_source_sha256':sha(SCORE_SOURCE), 'score_constants_sha256':sha(CONSTANTS),
        'TEST_read':False, 'VAL_read':False, 'inertia_reconstruction_enabled':False}
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'scene_id':scene,'status':result['status'],'Q_over_C5':result['Q_over_C5'],
        'candidate_task':scores['candidate']['task_SO3_rad'],'B_task':scores['B']['task_SO3_rad'],
        'gate':result['gate'],'criteria':checks,'parent_pointwise_max_abs_errors':parent_errors},indent=2))
    if not all(checks.values()):
        raise SystemExit('Fixed diagnostic failed: stop all remaining scenes')


if __name__ == '__main__':
    if len(sys.argv)!=2:
        raise SystemExit('usage: score_call_v2.py <exact scene>')
    main(sys.argv[1])
