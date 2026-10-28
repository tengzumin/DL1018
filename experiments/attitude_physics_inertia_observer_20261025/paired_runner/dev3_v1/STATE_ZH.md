# DEV3 执行入口阶段状态

截至 2026-10-25：无 Plant 完整输入预检已 PASS。实际 receipt SHA-256 为 `f770cfe55688314b104848ae1b7176245dd2ffc5592726be813c412897619bd6`；候选输入锁 SHA-256 为 `ce6e671d8174ab5204581923a56548c697a8ef703d8b50b43eb9421af23cd1b2`。旧 scene-only 状态与修复前静态审计已过时，原文件及首次失败证据保留。

仅从首次 scene-only launcher 失败到本次 full input preflight 结束计：launcher 调用 2 次，实际 MATLAB 启动 1 次，Plant 航次 0，训练 0。首次失败发生在启动 MATLAB 前，见 `../LAUNCH_PRECHECK_FAILURE_v1.json`。此前 synthetic v1/v2/v3 和其它只读检查不计入这段资源账本，均保留其历史记录。

本目录当前仅准备 DEV3 执行入口与候选最终锁；尚无 root release，未启动任何 DEV3 配对航次。状态 `NOT_FROZEN`，闭环运行未获授权。

本目录初版执行入口、`DEV3_ENTRY_STATIC_AUDIT_v1.json` 与 `source_lock_paired_runner_v1_candidate.json` 均未执行，已按原字节归档至 `provenance_before_entry_fix/`；其身份已由后续修订取代，不能作为 root release 的最终锁。
