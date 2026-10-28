"""Independent three-record objective audit; never fits a model."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = ROOT.parent / 'REFERENCE_FIX_FULL72_20261021_022342_313' / 'corrected_reference_training_v1'

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def main():
    index = ARCHIVE / 'corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv'
    runs_path = ROOT / 'reports/train_pcf_contract_reconstruction_20261022/TRAIN_FIXED_MODEL_5ca776c5f476_RUNS.csv'
    assert sha(index) == '257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca'
    assert sha(runs_path) == '4a072c8006042cbffa5e653e450432c748f337fa45790c330b9aa58a8ac32190'
    sources = {r['run_id']: r for r in read(index) if r['split'].upper() == 'TRAIN'}
    runs = read(runs_path)
    selected = []
    for task, role, band in [('FIG8_3D', 'B', 'W15'), ('HELIX', 'POS_OFF', 'W09_W14'), ('SQUARE', 'B', 'W00_W08')]:
        selected.append(min((r for r in runs if (r['task'], r['role'], r['wind_band']) == (task, role, band)), key=lambda r: r['run_id']))
    out = []
    for r in selected:
        s = sources[r['run_id']]
        cache, side = Path(s['cache_path']), Path(r['sidecar_path'])
        assert sha(cache) == s['cache_sha256'] and sha(side) == r['sidecar_sha256']
        ends = np.arange(31, 1999, 5)
        with np.load(cache, allow_pickle=False) as z:
            y = z['y'][ends].astype(float)
            phase = z['phase'][ends]
        with np.load(side, allow_pickle=False) as z:
            pred = z['pred_raw_valid'][ends - 31]
        scene_n = sum((v['task'], v['role'], v['class_index']) == (s['task'], s['role'], s['class_index']) for v in sources.values())
        phases, counts = np.unique(phase, return_counts=True)
        w = np.asarray([.5 / (3 * 16 * scene_n * len(phases) * counts[np.flatnonzero(phases == p)[0]]) for p in phase], dtype=np.float32).astype(float)
        for j, axis in enumerate('XYZ'):
            residual = (pred[:, j] - y[:, j]) / 3
            # Equivalent independent Huber expression: q=min(abs(residual),1).
            q = np.minimum(abs(residual), 1)
            loss = (q * q / 2 + abs(residual) - q) / 3
            zero = y[:, j]**2 / 54
            out.append(dict(run_id=r['run_id'], axis=axis, weight_mass=float(w.sum()),
                            prior_smoothl1_contribution_axis_div3=float(w @ loss),
                            zero_smoothl1_contribution_axis_div3=float(w @ zero),
                            prior_rmse_clip_weighted=float(np.sqrt(w @ (pred[:, j] - y[:, j])**2 / w.sum())),
                            zero_rmse_clip_weighted=float(np.sqrt(w @ y[:, j]**2 / w.sum()))))
        assert sha(cache) == s['cache_sha256'] and sha(side) == r['sidecar_sha256']
    with (HERE / 'INDEPENDENT_OBJECTIVE_SAMPLE_CHECKS.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=out[0]); writer.writeheader(); writer.writerows(out)
    print(json.dumps(dict(status='PASS_THREE_RECORD_OBJECTIVE_CHECKS', rows=out)))

if __name__ == '__main__':
    main()
