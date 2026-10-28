# A2 源码准备交接

状态：实现与无 Plant 检查已完成。正式训练由 Root 独占启动（session 54707）；本报告作者未启动训练、读取运行中 checkpoint 或执行 Plant。

## 实现范围

- `model_cm18_a2_v1.py` 与 `torch_model_cm18_a2_v1.py` 保留 A1 的 18→32→32→24、2456 参数、初始化、normalizer、`[z/2;u]` 形态基底。完整输入前向提供 roll/pitch；同一组权重对输入副本执行 raw feature `3:5=0`，再归一化并提供 yaw 系数行。Torch 两分支共同回传梯度。
- `train_cm18_a2_v1.py` 由 A1 trainer 隔离复制，保留原采样、60,000步、验证和选模协议；移除 SCREEN4 训练入口，只接受 Root SHA pin 的 A2 release。release gate 固定 A2 taskbook、续行门槛、ALL816 manifest、input/audit 与四项源码身份。数据 reader 复用 A1 只读模块。输出仅指向新 A2 run 目录。
- `export_best_cm18_a2_v1.py` 由 A1 exporter 隔离复制，只接受已自然完成的 A2 run；保留全48场 VAL 重算、normalizer 身份和 float32 checkpoint 对 canonical float64 部署数组的比较。训练后 fixtures 同时记录 RAW mask、yaw 扰动、零形态和完整输入分支结果。
- MATLAB A2 forward 与两个 Python 检查入口均在 A2 新目录。A2 检查不访问 TEST；fixture 使用合成输入和 A1 初始权重/normalizer，不从缓存拟合。

标签仍是行为残差 `alphaTrue-alphaVirtual`。这项 raw 输入不变性只检验冻结假设，不证明标签在所有状态下都独立于当前横向 BS，也不证明闭环一定改善。

## 实际检查

1. Python 语法检查退出码 0：

   ```powershell
   python -m py_compile experiments/attitude_cm18_a2_20261024/model_cm18_a2_v1.py experiments/attitude_cm18_a2_20261024/torch_model_cm18_a2_v1.py experiments/attitude_cm18_a2_20261024/check_cm18_a2_yaw_invariance_v1.py experiments/attitude_cm18_a2_20261024/check_cm18_a2_fixture_v1.py experiments/attitude_cm18_a2_20261024/train_cm18_a2_v1.py experiments/attitude_cm18_a2_20261024/export_best_cm18_a2_v1.py
   ```

2. CPU float64 A2 检查退出码 0，结果见 `A2_SOURCE_CHECK_RESULT_v2.json`。在启动 Python 前设置 `MKL_THREADING_LAYER=SEQUENTIAL`、`OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`CUBLAS_WORKSPACE_CONFIG=:4096:8`；检查结果 PASS：2456参数，A1 初值数组逐元素完全相同，yaw 对任意当前 alphaBS x/y 扰动不变且输入偏导精确为零，roll/pitch 与 A1 同权重前向完全相同，零形态精确输出零，batch/single 在 `1e-12` 容差内一致，NumPy/Torch 最大输出差 `3.552713678800501e-15`，两支路联合梯度误差 `4.440892098500626e-16`。检查未建 optimizer、未读缓存、未训练。

   ```powershell
   $env:MKL_THREADING_LAYER='SEQUENTIAL'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; $env:CUBLAS_WORKSPACE_CONFIG=':4096:8'
   python experiments/attitude_cm18_a2_20261024/check_cm18_a2_yaw_invariance_v1.py --result reports/attitude_cm18_a2_20261024/A2_SOURCE_CHECK_RESULT_v2.json
   ```

3. Python fixture checker对当前合成 fixture 实际退出码 0，结果见 `A2_FIXTURE_CHECK_RESULT_v1.json`；所有参考字段绝对误差为 0。另以合成18维输入直接调用 exporter fixture builder，得到 `PASS`，未落盘临时文件。

4. Root 实际运行 MATLAB R2025b parity 检查，OS receipt `ROOT_MATLAB_PARITY_OS_RECEIPT_v1.json` 记录 exit code 0；结果 `ROOT_MATLAB_PARITY_RESULT_v1.json` 为 PASS。该检查验证输出 `1×3`、系数 `3×8`、basis `1×8`、RAW-zero/归一化输入、扰动 yaw 不变、zero basis 与 roll/pitch fixture parity；没有 Plant 或 optimizer step。最终 MATLAB checker SHA 记录为 `8af38cab680e247e8ff8cbb1b262d519b7edddb853af583bc762279518c9a3bb`。

5. Root 的 CUDA 0-step 检查结果 `ROOT_A2_CUDA_ZERO_STEP_RESULT_v1.json` 为 PASS，明确记录 optimizer instance/step 均为 0、训练未开始，且共享分支梯度有限。

6. Trainer 与 exporter 在不提供 release 的情况下均由 argparse 拒绝，原生命令退出码均为 2；这两次调用没有创建 run/deployment 目录：

   ```powershell
   python experiments/attitude_cm18_a2_20261024/train_cm18_a2_v1.py --repo-root .
   python experiments/attitude_cm18_a2_20261024/export_best_cm18_a2_v1.py --repo-root .
   ```

首轮 CPU receipt 的 `batch_single_exact` 字段曾使用 `2e-14` 数值容差，后续 v2 结果已改为明确的 `1e-12` 容差字段；Root 的独立 MATLAB receipt 记录最终 checker SHA。正式训练 release SHA 为 `da2d803c612701ec0078855efe468660102a82d99d6a0b81a4a10aa073c66532`；Root 已开始唯一正式训练，本报告不读取其运行目录。

## 源码 SHA256

| 文件 | SHA256 |
|---|---|
| `model_cm18_a2_v1.py` | `588f36a9434b1bf0a8b8343fc6a18f52c65a74aa4494a85511a6c71a465a9352` |
| `torch_model_cm18_a2_v1.py` | `7886fae80c77e204dacdb4af82647053626eab11b9285c2ef3c388e1842f4df8` |
| `train_cm18_a2_v1.py` | `55ca254d9e586c463267a5b290f3edf984505c766366f3275f649fe15d6e27ea` |
| `export_best_cm18_a2_v1.py` | `4d5f980ff05ea3f229885fdaff65f8207ec7d1df4438b24702f7b9bba5059c04` |
| `check_cm18_a2_yaw_invariance_v1.py` | `b78b06d9ffd936b353fcef42969ad68457d589628d18ff6f00502aa4b23122ea` |
| `check_cm18_a2_fixture_v1.py` | `8d2c5a0311da582c50a14d2f1f45387071916375a9af510ddcc80e89cc9dd11f` |
| `matlab/cm18_a2_forward_v1.m` | `f6647ee60f22f32ee66c881bfdac820d4ce9b03fb0aabbd7bf0bdb930216b20d` |
| `matlab/check_cm18_a2_parity_v1.m` | `8af38cab680e247e8ff8cbb1b262d519b7edddb853af583bc762279518c9a3bb` |
| `cm18_a2_parity_fixture_v1.json` | `9c28c2acc3f43c40120035bac6709fa11dbd1ec3c1bb87c81d545155130869cc` |

Root 的 formal release 已 pin trainer、reader、NumPy model、Torch model SHA；上述 trainer SHA 与 release 中的 source pin 一致。A1、C5 和历史文件未由本实现修改。
