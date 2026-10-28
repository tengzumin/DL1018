# C3 DEV72 v2 输入与 PREPARE 独立复核

**结论：输入锁和 no-Plant PREPARE 门通过，可交主审签发 release；本结论不授权或代表已运行 Plant。**

我只读复核了 v2 锁、其所列运行源、PREPARE 结果、快照与 checkcode 记录。v2 锁 SHA 为 `a95eda8e6ab8b45408d24b560366636bab62f72ea619bf46fa602142b6708730`；合同 `9cbef5b5774a8b7a821c798f29caa6912755704f29f1a5e7f1f871f8ff1dc5fd`、runner `068968dcda079f0128e08dd551623f21aac6fa201f8e92eb24acb3634414e0f3`、prepare `5363a84a75ad2645bced6aca6df371d3501c4e990eee5d98bf6d06f192c1b572` 均与锁中 SHA 和当前文件实算一致；锁内 7 个入口/隔离源文件也逐一匹配。PREPARE 结果 SHA `2bc4403c644bafc16dc48622a0610be4910abc323afc6f29b62b974cea154c74`、配置快照 SHA `3ddf24ad98e0900a2bb105b34369e73be03d015c66ec599347dfb43d0e730ae6`、checkcode JSON SHA `90c695d821ecebf9f750f3d5034f80378f32d71ad893e939e26b4fa9ce49286b` 均与当前文件一致；结果中锁、合同、runner、快照的 pin 均吻合。

范围和守门计数相符：72 个唯一场景由 60 个新场景与 12 个既有 C3 复用场景互斥且完整组成；记录核验了 72 份 B 输入、12 份可用 C2 cfg/opts、32 个 MATLAB 源解析项。结果状态为 `PREPARED_NO_PLANT_WAIT_PARENT_RELEASE`，`plant_calls=0`、episode 未调用、训练/优化器步数为 0、无参数搜索、无新 B 航次、未访问 TEST。锁仍标记 `plant_authorized_by_this_lock=false`；因此这里仅通过准备/身份门，须等主审 release 才能开始航次。

v1 的合同字节 SHA 不匹配失败记录保留；v2 builder 以同一 UTF-8 字节串写文件并计算 SHA，修复的是 LF/CRLF 记账，不改科学条件。checkcode 不是零消息：候选 helper 与 episode wrapper 为零；prepare 有一条未使用赋值提示，runner 的消息均为可自动修复的风格建议，冻结 runtime 有 25 条既有提示。本次没有发现新增的功能性阻塞，但不能把 checkcode 描述成完全干净。

边界：no-Plant 准备结果不验证真实航次的事件递推或闭环行为。既有历史 B 的逐场源码身份缺口仍然存在；本批准备不会补成历史可复现性或论文公平复现证明。
