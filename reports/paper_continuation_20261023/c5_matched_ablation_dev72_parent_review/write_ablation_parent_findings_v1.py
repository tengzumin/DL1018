"""Publish the closed ablation findings without selecting favorable scenarios."""
from pathlib import Path
import csv
import hashlib
import json

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    summary_path = HERE/'MATCHED_ABLATION_DEV72_INDEPENDENT_SUMMARY_v1.json'
    pairs_path = HERE/'MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv'
    assert sha(summary_path) == '71b5b437b4d2515ef9abf1fa8ab19379a9e6e5520813ca5b499caed749fab9bd'
    assert sha(pairs_path) == '9ad962499032826a31ee0f4c3b424ec45793272f411314ab6c35d3356e34e49b'
    source = json.loads(summary_path.read_text(encoding='utf-8'))
    with pairs_path.open(encoding='utf-8', newline='') as stream:
        pairs = list(csv.DictReader(stream))
    freeze = source['variants']['C5_FREEZE_TRAINED_W0']
    nopred = source['variants']['C5_NO_DELAYED_PREDICTION']
    loss_rows = []
    for row in pairs:
        delta = float(row['candidate_Q_0_20_m'])-float(row['B_TRACEABLE_Q_0_20_m'])
        if delta > 1e-12:
            loss_rows.append({**row, 'ablation_minus_B_Q_m': delta})
    assert len(loss_rows) == 84
    losses = HERE/'ABLATION_ALL_84_LOSSES_VS_B_v1.csv'
    with losses.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=[*pairs[0], 'ablation_minus_B_Q_m'])
        writer.writeheader()
        writer.writerows(loss_rows)
    text = '''# C5严格DEV72消融：根主审结论

两配置各复用12场并新增60场，均真实自然OS0。主审已读取新增120份raw并逐事件复算236,160个更新；复用的24场另有闭合主审，共覆盖两配置144条记录、283,392事件。源码、模型、normalizer、cfg/opts、W0重置、同物理输入与时间/单位/符号检查全部通过。根另用场景等权math.fsum独立重算所有组及全部配对。新增训练0、TEST0；累计本续作自然完成300航次。

两消融均保持原PCF、M110、readiness、beta时钟、原legacy标志和物理链。FREEZE仅冻结实际权重；NO_PRED仅移除旧区间预测梯度，不顺带关PCF或改变tracking/leak/联合投影。

## 完整结果

所有Q均为场景等权0–20 s三维位置RMSE，单位mm。胜负用未舍入数值和1e-12 m容差。

|组|n|B|完整C5|FREEZE|NO_PRED|C5胜/负NO_PRED|
|---|---:|---:|---:|---:|---:|---:|
'''
    for group in ('ALL72', 'HF_W09_W14', 'W15', 'T1', 'T2', 'T3'):
        fg, ng = freeze[group], nopred[group]
        f, n = fg['scene_equal_mean_metrics'], ng['scene_equal_mean_metrics']
        wins = ng['C5_vs_ablation']
        values = [n['B_TRACEABLE']['Q_0_20_m'], n['C5_M110']['Q_0_20_m'],
                  f['C5_FREEZE_TRAINED_W0']['Q_0_20_m'], n['C5_NO_DELAYED_PREDICTION']['Q_0_20_m']]
        text += f"|{group}|{ng['n']}|"+'|'.join(f'{x*1000:.6f}' for x in values)+f"|{wins['wins']}/{wins['losses']}|\n"
    text += '''
完整C5对FREEZE为72胜0负，对NO_PRED为54胜18负，所有这些胜场改善均超过10微米。两消融对B分别3胜69负、57胜15负，都未满足原62/72开发门；NO_PRED的无风均值还略高于B。C5仍为已审正式候选中唯一满足原开发性能门者，不因消融结果切换模型或按任务拼接Head。

## 收益与限制

在线适应在这条冻结控制链上具有明显闭环作用。但trained W0的离线物理残差标签与在线PCF坐标标签并不完全相同，FREEZE差不能解释为DSSM表征“无价值”，更不能证明预训练不必要。这里没有做随机表征或无预训练对照。

预测项的平均收益为0.551242mm，高频为0.437847mm，无风为1.357158mm；它是范围明确的组件干预证据，不是新控制律稳定性证明。C5相对NO_PRED的18个退化全部保留。T2（FIG8）均值只改善约1.067微米，且对B胜场由NO_PRED的23/24降至C5的18/24；不能写成预测项在每个任务均明显有益。T1和T3的改善支持总体收益，但不能用来掩盖T2。

配对场景bootstrap固定seed2026102301、10,000次。以下为C5−NO_PRED平均Q差的95%描述性区间，单位mm；开发阶段已经选择方法，不是独立TEST推断或多重比较校正后的显著性结论。

|组|均值差|95%描述区间|
|---|---:|---:|
'''
    for group in ('ALL72', 'HF_W09_W14', 'W15', 'T1', 'T2', 'T3'):
        g = nopred[group]
        lo, hi = [1000*x for x in g['C5_minus_ablation_Q_95pct_scene_bootstrap_m']]
        text += f"|{group}|{g['C5_minus_ablation_Q_m']*1000:.6f}|[{lo:.6f}, {hi:.6f}]|\n"
    text += '''
## 完整C5相对NO_PRED的全部18个退化

下表正差表示完整C5更差；没有删去微小差、早段失败或不利任务。

|scene_id|C5 Q(mm)|NO_PRED Q(mm)|差(mm)|
|---|---:|---:|---:|
'''
    regressions = [row for row in pairs if row['variant'] == 'C5_NO_DELAYED_PREDICTION' and float(row['C5_minus_ablation_Q_m']) > 1e-12]
    assert len(regressions) == 18
    for row in regressions:
        text += f"|{row['scene_id']}|{1000*float(row['C5_M110_Q_0_20_m']):.6f}|{1000*float(row['candidate_Q_0_20_m']):.6f}|{1000*float(row['C5_minus_ablation_Q_m']):+.6f}|\n"
    text += '''
全部144行及完整逐轴/早后段/峰值/饱和/计时/身份见MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv；C5的18退化另存C5_ALL_18_REGRESSIONS_VS_NO_PRED_v1.csv。两消融对B全部84输场见ABLATION_ALL_84_LOSSES_VS_B_v1.csv。C5对B原8个输场及对C3的19个退化保持旧完整表，不因新结果删除。

## 主审裁决

保留C5固定科学版本，接受严格消融对“在线适应重要、预测项总体及无风收益”的支持；拒绝“每场/每任务均改善”的主张。预训练网络、复合学习、积分标签和投影已有先例，贡献须按具体离散时序/坐标机制整合与严格证据来审，不把修bug或32.24%总收益全部归给最后一个组件。Luna max独立贡献复核仍在进行。

限定理论采用已审核的条件有限路径误差界，不能升级为先验Plant稳定、参数收敛或数值区间认证。实际物理桥梁72场已核验，不等于反事实因果证明。当前耗时仍为NONISOLATED_NOT_FORMAL。

当前只允许TEST入口实现；DEV全数组生成器无Plant等价、最终贡献裁决、六方法/计分/统计冻结及独立放行均须闭合。TEST仍未解封，论文证据包仍未达标。不再为追逐100%胜率调参、换Head或追加模型。原总截止和历史G06 STOP保留。

工程记录：初次全量reader v2因四处MATLAB字符tuple未先解码而退出1，无Plant或科学结果改变；v3只补既有matlab_text解码与新输出名，原件和失败记录保留。Windows长路径用只读extended路径适配；旧PS启动日期门保守提前8h的事实已单列勘误，不回写冻结源码。

## 输入身份

- 全量raw主审JSON SHA256：ec696b9e80a1f22af26b8ef58cb3fcc0a275102ee68b82b286ddf6d54d0a75ba。
- 独立分组复算JSON SHA256：71b5b437b4d2515ef9abf1fa8ab19379a9e6e5520813ca5b499caed749fab9bd。
- 完整配对CSV SHA256：9ad962499032826a31ee0f4c3b424ec45793272f411314ab6c35d3356e34e49b。
- 审计器v3 SHA256：cb980b25b79d7ae61de97d95afd1f24400c16d1591b96d1f69ff345456151d84。
'''
    out = HERE/'C5_MATCHED_ABLATION_DEV72_PARENT_FINDINGS_ZH.md'
    with out.open('x', encoding='utf-8') as stream:
        stream.write(text)
    print(json.dumps({'report_SHA256': sha(out), 'all84_losses_csv_SHA256': sha(losses)}))


if __name__ == '__main__':
    main()
