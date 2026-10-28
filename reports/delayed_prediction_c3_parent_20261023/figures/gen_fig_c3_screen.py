"""Frozen 12-scene screen: paired RMSE and equal-weight group means."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'PARENT_ALL12_PAIRED.csv'
data = SOURCE.read_bytes()
source_sha = hashlib.sha256(data).hexdigest()
rows = list(csv.DictReader(data.decode('utf-8-sig').splitlines()))
assert len(rows) == 12 and len({r['scene_id'] for r in rows}) == 12
q = {m: np.array([float(r[m+'_Q_m'])*1000 for r in rows]) for m in ('B', 'C2', 'C3')}
assert sum(q['C3'] < q['B']-1e-9) == 10
plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'],
                     'font.size': 9, 'axes.labelsize': 9, 'axes.titlesize': 10,
                     'legend.fontsize': 8, 'legend.frameon': False,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'pdf.fonttype': 42, 'ps.fonttype': 42, 'savefig.dpi': 300})
colors = {'B': '#777777', 'C2': '#E69F00', 'C3': '#0072B2'}
fig, (ax, ag) = plt.subplots(1, 2, figsize=(7.0, 4.5), gridspec_kw={'width_ratios': [1.3, 1]})
y = np.arange(12)
for i in y:
    ax.plot([q['B'][i], q['C3'][i]], [i, i], color='#CCCCCC', lw=1.2, zorder=1)
for method, marker in [('B', 'o'), ('C2', '^'), ('C3', 's')]:
    ax.scatter(q[method], y, s=25, marker=marker, color=colors[method], label=method, zorder=3)
labels = [r['scene_id'].replace('DL1018_VAL_', '') for r in rows]
ax.set_yticks(y, labels)
for label, i in zip(ax.get_yticklabels(), y):
    if q['C3'][i] > q['B'][i]:
        label.set_fontweight('bold')
ax.invert_yaxis()
ax.set_xlabel('0–20 s position RMSE (mm)')
ax.set_xlim(0, 17)
ax.grid(axis='x', alpha=.18)
ax.set_title('(a) All paired scenarios', loc='left')
ax.legend(ncol=3, loc='upper left', bbox_to_anchor=(0, -.12), columnspacing=1.0)
groups = [('All\n(n=12)', np.ones(12, dtype=bool)),
          ('High frequency\n(n=6)', np.array([9 <= int(r['wind'][1:]) <= 14 for r in rows])),
          ('No wind\n(n=3)', np.array([r['wind'] == 'W15' for r in rows]))]
gx = np.arange(len(groups)); width = .23
group_values = {}
for j, method in enumerate(('B', 'C2', 'C3')):
    vals = [float(q[method][mask].mean()) for _, mask in groups]
    group_values[method] = vals
    ag.bar(gx+(j-1)*width, vals, width*.94, color=colors[method], label=method)
    for x, v in zip(gx+(j-1)*width, vals):
        ag.text(x, v+.12, f'{v:.2f}', ha='center', va='bottom', fontsize=7, rotation=90)
ag.set_xticks(gx, [name for name, _ in groups])
ag.set_ylim(0, 13)
ag.set_ylabel('Scene-equal mean RMSE (mm)')
ag.set_title('(b) Group means', loc='left')
ag.grid(axis='y', alpha=.18)
ag.set_axisbelow(True)
fig.suptitle('Fixed 12-scene mechanism screen — lower is better', y=.98, fontsize=11)
fig.subplots_adjust(left=.19, right=.99, top=.88, bottom=.18, wspace=.48)
fig.text(.19, .02, 'Bold scenario labels: C3 loses to B.  This is neither DEV72 nor independent TEST48.', fontsize=8)
for suffix in ('pdf', 'png'):
    fig.savefig(HERE / f'fig_c3_screen.{suffix}')
plt.close(fig)
assert SOURCE.read_bytes() == data
manifest = {'source': str(SOURCE), 'source_sha256': source_sha, 'scene_count': 12,
            'group_means_mm': group_values, 'scope': 'Fixed mechanism screen, no generalization claim',
            'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (HERE/'fig_c3_screen.pdf', HERE/'fig_c3_screen.png')}}
(HERE/'FIGURE_MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest))
