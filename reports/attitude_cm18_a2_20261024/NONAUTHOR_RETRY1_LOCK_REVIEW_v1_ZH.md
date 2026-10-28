# A2 Retry1 非作者复核

复核结论：retry1 trainer 的源码差异限于 Windows JSON 原子替换的有界重试，以及 retry1 自身的 source/output/release 身份；训练算法和训练常数未变。结合 v2 的真实 Windows 锁测试回执，我建议 ROOT 可按新 trainer SHA、新 release 身份和新输出目录批准一次同协议重跑；旧失败 attempt/release 保留，不续训旧 attempt。

Trainer SHA256：`b770a72f6f44273f105263cec7b6792f0bf6b6090f68c470a5549b0465328ef8`。相对 A2 原 trainer，diff 仅新增 `time`、把 TRAINER/输出路径切至 retry1、release schema 切至 `CM18_A2_RETRY1_TRAINING_RELEASE_V1`，以及 `_write_json` 在 `.tmp` 完整写入并 fsync 后，对 `PermissionError` 且 WinError 为 5/32/33 的 `Path.replace` 最多尝试 20 次、间隔 50 ms。训练 loop、seed 2026102001、60,000 steps、batch 512、每 1,000 步验证和优化器调用均无差异。上限是 19 次等待、0.95 秒；持续冲突仍会抛错，临时文件保留。

真实锁测试回执 [ROOT_WINDOWS_REPLACE_TEST_RESULT_20261024T135531.json](retry1_tinyfixture_v2/ROOT_WINDOWS_REPLACE_TEST_RESULT_20261024T135531.json) 的 SHA256 为 `8f448435ee4cc39bfe43759611fb7b2776216ee3cd66b451969589bb3c036872`，绑定 trainer SHA 与当前文件一致。v2 checker SHA256：`12bc31a2bf785f0936ec2189f662218f591cfcb75b7d34a25b8975b7c40afe4b`。测试实际用 Windows `CreateFileW` 打开目标；只包裹 `Path.replace` 以计数并调用原实现，没有模拟替换失败。三项均 PASS：不共享 delete 的短锁 4 次/0.162 秒后成功；持续长锁 20 次/0.982 秒后按界限失败，原目标 SHA 保持且 `.tmp` 保留；共享 delete 的短锁在持有期间实测 WinError 5 三次，释放后第 4 次成功（0.161 秒）。

旧 v1 lockcheck 对 FILE_SHARE_DELETE 句柄仍打开时要求首次替换成功，这与本机 `os.replace`/MoveFileExW 的实测行为不符；该次留下旧 target 和新 `.tmp`，没有 PASS 回执。v2 已用“句柄持有 150 ms、记录 WinError、释放后有界重试成功”替代，符合 retry 实际承诺。持续锁定场景仍会显式失败，因此重跑必须使用新的 ROOT release 和隔离输出目录；本复核没有运行锁测试或触碰训练/检查点。


