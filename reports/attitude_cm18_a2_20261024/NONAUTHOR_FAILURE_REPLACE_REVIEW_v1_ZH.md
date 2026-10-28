# A2 attempt 1 文件替换失败：独立只读复核

**归因边界。** failure.json 记载 2026-10-24 13:48:07Z、train stage、attempted/completed step 38200，以及 PermissionError / WinError 5：将 progress.json.tmp 替换为 progress.json 时被拒绝访问。traceback 落在 trainer 的 _write_json → Path.replace → os.replace；它证明失败发生在 progress 发布的 rename 阶段，不是本记录所示的 loss/梯度计算错误。progress.json 仍是 38100，progress.json.tmp 内容为 38200，run_receipt 也记录 38200 completed、failure_step 38200。代码顺序是 optimizer.step() 后先更新 completed 计数，再每 100 步写 progress（train_cm18_a2_v1.py:626-631），故这 38,200 次更新已经消耗。

_write_json 先写同目录 .tmp、flush+fsync，再调用 temp.replace(path)（train_cm18_a2_v1.py:80-87）。现有证据不能区分短暂共享锁、长期 delete-sharing 锁、ACL、杀毒/索引程序或其他 Windows 文件系统原因；时间重合不是唯一根因证明。不得把失败归因为某个具体桌面进程或“GPU/训练不稳定”。

失败处理源码会尽力保存 final_on_failure，但 _save_checkpoint 仅序列化模型 state_dict、step、kind 和 selection_score（train_cm18_a2_v1.py:288-291）；没有 Adam 状态、NumPy minibatch RNG 状态或 Torch RNG 状态，也没有合法 resume 流程。该 checkpoint 不能延续同一优化器/RNG 轨迹。旧 attempt 应保留为 FAILED 并计入 38,200 步资源消耗；修复后只能按相同科学协议、初始数组和 seed 2026102001，使用经修复的新 trainer 源及新的 ROOT release 身份，从 step 0 新建隔离的 retry attempt；旧 release 与失败 run 原位保留。不得接续 final_on_failure，也不搜索参数。

**修复验收建议。** 在独立临时目录对真实 Windows 文件句柄做测试：以 CreateFileW 打开目标 progress 文件，share flags 允许读写但不含 FILE_SHARE_DELETE，确认第一次 Replace 确实得到访问/共享拒绝；释放句柄后，有限次/有限时长重试应只重试同一个已 fsync 的临时内容，并原子替换成功，最终 JSON 是目标 step、临时文件消失且没有重复 optimizer step。第二个测试保持该句柄超过重试预算，必须有限次后明确失败，保留旧 target 和完整 latest .tmp，不宣称写入成功或无限等待。两种测试都不要触碰旧正式 attempt。

旧记录身份 SHA256：

- failure.json：EC655A32C8F3125DF9ECEAAE0171A8C33230A73DF1A39145DD8FF307C0DA3E78
- progress.json：36F7568557439D084987623CD3AF5C89F9DAE6EA8A9BF740ACB06CD6A76527EB
- progress.json.tmp：61039D903A763258B7A82136B3E8E594B2F29BBFACC8066BDF34A6DBB65C3623
- run_receipt.json：0C6FBE4A811F06F56203FBCBE95B60C8460FCAE8EE400CB065E78665AECB0FF3
- failure receipt 所 pin 的 trainer 源 SHA 与当前原 attempt 源相同：55CA254D9E586C463267A5B290F3EDF984505C766366F3275F649FE15D6E27EA

未读取 checkpoint、未修改源码、未启动训练。

