# MLP15 C5-RBF 全量教师重训任务书 v1

**状态：主模型已审核并放行一次全量开发训练；闭环仍未放行。** 本实验把同任务四架构离线 screen 已入围的 MLP15，用于一次 C5-RBF 教师全量开发重训。screen 只用于架构预选，不作为闭环证据。

## 冻结的数据身份

- 只复用 `mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz` 中的 `c5_train_x/y` 与 `c5_val_x/y`，按冻结 `DATASET_MANIFEST_v1.json` 的 split 内顺序拼成72场。教师源均为 `C5_RBF`；每场1999个事件，输入形状为 `13`，目标形状为 `3`，合计143,928个唯一教师事件。
- 13维输入白名单固定为：3维 wrapped attitude error、3维 body rates、3维 nominal BS torque、4维 morph command。wrapped error 使用 `atan2(sin(reference − Euler), cos(reference − Euler))`。输入不包含 `Jhat/Jdot_hat`、惯量或质量属性、Plant truth、RBF权重/隐状态、observer 或 physical feedforward；训练脚本会拒绝任何偏离冻结 feature order 的 source lock/manifest。
- `C5_VAL48` 已参与此前 C5-24 checkpoint 选择和动作比较。本次把这48场并入开发训练数据，作为 `C5_VAL48_AS_DEV_TRAIN`；它不再是 independent VAL，也不参与本次 checkpoint 选择。
- 该 NPZ 同时包含 B24 成员，但训练脚本只索引上面六个 C5 数组/scene-ID 成员，不读取 B24 数组值。TEST48 不读取、不哈希、不进入清单。不得重跑 B、C5 或 Plant，也不得修改旧产物。
- 独立评估只能使用封存 TEST，或另行生成的新场景；TEST 仍需单独授权。当前包不授权任何闭环调用。

## 单臂训练合同

- MLP15：13输入、15事件因果窗口、隐藏层 `[64, 32]`、SiLU、3输出；监督目标为 `rbf_output_raw`（post-DMAX/pre-beta，rad/s²）。
- 只用这72场拟合输入均值/标准差和目标逐轴 RMS；seed `2026102001`；Adam，lr `1e-3`，weight decay `1e-5`；batch 512；SmoothL1 beta 1.0；固定60,000 optimizer steps。
- 只发布 `final_step_60000`。关闭 VAL、checkpoint selection 和中途模型发布。训练损失按每1000步记录，供审计训练过程，不用于选择模型或步数。
- 全部训练事件共143,928个唯一样本；60,000×512=30,720,000次 batch 样本抽取（有放回）。这不是额外的唯一数据量。

## 数据量边界与结论范围

当前可复用的完整 C5 教师轨迹为72场/143,928事件。旧 C5 位置 DSSM14 训练量为1,536 episodes/605,184 windows；本实验场景数约为其4.69%，窗口/事件数约为23.78%。因此它是当前 C5 姿态教师数据的全量开发重训，但仍显著小于 C5 位置 DSSM14 数据规模。不得称为与该 C5 大数据同量、泛化验证、独立测试通过或论文通过。

## 审阅门与交付物

source lock 当前为 `PREPARED_PENDING_ROOT_REVIEW`，训练脚本会拒绝启动。root 审核任务书、锁文件和 trainer 后，须在 source lock 填写唯一的 root release（`approved=true`、`authorized_jobs=1`、`approved_by`、`approval_reference`），然后才可运行一次；固定输出目录已存在时脚本拒绝再次运行。

```powershell
python .\experiments\dl_attitude_replacement_20261026\mlp15_c5_teacher_full72_v1\self_check_mlp15_c5_full72_v1.py
python .\experiments\dl_attitude_replacement_20261026\mlp15_c5_teacher_full72_v1\train_mlp15_c5_full72_v1.py --device auto
```

第二条命令仅在 root 更新并批准 source lock 后可运行；本准备阶段不执行它。训练后固定输出目录只应包含最终 step checkpoint、MATLAB权重、72场 normalizer、parity fixture、training history/progress/config 和 receipt；receipt 记录所有输入文件、72场 raw/status/run-start 哈希及所有输出哈希。
