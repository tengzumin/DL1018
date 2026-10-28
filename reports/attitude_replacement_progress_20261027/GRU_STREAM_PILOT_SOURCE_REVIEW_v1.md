# GRU_STREAM pilot source review (snapshot)

## 结论

当前已冻结的 58 个 `.m` candidate source 未发现首场前的实质控制阻断。审查仅静态读取；未启动 Plant、训练或 TEST。首场任务书保留单场先审、通过后才扩其余五场，沿用 B/C5 和原 Q/SO(3)/inner 指标及 `1.10×C5` Q cap；无调参、Jhat、真实惯量重建或成功即论文达标的主张。

## 核验点

- `SOURCE_LOCK_v1.json` SHA-256 `c97c7c9d6f4acf525cb40c7a53e77a42b8865a7a81f8a800e35bde3ada4bc1e1`；逐文件复核 58/58 个 `.m` 当前 SHA，0 mismatch。`SOURCE_DIFF_v1.json` SHA `22733e39903ae76f54815b71773db719496e91664f9080e532788211e5d525ba` 声明仅 3 个 runtime 文件修改、2 个 stream helper 新增，generic gate 与源版字节相同。
- GRU helper 用 reset/update/new 门序推进一条当前 13 维特征并返回当前 hidden（`gru_stream_attitude_forward_v1.m:24–35`）；step 归一化后执行 `dmax → beta → fixed J0` 一次并推进 event count（`gru_stream_attitude_step_v1.m:33–46`）。实际 DEV 在场开始初始化零 hidden（`run_mlp15_dev72_closed_loop.m:1084–1089`），事件时从当前误差、角速度、BS nominal torque、arm command 构造特征，只在事件上更新状态和 torque，非事件保持上一 torque（`:2498–2525`）；当拍 torque 送入 `attitude_bs_step`，其控制矩为 `nominalMoment - estimateTorque`（engine `:2757–2764`；`attitude_bs_step.m:39–42`）。
- GRU arm spec 关闭 RBF、physics helper、feedforward、observer（`gate_attitude_arm_spec.m:14–16`）；运行身份/trace 写明 frozen weights、RBF off、无变量惯量重建（engine `:3186–3193`）。GRU 特征不读 Jhat/Plant 真值；engine 的通用 Plant/残差诊断路径不作为 GRU 输入或其补偿项。
- 训练模型实际 SHA 与冻结任务书一致：`963f7d994e881ac01b4b6d0c713f56ddd9e8d28efb19c800d0a130c781366021`。训练模型 Python/MATLAB 全序列 parity 报告均为 1999 事件；double 输出最大差 `3.66e-15`、全 hidden 轨迹 `4.44e-16`；MATLAB double 对 trainer float32 输出/hidden 差 `4.83e-6` / `8.58e-7`，均在预设门限内。no-Plant 报告核实实际 C5 cfg、`[Inf Inf 6]`、fixed J0、BS Jdot0=0、实际 `which` 路径与 release0 两入口拒绝，并确认没有建 run 目录。
- raw auditor 的事件重放预期与 engine trace 对齐：1999 events、20001 state samples、20000 transitions；独立重建当前特征、β、hidden carry、非事件 torque hold，并核对 `requested_generalized = nominal torque - applied compensation`（`audit_gru_stream_raw.m:41–80`）。本次未运行 raw auditor 或 Plant。

## 当前 release 快照

当前 `RELEASE.json` 仍是 `PREPARED_ROOT_REVIEW_REQUIRED`，授权 Plant calls 为 0。不要签这个未刷新版本：它的 driver SHA 是 `8b8c23…`，而当前 `run_gru_stream_dev_attempt.m` SHA 为 `6f11d97237839ec167164837843774d3786a8f70eebe1fcbbac091091c564fd4`；no-Plant、toy MATLAB parity、trained MATLAB parity SHA 字段仍为 pending。源码和控制分支结论不受此封账待办影响；签首场前需 writer 刷新 release 锁值，再由主审复核。
