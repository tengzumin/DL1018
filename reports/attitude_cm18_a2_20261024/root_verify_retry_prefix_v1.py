"""Verify a completed engineering retry preserves the interrupted training prefix."""
import hashlib
import json
from pathlib import Path
import numpy as np


def main():
    root = Path(__file__).resolve().parents[2]
    experiment = root / 'experiments/attitude_cm18_a2_20261024'
    old, new = experiment / 'training_run_v1', experiment / 'training_retry1_v1'
    old_receipt = json.loads((old / 'run_receipt.json').read_text(encoding='utf-8'))
    new_receipt = json.loads((new / 'run_receipt.json').read_text(encoding='utf-8'))
    assert old_receipt['status'] == 'FAILED' and old_receipt['optimizer_steps_completed'] == 38200
    assert new_receipt['status'] == 'COMPLETED' and new_receipt['optimizer_steps_completed'] == 60000
    paths = [root / 'experiments/attitude_cm18_a1_20261024/training_run_v1/initial_parameters.npz',
             old / 'initial_parameters.npz', new / 'initial_parameters.npz']
    arrays = []
    for path in paths:
        with np.load(path, allow_pickle=False) as archive:
            arrays.append({key: archive[key].copy() for key in archive.files})
    assert all(set(a) == set(arrays[0]) for a in arrays)
    assert all(np.array_equal(arrays[0][key], a[key]) for a in arrays[1:] for key in arrays[0])
    histories = [[json.loads(line) for line in (p / 'val_metrics.jsonl').read_text(encoding='utf-8').splitlines()]
                 for p in (old, new)]
    assert [v['optimizer_step'] for v in histories[0]] == list(range(0, 38001, 1000))
    by_step = {v['optimizer_step']: v for v in histories[1]}
    assert len(by_step) == 61
    deltas = [abs(v['scene_weighted_normalized_score'] - by_step[v['optimizer_step']]['scene_weighted_normalized_score'])
              for v in histories[0]]
    assert np.isfinite(deltas).all() and max(deltas) <= 1e-12
    result = dict(schema='ROOT_A2_RETRY_PREFIX_REPRODUCTION_V1', status='PASS',
                  initial_arrays_exact=True, compared_validation_steps=len(deltas),
                  maximum_absolute_score_difference=max(deltas), total_consumed_optimizer_steps=158200,
                  history_sha256=[hashlib.sha256((p / 'val_metrics.jsonl').read_bytes()).hexdigest() for p in (old, new)],
                  interpretation='Same scientific trajectory prefix after an engineering-only fresh retry; not independent-seed evidence')
    target = Path(__file__).with_name('ROOT_RETRY_PREFIX_REPRODUCTION_v1.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
