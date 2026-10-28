"""Reproduce the frozen development comparison; no TEST or model selection."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

here = Path(__file__).resolve().parent
summary_path = here / 'PARENT_DEV72_SUMMARY.json'
metrics_path = here / 'PARENT_ALL288_METRICS.csv'
summary = json.loads(summary_path.read_text())
with metrics_path.open(newline='') as stream:
    metrics = list(csv.DictReader(stream))
methods = ['B', 'DSSM14', 'KAN14', 'C3']
groups = [(name, summary['groups'][key]['n'],
           [summary['groups'][key]['methods'][m]['Q_0_20_m'] * 1000 for m in methods],
           summary['groups'][key]['C3_paired']['B']['WIN'])
          for name, key in [('All development', 'ALL72'), ('High frequency W09–W14', 'HF_W09_W14'), ('No wind W15', 'W15')]]
subset = [r for r in metrics if r['scene_id'].split('_')[2] == 'T2' and 9 <= int(r['scene_id'][-2:]) <= 14]
groups.append(('FIG8 high frequency', len(subset) // 4,
               [np.mean([float(r['Q_0_20_m']) * 1000 for r in subset if r['method'] == m]) for m in methods], 1))
plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'],
                     'font.size': 9, 'pdf.fonttype': 42, 'ps.fonttype': 42, 'axes.linewidth': .6})
fig, axes = plt.subplots(2, 2, figsize=(7, 4.7), layout='constrained')
colors, markers = ['.45', '#D55E00', '#CC79A7', '#0072B2'], ['s', 'o', '^', 'D']
for ax, (title, n, values, wins) in zip(axes.flat, groups):
    ax.axhline(values[0], color='.6', linewidth=.7, linestyle=':', zorder=0)
    for i, value in enumerate(values):
        ax.scatter(i, value, color=colors[i], marker=markers[i], s=32, zorder=3)
        ax.text(i, value + .25, f'{value:.3f}', ha='center', fontsize=8)
    ax.set(xticks=range(4), xticklabels=methods, xlim=(-.5, 3.5),
           ylim=(0, max(values) * 1.2 + .6), ylabel='Mean position Q (mm)',
           title=f'{title} (n={n}); C3 wins {wins}/{n}')
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(length=3, width=.6)
fig.suptitle('Frozen C3: development evidence (no independent TEST)', fontsize=11)
out = here / 'figures'
out.mkdir(exist_ok=True)
for suffix in ['pdf', 'png']:
    path = out / f'fig_c3_dev72.{suffix}'
    assert not path.exists(), 'Preserve earlier evidence'
    fig.savefig(path, dpi=300)
plt.close(fig)
files = [summary_path, metrics_path, Path(__file__), out / 'fig_c3_dev72.pdf', out / 'fig_c3_dev72.png']
(out / 'FIGURE_MANIFEST.json').write_text(json.dumps(dict(files=[dict(path=str(p.resolve()), sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files], qualification='Development only; no independent TEST; no error bars or cross-seed claims'), indent=2), encoding='utf-8')
