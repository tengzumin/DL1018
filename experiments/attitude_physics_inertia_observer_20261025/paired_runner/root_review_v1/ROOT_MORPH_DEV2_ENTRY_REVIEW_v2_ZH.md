# Root 审核与放行决定：MORPH_DEV2_DIAGNOSTIC v2

日期：2026-10-25（Asia/Shanghai）

## 审核结论

**批准仅执行任务书预登记的两个 DEV 主动形变场景，共四次闭环航次。** 限于 `DL1018_DEV_T2_C02_W15`（FIG8_3D、arm2、seed 2026122847）及 `DL1018_DEV_T3_C10_W11`（SQUARE、arms3/4、seed 2026123971），每场 baseline 后 candidate。性能正负都记录且不门控第二场；工程、安全、完整性或资源门槛失败即停止。这个release不授权训练、DEV72、TEST、调参或新的方法搜索。

C00 的既定失败不变。此批次用于判断已实现的物理惯量前馈/残差observer在**主动形变应用域**是否有实用价值；不能单凭这两场宣称普遍优于 RBF、闭环稳定性证明或论文结果包达标。

## 证据审核

- v2 候选锁 SHA-256：`a6a1bb439143b68d4e206e4468303061ff08abcdfaedafae05f8f62e10f76bb4`；静态审核 SHA-256：`18f1b30909e5e36a64d5a0b102bef0b528a7514a15d25dfd48ce0d7bb7f342b0`。root独立确认运行入口的61条身份记录与磁盘一致，39个MATLAB部署源及17个输入与已审DEV3冻结锁逐项一致；目标场景/seed与已完成无Plant预检一致。C00失败版和过期v1候选材料均保留，v2不引用过期文件。
- 独立审查者检查v2 wrapper、PS7 launcher和静态checker，无阻断缺陷。wrapper在MATLAB `checkcode` 下没有语法错误；提示仅为代码分析/效率风格项（STCI、AGROW、ALIGN、NOCOMMA、ISCL、MSNU、NASGU）。这个检查启动过一个短暂MATLAB静态分析进程，不运行Plant；检查结束后活动MATLAB/Octave进程为0。
- 负向门禁验证：故意提供错误schema且`approved=false`的release，PS7 launcher以退出码1拒绝，错误为“Root release does not authorize exactly the two-scene diagnostic scope”；没有创建attempt目录或启动MATLAB。fixture SHA-256：`c4b3dfac33e21aca71341c4d5f3a85eb63604daac6566156ea8154f94ee73baf`。
- launcher/wrapper锁定release路径与SHA、candidate锁、39源/17输入、MATLAB可执行文件hash、attempt新建标记和原始raw；保存数据后才计分。候选须全程有限且STABLE、20,000 transitions/20,001 states、无安全停止、motor saturation与generalized clipping均为0。Q与SO(3)的全程、早晚段、逐轴、峰值、安全/tilt计数及控制器调用均值、运行墙钟保存在CSV/JSON；性能差异不作为停止条件。控制器计时字段仍明确不含candidate post-allocator commit，报告时不能据此声称完整耗时优势。
- 资源条件满足：C盘可用 `208,643,739,648` bytes（约194.3 GiB），高于30 GiB下限；2 GiB本阶段预算；attempt目录尚不存在。launcher会等任何已存在MATLAB结束，不会杀进程。当前没有活动MATLAB/Octave进程。

## 当前可复现执行入口

使用PowerShell 7启动：

`pwsh -NoProfile -File "<launch_morph_dev2_diagnostic.ps1>" -ReleasePath "<root release json>" -ReleaseSha256 <root release SHA256>`

本文件与单独冻结锁、root release分离。release文件写成并hash核对后才会触发执行；v2候选锁 `NOT_FROZEN` 本身没有闭环授权。第一场C02先跑baseline/candidate；performance delta只记账，安全/工程通过后才继续C10。任何已启动的航次都不得自动重跑或覆盖。