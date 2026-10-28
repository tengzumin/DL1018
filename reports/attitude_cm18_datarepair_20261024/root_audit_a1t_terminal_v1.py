"""Independent terminal history and artifact selection audit; no training."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'experiments/attitude_cm18_datarepair_20261024/training_a1t_v1'
OUT = Path(__file__).with_name('ROOT_A1T_TERMINAL_SELECTION_AUDIT_v1.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not OUT.exists(), 'Refusing overwrite'
    receipt = json.loads((RUN / 'run_receipt.json').read_text(encoding='utf-8'))
    assert receipt['status'] == 'COMPLETED'
    assert receipt['optimizer_steps_completed'] == receipt['optimizer_step_calls_attempted'] == 60000
    assert receipt['candidate_frozen'] is True and receipt['TEST_accessed'] is False
    assert receipt['C5_VAL48_used_for_training_or_selection'] is False
    rows = [json.loads(line) for line in (RUN / 'val_metrics.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [r['optimizer_step'] for r in rows] == list(range(0, 60001, 1000))
    best = None
    for row in rows:
        score = row['b_val_scene_weighted_normalized_score']
        assert isinstance(score, (int, float)) and 0 <= score < float('inf')
        improved = best is None or score < best['b_val_scene_weighted_normalized_score']
        if improved:
            best = row
        assert row['best_updated'] is improved
        assert row['best_step'] == best['optimizer_step']
        assert row['best_score'] == best['b_val_scene_weighted_normalized_score']
        assert row['best_checkpoint_sha256'] == best['best_checkpoint_sha256']
    assert receipt['best_step'] == best['optimizer_step']
    assert receipt['best_score'] == best['b_val_scene_weighted_normalized_score']
    checkpoint_sha = sha(RUN / 'best.pt')
    assert checkpoint_sha == receipt['best_checkpoint_sha256'] == best['best_checkpoint_sha256']
    release = Path(receipt['release']['release_path']).resolve(strict=True)
    release.relative_to(ROOT)
    assert sha(release) == receipt['release']['release_sha256']
    result = dict(schema='ROOT_A1T_TERMINAL_SELECTION_AUDIT_V1', status='PASS',
                  validation_records=len(rows), optimizer_steps=60000,
                  best_step=receipt['best_step'], best_score=receipt['best_score'],
                  best_checkpoint_sha256=checkpoint_sha,
                  terminal_receipt_sha256=sha(RUN / 'run_receipt.json'),
                  training_release_sha256=sha(release), Plant_calls=0, TEST_accessed=False,
                  limits='History/hash/strict-min audit; not a forward or closed-loop performance test.')
    OUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
