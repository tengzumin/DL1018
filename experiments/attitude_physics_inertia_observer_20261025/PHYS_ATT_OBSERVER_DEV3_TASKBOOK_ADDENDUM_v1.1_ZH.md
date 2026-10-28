# DEV3 任务书 v1.1 补充条款

日期：2026-10-25。只修订 [v1 任务书](PHYS_ATT_OBSERVER_DEV3_TASKBOOK_v1_ZH.md) 的合成检查与执行放行顺序；不授权当前实施或运行。

## 放行顺序与运行身份

1. 主审先批准隔离实现和纯合成测试；此批准仅覆盖这两项，不包含任何 Plant/闭环航次。
2. 实现完成后只运行任务书规定的无 Plant 合成测试及必要的接口检查。通过后生成完整且不可变的 `source_lock_v1.json`，锁定 runner/调用链全部源码（含候选实现）、MATLAB/依赖版本、有效配置、三场 scene 数据、两臂选项、模型/权重工件与随机种子，并为每项记录规范路径和 SHA-256。不得先跑闭环再补锁。
3. 主审审阅并冻结该 source lock 后，须另行批准六个 fresh closed-loop runs；未获该次批准不得启动。
4. 每个 baseline/candidate `run_start.json` 都记录相同的 `runner_sha`、`source_lock_sha`、`scene_sha`、`effective_config_sha`、`common_options_sha`、seed 和场景 ID，同时记录本臂 `effective_options_sha`、控制器/RBF 工件 SHA 与 `arm`。两臂除预注册处理差异外的有效选项必须一致：baseline 启用 attitude RBF 输出/更新；candidate 禁用二者并启用候选。按规范化后的选项逐项比较，任何额外差异或锁不一致即停。六次运行均使用锁内同一个 runner；不得复用缺少该身份绑定的旧 baseline。

## 加强后的无 Plant 合成检查

测试须调用现有 `attitude_bs_step(state,reference,estimateTorque,P0)` 接口，而非只验证力矩代数恒等式。用非对角 SPD `J0`、轴分量不同且正负混合的 `omega`、`alphaBS`、`dhat_tau`，令 `P0.inertia=J0` 且 BS 惯量导数项为零；从 `info.nominal_body_angular_acceleration` 取 `alphaBS`，计算 `Mnom` 与任务书定义的 `tau_shape`。在不触发 clip 的样例中令 `beta=1`，分别测试零扰动/零估计和已知非零合扰动/精确估计：设置 `tau_comp=tau_shape-dhat_tau`、传入 `estimateTorque=-tau_comp`，断言接口输出严格为 `Mnom+tau_comp`，再用合成刚体方程

```text
alpha = Jhat \ (tau_command + d_true
                 - omega × (Jhat*omega) - Jdothat*omega)
```

验证 `Jtrue=Jhat`、`Jdottrue=Jdothat` 时，`d_true=dhat_tau` 得 `alpha=alphaBS`；零扰动时同样成立。再故意令 `d_true≠dhat_tau`，核对 `alpha-alphaBS=Jhat\(d_true-dhat_tau)`，以证实符号。逐轴断言向量和限幅坐标，不能只比范数，以发现 x/y/z 置换或正负号错误。另行覆盖 `beta<1` 与 acceleration-equivalent clip 的坐标变换；这些截断场景不要求 `alpha=alphaBS`，只核对实际传入力矩与公式一致。全部采用人工矩阵/向量，无 Plant、真值参数、scene 或运行日志。

合成动力学方程中的 `tau_command` 指 `attitude_bs_step` 返回的力矩，并明确假设理想合成执行器 `tau_act=tau_command`；该项只查控制接口与刚体符号，不覆盖 C0 分配、电机饱和或真实 actuator mismatch。

任一接口符号、轴序、合成动力学、单位、时戳、因果或有限性断言失败即停止，不生成可供运行的冻结锁，也不启动 DEV。通过只说明合成闭环方程和接口一致；不证明 observer 收敛、闭环稳定、ISS、硬件表现或 TEST 泛化。
