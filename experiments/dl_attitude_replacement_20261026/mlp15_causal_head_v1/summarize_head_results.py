"""Freeze the actual six-run outcome under the user's B/C5 acceptance rules."""
from pathlib import Path
import csv
import hashlib
import json
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    output = HERE / 'ROOT_RESULT_v1.json'
    if output.exists():
        raise FileExistsError(output)
    manifest = load(HERE / 'MANIFEST.json')
    audits = []
    for record in manifest['records']:
        audit = load(HERE / 'audits' / f"{record['scene_id']}_AUDIT.json")
        assert audit['engineering_pass']
        assert sha(HERE / 'runs' / record['scene_id'] / 'raw_run.mat') == audit['raw_sha256']
        audits.append(audit)
    assert len(audits) == 6
    groups = {}
    for group, selected in [('ALL6', audits),
                            ('W15', [a for a in audits if a['scene_id'].endswith('W15')]),
                            ('HF', [a for a in audits if not a['scene_id'].endswith('W15')])]:
        methods = {method: {metric: sum(a[method][metric] for a in selected)/len(selected)
                            for metric in ['Q_m', 'SO3_rad', 'inner_tracking_rad']}
                   for method in ['candidate', 'frozen_MLP', 'B', 'C5']}
        c, b, c5 = methods['candidate'], methods['B'], methods['C5']
        groups[group] = {'count': len(selected), 'methods': methods,
                         'position_improves_B': c['Q_m'] < b['Q_m'],
                         'attitude_improves_B': c['SO3_rad'] < b['SO3_rad'],
                         'attitude_improves_C5': c['SO3_rad'] < c5['SO3_rad'],
                         'position_within_10pct_C5': c['Q_m'] <= 1.1*c5['Q_m'],
                         'position_degradation_fraction_vs_C5': c['Q_m']/c5['Q_m']-1}
    rows = []
    for a in audits:
        c, b, c5 = a['candidate'], a['B'], a['C5']
        rows.append({'scene_id': a['scene_id'], 'Q_mm': 1000*c['Q_m'], 'B_Q_mm': 1000*b['Q_m'],
                     'C5_Q_mm': 1000*c5['Q_m'], 'SO3_mrad': 1000*c['SO3_rad'],
                     'B_SO3_mrad': 1000*b['SO3_rad'], 'C5_SO3_mrad': 1000*c5['SO3_rad'],
                     'position_win_B': c['Q_m'] < b['Q_m']-1e-12,
                     'attitude_win_B': c['SO3_rad'] < b['SO3_rad']-1e-12,
                     'attitude_win_C5': c['SO3_rad'] < c5['SO3_rad']-1e-12,
                     'position_degradation_percent_vs_C5': 100*(c['Q_m']/c5['Q_m']-1),
                     'weight_projection_events': a['weight_projection_count'],
                     'residual_clipping_events': a['residual_dmax_clipped_event_count'],
                     'tilt_samples': a['tilt_projection_samples'], 'raw_sha256': a['raw_sha256']})
    result = {'schema': 'ROOT_CAUSAL_HEAD_SIX_SCENE_RESULT_V1',
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'decision': 'FAIL_FINAL_B_C5_GATES_NO_DEV72_OR_TEST',
              'goal_status': 'ACTIVE_NOT_PAPER_QUALIFIED', 'groups': groups,
              'position_wins_B': sum(r['position_win_B'] for r in rows),
              'attitude_wins_B': sum(r['attitude_win_B'] for r in rows),
              'attitude_wins_C5': sum(r['attitude_win_C5'] for r in rows),
              'all_six_full_stable_safe': True, 'new_Plant_calls_in_this_study': 6,
              'new_training_jobs': 0, 'baseline_reruns': 0, 'TEST_read': False,
              'all_input_output_update_replay_passed': True,
              'prior_ablation_offline_gate_passed': load(HERE / 'audits/FIXED_STATE_PRIOR_DIAGNOSIS.json')['screen_gate_passed'],
              'weight_bound_relaxation_supported': False,
              'acceptance_clarification_sha256': sha(HERE / 'USER_ACCEPTANCE_CLARIFICATION.md'),
              'rows': rows}
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with (HERE / 'ALL_PAIRED_SCENES_AND_LOSSES.csv').open('x', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (HERE / 'ROOT_RESULT_v1.md').write_text(
        '# 合法在线头 v1 六场主审结果\n\n'
        '六场真实闭环全部完整稳定，输入/输出/过去残差/更新逐事件独立复算通过。'
        '头开始影响控制前与冻结对照的完整状态数组完全一致，确认位置栈与物理场景没有暗改。\n\n'
        '结果不满足用户最终要求：双环必须优于 B、姿态优于 C5、位置相对 C5 退化不超过既定10%上限。'
        '六场位置胜 B 2/6、姿态胜 B 2/6、姿态胜 C5 0/6；不放行 DEV72 或 TEST。'
        '三场无风的双环宏平均虽优于 B，姿态仍落后 C5；不得将机制门冒充最终通过。\n\n'
        '预训练输出先验归零的固定记录诊断未过门，因此没有运行零先验闭环。'
        '放宽权重投影也未改善记录状态上的预测误差。下一项检查冻结先验与修正头是否使用一致的隐藏特征基底。'
        '这些是待验证的具体机制，不是全部根因已经解决。\n\n'
        '全部数值、分组和输场见 ROOT_RESULT_v1.json 与 ALL_PAIRED_SCENES_AND_LOSSES.csv。'
        '当前研究目标继续保持 ACTIVE，论文级证据尚未达标。\n', encoding='utf-8')
    print(json.dumps({'groups': groups, 'wins': [result['position_wins_B'], result['attitude_wins_B'], result['attitude_wins_C5']]}))

if __name__ == '__main__':
    main()
