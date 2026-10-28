# MORPH_DEV2_ROOT_RELEASE v2 先验拒绝记录

- 时间：2026-10-25；失败 release SHA-256：e7fec2cd82c782c96e12622fef9d55f1d3c373d6eda88e33129956fb5bad88c6。
- PowerShell 7 launcher 在 release 字段校验阶段拒绝启动：`release.training_authorized` 属性缺失；同一段校验也要求 `TEST_authorized`、`retry_authorized` 显式为 false。
- `attempts/MORPH_DEV2_20261025_A01` 未创建；runner marker=0、MATLAB start=0、Plant runs=0、raw/status/stdout/stderr=0；确认无 MATLAB/Octave 进程。
- 根因是 root release JSON 漏了三项显式禁用字段，不是 Plant、源码、输入或候选失败。旧 release 保留，不重用。
- 决策：修正 root 授权文件，保留同一范围、预算、对照和安全条件，签发新 attempt ID `MORPH_DEV2_20261025_A02`；不修改冻结代码/锁，不增加或替换场景，也不执行训练/TEST。之后只执行新 release 命令一次。