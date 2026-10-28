# 因果 N4 门控 v2：三场固定闭环结果

仅限 TRAIN_C5_24 中预先指定的 3 场；每场各一次，共 3 次 Plant 调用。三场预检均停在主循环之前，均为零调用。无 VAL/TEST、惯量重建、参数调整或场景扩展。

| 场景 | 对照 | Q_m | task_SO3_rad | inner_SO3_rad |
|---|---|---:|---:|---:|
| DL1018_DEV_T1_C00_W03 | B | 0.0132726137916 | 0.0537015761514 | 7.11278446998e-05 |
| DL1018_DEV_T1_C00_W03 | C5 | 0.00824325789253 | 0.0464632902358 | 3.5885983843e-05 |
| DL1018_DEV_T1_C00_W03 | parent | 0.00824685259554 | 0.046442642675 | 0.000235046630001 |
| DL1018_DEV_T1_C00_W03 | candidate | 0.00824685259554 | 0.046442642675 | 0.000235046630001 |
| DL1018_DEV_T3_C09_W09 | B | 0.0110221858047 | 0.059061256281 | 0.0107032485045 |
| DL1018_DEV_T3_C09_W09 | C5 | 0.0096449711097 | 0.0607047777057 | 0.0107854933023 |
| DL1018_DEV_T3_C09_W09 | parent | 0.0094184570738 | 0.0606628061923 | 0.00964529311755 |
| DL1018_DEV_T3_C09_W09 | candidate | 0.00941990399015 | 0.0585829493573 | 0.00929661782111 |
| DL1018_DEV_T1_C11_W12 | B | 0.0105066718525 | 0.0444420679445 | 0.0196317762231 |
| DL1018_DEV_T1_C11_W12 | C5 | 0.00986151603388 | 0.0445366427867 | 0.0196729743782 |
| DL1018_DEV_T1_C11_W12 | parent | 0.00903651363897 | 0.0445245547974 | 0.0166145941374 |
| DL1018_DEV_T1_C11_W12 | candidate | 0.00916666262721 | 0.0441532372055 | 0.0166703070114 |

| 场景 | Q/C5 | task≤B（高风） | g均值（t≥2） | g≥0.5比例 | g=0.5穿越次数 | 结论 |
|---|---:|---|---:|---:|---:|---|
| DL1018_DEV_T1_C00_W03 | 1.000436078 | 不适用 | 0.000000 | 0.0000% | 0 | PASS |
| DL1018_DEV_T3_C09_W09 | 0.976664822 | 是 | 0.977953 | 98.8889% | 1 | PASS |
| DL1018_DEV_T1_C11_W12 | 0.929538886 | 是 | 0.983610 | 98.8889% | 1 | PASS |

每场均 20,000 步稳定、五项评分安全计数为零，1,999 事件中前 31 次无动作按零处理；门控、N4、输出限幅及 1 ms 保持的独立 SciPy 重放通过。低风 g 全程为 0，状态与保持动作相对 parent 的逐点最大误差均为 0。
三场复核得到 `held_force = 0.695 × held_action` 和 `commanded_force = nominal_force − residual_argument` 最大误差均为 0；这是 position_bs_step 的估计残差补偿接口。
两场高风的门在起动后基本常开，没有反复穿越 0.5；各时间窗的 2–5 Hz 动作能量低于同场 parent。单次对照不足以证明不存在闭环自激。
MATLAB R2025b 对齐 24 场事件及压力样例最大误差 `2.22e-16`，并验证非事件状态保持。

## 协议、锁与调用记录

- 预先冻结协议：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\CALL_PROTOCOL_v2.json`；SHA-256 `5cfec030685a180db167cc2488753c7383ac4f73b4e2bb528f40c11270eda7a7`。
- 三场 no-Plant 源锁：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\SOURCE_LOCK_v2.json`；SHA-256 `94301260f83dc097d2fb5b95d71ea081d3c5639163e65cb393cf85655dc3b6bb`。
- TRAIN24 审计 NPZ：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\causal_n4_gate_train24_acden_v2\CAUSAL_N4_GATE_TRAIN24_ACDEN_V2_PER_EVENT.npz`；SHA-256 `a5d6654654da3a7d3ccee4864c91491e47a501d859dc64096567dfda429f66da`。
- MATLAB 一致性：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\MATLAB_PARITY_RESULT_v2.json`；SHA-256 `6ba110ed9c1eae71f8469e90c107e4f81b01b6ee408c19e4657b6102a59cb220`。
- `DL1018_DEV_T1_C00_W03`：单次 release `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r0\RELEASE.json`；源锁 SHA-256 `cb07ac82756e62dc92df4acb3d2f84148100557ecf058ccbeba254a0c4eece81`；评分 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r0\SCORE_v2.json`；调用状态 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r0\runs\DL1018_DEV_T1_C00_W03\attempt_01\run_status.json`；raw SHA-256 `31ef2ae1116227ecb62948dd43e82f640819183abfcb268c09893137dc0450d6`。
- `DL1018_DEV_T3_C09_W09`：单次 release `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r1\RELEASE.json`；源锁 SHA-256 `e4c0100f117dfb003afdcb7a242451703dbb2d3f9932d893ce6cac97506058ae`；评分 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r1\SCORE_v2.json`；调用状态 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r1\runs\DL1018_DEV_T3_C09_W09\attempt_01\run_status.json`；raw SHA-256 `7c14e5bb271a4141983075ef4cbddef169ff3cff97147d295ab02bb9b757f11e`。
- `DL1018_DEV_T1_C11_W12`：单次 release `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r2\RELEASE.json`；源锁 SHA-256 `9eae5d340566312aa4668ee56727797bcf9347a94520d929a33501b2163c8855`；评分 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r2\SCORE_v2.json`；调用状态 `C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\dl_attitude_replacement_20261028\n4cg_v2\r2\runs\DL1018_DEV_T1_C11_W12\attempt_01\run_status.json`；raw SHA-256 `e4839cfcfab82f32e3fc21c56add89c524b0257030173cc8c79ac697ff6abac4`。

完整对照分数、安全计数、逐场重放误差、能量窗口、所有调用与输入文件哈希见同目录 `THREE_SCENE_RESULT_v2.json`。
复用入口为独立 runner 的 `position_compensation_n4_causal_gate_init/step.m` 和 `position_compensation_static_n4_init/step.m`；三个单次 release 均已消耗，后续研究应另建隔离运行与新协议。
