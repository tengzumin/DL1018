# C1：统一先验初值校准与固定12场配对验证

状态：当前先批准一次TRAIN校准拟合的实现/离线验证。闭环须待源码、模式、场景、物理身份和校准产物的独立主审通过后分别放行probe与剩余场次，不凭本文件直接启动。依据用户本轮“查完问题修复完后再继续跑”的指示，采用独立C1协议；不重开旧三轮，不改旧STOP，不自动扩成新72小时计划。

## 审核依据与唯一假设

TRAIN1536/605184端点的原目标重放及固定readout梯度已通过。无风原相位/能量加权目标略优于zero，但运行等权与晚段更差；W15 X及高频Z有局部readout欧式方向冲突，不是所有无风方向都被忽略。稀疏6144窗口中history与phi的精确重复对集合均为630且标签差均为0，没有发现额外phi合并矛盾；不能推成表示充分。

H_C：原训练得到的统一W0初值对小残差工况校准不足；仅改变其全局幅度，可在保留在线适应/PCF的条件下减轻无风退化。该假设必须用同一原corrected DSSM ON的c=1与c=c*闭环总效应区分。它不是实现bug修复或已证明的论文创新。

## 校准定义（不得看VAL拟合）

源模型、normalizer、TRAIN1536、394端点及原权重沿TASKBOOK_ZH.md。p为导出模型的未clip raw W0输出，y为同端点原cache float32训练标签。对每个run将其原相位weights归一为q，计算：

```text
E_y(r) = sum_i q_i ||y_i||²
A_r = sum_i q_i ||p_i||² / E_y(r)
B_r = sum_i q_i p_i·y_i / E_y(r)
L_r(c)/L_r(0) = A_r c² − 2 B_r c + 1
```

任一E_y非有限或<=0则停止，不能看数据后另选epsilon或丢run。按既有三wind_band（W00_W08/W09_W14/W15）各组运行等权平均A_r/B_r，固定求解：

```text
c* = argmin_{0<=c<=1} max_g [A_g c²−2B_g c+1]
```

候选集合只含0/1、A_g>0时组驻点B_g/A_g，以及两二次式在[0,1]内的解析交点；相同函数/线性退化明确处理。不是网格扫c，更不跑多个闭环c。数值目标值相差<=1e-12时选最大的c，保留较多原先验。记录全部系数/解析候选作为求解证明，唯一c写入冻结产物。

这是一次单参数校准拟合，不能表述为零学习；optimizer steps=0、无新encoder/normalizer训练、无seed搜索。部署只用一个固定常数，不用真实风/构型、分组选择器或额外输入。它优化的是raw prior的相对平方误差代理，不等同于beta*clip输出、Q或泛化。

启动闭环前的TRAIN门固定为：1−c*>=0.01，并且最坏组相对平方误差至少比c=1降低0.01。未过则不Plant，保留拟合失败/无效结论，不改门限重算。

## 唯一部署改动及基线

仅将原FEATURE初始state设为c*W0，完整缩放33×3矩阵（含常数feature列）；原模型output_W、checkpoint和normalizer保留。归档position_only_search_options(...,'FEATURE',12,c)已有p.weight=c*W0的实现，应优先复用。不能只在构造options之后改head.kappa而不改p.weight：FEATURE head更新函数本身不使用kappa缩放输出。对照options的数值差仅为初始weight与对应kappa元数据，须验证后者在FEATURE动态中不另起作用。所有后续更新、gamma、beta/readiness、更新周期、sEff、dmax和投影界相同。真实FEATURE泄漏为−0.002W（零中心），投影±60；不改为W0-anchor。

基线明确是原corrected DSSM14 ON，使用R2 frozen_inputs.json所钉住的归档 corrected_pair_eval_v1/sources/local_runtime 源包。不能使用R3强制eta_mask=[1,1,0]的runner后再改mask称单因素。C1自身ON(1)与ON(c*)必须同一新冻结源包，PCF设置完全相同；原ON是否全轴需由实际源码和运行opts验证，不靠本文猜测。若原ON身份无法闭合，停止放行并报告缺口。

物理Plant、执行器、原位置BS、B姿态控制、C0/J0、X14/encoder/normalizer与原ON一致。B新运行只作额外基准。不得拼接B某轴，不能解除旧参考保护或改G06 STOP。

## 固定场景、资源与放行门

- 场景复用既有R2/R3固定VAL12字典及物理payload：每任务低风一场、W09–W11一场、W12–W14一场、W15一场；按冻结清单核对ID/seed，不重新挑输场。不能把TRAIN校准、开发VAL12或训练VAL称为独立TEST。
- 最多一个校准候选、一次校准拟合；全新闭环上限36航次（B、ON(1)、ON(c*)各12），合法复用要有完整身份，不能把历史B runtime缺口补写为已知。probe计入36，不额外增加。新产物预算6GiB（包含raw），余盘<30GiB停止启动。
- PowerShell7、Luna max实现/证据复核、主模型审核；最多两执行者，不并发改同一文件。闭环最多一个重负载job，不停现有实验、不抢锁。新目录为 experiments/position_prior_calibration_c1_20261022/；历史原件只读，无删除/移动。
- 首次Plant之前核源码diff、模型缩放恒等式、Python/MATLAB输出先于更新、共享物理场景、评分器和资源锁。主审先批准一场probe，身份/完整性/安全和数字复算过关后才批准其余11场。首次失败保留且停止，不自行换c/换mask/重跑挑结果。
- 闭环主指标为0–20s三维位置RMSE，未舍入和1e-12m胜负容差；另报每任务/风组/轴/早晚阶段/峰值/安全/饱和。ON(c*)−ON(1)为初值缩放的配对总效应，B为性能基准；不把时间窗当独立样本。

## 筛查决定

本阶段筛查预期是W15组Q不高于同批ON(1)与B，高频组也不高于两对照，全12宏平均Q不高于ON(1)，且全部完整性/物理安全门通过。低风逐场退化必须完整报告，不能用其他组收益隐藏。

任何门失败：停止C1，不另拟第二个c、不扩72或动TEST。通过：只申请主审下一步完整72场任务书与剩余预算审核，不自动启动。论文既有62/72、41/48及理论/贡献/消融门保持，C1筛查通过不等于论文证据包达标。
