"""Independent descriptive C6/C5 DEV scoring; not the full raw audit."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS'):
    os.environ[key] = '1'
import pathlib, json, hashlib, importlib.util
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[4]
TASK = ROOT / 'experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp'
OUT = pathlib.Path(__file__).with_name('PARENT_SCREEN12_DESCRIPTIVE_METRICS_v1.json')
def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert not OUT.exists()
    source = ROOT / 'reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py'
    assert digest(source) == 'c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1'
    spec = importlib.util.spec_from_file_location('pinned_scorer', source)
    scorer = importlib.util.module_from_spec(spec); spec.loader.exec_module(scorer)
    lock = load(TASK / 'C6_STARTUP_RAMP_INPUT_LOCK_v1.json')
    batch = load(TASK / 'C6_TAIL11_BATCH_STATUS_v5.json')
    assert batch['completed_scenes'] == 11
    paths = {r['scene_id']: pathlib.Path(r['run_status_path']) for r in batch['records']}
    sid = lock['first_scene_id']
    paths[sid] = TASK / 'runs_c6_startup_ramp_v1' / sid / 'C6_STARTUP_PREDICTION_RAMP/attempt_01/run_status.json'
    rows = []
    for sid in lock['scene_ids_reuse_12']:
        statuses = {'C6': paths[sid], 'C5': ROOT / 'experiments/position_axis_coordinate_c5_20261023/runs_c5_v1' / sid / 'C5_AXIS_MASK_M110/attempt_01/run_status.json'}
        pair = {}
        for method, path in statuses.items():
            status = load(path)
            pair[method] = scorer.score(dict(scene_id=sid, method=method, path=status['raw_path'], sha256=status['raw_sha256']))
        assert pair['C6']['external_identity_sha256'] == pair['C5']['external_identity_sha256']
        rows.append(dict(scene_id=sid, metrics=pair))
    hf = [r for r in rows if 9 <= int(r['scene_id'][-2:]) <= 14]
    assert len(rows) == 12 and len(hf) == 6
    mean = lambda group, method, key: float(np.mean([r['metrics'][method][key] for r in group]))
    summary = {m: {k: mean(rows, m, k) for k in ('Q_0_20_m', 'Q_0_5_m', 'Q_5_20_m')} for m in ('C6', 'C5')}
    y_mse = {m: float(np.mean([r['metrics'][m]['rmse_y_0_5_m']**2 for r in hf])) for m in ('C6', 'C5')}
    result = dict(status='DESCRIPTIVE_ONLY_FULL_RAW_AUDIT_PENDING', rows=rows, overall=summary, HF_early_Y_MSE=y_mse,
                  wins_vs_C5=sum(r['metrics']['C6']['Q_0_20_m'] < r['metrics']['C5']['Q_0_20_m']-1e-12 for r in rows),
                  new_Plant=0, TEST_accessed=False, script_sha256=digest(pathlib.Path(__file__)))
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
if __name__ == '__main__':
    main()
