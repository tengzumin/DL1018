# Recovery288 统计器源码独立复核

复核对象：test48_statistics_recovery288_v1.py，SHA-256 535a14ef2593dad33a564a4fddfce1ecf776fbcd8e0d6e6a8df453c861fee866。对照冻结统计器 test48_statistics.py，SHA-256 5a5e102f57d48ff60e83404606baf306a9a7d7160304919e98dc4f57eb7cbd08。

未发现统计数值计算改动或阻断性缺陷。旧统计器的11个数值函数、自检、常量及 analyze_payload 数值计算段与冻结基线逐字一致；新逻辑限于 Recovery288 输入门、来源披露与输出 envelope。对应比较片段 SHA-256：数值函数 7c0dc58c29de1f49ea425ac4ae939c5ece9b5e49a19da766666e1d02fed56e6d，常量 77dfa6225fbf02c62ad364f12e26251c624dc69ba7519797e74d63753cb0d5ed，analyze 数值段 92559655c37d6b08f1e6391b6b76031a91177489432693c7377e8eabbdeb9994。

## 发现

- **P2，非阻断：receipt 整数栏位接受 JSON 布尔值。** validate_recovery288_envelope 第251、256、259行用 == 检查 block_index、matlab_os_exit_code、training_steps 和 optimizer_steps。Python 中 true == 1、false == 0，因此类型错误的 receipt 仍可能通过，例如首个 block 的 block_index: true 或 matlab_os_exit_code: false。当前 SHA 锁定的 reader 会输出整数，所以正常生成的 payload 不受影响；若要求严格拒绝手改或错误类型的 JSON，应先要求 type(value) is int 再比较。未修改源码。

## 其余复核

- Recovery288 reader SHA 与 release、scope SHA 均固定；统计器读取的字段与 reader 输出对应：288条 score rows、五个 Recovery208 receipt、DSSM 原始自然退出 UNKNOWN、旧六进程门 UNMET_DO_NOT_RECLASSIFY、scene32 缺 runIdentity 例外、144条事件账本、288条执行器完整性账本，以及96条 W0 校验行。没有发现虚构的 receipt、event、actuator 或 W0 字段。
- 入口要求输入位于 raw_review_v1 直接子目录、输出位于 statistics_v1 直接子目录；输出以独占创建模式写入，已存在文件会被拒绝。
- 本复核只读源码与既有静态材料；未读取 TEST raw 或成绩，也未运行正式 CLI/MATLAB。根另行报告已运行 guarded self-check、19个 schema 负例和 synthetic analyze；这些执行不属于本次独立复核。
