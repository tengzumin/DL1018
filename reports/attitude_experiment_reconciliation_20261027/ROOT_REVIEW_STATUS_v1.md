# 实验整理与当前判定

目标仍未达成：高频任务姿态必须不差于 B，同时保持位置相对 B 的优势。不能用总体均值或内环跟踪误差替代这个门槛。当前未推送 GitHub，未读取 TEST。

## 当前已完成闭环筛选

| 方案 | 场数 | 高频位置 RMSE / mm | 高频任务姿态 RMSE / mrad | 判定 |
|---|---:|---:|---:|---|
| B，共同配对基线 | 6 HF | 11.266 | 57.619 | 比较基准 |
| C5，共同配对基线 | 6 HF | 10.584 | 61.204 | 比较基准 |
| 物理残差 MLP 原版 | 12，其中6 HF | 10.825 | 61.355 | 姿态未过 B |
| MLP 先RLS更新后输出 | 12，其中6 HF | 10.916 | 61.364 | 拒绝，未改善 |
| 原版 MLP +位置NN补偿×0.9 | 12，其中6 HF | 12.250 | 60.502 | 拒绝，两项均未过 B |

证据：experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1 下三个 closed_loop_* study 的 audits/CLOSED_LOOP_SCORE_v1.json；当前 force09 的正式评分与 root 独立汇总完全一致。这些是开发诊断，不能宣称独立泛化或论文最终成功。

## 已确认且需要保留的限定

1. 首版物理残差 MLP 实际为 RLS+tracking，任务书原先要求 RLS-only；不能声称仅替换监督标签的一因子实验。后续相对真实已部署基线的单项变更仍可比较。
2. 通用评分的 head projection/output saturation 读取 legacy v39 字段，不能代表 MLP 在线状态。当前 force09 实际投影902事件、残差裁剪34事件；12场独立trace检查因果超前0、实际施加力矩误差0。投影属于限界更新，并不等同执行器饱和。
3. 当前评分原把W00称为无风；实际raw显示3场W15环境风速全零，另9场非零。已修当前评分分组，保留旧结果并另写勘误；既有Q/task/inner数值未改。W索引不能擅自解释为风速等级。
4. 旧GRU模型使用DEV24+VAL48训练，必须称开发集结果。full72的66新增raw+6父实验复用构成72评分；准备阶段的Plant_calls=0快照不能单独用于否定后续运行。
5. 旧WN12候选raw的已记录路径目前缺失（历史审计和分数仍在），完整重放的可用性需要单独标记。当前B/C5原始基线绑定可校验，不因此认定WN12候选raw仍在。

## 当前下一步

较强的旧WN18 GRU tracking参考准备固定位置NN补偿×0.9对照，不新增训练。首轮准备曾因最后加入路径恢复语句而使entry哈希过期；root与MATLAB启动前检查均拒绝，未进入Plant。正在重新审核该改动并重跑noPlant，之后运行首场与相同12场。不得把旧receipt当作修复后的有效证据。

有界历史实现审查见 HISTORY_CONTRACT_FINDINGS_v1.json；其空finding只说明所检查源码未发现新增确证缺陷，不代表所有历史副本已逐字节验收。更广历史索引由 HISTORY_INVENTORY_v1.json 补充。

## 后续运行更新（2026-10-28）

用户再次明确硬约束：禁止惯量重建；网络不预测J/Jdot/Jhat，不做惯量辨识，按实际输入/输出维度选择深度学习模块。固定标称J0仅用于控制代数计算。

GRU入口哈希问题已修复并重跑noPlant；root独立核对64项源码SHA通过。首场稳定完成：Q=0.010760563710609187 m，taskSO3=0.04296273984795624 rad，inner=0.020218431709927442 rad；task尚未过该场B。其余11场已启动，exec session=61945。不得把第一场或运行状态视为最终达标。

历史总索引已完成：HISTORY_INVENTORY_v1.json。旧wind勘误见 reports/attitude_replacement_progress_20261027/FORCE09_WIND_GROUP_ERRATUM_v1.md。当前后续状态以 CONTINUATION_STATE_v2.json 和实际进程/原始终态为准。

GRU×0.9完整12场与正式评分现已完成：ALL12 Q=10.920mm/task=45.987mrad/inner=11.442mrad；HF6 Q=11.717mm/task=60.303mrad/inner=14.347mrad。高频任务姿态0/6胜B，位置宏误差也高于B，判FAIL，不扩场。模型输入13维、hidden32、输出3维加速度残差；online DeltaW为33×3，不输出惯量。源码禁用惯量重建helper，控制P固定为标称J0；Plant动力学的真值参数仅用于仿真，不作为GRU输入。正式结果：gru_tracking_force09_v1/audits/GRU_TRACKING_FORCE09_SCORE_final12.json。

## 位置目标澄清

用户明确：C5平均位置超过B三十多百分比，微弱超过B没有研究价值。冻结FULL72 ALL72宏平均B=17.057913mm、C5=11.558718mm，C5收益32.23838%；原GRU双环=11.128768mm，已保留且略改善该位置收益。因此下一方案必须保留约C5位置水平并解决高频task姿态。此要求按匹配cohort比较，不机械要求HF子组也30%（C5自身HF优势较小）。允许按实际维度改变DL模块、训练目标和耦合结构，仍禁止惯量重建。

固定fc=18/(2pi)Hz的同状态因果补偿低通重放也不足以过B，拒绝据此启动闭环：MLP/GRU原版条件理想内环task分别61.986/61.315mrad，B实际57.619mrad。这是条件诊断，不是新闭环成绩。下一步转向保留位置收益的时序/学习目标机制设计。

## NCMD跟踪组合与接口审查更新

NCMD future-residual GRU + existing trackingdelta首场已COMPLETED：Q=9.161947mm，task=43.392929mrad，inner=16.903922mrad；同场cosine父为9.492907/43.308356/20.245017。位置/内环改善，任务姿态略退且仍输B，不能宣称成功。源码62项root SHA通过，父59个控制源码逐字节相同；其余11场已启动session29905。启动命令须先cd studyRoot并addpath candidate_runner_work/matlab/runtime。

C5历史HF修复审查见C5_HF_INTERFACE_LINEAGE_AUDIT_v1.json：M110/PCF修复在当前实际通路中存在。另查到RP按actual yaw求解、再拼desired yaw的混合旋转；原GRU同6HF target差pool0.2977mrad、prefilter force-closure误差pool0.00293m/s2，单独不足以解释3.58mrad task gap。准备独立一致yaw单因素试验，无效也须如实报告。

频谱/相位诊断已完成：experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/closed_loop_force09_v1/audits/FREQUENCY_PHASE_MECHANISM_REPORT_v1.md。18rad/s是command-filter参数而非inner自然频率；same-state重放不构成新闭环误差上下界。

## 两项接口pilot结果（各1场，非整组结论）

T3_C01_W14：yaw一致性Q9.6346mm/task65.4221mrad；父9.6207/65.4173，差异几乎无收益，关闭不扩场。此接口选择不能解释主要HF缺口。

实测姿态PCF Q29.9712mm/task65.3741mrad，位置比父恶化3.1倍、任务只改善0.066%，关闭不扩场。root逐点核af=issuedT/m*R(measuredEuler)e3-g误差1.78e-15，且位置NN与在线更新真实开启，确认改动有执行。原C5滤波坐标/实现关系应保留；label里存在内环项并不意味着删除它就改善闭环。

NCMD完整12正式结果与独立计算一致，见gru_ncmd_tracking_v1/audits/GRU_NCMD_TRACKING_SCORE_final12.json。位置保留约31.7%相对B的screen收益，但HF任务0/6胜B，不扩场。

下一有界候选只改位置delayed预测项tau=1s→0.1s(rho .01→.1)，保留gamma12、全部NN、原PCF和补偿强度。先查历史和离线同迹线head重放，再单场验证；不是盲扫参数或已证明根因。


## tau01完整12正式审查

12/12稳定完成，每场20000 transitions，零执行器/clip/tilt安全计数。root核score SHA与逐场重算宏均值。ALL12 Q11.081672mm/task45.787796mrad，匹配B位置收益22.5392%，C5同12约29.54%；HF6 Q12.174885mm/task59.609709mrad，分别比B差8.0697%/3.4556%，任务0/6胜B。相对父方案任务改善2.5969%，位置恶化20.0545%。拒绝原样扩72；离线预测RMSE下降未转化为目标闭环收益。转向TRAIN24因果H110预测可行性与0-C5方法假设审查，禁止惯量重建，TEST未读。
