> **状态横幅：未审批 / 已取代 / 未执行 / 不得运行。请勿执行旧稿；请改用 `C5_CM18_FIT_GENERALIZATION_TASKBOOK_v1_ZH.md`。**
# C5 停止后的 CM18 离线可辨识性诊断任务书 v1

状态：待审核。本文只授权准备并执行下述离线诊断；**不授权修改现有代码、训练任何模型、调用 Plant、启动航次、读取 TEST 或推进闭环**。诊断输出不得自动触发训练、闭环或 TEST。

## 背景与问题边界

C5_COVERAGE33 的 15 场 DEV 闭环没有达到既定门槛，静态映射路线已按原任务书停止。闭环 raw 按冻结方程可重建 `Cstar/beta`，并与对应事件输入、CM18 输出和力矩应用闭合到机器精度；首次形变时模型误差已经出现在教师状态。现有全时域候选与教师状态残差相近，但 X18 邻域稀疏且跨相位混杂，尚不能据此声称条件混叠已证实。

X18 的固定顺序为 `omega_B(3), alpha_BS(3), thrust/mass(1), u(4), z(4), a(3)`。它没有显式 `rho/rhoDot/phase`；物理标签由实际形态惯量、惯量变化、实现力矩和风力矩共同决定。本诊断只检验：在固定数据、固定近邻规则下，用 X18 与“可由现有部署状态得到的最小形态估计”分别预测同一直接物理标签时，预测误差与同相位局部标签离散度是否有稳定差异。结果只说明本数据覆盖和本固定估计器下的预测信息，不给出因果结论，也不证明未知风力矩可被形态状态替代。

## 数据范围与身份

仅用下列既有材料，不发现、补入或替换场景：

- 33 个 TRAIN 场景的事件缓存：原 24 个 `C5 TRAIN24` 缓存，加 coverage33 任务书列出的 9 个 `TRAIN_EXTRA` 缓存。每场仅用事件 ordinal `0,5,...,1995`，共 400 行/场、13,200 行。逐文件路径、SHA-256、scene ID 和行图以 `experiments/attitude_cm18_c524_coverage33_20261025/data/C524_COVERAGE33_RELABEL_MANIFEST_v1.json` 为准；该文件 SHA-256 为 `7d6a7d079d32120849cee62eadecd8e69a68d5a538608dd8959849ac5fe2dd8c`。其 24 个原始 TRAIN 缓存继承 `reports/attitude_cm18_datarepair_20261024/ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json`，SHA-256 `88d7312087025a331dd532410b0ef31ed2dcb7dd3175239ad1d47bc68dd65f0b`。
- 15 个 DEV 候选输出 raw：使用闭环 binding v3 的 scene 顺序及各自官方 scene audit 记载的 `candidate_raw_path`、`candidate_raw_sha256`。binding `experiments/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_CLOSED_LOOP_BINDING_v3.json` SHA-256 `87ac859a29488d66f87330a7f0060183fb9a3e07178244677db28cbd8a527ee8`；模型、训练和数据身份也须与 binding 及审计相符。

| DEV scene ID | 候选 raw 相对路径 | SHA-256 |
|---|---|---|
| `DL1018_DEV_T2_C02_W15` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T2_C02_W15/attempt_01/raw_run.mat` | `d226bba3afc065aaa5b64a93f5f348dc33a705a5706a81ddb20dafa30fbbedbe` |
| `DL1018_DEV_T3_C03_W15` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T3_C03_W15/attempt_01/raw_run.mat` | `824e419a7a0c9a4385f32a4eeaf4d481a65da28193cb87800120bca961e60572` |
| `DL1018_DEV_T1_C04_W00` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T1_C04_W00/attempt_01/raw_run.mat` | `88d6e292dd7d2a86b0b5bed9dda192c3106fbc1486606d8944a197c83e1d2a71` |
| `DL1018_DEV_T1_C07_W08` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T1_C07_W08/attempt_01/raw_run.mat` | `9f5ef56e35fcc98321e0a24268300f73567f34971bf78d8cdf5cac3cf37e8107` |
| `DL1018_DEV_T1_C10_W09` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T1_C10_W09/attempt_01/raw_run.mat` | `539dedf229c0004c8ba7602ee4104b37c20e2137af688eebd44fadde9472a8e4` |
| `DL1018_DEV_T1_C11_W12` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T1_C11_W12/attempt_01/raw_run.mat` | `d7f420eb2070efe7ef881a09f160e4b2d2faaf24b26d5c6fc18a531704fba506` |
| `DL1018_DEV_T2_C03_W01` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T2_C03_W01/attempt_01/raw_run.mat` | `dcf968ca9aaf879d43feabbdd454b05ac927e0b18f1604d3da0de26a36f778e4` |
| `DL1018_DEV_T2_C08_W08` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T2_C08_W08/attempt_01/raw_run.mat` | `58e0a5ba13105c19fe5cfbae27b665419df0dd97eee6ad0510622e39c509f68c` |
| `DL1018_DEV_T2_C09_W10` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T2_C09_W10/attempt_01/raw_run.mat` | `b67c5cebddc6077d925b9ddc043fceb777a6868b6bfe5566272935e45e54f985` |
| `DL1018_DEV_T2_C12_W13` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T2_C12_W13/attempt_01/raw_run.mat` | `374e9eb0b274c7ab70a3da35cd3a93325b4accc9957a6ddf243ac85e14e216d4` |
| `DL1018_DEV_T2_C14_W14` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T2_C14_W14/attempt_01/raw_run.mat` | `5fd2004d217b680ddce0c5af8eabbaaf67fdf511cea0b5f3c81a2420c7916617` |
| `DL1018_DEV_T3_C06_W08` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T3_C06_W08/attempt_01/raw_run.mat` | `1ee0e17aa3a8d2afb5b8b4a35eb0a99a32ad5a1da29db5311dbff08027a4e922` |
| `DL1018_DEV_T3_C09_W09` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T3_C09_W09/attempt_01/raw_run.mat` | `a7ae7f363bc7c5497e0b86e2f9ea71b591c8cbe16b9a0292093d0c25c25a5e2c` |
| `DL1018_DEV_T3_C10_W11` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T3_C10_W11/attempt_01/raw_run.mat` | `4f4d5821e566969d25117813d94cb941c16d8fc07d69009eaf324b032bf07b68` |
| `DL1018_DEV_T3_C13_W12` | `experiments/attitude_cm18_c524_coverage33_20261025/runs/DL1018_DEV_T3_C13_W12/attempt_01/raw_run.mat` | `7039cb6795826804dd242b7cca1a28756b23ab4cb824bf71f21265855fe2b673` |

15 个场景也是 DEV 开发候选，且已用于本轮闭环门槛判断；不得称为独立测试、统计独立样本或论文最终测试。`C5_VAL48` 不在本任务输入内。任何 TEST 样本、缓存、raw、指标或身份材料均不得访问。

## 特征和标签

共同标签统一为直接物理目标 `target_raw_output_rad_s2 = Cstar / beta`，不是旧 behavior-residual 标签。对 15 个候选 raw，按已冻结 `relabel_c524_coverage33_v1.m` 与 `extract_cm18_events_v1.m` 的相同定义重建：

1. 按固定 `cfg`、实现力矩、记录风力矩、实际 `rho_true/rhoDot_true`、真实角速度重算真实刚体角加速度及固定名义模型角加速度残差 `E0`。
2. 对每个 canonical attitude event，使用该 event 的 `G` 解 `Cstar = G \ E0`；`beta = min(k*dt/betaRise, 1)`；标签为 `Cstar/beta`。另核 `beta*clip(label, -dmax, dmax)` 与 raw 中实际 applied acceleration/torque 的闭合。
3. 核 1,999 个事件及时间索引、`requested_generalized` 与名义减补偿请求力矩闭合，以及 raw 中记录的 X18、事件输出和 model output 关联。逐场保留最大绝对误差。

两个输入组只差是否显式提供形态估计：

- `G_X18`：冻结顺序的 18 维 X18。
- `G_MORPH`：X18 中去掉 `u(4),z(4)` 后，使用 `omega(3), alpha_BS(3), thrust/mass(1), rho_hat(4), rhoDot_hat(4), a(3)`，共 18 维。`rho_hat/rhoDot_hat` 必须是当前事件可部署的估计量；不许用 `rho_true/rhoDot_true`、风力矩、target 或 `phase_code` 作为输入。相位仅用于分层诊断。

TRAIN 缓存不直接含 `rho_hat/rhoDot_hat`。执行前必须只从现有冻结 C5 源定义与缓存中的 `u,z` 确定一个无参数拟合、因果、逐事件的确定性重建式，并在 15 个候选 raw 中与同事件记录的 `rho_hat/rhoDot_hat` 对照。不得从 DEV 标签拟合映射或回看 TRAIN raw。若现有冻结源无法唯一确定该重建式，或任一 raw 的状态重建最大绝对误差超过 `1e-8`（形态 m、形态速率 m/s），立即停止并报告“TRAIN 可部署形态特征不可从授权缓存恢复”；不得退回真实状态 oracle。

## 固定 scene-blocked 估计与统计

不训练、不拟合模型参数、不做超参数搜索。只使用固定的 5-scene nearest-neighbor 平均作为诊断预测器：对每个查询事件，从 TRAIN 参考场景中分别取每场最近的事件，再选距离最近的 5 个不同场景；五个邻场景等权平均其三轴标签。每次比较均复用相同事件集合、同样场景权重和相同邻居数。

对 TRAIN 做 33 折 leave-one-scene-out：查询场景的 400 行不进入参考集；其余 32 场作为参考。DEV 阶段用全部 33 TRAIN 场的 400 行作为参考，按 binding 顺序评估 15 个候选 raw 的全部 1,999 个事件。事件不跨场景拆分；不得随机按行切分。

距离规则固定：`G_X18` 的 18 项用共同冻结 normalizer（`experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json`，文件 SHA-256 `23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781`，canonical SHA-256 `12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a`）。`G_MORPH` 的共同 `omega/alpha_BS/thrust-mass/a` 十维沿用 X18 中对应列的同一 mean/std；`rho_hat` 四维按 cfg 允许的 0.10 m 行程归一化，`rhoDot_hat` 四维按冻结指令最大速率归一化。距离为归一化逐维均方根欧氏距离。不得从 DEV 统计量重新归一化。若 cfg 的行程/速率与上述物理尺度不符，停止并报告，不改尺度。

主预测指标为每场三轴合并、TRAIN 逐轴 RMS 标准化的事件 RMSE；先算每场 RMSE，再对场景等权平均。报告 G_MORPH 相对 G_X18 的宏平均变化、逐场差和胜/负/平场数。TRAIN 33 场也按逐场指标等权汇总。不得按事件数汇总成一个总 RMSE 作为主结论。

条件离散度只在**同一 phase_code** 中计算：对每个 DEV 事件分别用 G_X18 和 G_MORPH 找到五个不同 TRAIN 场景的最近同相位邻居，计算邻居标签相对五场等权均值的三轴 TRAIN-RMS 标准化离散度。phase 不进入估计输入或部署提案。报告每相位有支持的 DEV 场景数、覆盖事件数、第五邻居距离、标签离散度与形态输入变化。若某查询缺少五个有同相位事件的 TRAIN 场景则标为不支持，不能补位或跨相位借邻居。

## 明确决策门槛

所有门槛在分析前固定，不能根据结果改阈值：

1. **身份/闭合门**：33 个 TRAIN cache 的文件哈希、scene ID、400 行索引、row map SHA 与 TRAINING_RELEASE 一致；15 个 DEV raw 与官方 audit 的路径和哈希一致；15 场事件数均为 1,999；重建标签和执行闭合最大绝对误差均 `<=1e-8`。任一不满足即 `STOP_IDENTITY_OR_CLOSURE`，不继续统计。
2. **支撑门**：15 场中至少 12 场在 phase-conditioned 分析中有至少 80% 事件能找到五个同相位 TRAIN 场景；否则结果为 `STOP_INSUFFICIENT_SUPPORT`，不得声称条件混叠被确认或被排除。
3. **继续到单独审核的下一份离线设计草案**：支撑门通过，且 G_MORPH 的 DEV 场景等权标签 RMSE 至少比 G_X18 低 20%，至少 10/15 个场景逐场改善；phase-conditioned 标签离散度宏平均至少低 20%，TRAIN 的 LOSO 宏平均标签 RMSE 方向也改善。该决定只表示可继续讨论一个独立的、仍限 DEV 的后续设计；不放行训练、闭环、Plant 或 TEST。
4. **停止当前形态补充假设**：支撑门通过但上述任一效果门未通过，结论为 `STOP_NO_ROBUST_MORPH_GAIN`。仍需写明“本固定近邻诊断未显示达到预登记效应门槛”，不能写成“形态无用”或“已排除条件混叠”。若 X18 的同相位邻居离散度并未显示实际标签散布，结论须为“没有足够证据确认条件混叠”。

15 场无论统计结果如何始终是 DEV 开发证据。不得据此申请自动扩展闭环或 TEST。若未来决定把这 15 场任一标签/raw 用于训练，必须另建新的 DEV 开发验证集，继续完整保留 TEST，并另立任务书。

## 复现命令与输出

命令从仓库根目录、PowerShell 7、现有 Python 环境运行；实现脚本需先单独提交审核。本任务书本身不创建或执行脚本。审核通过实现后，固定调用为：

```powershell
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
python -B reports/attitude_cm18_c524_coverage33_20261025/offline_identifiability_v1/run_cm18_offline_identifiability_v1.py `
  --taskbook reports/attitude_cm18_c524_coverage33_20261025/C5_CM18_OFFLINE_IDENTIFIABILITY_TASKBOOK_v1_ZH.md `
  --train-release reports/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_TRAINING_RELEASE_v1.json `
  --relabel-manifest experiments/attitude_cm18_c524_coverage33_20261025/data/C524_COVERAGE33_RELABEL_MANIFEST_v1.json `
  --closed-loop-binding experiments/attitude_cm18_c524_coverage33_20261025/C5_COVERAGE33_CLOSED_LOOP_BINDING_v3.json `
  --audit-dir reports/attitude_cm18_c524_coverage33_20261025/scene_audits `
  --output-dir reports/attitude_cm18_c524_coverage33_20261025/offline_identifiability_v1
```

实现须先只做身份/字段 preflight；所有身份和映射前提通过后才可读取数值做上述离线近邻计算。仅写 `reports/attitude_cm18_c524_coverage33_20261025/offline_identifiability_v1/`；保存脚本 SHA、精确命令、输入路径/哈希、逐场/逐 phase 支撑数、输出指标、闭合误差、结论枚举和 `TEST_accessed=false` 声明。报告使用现有 cache/raw 与审计 JSON，不复制 raw，不写入 experiments，不修改任何已有文件。

## 最终交付与停机

输出逐场 CSV/JSON、总报告、复现回执和源文件哈希。报告必须展示 TRAIN LOSO 与 15 场 DEV 结果分开统计，按场景等权；phase 分层只用于诊断并披露缺支持场景。只允许给出上面四种门槛结论及证据边界。完成即停，等待主审核是否另写后续任务书；不把诊断结论转换为任何自动执行权限。

