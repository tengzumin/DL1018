# C2β：位置补偿渐入时钟对齐（先实现／离线核验）

依据：对照审计发现冻结B位置RBF使用min(k*dt/T,1)，原ON1有效DSSM Head使用min(t(k)/T,1)，t(k)=(k−1)dt，T=1.8s。主审已独立读取首场真实beta值；这是一处具体的比较条件差异，不是已证实闭环根因。

## 当前放行范围

只批准在独立experiments/position_beta_clock_c2_20261023/内准备最小源码改动、无Plant验证、单配置运行入口及身份/计分工具。0新Plant、0训练/拟合、0GPU、0TEST。旧三轮已用完，旧C1已STOP；新增闭环预算须在具体源码和无Plant核验通过后另行明确，不能默认计入或重置旧预算。

## 唯一行为改动

从C1_SOURCE_LOCK_v2钉住的归档runtime逐字节复制run_dl1018_closed_loop.m和run_episode_dl1018.m到新runtime目录，只将有效stage1分支的

```matlab
betaOriginal=min(max(t(k)/cfg.rbf.position.beta_rise_time,0),1);
```

替换为

```matlab
betaOriginal=min(max(k*dt/cfg.rbf.position.beta_rise_time,0),1);
```

单处替换必须assert命中数=1；其余源码包括换行字节保持。这是向冻结B时钟对齐，不改B。β同时作用于输出与权重更新，必须如实声明新候选的完整在线轨迹会改变。

候选固定为原ON1的c=1、W0 FINAL60000、gamma12、原encoder/X14/normalizer、全三轴PCF、全部filter/BS/姿态RBF/C0/J0/Plant/执行器。不能用C1的c*、重拟合、切mask、扩输入或另改更新律。此实验不重判或覆盖C1，不作为充分论文创新。

## 必须同时修正的记录方式（无控制行为变化）

新的run_start逐航次实际序列化cfg、该候选实际opts、解析到的源码路径及SHA、模型/normalizer和物理场景身份。不能再把包含多个方法的共享options_audit写成每个条件的实际配置。历史C1原件不改；可新建说明指出B侧options_audit.pcf_enabled=1是公共候选元数据，不是B实际PCF开启。

## 无Plant验收

1. 原／新runtime字节差异恰好一行表达式，wrapper字节不变；所有共用源/配置/模型身份不变。
2. 直接读取固定12原ON1事件（有效事件掩码），核原beta=t/T、B beta=kdt/T、两者饱和后相同；量化同状态raw/applied输出及单步权重变化的差异，不把它当Q因果。
3. MATLAB源码checkcode、构造options/解析函数路径、固定输入Head输出先于更新及新beta公式检查，无run_episode/Plant调用。无Plant脚本必须便于审查，不能调用旧带main副作用的入口。PowerShell7启动准确R2025b，先核无现有MATLAB/重负载实验；不杀进程。
4. 运行入口应有源码/模型/场景/配置身份、独立主审批准文件、fresh resource preflight、独占锁、拒绝覆盖/自动重试、逐场真实启动账本、失败保存。不要创造通用框架，优先复用已核读取/评分逻辑。

## 待明确的新闭环范围（当前未批准启动）

拟仅1个候选、固定原12场、最多12个新航次；同批C1的B和ON1精确只读复用，不重跑。候选按冻结字典顺序先首场probe，再决定剩余11场。新产物≤1GiB、余盘<30GiB不启作业、仅1个重负载仿真、无GPU训练、无TEST/72扩展。预计纯运行约7分钟，含审核/启动/评分另计。

probe只以身份、完整、安全、实际beta匹配B及输出/更新时序过门；不能按单场Q挑场或换参数。全12公开Q/早晚段/轴/峰值/饱和及全部输场，未舍入1e-12m胜负容差。组均值目标沿总体、高频和无风共同改善，但本实验首先量化具体clock差异的实际影响；无论结果如何均不自动新增候选或扩72/TEST。

主审最后核实际源码、配置快照、原始输出和完整配对，再决定将对齐版本保留为新工程基线或否决。若影响很小或不能满足性能目标，明确尚待其他机制定位，不将小索引修正包装成论文成果。
