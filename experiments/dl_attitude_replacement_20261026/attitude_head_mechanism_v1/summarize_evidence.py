"""Save root decisions and all losses from real completed runs, without reading TEST."""
from pathlib import Path
import csv
import hashlib
import json
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    reports = {
        'BALANCED_MLP15': RESEARCH / 'mlp15_balanced_devscreen_v1',
        'C5_FULL72_MLP15': RESEARCH / 'mlp15_distribution_countercheck_v1',
    }
    output = HERE / 'ROOT_DECISION.json'
    if output.exists():
        raise FileExistsError(output)
    losses = []
    methods = {}
    resources = {'new_Plant_calls': 0, 'new_training_jobs': 0, 'baseline_reruns': 0,
                 'TEST_read': False, 'new_raw_bytes': 0}
    for method, directory in reports.items():
        report = load(directory / 'ROOT_TARGET_REVIEW.json')
        rows = [r for r in report['rows'] if r['method'] == method]
        b = {r['scene_id']: r for r in report['rows'] if r['method'] == 'B'}
        c5 = {r['scene_id']: r for r in report['rows'] if r['method'] == 'C5_RBF'}
        for row in rows:
            sid = row['scene_id']; raw = directory / 'runs' / sid / 'raw_run.mat'
            status = load(raw.with_name('run_status.json'))
            assert status['engineering_pass'] and sha(raw) == status['raw_sha256']
            resources['new_raw_bytes'] += raw.stat().st_size
            resources['new_Plant_calls'] += 1
            losses.append({'method': method, 'scene_id': sid,
                           'Q_mm': row['Q_m'] * 1000, 'B_Q_mm': b[sid]['Q_m'] * 1000,
                           'C5_Q_mm': c5[sid]['Q_m'] * 1000,
                           'task_SO3_mrad': row['task_SO3_RMSE_rad'] * 1000,
                           'B_task_SO3_mrad': b[sid]['task_SO3_RMSE_rad'] * 1000,
                           'C5_task_SO3_mrad': c5[sid]['task_SO3_RMSE_rad'] * 1000,
                           'position_loss_B': row['Q_m'] > b[sid]['Q_m'] + 1e-12,
                           'attitude_loss_B': row['task_SO3_RMSE_rad'] > b[sid]['task_SO3_RMSE_rad'] + 1e-12,
                           'inner_tracking_mrad': row['inner_filtered_reference_SO3_RMSE_rad'] * 1000,
                           'C5_inner_tracking_mrad': c5[sid]['inner_filtered_reference_SO3_RMSE_rad'] * 1000})
        methods[method] = {'summary': report['summary'],
                           'position_wins_B': sum(r['Q_m'] < b[r['scene_id']]['Q_m'] - 1e-12 for r in rows),
                           'attitude_wins_B': sum(r['task_SO3_RMSE_rad'] < b[r['scene_id']]['task_SO3_RMSE_rad'] - 1e-12 for r in rows),
                           'report_sha256': sha(directory / 'ROOT_TARGET_REVIEW.json')}
    capacity = load(HERE / 'ORACLE_HEAD_CAPACITY.json')
    target = load(HERE / 'CAUSAL_NOMINAL_TORQUE_RESIDUAL.json')
    replay = load(RESEARCH / 'mlp15_distribution_countercheck_v1/SAME_STATE_REPLAY.json')
    evidence = {'schema': 'ROOT_ATTITUDE_DISTRIBUTION_DECISION_V1',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'goal_status': 'ACTIVE_NOT_PAPER_QUALIFIED',
                'previous_goal_turn_classification': 'PROGRESS_REAL_18_FLIGHTS_AND_NEW_MECHANISM_EVIDENCE',
                'decision': 'REJECT_BOTH_FROZEN_MLP_PROMOTIONS; IMPLEMENT_AND_VERIFY_LEGAL_CAUSAL_ADAPTIVE_HEAD_NEXT',
                'resources': resources, 'methods': methods,
                'oracle_capacity_status': capacity['status'],
                'causal_target_accounting_status': target['status'],
                'oracle_labels_allowed_at_deployment': False,
                'limitations': ['Teacher data used in training, not independent validation',
                                'No legal adaptive head closed-loop result yet',
                                'Ideal state feedback; noisy derivative robustness unproven',
                                'No attitude closed-loop stability theorem established'],
                'next_taskbook': str(HERE / 'NEXT_LEGAL_HEAD_TASKBOOK.md'),
                'next_taskbook_sha256': sha(HERE / 'NEXT_LEGAL_HEAD_TASKBOOK.md'),
                'capacity_report_sha256': sha(HERE / 'ORACLE_HEAD_CAPACITY.json'),
                'causal_target_report_sha256': sha(HERE / 'CAUSAL_NOMINAL_TORQUE_RESIDUAL.json'),
                'same_state_report_sha256': sha(RESEARCH / 'mlp15_distribution_countercheck_v1/SAME_STATE_REPLAY.json')}
    assert len(replay['rows']) == 12 and resources['new_Plant_calls'] == 18
    with output.open('x', encoding='utf-8') as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    with (HERE / 'ALL_PAIRED_SCENES_AND_LOSSES.csv').open('x', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(losses[0]));writer.writeheader();writer.writerows(losses)
    text = '''# 姿态替代最新主审决定

本轮已真实完成 balanced 十二场和纯 C5 full72 六场，共 18 个新增候选航次；全部完整稳定，零倾角投影、零电机饱和、零广义指令裁剪。B/C5 全部复用，新训练 0，TEST 未读。原 C5 位置环证据保持冻结。

balanced 十二场：位置均值 15.621 mm，B 10.349、C5 9.055；外部任务 SO(3) 46.605 mrad，B 40.611、C5 40.669。位置与姿态各仅 1/12 胜 B。实际姿态对滤波参考的跟踪误差 38.211 mrad，C5 13.820 mrad。停止晋级。

纯 C5 full72 六场：位置均值 18.425 mm，B 9.143、C5 8.357；外部任务姿态 41.750 mrad，B 27.613、C5 26.428。该模型在相同六场 C5 教师状态上动作拟合六场都更好，然而闭环位置五场比 balanced 更差、外部任务姿态六场都更差。只改数据权重或根据离线拟合选模型不能解决本问题。

确认：用户先前确实取消了 roll/pitch 命令滤波角加速度上限，锁定快照为 [Inf,Inf,6] rad/s²；30°位置指令倾角投影是另一个环节。本轮十八场投影均为零，退化不能归咎于它。

唯一优先方向：冻结神经表征加合法因果更新头。oracle 教师标签容量检验使三个 W15 后十秒动作误差下降 60.5%、61.0%、77.0%；这只支持表征容量，绝不是部署或闭环改善证据。过去机体角速度、已发控制力矩和固定 J0 的区间名义残差核算已通过；不重建时变惯量，也不读取 Plant 真值。roll/pitch 与教师补偿大体一致，低幅 yaw 仍需谨慎处理和完整报告。

下一份任务书为 NEXT_LEGAL_HEAD_TASKBOOK.md：先实现与跨语言/因果无 Plant 核验，再冻结真实三场 W15 机制筛查；不得把 oracle RBF 标签送入运行时。论文目标仍未达到，原测试封存与所有失败保留。全部输场见 ALL_PAIRED_SCENES_AND_LOSSES.csv，机器身份和账本见 ROOT_DECISION.json。
'''
    (HERE / 'ROOT_DECISION_ZH.md').write_text(text, encoding='utf-8')
    print(json.dumps({'decision': evidence['decision'], 'resources': resources}, ensure_ascii=False))

if __name__ == '__main__':
    main()
