from __future__ import annotations
import csv, hashlib, json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT=Path(__file__).resolve().parent
CORE=OUT/'reconstruct_stratified.py'
WORKER=OUT/'reconstruct_full_worker.py'
RESULTS=OUT/'stratified_reconstruction_checks.csv'
STATE=OUT/'PHASE_STATE.json'
MANIFEST=OUT/'stratified_sample_manifest.csv'
FAILURES=OUT/'FAILURES.csv'
EXPECTED_MANIFEST='4019aac3a23f1aef4a70f5d37b364d1ca09bfd1bcfe9ce39e486b3772af18b49'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''): h.update(block)
    return h.hexdigest()

def main():
    state=json.loads(STATE.read_text(encoding='utf-8'))
    if state.get('status')!='PASS_18_FROZEN_STRATA': raise RuntimeError(f'18 phase is not complete: {state.get("status")}')
    core_sha=sha(CORE);worker_sha=sha(WORKER);manifest_sha=sha(MANIFEST)
    if state.get('script_sha256')!=core_sha or state.get('manifest_sha256')!=EXPECTED_MANIFEST or manifest_sha!=EXPECTED_MANIFEST:
        raise RuntimeError('18 phase/source/manifest SHA does not match the current frozen inputs')
    with RESULTS.open('r',newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    if len(rows)!=18 or len({r['run_id'] for r in rows})!=18 or any(r.get('status')!='PASS' or r.get('script_sha256')!=core_sha for r in rows):
        raise RuntimeError('18 results CSV is not a complete single-version PASS table')
    error_fields=('a0_replay_max_abs_mps2','a_req_vs_a0_minus_u_max_abs_mps2','physical_Y_vs_event_H5_max_abs_mps2','X14_vs_event_H5_max_abs','mixed_identity_max_abs_mps2','event_time_vs_transition_max_abs_s','raw_log_teacher_beta_vs_event_H5_max_abs','Y_clip_vs_event_H5_max_abs_mps2')
    maxima={name:max(float(r[name]) for r in rows) for name in error_fields}
    if any(v>1e-9 for v in maxima.values()): raise RuntimeError(f'closure maximum exceeds tolerance: {maxima}')
    rel=f'18_RELEASE_core-{core_sha[:12]}_worker-{worker_sha[:12]}.json'
    release={'phase':'18_STRATIFIED_NUMERIC_RECONSTRUCTION','status':'PASS_18_FROZEN_STRATA','released_local':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
        'release_script':str(Path(__file__).resolve()),'release_script_sha256':sha(Path(__file__)),
        'core_script':str(CORE.resolve()),'core_script_sha256':core_sha,'full_worker_script':str(WORKER.resolve()),'full_worker_script_sha256':worker_sha,
        'results_csv':str(RESULTS.resolve()),'results_csv_sha256':sha(RESULTS),'phase_state':str(STATE.resolve()),'phase_state_sha256':sha(STATE),
        'manifest_sha256':manifest_sha,'failure_ledger':str(FAILURES.resolve()),'failure_ledger_sha256':sha(FAILURES),
        'samples':len(rows),'run_ids':[r['run_id'] for r in rows],'max_closure_errors':maxima,
        'optimizer_steps':0,'plant_calls':0,'gpu_jobs':0,'test_accessed':False,'full_1536':'NOT_STARTED_PENDING_MAIN_MODEL_REVIEW'}
    path=OUT/rel
    with path.open('x',encoding='utf-8') as f: f.write(json.dumps(release,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'release_path':str(path.resolve()),'release_sha256':sha(path),'core_script_sha256':core_sha,'results_csv_sha256':release['results_csv_sha256'],'phase_state_sha256':release['phase_state_sha256'],'worker_sha256':worker_sha},ensure_ascii=False))

if __name__=='__main__': main()
