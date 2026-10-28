# CM18 runtime SOURCE_PREP 交接

状态：仅完成隔离源码准备。没有调用 `run_cm18_closed_loop_v1`，没有推进 episode/状态，没有启动 Plant、训练或 optimizer；没有运行 SCREEN4 replay。正式权重尚未绑定，后续 replay 命令等待 ROOT 审核。

## 源码身份与父子关系

- 父引擎：`experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m`，SHA256 `48350037B66EFE00301B138068F187C62CF92583F0F9BA2FABC9B24F248A963C`。本次未修改。
- 新引擎：`experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m`，SHA256 `4F72DB75F176E76DE03F77B45E0B82F05FF0E3206907714F3C7FAF786BA1092A`。
- 完整父子源码差异：[`run_cm18_closed_loop_v1.patch`](run_cm18_closed_loop_v1.patch)，16 个 diff hunks；引擎净增 236 行、删除 16 行。主要块：入口/模型参数和本地 forward helper 身份检查（新文件 1–55）；fusion/head 排他与固定 J0/C0 配置（约 84–160）；1 ms/100 Hz/首事件约束及逐航次日志初始化（约 706–923）；CM18 torque/hook isolation 和 C5 position/PCF/mask 限制（约 956–1000）；每事件 X18 组装、forward、clip-beta-J0、held compensation（约 2397–2475）；禁用 RBF 日志清零、z 在本次转移后推进、独立 CM18 输出字段（约 2681–2950）。
- C5 延迟预测 helper 为引擎原有同目录路径检查所需：父源 `experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m` SHA256 `48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D`；新目录副本 `experiments/attitude_cm18_a1_20261024/delayed_prediction_step_candidate.m` SHA 完全相同，未改内容。
- 已存在的 CM18 推理 helper 未改：`experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m` SHA256 `1FF450F9BE6A5C16FE98CB4F169EF9930F1B806FECFC10AD664C11CE940F42E9`。接口为 `[physical_output, normalized_output, coefficients, basis] = cm18_a1_forward_v1(raw_features, p)`，其中输入 18 维顺序是 `[omega_B(3), alpha_BS(3), thrust/mass, u(4), z(4), a(3)]`。

## 接入约束

新入口只接受 `opts.cm18_attitude_v1.enabled` 为逻辑标量 `true`，且须传入有限、形状固定的模型。姿态 RBF runtime/output/update 三个 flag 必须逐个显式逻辑 `false`；旧 attitude fusion/Head 互斥。源码锁定 `B2-RBF-Full-SPLIT`、固定 nominal controller/J0/C0、1 ms Plant 配置、100 Hz 事件时钟、`dmax=[45;45;4.7124]` 与 2.2 s beta 时钟，并要求首事件为 MATLAB `k=11,t=0.01 s`。CM18 接入要求原 Stage1 C5/PCF position path 与 `[1;1;0]` mask；拒绝 NDO/SMC、其他在线 torque/attitude hooks、oracle 和外部 torque injection。没有调用 `rbf_mimo_update` 的 CM18 分支。

事件输入从当前 omega、当步无补偿 BS nominal acceleration、thrust/mass、当前命令 `u`、过去命令积分 `z`、已完成十行请求力矩加权均值 `a` 构造。当前 1 ms 转移完成后才推进 z。网络输出按轴 clip，再乘 beta、经固定 J0 得 held torque；控制调用使用 `tau_BS - tau_compensation`。CM18 字段独立记录输入、上下文、raw/clipped/applied acceleration、beta、held torque、clip flag、inference time 和事件计数；姿态 RBF 输出/更新字段明确置零。

## 实际检查

实际执行的静态命令：

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "checkcode('experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m','-id'); checkcode('experiments/attitude_cm18_a1_20261024/delayed_prediction_step_candidate.m','-id'); checkcode('experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m','-id');"
```

实际进程 exit code：`0`。MATLAB 静态检查输出仅为 checkcode advisory（如旧引擎的未使用赋值/对齐提示，以及 CM18 guard 后不可达的旧 RBF 分支）；没有 parser error。原始输出留在 `matlab_checkcode_output.txt`。另外用 SHA256 核对父引擎未变、C5 helper 副本与父源字节一致。没有执行入口函数或任何 replay。

ROOT 后续 parse/source 审核可直接读取完整 patch。无积分 replay 尚未运行，也没有造合成 receipt；请在 ROOT 审核实际命令及只读数据身份后再执行。
## ROOT 复审修正与耗时口径

ROOT diff 复审后，恢复了父引擎位置路径的原条件 `elseif isRbfFullScheduled`，使原有禁用输出/更新时仍运行的位置 RBF 计算与计时/日志路径保持一致；CM18 姿态分支仍不调用姿态 `rbf_mimo_update`。本次仅该条件恢复，无数学、Plant 或 C5 控制路径改动。更新后的完整 diff 仍见 `run_cm18_closed_loop_v1.patch`。

最终引擎 SHA256：`4F72DB75F176E76DE03F77B45E0B82F05FF0E3206907714F3C7FAF786BA1092A`。追加执行 MATLAB 解析检查：`addpath('experiments/attitude_cm18_a1_20261024'); assert(nargin('run_cm18_closed_loop_v1')==4); disp('NARGIN_PARSE_OK'); checkcode('experiments/attitude_cm18_a1_20261024/run_cm18_closed_loop_v1.m','-id');`，输出 `NARGIN_PARSE_OK`，进程 exit `0`；日志见 `matlab_parse_check_output.txt`。该检查未调用入口函数或 Plant。

耗时口径：`controllerTime` 沿用父 timer 边界，不包含 Plant 后的 z 记忆推进与日志开销；当前 `cm18_inference_time_s` 只表示网络推理耗时。未来正式耗时比较需要单独测量完整 runtime，不可据当前日志宣称全控制耗时优势。