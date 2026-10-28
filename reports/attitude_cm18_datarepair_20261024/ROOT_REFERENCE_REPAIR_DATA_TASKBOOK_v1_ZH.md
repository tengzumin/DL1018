# CM18：先修参考数据链，再验证上游位置匹配

2026-10-25。Root批准本任务书范围的离线数据实现与准备，不批准optimizer、Plant或TEST。C5位置证据冻结、C7暂停，历史原件全部保留。目标仍是主动变形四旋翼应用证据与姿态RBF替代，修复数据错误本身不计方法创新。

## 依据与分开处理的因素

1. 原T2 FIG8的Y/Z参考加速度二阶系数少一半；A1数据仍取原B轨迹，C5部署参考已修正。现有corrected T2 B原始日志可复用。Root实测 corrected TRAIN C00W00的cfg与当前C5完全相同，完整B opts与新探针B仅差firstPlant marker路径。
2. T1/T3同参考配对证明B→C5使冻结A1误差增加，两场预登记门均通过；约三成事件alphaXY越过旧训练范围。这是另一项部署数据覆盖变化，不能与T2公式修复混为同一因素。

本阶段只先构造B参考修复数据集（记B_REF_REPAIRED），为参考修复控制模型及后续C5匹配模型提供干净参照；不声称它已解决T1/T3上游迁移问题。

## 固定输入与输出

保持A1原ALL816中768 TRAIN/48 VAL场景ID、顺序、每场1999事件及原400行stride规则。

- T1/T3：复用已认证原缓存512 TRAIN+32 VAL，按原ALL816 manifest和reader核路径、bytes、SHA与身份，不复制原raw或缓存。
- T2 TRAIN256：仅G3_D4_CACHE_INDEX_1632.csv中split=TRAIN、task=FIG8_3D、role=B、eligible=true、合法完成状态的256条。runtime_scene_id必须精确对应原canonical ID加_ACC_FIX_V1；拒绝POS_OFF。
- T2 VAL16：采用C5输入锁/已审候选清单的physical B source，不能用C5 result raw冒充B。它们使用corrected参考。逐场记录真实raw/start SHA及原A1 source SHA。
- 新缓存只写当前项目独立datarepair目录，输出X18/target/phase/time/index及source identity。旧eventH5、position sidecar、old label都不作为新姿态标签来源。

关键源pin：原ALL816 7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271；原INPUT a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5；G3_D4索引3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e；VAL候选80ef7a37cb0fff237086ccc138772c71494cacd50a916ed2dba4037d4f833494；C5 snapshot842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a。

## 实现与审核门

最少两个入口：Python准备source manifest；MATLAB按明确scene ID列表导出新272条，不做通用配置框架。准备manifest区分544旧cache复用与272新raw重建；全部来源身份可回溯，不以文件存在代替合格。

每个新T2 source须实际核raw/start SHA、cfg与C5一致、去除唯一firstPlant marker后B opts与冻结B一致、20s时序、1999姿态事件及原RBF初始化。raw.scene与原A1 scene除允许的加速度Y/Z修正外全部相同；scene_id仅可使用与该canonical ID精确对应的_ACC_FIX_V1别名，明确记录，不能扩大白名单。corrected参考必须与已手工微分核对并锁SHA的audit_reference_fixed('FIG8_3D',time)一致；位置/速度与原件相同。禁止只改raw.reference后保留旧log。

物理标签调用新的纯函数extract_cm18_events_v1，其SHA15d8fb369b93e3a251d70c7eb7a590f732da839d35a5bebfb2011f25123e37c1。Root已实际完成四份golden raw parity，X18/target/phase/time差均0；依赖arm_mass_properties等三源/path核定。真J/风仅离线标签使用，不新增部署输入。

实现交Root审核后，先只导出SCREEN4：TRAIN T2_C00_W00、TRAIN T2_C15_W14、VAL T2_C00_W10、VAL T2_C15_W09。Root核真实产物、来源差异与闭合后才放行其余268；成功screen4原位复用不重导，失败保留不自动重试。最终manifest仅在全部816可用且272新条目真实PASS后生成；每条source/cache identity与失败记录保留。

本阶段0 Plant、0训练步；新小型数据产物预算512MiB，磁盘不足30GiB不启动。当前C盘约余206GiB。不得删除旧数据/事故partial，不上传MAT/checkpoint/cache。只用PowerShell7与MATLAB R2025b绝对路径。

## 后续决定（此任务书未授权）

另行审核C5 VAL48真实raw复用认证；它们只能作开发验证，不能进TRAIN。考虑一次固定A1R参考修复控制训练，保持A1结构/种子/优化/60000步和best规则，仅改为B_REF_REPAIRED数据及其TRAIN派生normalizer；先准备并审核，才有optimizer release。随后C5匹配TRAIN采集采用正确T2参考，旧TRAIN24草案的原T2 source规则作废，不得照旧草案启动。是否扩完整C5 TRAIN取决于先导数据/资源/协议审核，不自动开新结构或种子搜索。
