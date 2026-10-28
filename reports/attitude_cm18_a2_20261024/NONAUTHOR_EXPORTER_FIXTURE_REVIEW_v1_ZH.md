# A2 exporter 与 trained fixture 独立只读复核

复核对象与 SHA256：

- A2 exporter：**export_best_cm18_a2_v1.py**，**4d5f980ff05ea3f229885fdaff65f8207ec7d1df4438b24702f7b9bba5059c04**。
- A1 对照 exporter：**export_best_cm18_v1.py**，**9aa9dea1a5dbaedc3b49dbac13ea23ea95c49c4bbe1c27b73d65658510a09b29**。
- A2 fixture checker：**check_cm18_a2_fixture_v1.py**，**8d2c5a0311da582c50a14d2f1f45387071916375a9af510ddcc80e89cc9dd11f**。

未运行导出器或 checker；未打开训练运行目录中的 checkpoint；未调用 CUDA。

未发现 best-step、VAL 复算、normalizer 或参数布局方面的阻断问题。导出器要求自然 COMPLETED 收据、恰好 60,000 步和 ROOT release SHA；按 step 0、每 1,000 步至 60,000 的记录顺序重算严格最小值，严格相等时保留较早步，并交叉核对收据、best.pt 中的 step/score/SHA 和逐场记录（export_best_cm18_a2_v1.py:282-318,420-477,490-495）。独立 VAL 重算覆盖 48 场、每场 1,999 个事件，逐场重新算相同的归一化 L2 scene score 后取场景等权平均；这与 trainer _evaluate 的口径相同（导出器 :148-170,192-210,526-533；trainer train_cm18_a2_v1.py:304-341）。

Normalizer 从 canonical float64 JSON 数组读取，并按 TRAIN 768 场、每场 offset 0,5,...,1995 的 307,200 行独立重算，ddof=0、std 下限 1e-6，最大绝对容差 1e-10。同时验证 checkpoint 中三个 float32 buffers 与 JSON 及其 SHA 一致。导出 W/b 从 best state dict 的 float32 数组提升为 float64，部署 normalizer 保留 canonical float64 值；布局与 A2 网络 18→32→32→24、输出 reshape 为 3×8 一致（export_best_cm18_a2_v1.py:173-184,393-418,504-524）。

导出器构造的三份 fixture 确实使用 best.pt 提取出的参数字典：C00 首事件、C01 首个 u 非零事件和 C01 首个 HOLD 事件；各自保存输入/缓存/manifest 身份与 raw 特征 SHA。生成时对 raw alphaBS x/y 做扰动并要求 yaw 输出精确不变，同时将 8 维形态基底清零并要求输出精确为零（export_best_cm18_a2_v1.py:222-267,553-581）。部署身份记录 checkpoint SHA、step、normalizer SHA；export receipt 再将 fixture 文件 SHA 和 checkpoint SHA 放在同一包内（export_best_cm18_a2_v1.py:589-679）。

**剩余证据缺口：当前 checker PASS 不是 trained-fixture PASS。** Checker 只读取 fixture 内嵌的参数与期望值，自行调用 NumPy A2 forward；它记录 fixture/model 源码 SHA，但不校验 fixture 参数是否等于部署 JSON 或 best.pt，也不要求 checkpoint SHA/selected step 字段（check_cm18_a2_fixture_v1.py:25-40,66-80）。现有 A2_FIXTURE_CHECK_RESULT_v1.json 的 fixture_path 是通用合成文件 cm18_a2_parity_fixture_v1.json，case_identity 为 null。因此现有 PASS 证明通用 A2 parity/zero/yaw invariance 测试通过，不能作为实际训练权重的 parity 证据。导出完成后，应对三份 trained_val_*_parity_v1.json 分别运行 checker，并将每个 checker 结果的 fixture SHA 与 export receipt 中的 artifact SHA 对上；若需 checker 单独证明训练身份，还要核对 fixture 参数对 deployment 文件的对应关系。

此复核只评估源码和已有 fixture-check 结果；没有检查或推断运行中的训练产物。

