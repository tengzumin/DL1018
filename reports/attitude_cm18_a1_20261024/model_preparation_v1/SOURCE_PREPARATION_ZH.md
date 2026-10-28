# CM18-A1 forward 源码准备

按冻结任务书 `A1_CM18_PREPARATION_TASKBOOK_v1_ZH.md` 实现了 CPU 纯推理函数与 Python/MATLAB 小型 parity 源码。任务书 SHA256：`f6d415a3272f9a48e5dd6ab7c003ab90ce6f5fd8736c8f446aab8412637cbf7e`。

实现固定为 `18→32 tanh→32 tanh→24 linear`。24 个输出按 Python row-major 重排成 `A(x)∈R^{3×8}`，再乘未中心化基向量 `[z/2;u]`；物理输出乘 TRAIN 三轴 RMS。输入顺序为 `ω_B(3), α_BS(3), thrust/mass(1), u(4), z(4), a(3)`。无独立的 3 维输出偏置；末层 24 维偏置只影响系数矩阵，输出仍乘形态基，因此 `z=u=0` 时结构上输出精确为零。全网共有 2,456 个可训练参数，包含 24 个系数输出偏置。

新源码路径与 SHA256：

- `experiments/attitude_cm18_a1_20261024/model_cm18_v1.py`：`ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6`
- `experiments/attitude_cm18_a1_20261024/matlab/cm18_a1_forward_v1.m`：`1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9`
- `experiments/attitude_cm18_a1_20261024/matlab/check_cm18_a1_parity_v1.m`：`f80070b536f63e4f775e18c9b5533b1966b6dc1b50f665d0a5330e28ee5af2ff`

NumPy 代码是推理参考，提供 Xavier-uniform 随机初始化、前向推理和合成 parity fixture 导出；它不是训练模块，也没有训练器、优化器、在线状态或 online head。后续 Torch 训练模块若获准，将另行实现同一公式。两端前向均拒绝非有限的标准化输入、系数矩阵、形态基、归一化输出或物理输出。MATLAB parity 检查使用 Python 输出的 fixture，核对 3×8 系数顺序、基向量、归一化/物理输出及严格零输出。后续可在仓库根目录执行以下命令；本次没有运行 Python fixture 导出，也没有运行 MATLAB：

```powershell
python .\experiments\attitude_cm18_a1_20261024\model_cm18_v1.py --export-parity-fixture .\experiments\attitude_cm18_a1_20261024\parity_fixture_v1.json
matlab -batch "addpath(fullfile(pwd,'experiments','attitude_cm18_a1_20261024','matlab')); check_cm18_a1_parity_v1(fullfile(pwd,'experiments','attitude_cm18_a1_20261024','parity_fixture_v1.json'));"
```

本交付只完成源码准备；不含事件特征重建、训练、闭环接入或运行结论。实际 TRAIN-only normalizer、数据重标注、独立复核以及后续训练放行仍按任务书单独审核。
