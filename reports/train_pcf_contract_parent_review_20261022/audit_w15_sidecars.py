"""Parent independently recomputes W15 late-time metrics from completed TRAIN sidecars."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'train_pcf_contract_reconstruction_20261022'

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    runs_path = SOURCE / 'TRAIN_FIXED_MODEL_5ca776c5f476_RUNS.csv'
    runs_sha = sha(runs_path)
    with runs_path.open(encoding='utf-8-sig', newline='') as f:
        runs = [r for r in csv.DictReader(f) if r['wind_band'] == 'W15']
    assert len(runs) == 96
    rows = []
    for r in runs:
        p = Path(r['sidecar_path'])
        assert sha(p) == r['sidecar_sha256']
        st = p.stat()
        with np.load(p, allow_pickle=False) as z:
            times = z['event_time_s']
            ix = np.flatnonzero(times >= 5)
            pred = z['pred_applied_valid'][ix - 31]
            targets = {k: z[n][ix] for k, n in [('Y_raw', 'Y_raw'), ('Y_plus_Mrf_raw', 'mixed_raw')]}
        # Independent DC + positive-frequency complex Fourier projections.
        n = len(ix)
        bins = np.arange(int(np.floor(n * .01)) + 1)
        basis = np.exp(-2j * np.pi * np.outer(bins, np.arange(n)) / n)
        for label, target in targets.items():
            err = pred - target
            coeff = basis @ err / n
            low = np.sqrt(abs(coeff[0])**2 + 2 * np.sum(abs(coeff[1:])**2, axis=0))
            zero_coeff = basis @ (-target) / n
            zero_low = np.sqrt(abs(zero_coeff[0])**2 + 2 * np.sum(abs(zero_coeff[1:])**2, axis=0))
            for axis, name in enumerate('XYZ'):
                rows.append(dict(run_id=r['run_id'], task=r['task'], role=r['role'],
                                 target=label, axis=name, events=n,
                                 zero_rmse=float(np.sqrt(np.mean(target[:, axis]**2))),
                                 prior_rmse=float(np.sqrt(np.mean(err[:, axis]**2))),
                                 zero_absbias=float(abs(np.mean(target[:, axis]))),
                                 prior_absbias=float(abs(np.mean(err[:, axis]))),
                                 zero_lowfreq=float(zero_low[axis]), prior_lowfreq=float(low[axis])))
        assert sha(p) == r['sidecar_sha256']
        assert (p.stat().st_size, p.stat().st_mtime_ns) == (st.st_size, st.st_mtime_ns)
    assert sha(runs_path) == runs_sha
    with (OUT / 'parent_w15_late_scene_checks.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    groups = []
    for target in ('Y_raw', 'Y_plus_Mrf_raw'):
        for axis in 'XYZ':
            rr = [r for r in rows if (r['target'], r['axis']) == (target, axis)]
            groups.append(dict(target=target, axis=axis, episodes=len(rr),
                               bad=sum(r['prior_rmse'] > r['zero_rmse'] for r in rr),
                               **{k: float(np.mean([r[k] for r in rr])) for k in
                                  ('zero_rmse', 'prior_rmse', 'zero_absbias', 'prior_absbias', 'zero_lowfreq', 'prior_lowfreq')}))
    result = dict(status='PASS_PARENT_W15_LATE_RECOMPUTATION', input_runs_sha256=runs_sha,
                  episodes=96, rows=len(rows), groups=groups,
                  low_frequency='Direct complex Fourier projections, 0-1Hz including DC, contiguous 5-19.99s',
                  sources_and_sidecar_sha_stat_unchanged=True, MAT_read=False)
    (OUT / 'parent_w15_late_metadata.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
