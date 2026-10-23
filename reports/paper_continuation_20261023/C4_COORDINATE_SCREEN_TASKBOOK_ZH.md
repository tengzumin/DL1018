# C4：一致残差坐标的固定12场筛查任务书

状态：主审批准隔离实现与无Plant准备。须先完成新B单场入口审核；本页不代替确切源码/输入/准备结果绑定后的Plant release。必要新增航次已获用户授权，无需另询许可。

## 机制与唯一改动

唯一因子为标量 `m=1→0` 的**整体残差坐标干预**。不是“只删eta”或“只改标签”。C3固定host局部残差拟合改善；精确采样分解还显示FIG8高频Z存在明显eta响应，但尚未证明改变该通道能改善真实闭环。C4用于检验这一点。旧无预测项的R2关闭PCF曾12/12退化，是必须保留的负结果。

保留PCF辅助计算开关，以相同实现计算并记录a_req、a_f、r_f、eta；显式新增并记录二值坐标因子m。C4固定m=0，不扫中间值、不分轴挑选：

```
tracking_surface = clip(s - m*eta_before, [7,8,10])
prediction_reference = a_req - m*r_f
y[j:k] = ((v[k]-v[j]) - integral_[j,k)(prediction_reference)) / .01
```

为保持m=1的数值语义，m=1分支直接取原a_f并沿用原运算顺序；m=0直接取a_req。a_req包含当步已经应用的补偿。目标在当前事件k调用helper前形成，配前事件phi_j，j=k−10；当前输出由W_k产生，再一次联合tracking/leak/prediction及投影。n=320首个ready事件不得伪造历史样本，其后n=330起使用合法过去10ms区间；当前尚未发生的转移不得进入积分。

实际a_f积分与新prediction_reference积分须分别记录，字段名/元数据不能把a_req积分称为a_f积分。保留原误差面、eta、坐标面、实际使用的clip后面及事件前后权重，能逐事件独立复算。PCF辅助开关为true不代表m=1，报告和图必须明确m。

## 固定输入及对照

源自冻结C3 core `e5f1e30c433ee3f8206b36446cde71776589c161fe2a3ec60fbaf070585eb07f`；helper保持 `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`。只改隔离core中的m读取/契约、tracking坐标、参考积分/目标与必要日志。输出helper、编码器/特征、BS、B姿态、Plant、执行器不改。

DSSM14/X14/32；W0 SHA `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`，normalizer SHA `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`；原seed2026102001、step60000，每场重置W0。不训练、种子搜索或新增Teacher。gamma12、leak.002/s、h.01s、tau1s/rho.01、dt.001s、beta=min((n+1)dt/1.8,1)、输出clip±3、权重clip±60均不变。

固定12场及B_source/外生身份/C3对照由C3 DEV72锁SHA `a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730` 的scene_ids_reuse_12及对应行绑定，顺序：

1. DL1018_VAL_T1_C00_W07
2. DL1018_VAL_T1_C02_W09
3. DL1018_VAL_T1_C05_W12
4. DL1018_VAL_T1_C08_W15
5. DL1018_VAL_T2_C00_W10
6. DL1018_VAL_T2_C02_W12
7. DL1018_VAL_T2_C05_W15
8. DL1018_VAL_T2_C06_W00
9. DL1018_VAL_T3_C00_W13
10. DL1018_VAL_T3_C02_W15
11. DL1018_VAL_T3_C03_W00
12. DL1018_VAL_T3_C12_W09

首场工程核验固定第5场T2_C00_W10，随后按清单顺序执行其余11场，不按首场结果换场。复用原C3全部12条；B优先采用同源新B，身份不完备的旧B比较仍标为历史描述，不用新运行追溯改写旧B源码身份。不另跑C3、不跑TEST。

## 准备、启动与审核

代码/运行只写 `experiments/position_coordinate_c4_20261023`，结果审核只写 `reports/paper_continuation_20261023/c4_coordinate_parent_review`。历史工程和原MAT不改。保持32源库存，新增/替换的隔离core及必要新入口单列SHA；逐个which校验、完整cfg/opts及模型身份封存。禁止批量改工作区或新增通用框架。

无Plant检查至少覆盖：新opts与C3仅m字段有语义差异；原helper身份；m=1与旧C3的合成时序/目标/权重递推一致；m=0与独立Python参考一致；首事件无历史及后续区间；输出先于更新；新积分含已完成步、不含当前步。模型/normalizer未变不要求重复旧64个模型parity夹具，但必须重新核实际身份/shape。静态checkcode和实际MATLAB无Plant退出码均记录。

主审绑定确切源码、输入锁、合同、无Plant结果及cfg/opts快照后，先放行1场。主审实际读取raw，独立复算全部有效事件目标/更新、力链、完整性/安全与指标，工程门通过后才放行其余11场。首场性能可作为反例保留，不据单场调参或换结构；整组仍须按冻结门判断。

完整12场才作机制/性能筛查：两场FIG8高频（T2_C00_W10、T2_C02_W12）的Z RMSE及位置Q相对C3都严格降低；12场等权平均Q不高于C3；HF6（6场）与W15（3场）的组平均Q不高于B；全部完整安全。使用未舍入0–20s三维位置RMSE和1e-12m容差。报告所有场景、任务/风组、XYZ/早晚/峰值/尾部及全部输场。任一预登记门失败则否决C4，不扩72，不改门槛，不在本版本扫m/gamma/tau。通过才由主审另冻结补齐72场任务。

新增本阶段最多12航次、1GiB，PowerShell7、1个重仿真、共享锁不抢占、不打断旧实验，磁盘≥30GB，沿用总80GB预算及UTC2026-10-24T17:01:00截止。所有真实启动/失败/修复留账；同一工程故障最多两次有明确原因的修复，不覆盖失败。无独立TEST、无论文达标宣称。
