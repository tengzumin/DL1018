# 主审记录：GRU15 C5 教师 full72 离线训练放行

日期：2026-10-26。审核对象仅为一轮 60,000-step 离线训练。闭环、Plant 和 TEST 仍未授权。

## 审核结论

训练准备通过，可启动一次 GRU15 C5 教师 full72 开发训练。

批准后的 source lock SHA-256：`d169d6f6f83e127148f050f93f1d9994d3e3f2adbf8eb5753d0e4945bc42eb4e`。

- 数据 source lock 已通过：72 场、每场 1,999 事件，输入 `(72,1999,13)`，标签 `(72,1999,3)`；有序场景 ID、逐场 raw/status/run-start 身份、所选 NPZ 数组 SHA 全部与冻结 manifest 一致。
- 输入合同严格是 13 维 `wrapped attitude error ×3 + body rates ×3 + nominal BS torque ×3 + morph command ×4`。trainer 对 feature order 和禁止字段作硬校验；数据 manifest 记录 `inertia_config_read=false`、`plant_truth_read=false`、`TEST_accessed=false`。trainer 只索引六个 C5 数组，不读取 B24 成员。
- 监督标签沿用 C5 的 `rbf_output_raw`，单位 rad/s²，post-dmax / pre-beta；不将 RBF 权重、隐状态或 Plant 真值作为输入。
- 结构复用已 screened GRU15：单层、hidden size 32、15 个因果事件窗口、3 维输出。旧 screen 的 teacher-action RMSE 排名里 GRU15 为第三，MLP15 为第一；本次选 GRU 是为了单独检验序列状态是否有助于模仿 RBF 在线适应，属于有根据但尚未验证的假设，不声称它优于 MLP。
- 训练器与 full72 MLP 采用相同 72 场 C5 教师数据、seed `2026102001`、60,000 steps、batch 512、Adam/SmoothL1、训练集 normalizer 和仅发布 final step 的合同；模型差异仅为 GRU15 结构及其权重导出。CPU self-check 与锁定数据身份核验均 PASS。
- 训练不调用 Plant、不读取 TEST、不改动既有 MLP、raw 或基线。运行后仍须做独立 MATLAB parity；parity 通过后再另行审核闭环源锁和 release。

## 参数与结论范围

该训练不调 `max_tilt` 或其他闭环条件；其后的配对 pilot 暂按复用 B/C5_RBF 的锁定 C5 快照（`max_tilt=pi/6`）设计，以维持可比性。用户提及的其他限幅设置尚未在当前锁定快照/工作区配置中找到，启动 Plant 前需先核实并统一所有臂的配置。

训练数据是开发教师数据，不构成独立测试。即使训练、parity 和六场 GHP7 pilot 均通过，也不能声称跨任务泛化、TEST 通过或论文结果达标。
