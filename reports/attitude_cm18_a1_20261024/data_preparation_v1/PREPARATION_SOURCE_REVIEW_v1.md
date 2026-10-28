# CM18 A1 数据准备源码静态审查

状态：**三份准备源码已静态审阅，等待主审核；未生成输入清单、未读取数值数据、未执行 MATLAB 导出。** 本报告不构成 TRAIN/VAL 数据合格结论。

| 文件 | SHA-256 | 本次核验 |
|---|---|---|
| `experiments/attitude_cm18_a1_20261024/prepare_input_manifest_v1.py` | `8be5a22a45192ab3651702067a95940317a5e8f26000e8e8d1b341ecc2113ba0` | Python AST 解析通过；11 个硬编码参考源 SHA 均为64位且与当前源文件实算值相符；脚本未执行 |
| `experiments/attitude_cm18_a1_20261024/export_cm18_events_v1.m` | `5264586d5e2120cdaf5f5cf6a42c07e21e1ed9afd244b92ef7a7f89bbedfc6d6` | 静态审阅；未运行 MATLAB |
| `experiments/attitude_cm18_a1_20261024/run_cm18_export_v1.m` | `ca2dd97ad636a65c0afb880da2f43fbd89fc260491264348659d26d49b42409b` | 静态审阅；未运行 MATLAB |

输入清单脚本固定枚举 `data/events/attitude/{train,val}/*/B.h5`，配对 `data/raw/{split}/{scene}/B/attempt_01/{raw_run.mat,run_start.mat}`，并要求 TRAIN=768、VAL=48。它流式计算输入和源码 SHA/字节数，不加载 H5 或 MAT 数组，不访问 TEST，不复制 raw。参考源 pin 包括共享的 `arm_mass_properties`, `distributed_mass_properties`, `arm_directions`, `simulation_parameters` 和 `controller_parameters` 等；这些 pin 只确认当前重标注依赖来源，不宣称恢复了旧 B 数据的原始生成器源码。若输入/源码在哈希期间变化或目标清单已存在，脚本拒绝发布/覆盖。

导出函数仅接受 fixed/full 配置，严格要求 20,000 条 transition、20,001 个 `0…20 s` 状态、1 ms 时间轴、1,999 个事件且 Plant 行为 11…19,991，规范事件间隔为10行，并要求 scene 时间、事件 flag、H5 索引/时刻、身份属性完全一致。四通道形态命令逐值限于 `{-1,0,1}`。特征顺序为 `[omega_B(3), alpha_BS(3), thrust/mass(1), u(4), z(4), a(3)]`：`alpha_BS=J0\(tau_nom-cross(omega,J0*omega)-Jdot0*omega)`；`u` 是当前事件命令；`z` 只积分当前事件之前的左端点命令；`a` 是前一完整区间 MATLAB 行 `k-10:k-1` 的请求力矩时间加权均值。旧 H5 的 omega、alpha_BS、thrust/mass 仅用于交叉检查，不进入特征。

标签用当前事件实际 realized torque、风矩、真实 omega 和共同 `arm_mass_properties` 离线计算的真实 J/Jdot，减去固定名义模型下 `tau_nom-applied_compensation` 对应的角加速度。另核验记录的 requested torque 与 `tau_nom-applied_compensation` 闭合，阈值为 `1e-8 N·m`。`J*alpha-forcing` 最大值的单位是 `N·m`，只作为线性方程求解残差且阈值为 `1e-12 N·m`，不是独立物理验证；标签重建的独立数据闭合门是相对 H5 `target_raw` 最大差不超过 `1e-8 rad/s^2`。不使用真实风、真实形态或速度差分作为部署输入。每场失败会由 `meta.qualified=false` 与失败原因显式标记，失败场不得进入拟合。

批处理默认 `SCREEN4`，逐 TRAIN/VAL split 选择字典序首个 C00/C01 场；只有显式 `ALL816` 才处理完整 TRAIN768+VAL48。逐场缓存为扁平 MATLAB v7 MAT：`X18` double `[1999,18]`，`target_raw` double `[1999,3]`、原尺度 `rad/s^2`，`event_time_s` double `[1999,1]`，`phase_code` uint8 `[1999,1]`，`plant_index` double `[1999,1]`，以及 `scene_id`、`split`、`input_identity`、`export_meta`。行 `q` 对应 1基 `plant_index(q)`；各数组同一行共享同一个事件。缓存不做输入/目标归一化；任何尺度必须由训练协议仅从 TRAIN 推导。SCREEN4 与 ALL816 各自生成 DATASET_MANIFEST，逐场列出缓存路径/SHA/字节数、合格标志、输入 SHA 和失败状态。ALL816 要求同一输入清单下 SCREEN4 四场均合格，并在全量清单中引用这四份缓存的原路径，不复制或覆盖它们；其余场单独写入 ALL816 目录。输出目录已存在时拒绝重跑覆盖，异常逐场留在进度/结果账本中。唯一缓存预算按事件数组与元数据保守估算并限制为1 GiB。

本次仅执行了 Python AST 和11个参考源的 SHA 静态核验；未调用 MATLAB，也未读取清单中的 raw/H5 输入。下一步需主审核通过后才可先导出四个 SCREEN4 场并检查逐场闭合；所有816场批次须显式调用 `ALL816`。当前无 Plant、runner、训练、缓存或 TEST 作业由本次执行启动。
