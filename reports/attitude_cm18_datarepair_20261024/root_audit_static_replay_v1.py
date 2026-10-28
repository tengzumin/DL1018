"""Recompute same-state action errors from serialized event CSV; no Plant."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report')
    parser.add_argument('output')
    args = parser.parse_args()
    path, out = ROOT / args.report, ROOT / args.output
    assert not out.exists()
    report = json.loads(path.read_text(encoding='utf-8'))
    assert report['status'] == 'PASS'
    assert report['scope']['Plant_calls'] == report['scope']['engine_calls'] == 0
    rows = []
    models = ('RBF', 'A1R', 'A1T')
    for scene in report['scene_results']:
        csv = ROOT / scene['event_csv']
        assert hashlib.sha256(csv.read_bytes()).hexdigest() == scene['event_csv_sha256']
        data = np.genfromtxt(csv, delimiter=',', names=True, dtype=None, encoding='utf-8')
        assert len(data) == 1999 and np.all(data['scene_id'] == scene['scene_id'])
        assert np.array_equal(data['plant_index'], np.arange(11, 19992, 10))
        results = {}
        for model, summary in zip(models, scene['strategy_summary'], strict=True):
            assert summary['strategy'] == model
            actual = np.column_stack([data[f'{model}_alpha_true_{axis}_rad_s2'] for axis in ('roll','pitch','yaw')])
            target = np.column_stack([data[f'alpha_BS_{axis}_rad_s2'] for axis in ('roll','pitch','yaw')])
            error = actual - target
            logged = np.column_stack([data[f'{model}_error_{axis}_rad_s2'] for axis in ('roll','pitch','yaw')])
            assert np.isfinite(error).all() and np.max(np.abs(error - logged)) < 1e-10
            axis_rms = np.sqrt(np.mean(error**2, axis=0))
            vector = float(np.sqrt(np.mean(np.sum(error**2, axis=1))))
            assert np.max(np.abs(axis_rms-summary['axis_rmse_rad_s2'])) < 1e-10
            assert abs(vector-summary['vector_rmse_rad_s2']) < 1e-10
            results[model] = {'vector_rmse_rad_s2': vector, 'axis_rmse_rad_s2': axis_rms.tolist()}
        rows.append({'scene_id': scene['scene_id'], 'metrics': results})
    result = {'schema':'ROOT_STATIC_ACTION_REPLAY_AUDIT_V1','status':'PASS',
              'scene_count':len(rows),'scenes':rows,'models':report['models'],
              'C5_VAL48_manifest_sha256':report['C5_VAL48_manifest_sha256'],
              'replay_report_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'Plant_calls':0,'TEST_accessed':False,
              'limits':'Independent CSV/hash/error recomputation; physics reconstruction covered by reviewed MATLAB, not independently repeated here. Not closed-loop tracking.'}
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','scene_count':len(rows)}))


if __name__ == '__main__':
    main()
