# 推导与 CPU 零步检查复核记录

- 推导文档：`ROOT_SAME_STATE_ACTION_DERIVATION_v1_ZH.md`，SHA256 `45273eb99e3b793a68419c5a932b6d53b40af9977dd9691104b758b3fad5a22d`。
- 结论：代数、单位和假设条件通过复核，未发现具体错误。由 `E(c)=E0−Mc` 得 `d_old=E0+(I−M)c_old`，再代入新补偿式及精确预测特例均一致。`M` 无量纲，`c`、`E` 与 `d_old` 的单位均为 rad/s²。结论仅适用于文档列出的同状态、同形态/形态速度、同推力、固定分配与惯量、无裁剪和电机瞬时执行条件；不构成闭环稳定性证明。
- CPU 检查命令：`python reports/attitude_cm18_a1_20261024/model_preparation_v1/root_trainer_zero_step_check_v1.py --device cpu`，此前退出码 0。检查源 trainer SHA256 为旧版 `05535dc973c3ce27ddeb50c9ac15ad17d465b897c0a421b37cbdea2eb67ea06c`；零步模型前后向使用 64 个非零 basis，梯度有限且非零，权重/buffer 不变、无 optimizer 调用，float32 与 canonical double 最大输出差 `5.160418660832278e-06 rad/s²`。
- CPU 检查脚本 SHA256：`fe3b866e1c2efb78be59cf9130c92b28fbb07af7ff35c4befe9c1910c763255d`。它不覆盖后续 trainer release gate，也不代表 CUDA 环境检查。复核时当前 trainer SHA256 为 `7544a04329bc1e06ff5d7a113a077033a65f0b7c2de8a6f1b25ac54710e62c76`；ROOT 独立执行的 CUDA 零步结果单独记录。
