# dAtt oracle 量的一事件滞后持续性诊断

状态：**完成非 TEST 离线诊断；仅确认 oracle dAtt 的描述性一事件持续性，不构成可部署性、因果、安全或论文资格证据。** 未运行 Plant、闭环航次或训练；未访问 TEST；未修改任何原始 MAT。

## 信号与时间

位置事件 `k` 开始时，Plant 状态姿态可读；当次 DSSM 输出之后才产生 `R_raw,k` 与 `T_req,k`。因此

$$
dAtt_k = (R_actual,k - R_raw,k) e_3 T_req,k / m_true
$$

只能在事件 `k` 末计算，最早于 `k+1` 使用。此处将既有轨迹中的 `dAtt_k` 作为 persistence predictor，与同一轨迹的 `dAtt_(k+1)` 比较。只纳入连续、有效的 100 Hz 推理事件；每个场景 1,967 个相邻事件对，共 72×1,967=141,624 对。分组统计先在场景内计算，再对场景等权宏平均；时间事件不是独立样本。

这里的 `R_actual,k` 是仿真 Plant 真姿态，`m_true` 是 Plant 真质量；这项诊断没有使用姿态估计器输出，也没有计入真实设备姿态估计与质量估计误差。因此报告中的 dAtt 是**离线 oracle 诊断量**，不是已验证的部署输入。干预会改变后续闭环状态和命令，所以持续性结果不能作为处理效应。

未来若筛查部署可用代理，可预登记
\[
\widehat{dAtt}_k=(\widehat R_k-R_{raw,k})e_3 T_{req,k}/m_{nom},
\]
其中 `R_hat` 必须来自实际可用、时间戳明确的姿态估计信号，`m_nom` 必须来自控制器可用的名义质量；`R_raw` 与 `T_req` 也须确认在事件时刻可读。当前仿真未验证这些输入契约。只有先锁定信号来源、延迟和误差界，再用该代理重算滞后持续性，才能判断 oracle 结果是否转移到可部署信号。真姿态与真质量仅可保留为离线标签/分层变量，不得进入模型或控制路径。

源码接口核验进一步限制了这一候选：R3 runner 直接把 Plant 状态 `x(k,7:9)` 拼入 X14（[`run_dl1018_closed_loop.m`](../../../experiments/paper14_v2_round3_xy_pcf_screen/runtime/run_dl1018_closed_loop.m)，第 1932–1935 行）；事件导出器也用 `x(7:9)` 填入 Euler 特征，并用它与 `Ptrue.mass` 重建离线 `dAtt`（[`export_position_events_dl1018.m`](../../../matlab/data/export_position_events_dl1018.m)，第 27–28、47–50 行）。所查 R3 runtime、`matlab/core` 与 `matlab/models` 没有发现输出姿态估计量 `R_hat` 的估计器接口。名义质量并非缺失：固定控制器参数 `P.mass` 来自配置质量，并已用于 X14 的 `previewThrust/P.mass`；但它不改变 `x(k,7:9)` 是 Plant 状态直接馈入的事实。因此当前闭环结果隐含理想全状态/姿态反馈假设，不是带姿态估计误差的仿真证据。若计划中的“Plant 真值仅用于离线”也禁止将真实姿态作为控制反馈，现有 X14 输入契约必须先解决；不能只靠新增 `dAtt_hat` 定义来满足该约束。未来筛查前须明确理想状态量是否按可用测量处理；若不允许，则需要另立有估计器接口、输入身份和相应训练/验证的新方案，本周期不得改写现有结果身份。

## X14 训练—部署输入血缘补充核验

为判断将 Euler 姿态换成估计姿态能否复用现有 DSSM14，只读核对了归档训练输入索引、G3 D4 cache 索引、全部 1,632 个 TRAIN/VAL 事件 H5 的根元数据与 `x14` 形状，以及相关数据管线源码；没有读取 H5 数值数组、任何原始 MAT 或 TEST。训练输入索引与 G3 cache 索引逐行按 raw、event-H5 和 cache 三个 SHA-256 完全对齐（1,632/1,632）；其中 1,536 行 TRAIN、96 行 VAL。全部 H5 都记录相同的 `DL1018_V311_R2E_PAPER_FINAL` 合同、`e_p_xyz_m, s_p_xyz_mps, euler_rpy_rad, nominal_thrust_mps2, arm_command_1_to_4` 特征顺序、与索引一致的 split/collector，以及 `(1999,14)` 的 X14 形状。TRAIN/VAL 字段仅大小写不同，按不区分大小写比较均匹配。

其中 1,094 个事件 H5 的文件 SHA 出现在 G3 源文件清单，具体为 1,088 个复用 H5 和 6 个 PILOT6 导入 H5；其余 538 行对应 522 个 G3 `RUN_PLANT` 事件和 16 个 `REUSE_FULL72_B_REBUILD_D2_D4` 重建事件。G3 冻结身份中 D2 exporter、H5 writer、D4 builder 的 SHA 均与当前项目源码一致。当前 exporter 直接将 Plant `x(7:9)` 写入 X14 的 Euler 槽；D4 builder 从事件 H5 读取 X14 并构造后续 X20，训练 loader 再将 X20 前 14 列作为 X14。DSSM14 训练身份为 seed `2026102001`、14 维、32 事件窗口、60,000 步；normalizer 只用 G3 TRAIN D4 cache，覆盖 1,536 个 episode、3,070,464 个事件行。

这条证据链支持“当前 checkpoint 训练和部署的 Euler 特征槽契约一致，且部署输入直接取理想 Plant Euler”的结论。边界是：本次只检查 H5 根元数据和 `x14` 形状，没有读取数值数组逐样本复算 Euler 值是否等于 Plant `x(7:9)`；H5 含合同版本与特征顺序，但不含逐文件 exporter 源码 SHA。因此对 1,088 个复用及 6 个 pilot 导入 H5，已核验文件身份与元数据契约，未证明其生产者与某个 exporter 字节版本逐文件密码学绑定。若把该槽改为 `R_hat`，语义/误差分布会变化，不能沿用旧 checkpoint 与 normalizer 作为同一输入身份；须在新授权周期冻结新特征数据并重新训练、验证。该核验不改变三轮筛查已耗尽、性能/理论门未通过及 TEST 封存状态。

## 结果

| 分组 | 场景数 | 一事件滞后向量 NRMSE（场景宏平均） | 配对向量余弦（场景宏平均） | 逐事件余弦为正比例（场景宏平均） | Z 轴相关（场景宏平均） |
|---|---:|---:|---:|---:|---:|
| 全部 VAL+DEV | 72 | 0.1091 | 0.9728 | 0.9944 | 0.9878 |
| W00–W08 | 38 | 0.0584 | 0.9914 | 0.9984 | 0.9965 |
| **W09–W14** | **28** | **0.1944** | **0.9420** | **0.9878** | **0.9734** |
| W15 | 6 | 0.0330 | 0.9982 | 0.9997 | 0.9993 |
| W09–W14 VAL | 18 | 0.1932 | 0.9421 | 0.9877 | 0.9738 |
| W09–W14 DEV | 10 | 0.1964 | 0.9418 | 0.9881 | 0.9727 |

高频组的滞后方向仍较稳定，但 oracle dAtt 的滞后误差高于低频和 W15；VAL 与 DEV 的描述性数值接近。它只支持“oracle 诊断量在下一事件仍有描述性持续性”，不证明可部署代理具有同等持续性。它**没有**验证加入该信号会降低位置误差；也不能把上一报告的 dAtt—下一块 Z-RMSE 观察性斜率解释成干预方向。

旋转几何界 `||dAtt_k||_2 <= 2 T_req,k / m_true` 在全部事件逐点通过。它只是信号幅值恒等式，不是滞后误差界、执行器余量或安全 `alpha` 界。现有数据没有给出可支撑一个固定补偿增益的状态不变域、安全余量或候选闭环轨迹。因此当前**不能冻结补偿增益，也不能放行新航次**。

## 身份与复现

输入为冻结的 corrected DSSM14 VAL48+DEV24；脚本核对机制清单、配对评分表和两份 frozen RAW_INDEX 的 SHA，逐条验证 72 个 raw 路径及 SHA，限制 split 只含 `VAL`、`DEV`，读前读后重新计算每个 raw SHA。72 个 raw SHA 均唯一，身份集合指纹为 `6225763db893447b748dbdf5f79cb7962bd6e7d1ce7265113a9486871c262a33`。没有打开任何 TEST 路径。

PowerShell 7 下的复现命令：

```powershell
python -B reports/paper14_v2/phase1/datt_lag_proxy_analysis.py
```

脚本 SHA256：`1732811c13952c4251551d655c2ae83b8939c5aba698232d74e6da67ef6c9e8f`。

| 产物 | SHA256 |
|---|---|
| 场景级结果 CSV | `af98a87087ddd31c2a828d410611bafe1cb47f64def8cdb5935cb6e3fcbf3f97` |
| 分组结果 CSV | `ef012bd56c69dc2a14485e4c463d2bfc1924da581ee8c8def9f4a3a7a9ff3635` |
| 输入身份与边界 metadata | `7b14dd6b17639df45f37a2d84e67b710ab0e336dde0b4d5d3fa6bbacfe4fffac` |

结果目录：`reports/paper14_v2/phase1/datt_lag_proxy_v1/`。报告不读取或复制 MAT，未生成新的闭环数据。该诊断不会解除三轮上限，也不改变当前 `NOT_QUALIFIED` 与 TEST48 封存状态。

## 独立审核与决策

独立只读复核未发现公式、事件配对或宏平均错误：Python Z 轴旋转公式与 MATLAB `export_position_events_dl1018.m` 一致，质量口径使用 Plant/controller 固定总质量；每场 1,968 个有效事件及 1,967 对相邻事件均满足 100 Hz 时序。复核者按场景 CSV 独立重算主要分组宏平均，结果与分组 CSV 一致；脚本及三个结果文件哈希与上表一致。

主模型另行复算了场景数、raw SHA 唯一性、VAL/DEV 边界、每场配对数和四个主要组 NRMSE，均通过。审核决定：接受为**描述性机制候选证据**，不接受为干预因果、安全、性能改善或论文资格证据；不据此批准闭环航次、固定增益或 TEST 解封。
