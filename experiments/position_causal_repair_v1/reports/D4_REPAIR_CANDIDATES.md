# D4 修复候选训练与选择

## 控制组与候选

C0 复用 G05 Final：训练协议、TRAIN/VAL 角色与权重、X14 N_KAN、Initial warm start、优化器、预算、stride 和 756,480/56,736 计数均一致；G05 的 MATLAB 导出 parity 为 PASS。D3 使用的 selected 与 G05 Final 包的 `best_model.pt` SHA-256 完全相同（`3836ed75a19bfff549cac197465c63b22b289cdbdef33c119344554837309017`），normalizer SHA-256 也完全相同（`619a343fc73b707c0b2f640f4a261e81ee779e1351d67e4e4af243cc489ce0ab`）；D3 另有六场同 cfg 的实际桥接。C0 的 VAL 固定头分数为 **0.289300 m/s²**。

C1 两个 seed 均从 DL1018 Initial X14 初始化，只新增 `v_I_xyz` 与 `a_nom_xyz` 六列；原 14 列归一化保留，新列统计仅来自 TRAIN。训练前 X20 的 φ 和输出与 X14 最大差均为 0。固定头 VAL 分数按冻结规则选 epoch。

| Candidate | Seed | Best epoch | TRAIN/VAL windows | Optimizer steps | Endpoint exposures | Fixed VAL (m/s²) | Adaptive VAL (m/s²) |
|---|---:|---:|---:|---:|---:|---:|---:|
| C0 reused G05 Final | 2026101802 | 12 | 756480 / 56736 | 59100 (historical 20 epochs) | 15129600 | 0.289300 | n/a |
| C1 X20 fixed | 2026101901 | 9 | 756480 / 56736 | 50235 | 12860160 | 0.272568 | n/a |
| C1 X20 fixed | 2026101902 | 10 | 756480 / 56736 | 53190 | 13616640 | 0.273048 | n/a |
| C2 X14 adaptation-aware | 2026101901 | 24 | 756480 / 56736 | 61440 | 24207360 | 0.348006 | 0.288226 |
| C2 X14 adaptation-aware | 2026101902 | 33 | 756480 / 56736 | 78720 | 31015680 | 0.347174 | 0.287701 |

C2 每条 TRAIN episode 的 W 从共享可学习 W0 重置；每条 1,968 个 ready 事件均按原 100Hz 递推，stride 5 只抽稀损失端点。C2 训练目标是**记录轨迹上的适应导向训练**，不是完整可微闭环。两个 seed 的递推投影回退数均为 0。固定 W0 与适应后分数分开列出，依任务书仅用适应 VAL 选择 C2 epoch。

| Candidate | Seed | Best epoch | Optimizer steps | Loss endpoint exposures | Recurrence event exposures | Fixed W0 VAL | Adaptive VAL | Projection fallback sequences |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C2 | 2026101901 | 24 | 61440 | 24207360 | 120913920 | 0.348006 | 0.288226 | 0 |
| C2 | 2026101902 | 33 | 78720 | 31015680 | 154920960 | 0.347174 | 0.287701 | 0 |

## 冻结选择及解释边界

- 预定飞行 seed 为 2026101901；2026101902 只做方向复核，不因结果更好而替换。
- C1 seed1 固定 VAL 0.272568，seed2 0.273048，方向一致；相对 C0 的同口径 VAL 有改善，支持进入 D5，但不能据离线分数宣称闭环改善。
- C2 seed1/seed2 的适应 VAL 分别为 0.288226 / 0.287701；C2 固定 W0 分别为 0.348006 / 0.347174。两个 seed 适应分数方向一致；固定 W0 与适应分数、C1/C0 与 C2 的不同目标不能混作同一指标排名。
- 因 D2 的 early-ridge 只在记录轨迹上显示可适应余地、且 D3 确认 Final 相比 Initial 有同场收益但仍输 B，本轮以 C1（增加合法状态/名义输入）与 C2（对齐在线递推目标）作为两个最小干预送零 Plant 部署检查。
- C0 直接复用 D3 的六场 Final P_A 结果；身份/配置由 D3 预检验证，不能把 G05 离线分数当作 D5。
- 新 fit=4/6 预算；D4 新 Plant=0。D5 预登记候选按冻结顺序为 C2 seed 2026101901、再 C1 seed 2026101901；每个只跑固定 BRIDGE6。C0 复用 D3，不新增 Plant。
- 训练按 CUDA 确定性算法运行，`CUBLAS_WORKSPACE_CONFIG=:4096:8`；第一轮遇到环境缺项时 fit 尚未登记/未训练，补齐后同一身份启动。所有最终 fit 均 COMPLETE，无重训身份。

源数据、原 G06、原选模及原始模型包未修改；G06 仍为 `STOP_POSITION_NOT_QUALIFIED`。
