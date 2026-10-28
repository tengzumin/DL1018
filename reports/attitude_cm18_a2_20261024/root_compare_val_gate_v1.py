"""Aggregate independently recomputed VAL reports; no model or Plant calls."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def aggregate(report):
    rows = report['scene_metrics']
    assert report['status'] == 'PASS' and len(rows) == 48
    ids = [r['scene_id'] for r in rows]
    assert len(set(ids)) == 48 and all('_VAL_' in sid for sid in ids)
    assert all(r['physical_error']['events'] == 1999 for r in rows)
    values = {
        'normalized_macro': sum(r['normalized_scene_score'] for r in rows) / 48,
        'physical_vector_macro_rad_s2': sum(math.sqrt(sum(
            r['physical_error']['axis'][a]['rmse_rad_s2'] ** 2 for a in 'xyz'
        )) for r in rows) / 48,
        'yaw_pooled_rad_s2': math.sqrt(sum(
            r['physical_error']['axis']['z']['rmse_rad_s2'] ** 2 for r in rows
        ) / 48),
    }
    assert all(math.isfinite(v) and v >= 0 for v in values.values())
    assert abs(values['normalized_macro'] - report['recomputed_scene_weighted_normalized_score']) < 1e-12
    return ids, values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    reference = root / 'experiments/attitude_cm18_a1_20261024/deployment_v1/validation_recomputed_v1.json'
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == '6225eb5509ce72c52c5624599b8eded142ebf65a6f1a812e41eeead5750c2c60'
    reference_ids, ref = aggregate(json.loads(reference.read_text()))
    candidate_ids, candidate = aggregate(json.loads(args.candidate.read_text()))
    assert set(reference_ids) == set(candidate_ids)
    passed = {key: candidate[key] <= 1.05 * ref[key] for key in ref}
    result = dict(schema='ROOT_A2_VAL_GATE_EVALUATION_V1', status='PASS' if all(passed.values()) else 'FAIL',
                  reference=ref, candidate=candidate, passed=passed,
                  candidate_sha256=hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
                  scope='Aggregation gate only; input reports must separately pass raw/model/source identity review',
                  Plant_calls=0, optimizer_steps=0)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
