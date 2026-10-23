"""Audited twelve-scene mechanism screen; no confidence or TEST claims."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / 'screen12_parent_review'


def main():
    summary = json.loads((DATA / 'SUMMARY.json').read_text(encoding='utf-8'))
    with (DATA / 'ALL12_PAIRS.csv').open(encoding='utf-8-sig', newline='') as f:
        pairs = list(csv.DictReader(f))
    assert summary['event_count'] == 23616 and summary['status'] == 'C5_SCREEN_PASS'
    plt.rcParams.update({'font.family': 'serif', 'font.serif': ['Times New Roman', 'DejaVu Serif'],
                         'font.size': 8.5, 'axes.labelsize': 9, 'axes.titlesize': 9,
                         'legend.fontsize': 8, 'legend.frameon': False, 'pdf.fonttype': 42,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'savefig.dpi': 300, 'axes.axisbelow': True})
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 4.0), gridspec_kw={'width_ratios': [1, 1.6]})
    labels = ['All (12)', 'High frequency (6)', 'No wind (3)']
    groups = ['ALL12', 'HF6', 'W15']
    colors = {'B': '#777777', 'C3': '#0072B2', 'C4': '#E69F00', 'C5': '#009E73'}
    x = np.arange(3)
    for i, method in enumerate(colors):
        values = [1000 * summary['groups'][g][method] for g in groups]
        axes[0].bar(x + (i - 1.5) * .18, values, .17, color=colors[method], label=method)
    axes[0].set_xticks(x, labels, rotation=20, ha='right')
    axes[0].set_ylabel('Scene-equal mean position RMSE (mm)')
    axes[0].set_ylim(0, 12)
    axes[0].set_title('(a) Fixed development screen')
    axes[0].grid(axis='y', alpha=.18)
    axes[0].legend(ncol=2)
    y = np.arange(len(pairs))
    for method, marker, offset in [('C4', 'x', -.12), ('C5', 'o', .12)]:
        values = [1000 * (float(r['Q_' + method + '_m']) - float(r['Q_C3_m'])) for r in pairs]
        axes[1].scatter(values, y + offset, s=22, marker=marker, color=colors[method], label=method + ' minus C3')
    axes[1].axvline(0, color='#444444', linewidth=.8, linestyle='--')
    axes[1].set_yticks(y, [r['scene_id'].removeprefix('DL1018_VAL_') for r in pairs])
    axes[1].invert_yaxis()
    axes[1].set_xlabel('Paired position RMSE difference (mm); lower is better')
    axes[1].set_title('(b) Every screened scene')
    axes[1].grid(axis='x', alpha=.18)
    axes[1].legend(loc='lower right')
    fig.tight_layout(w_pad=2)
    for suffix in ('pdf', 'png'):
        target = HERE / ('fig_c5_screen.' + suffix)
        assert not target.exists()
        fig.savefig(target, bbox_inches='tight', dpi=300)
    plt.close(fig)
    refs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (DATA / 'SUMMARY.json', DATA / 'ALL12_PAIRS.csv', Path(__file__))}
    (HERE / 'FIGURE_SOURCE_IDS.json').write_text(json.dumps(refs, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'GENERATED_SCREEN_FIGURE_NOT_TEST', 'scene_count': 12, 'source_ids': refs}))


if __name__ == '__main__':
    main()
