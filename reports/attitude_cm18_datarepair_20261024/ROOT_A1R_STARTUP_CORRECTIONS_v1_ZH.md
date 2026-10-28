# A1R 启动检查修正记录

2026-10-25。以下均发生在 optimizer 步数为零时，不改变数据、模型或训练算法。

## normalizer 指纹

Root 第一份独立数据审计用 `x[::5]` 取样，训练器沿原 A1 用高级索引 `x[np.arange(0,1996,5)]`。两者取出的全部 X/Y 值逐元素、逐位完全相同，但 concat 后分别为 F/C 连续内存，NumPy float64 reduction 顺序造成约 1e-13–1e-12 的末位差，字节 SHA 因而不同。是 Root 对字节级复现口径的疏漏，不是数据或训练器错误。

Root 实际复算并保存 `ROOT_NORMALIZER_LAYOUT_DIAGNOSIS_v1.json`，另保存 v2 审计源码/报告，严格沿原 A1 高级索引布局；816 缓存再次通过，canonical normalizer SHA 为 `faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c`。v1 保留，只有它的 normalizer 指纹不用于训练放行。源数据/manifest SHA 和资格结论不变。

训练器仅更新预期指纹，没有放宽精度、修改公式或换训练数据。第二次零步检查通过，loss 有限、初始化一致、optimizer calls=0。

## GPU 使用率预检

首条正式启动命令在创建 formal 目录前被 GPU 利用率 10% 硬门拒绝；Root 观察桌面负载由 2% 短时升至 19%，没有其他已识别的 ML GPU 作业。该利用率硬门不是科学要求，也不能区分 GUI 与训练，因此不适合作为启动阻断。Root 决定只保留可解析利用率记录与单训练作业人工核查，取消此阈值阻断；不终止任何桌面或实验进程。

首次命令实际退出 1、0 optimizer、formal 目录未创建。失败源码和记录另存 `a1r_formal_attempt01_preflight`；后续使用新 source SHA 和 v2 release 重试，不能隐去此启动尝试。该修正只涉及启动条件，数值训练逻辑和已经通过的零步数值自检不变。
