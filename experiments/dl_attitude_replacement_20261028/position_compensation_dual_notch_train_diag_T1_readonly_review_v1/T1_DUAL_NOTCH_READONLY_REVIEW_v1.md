# T1 W09 dual-notch single-call: independent read-only review

## Scope and identity

只复核既有单场运行：`DL1018_DEV_T1_C10_W09`，physical split `TRAIN_C5_24`，fold `holdout_W06_10`。只读取该诊断目录中 T1 raw、锁定的同场 B/C5/parent/pre-notch raws 与必要的 score/source-lock 文件；未读取 TEST/VAL raw 或 score，未启动 Plant，未做惯量重建。

source lock 列出101个依赖文件，本地逐一核验101/101路径存在且SHA匹配；绑定及run status的B/C5/parent hashes与独立paired score相同。双陷波 raw SHA 为 `ab14472c4fa827f087c3de6b40741a9868015df8117fee81c765c7ddbf289fb4`。已有 run status 记载 `COMPLETED/STABLE`、20000 transitions、20001 states、`Plant_calls=1`；这是目录中既有的授权单次运行，本审计没有再执行Plant。

`holdout_W06_10` checkpoint 用16个TRAIN场景训练、8个场景留出；目标T1 W09在holdout列表、不在fold train列表。它是fold-held-out TRAIN诊断，不是独立VAL；parent cosine-GRU本身看过这批DEV场景。

## 改动位置与动作递推

诊断 runner 是 preflight runner 的隔离副本。与preflight逐文件比较，新增2个Q4 helper，改动原runner及两个单次运行/准备包装器；源差异仅支持固定滤波器的release校验、runner身份绑定、日志和动作链集成。主控制路径在 C5 + residual-GRU 最终动作形成后、`dF=stage1PositionHeldForce` 和 `position_bs_step` 前应用双notch；100Hz event更新、event间ZOH；nominal加速度和现有yaw命令不改。raw日志确认双notch enabled、中心2.2/3.2Hz、Q=4，原3.5Hz/Q1 applied notch disabled。

逐event独立重放 `position_compensation_dual_notch_step`：notch输入与raw记录的post-GRU action逐event最大误差0；使用release锁定系数和首次非零输入初始化后，event raw输出、限幅输出及全时段ZOH输出相对raw日志的最大误差均为0；输入首次非零于0.32s；限幅事件0。notch输出转成position force为 `0.695 kg × action`，最大残差0。动作递推可逐样本重放。

## 同场score与频谱

用锁定的 frozen scorer 从五条同场 raw 独立重算，Q/task SO(3)/inner SO(3)均与 score JSON 达到数值一致（差小于1e-12）。Q_m为越低越好。

| 方法 | Q_m (m) | task SO(3) (mrad) | inner SO(3) (mrad) |
|---|---:|---:|---:|
| B | 0.010985 | 42.201 | 23.237 |
| C5 | 0.010466 | 43.273 | 23.274 |
| Parent GRU | 0.009493 | 43.308 | 20.245 |
| Candidate pre-notch | 0.010603 | 43.168 | 20.255 |
| Dual-notch candidate | 0.010809 | 41.527 | 20.117 |

相对pre-notch，dual-notch的task分数改善3.80%；Q_m恶化1.94%，仍低于单次诊断预设的5%上限。dual-notch仍比B的Q_m好1.60%，但比C5差3.28%，保留了对B的微弱位置优势，没有达到C5本身的Q_m。它只跑了一条T1 W09，不能外推到其他W组。

冻结scorer的2.2/3.2Hz邻带谱独立复算也与JSON一致。task−actual band RMS从pre-notch的11.705/6.450 mrad降到4.121/0.980 mrad，即下降64.79%/84.80%；dual-notch仍略高于B的3.567/0.894 mrad。command target分别从19.085/15.245降到5.740/2.027 mrad。

在这次闭环raw内，event输入经ZOH形成的stage-1动作在 `[1.5,2.5)` / `[2.5,3.5)`Hz的RMS为0.1390/0.0840 m/s²，滤波输出为0.0192/0.00795 m/s²；两带动作改变量约98.6%/99.0%。低频`[0.05,0.5)`Hz滤波输入/输出幅值相近，但输入与输出的低频差量为0.00444 m/s²，即输入低频RMS的2.27%。

## 与旧冻结门槛的关系

单场actual-run falsifier按自身预设通过：两条task误差带改善均大于25%、Q_m恶化1.94%小于5%、stable且安全计数为0。此前的双notch frozen replay另有低频action差量不超过2%的门槛；它仍是`FAIL_FIXED_FROZEN_REPLAY`：T1为2.233%，T3为3.116%。本次闭环T1重算低频action差量约2.27%，同样超过2%。单场闭环falsifier通过不撤销旧门槛失败，也不证明低频位置动作影响可接受。

详细原始绑定、频谱和score继续以 `position_compensation_dual_notch_train_diag_single_call_T1_v1/audits/DUAL_NOTCH_SINGLE_CALL_T1_SCORE_v1.json` 与 `references/W09_FIXED_NOTCH_FROZEN_REPLAY_v1.json` 为准。本报告只作为独立只读核查记录。
