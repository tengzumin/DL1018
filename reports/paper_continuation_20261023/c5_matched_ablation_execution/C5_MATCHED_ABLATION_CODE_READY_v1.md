# C5 配对消融 CODE_READY

清单 SHA-256：`946a9c10120524dafe43f8c415765c40d00cbcafaf019fdbe50468932f5c111e`。本交付只封存实现和输入；无 MATLAB/Plant 授权，当前未启动 MATLAB。

同一 runner 仅接受三个明确入口：`PREFLIGHT_ONLY_C5_MATCHED_ABLATION_V1`（完整无Plant预检，并在共享锁/episode前返回）、`PARENT_APPROVED_C5_ABLATION_FIRST_V1`（需独立首场release）、`PARENT_APPROVED_C5_ABLATION_TAIL11_V1`（需独立尾11 release并核验同配置首场raw/status）。尾批仍沿原12场顺序排除已审首场。

两个配置各有独立输入锁、合同、source binding、helper、fixture及PS入口；core/wrapper逐字等于冻结C5。source binding每项69个引用已逐SHA核验。helper差异见 `C5_ABLATION_HELPER_DIFF_v2.patch`。

无Plant执行命令（每次单独运行一个配置）：

- `C5_FREEZE_TRAINED_W0`：`& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_c5_matched_ablations_20261023/C5_FREEZE_TRAINED_W0/RUN_C5_ABLATION_NOPLANT_EXACT_v1.ps1'`。脚本内部顺序为合成MATLAB检查 → prepare → 同一runner的 `run_c5_matched_ablation_v1('PREFLIGHT_ONLY_C5_MATCHED_ABLATION_V1')`，并写实际MATLAB OS退出码。
  lock `7c76ad797bab9aefa7cfb8b13031afc9e98c2f0082805f301659382164a59582`；run contract `15b175a440378e56b94893f491215eafc440ed2078eab37f4134c08e92402545`；source binding `552470ddec1a383e0e5b0e80d09c92f7fe13c66c83200fae189cbbb7802b326c`；runner `9467fc8be27066b37d94b0a8cc5bd7156d580329d29c58cd273cae40e8ae1e68`。
- `C5_NO_DELAYED_PREDICTION`：`& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_c5_matched_ablations_20261023/C5_NO_DELAYED_PREDICTION/RUN_C5_ABLATION_NOPLANT_EXACT_v1.ps1'`。脚本内部顺序为合成MATLAB检查 → prepare → 同一runner的 `run_c5_matched_ablation_v1('PREFLIGHT_ONLY_C5_MATCHED_ABLATION_V1')`，并写实际MATLAB OS退出码。
  lock `591630ad1fa27f8f7e4486b8a04bcbffa8ece5ebc63f16d2a4deff1141a8d554`；run contract `f7a2fc8e5b00adc901ca860387b73deb24127a47423ce216b17ca25e8462f033`；source binding `32a5e0b1d3426f04dd41b557a6c6804ffa1140d4ce32759a8531bd5bc6b2b07e`；runner `9467fc8be27066b37d94b0a8cc5bd7156d580329d29c58cd273cae40e8ae1e68`。

实际首场/尾场入口分别绑定阶段专属 parent release；launcher 已纳入source binding，未创建release，也未运行。freeze正式raw的runner检查1968事件before/after精确等于trained W0；no-pred正式raw检查所有已记录延迟预测项范数为0。两种配置都要求每场重置到冻结W0。
