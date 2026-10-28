"""Independent release/count/source-protection/sidecar-hash gate. No MAT reads."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'train_pcf_contract_reconstruction_20261022'
WORKER = '5ca776c5f476c8e7ad824c11ab1381d48b6fdf0b385f9471522a8f5826a8021a'
CORE = 'd2e2c807b8119b32eddba8f765c6c566bee40d5e37c0590363f9091d30a47f70'
MODEL = '8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--split', choices=['TRAIN', 'VAL'], required=True)
    split = ap.parse_args().split
    n = 1536 if split == 'TRAIN' else 96
    prefix = SOURCE / f'{split}_FIXED_MODEL_{WORKER[:12]}'
    paths = [Path(str(prefix) + suffix) for suffix in
             ['_PHASE_STATE.json', '_RUNS.csv', '_METRICS.csv']]
    before = {str(p): sha(p) for p in paths}
    state = json.loads(paths[0].read_text(encoding='utf-8'))
    assert state['status'] == f'PASS_{split}_{n}'
    assert state['worker_script_sha256'] == WORKER
    assert state['core_script_sha256'] == CORE
    assert sha(SOURCE / 'reconstruct_full_worker.py') == WORKER
    assert sha(SOURCE / 'reconstruct_stratified.py') == CORE
    assert state['model']['model_array_identity'] == MODEL
    assert state['all_fixed_sources_sha_stat_unchanged'] is True
    assert state['all_samples_passed'] is True
    assert state['optimizer_steps'] == state['plant_calls'] == state['gpu_jobs'] == 0
    assert state['test_accessed'] is False
    runs, metrics = read_csv(paths[1]), read_csv(paths[2])
    assert len(runs) == n and len({r['run_id'] for r in runs}) == n
    assert len(metrics) == n * 16
    ids = {r['run_id'] for r in runs}
    assert set(state['completed_run_ids']) == ids
    assert {r['run_id'] for r in metrics} == ids
    sidecar_bytes = 0
    for r in runs:
        assert r['status'] == 'PASS' and r['split'] == split
        assert r['worker_script_sha256'] == WORKER and r['core_script_sha256'] == CORE
        assert r['model_array_identity'] == MODEL
        assert r['source_sha_stat_unchanged'] == 'True'
        assert int(r['events']) == 1999 and int(r['valid_inference_events']) == 1968
        assert sum(m['run_id'] == r['run_id'] for m in metrics) == 16
        for kind in ['raw', 'run_start', 'event_h5', 'cache']:
            assert r[kind + '_sha256_before'] == r[kind + '_sha256_after']
            assert r[kind + '_mtime_ns_before'] == r[kind + '_mtime_ns_after']
        p = Path(r['sidecar_path']).resolve()
        assert p.parent == (SOURCE / 'fixed_model_sidecars').resolve()
        st = p.stat()
        assert st.st_size == int(r['sidecar_bytes'])
        assert sha(p) == r['sidecar_sha256']
        assert (p.stat().st_size, p.stat().st_mtime_ns) == (st.st_size, st.st_mtime_ns)
        sidecar_bytes += st.st_size
    assert len(list((SOURCE / 'fixed_model_sidecars').glob(f'{split}_*_{WORKER[:12]}.npz'))) == n
    assert sidecar_bytes == state['sidecar_bytes_written'] < 2 * 2**30
    assert {str(p): sha(p) for p in paths} == before
    result = dict(status='PASS_PARENT_COMPLETED_PHASE_GATE', split=split,
                  episodes=n, metric_rows=len(metrics), sidecar_bytes=sidecar_bytes,
                  inputs_sha256=before, sidecars_all_hash_verified=True,
                  recorded_source_hash_stat_unchanged=True, MAT_read=False,
                  checked_utc=datetime.now(timezone.utc).isoformat())
    (HERE / f'{split}_COMPLETED_PHASE_PARENT_GATE.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
