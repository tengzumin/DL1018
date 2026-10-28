# 先核对比较条件：主审发现与处理

用户要求先确定B与DSSM控制器/代码差异，再定位学习机制。本轮因此暂停了残差全12计算，先完成配置、执行分支和数值方程三层核对。未运行新Plant或训练，TEST未访问。

## 结论与具体问题

没有发现B与原DSSM暗中改用另一套姿态控制器、名义位置反步或Plant的证据。两者比较的是“原位置RBF”与“DSSM FEATURE在线头+全轴PCF”的两种位置补偿方法：readiness、表示、位置学习律和PCF本来不同，不能简称为只换网络。

已确认两个需要处理的问题：

1. **位置补偿β的时间索引未对齐。** B用min(k*dt/T,1)，DSSM有效Head用min(t(k)/T,1)，而t(k)=(k−1)dt。T=1.8s、dt=.001s；首个有效DSSM事件t=.320s时，B为.1783333333，DSSM为.1777777778。这是实际存在、此前未在比较口径中展开的一步时钟差异；β同时影响输出和更新，不能只改日志标签。
2. **C1公共options_audit容易被误读为B实际设置。** 同一候选审计结构写入所有方法，故B侧也看到pcf_enabled=1，但B实际raw与构造分支为PCF关闭。它是记录口径问题，不是B实际启用了DSSM/PCF。新运行须保存各条件自己的完整cfg/opts和解析源码身份，旧原件保持不动。

这两项都不能直接宣称为原高频/无风落后的唯一根因。尤其ON1与ONC采用同一原β时钟，因此该B/ON时钟差异本身解释不了C1缩放候选相对ON1的退化。

## 已实际核验的范围

- 原72对run_start中的cfg均为120个叶字段，完整字段集合、数值/逻辑形状和值比较无差异。共有opts差异仅原位置RBF输出/更新开关、first-Plant marker路径；ON侧另有stage1 runtime。没有只选26个输场。主审扫描未重读这批raw；旧B逐运行可执行runtime身份缺口仍保留，配置相同不补写历史执行环境。
- 新C1固定12对、24份raw/run_start/status完整结构/身份审计通过。完整配置未逐航次序列化，但effective_config.mat本身在source lock里有SHA，runner校验后单次加载cfg，并用同一个cfg构造所有条件。不能把“缺完整快照”说成“配置完全无来源”，也不能将源码推定冒充当时内存快照。
- 主审直接重读24份raw，用各自记录状态重构相同F_nom=m[r_a+K1*de+e+K2(de+K1e)]及F_cmd=F_nom−F_comp。最大方程残差4.44e-16 N；ON侧乘m的单位转换与PCF请求一致。12对参考、初态、环境风、形态真值/估计轨迹逐元素一致。这里的方程残差不是外部输入差异；输入配对差为零。
- 代码链确认两条件最终都调用同一个B2-RBF-Full-SPLIT家族，collector标签不路由控制器；formal分支共同使用由固定arm_initial建立的名义控制器、同一姿态RBF/BS、力到姿态转换、命令滤波、分配、电机和RK4。不同闭环状态使其输出不同是预期结果，不当作配置不公平。
- 不能把cfg.plant.inertia的保存值直接叫实际J0：distributed_v1通过arm_mass_properties重建惯量。两条件调用同一函数、固定初始几何/质量；新无Plant检查将另保存实际重建P0的J0/C0并明确重建来源。

## β差异的可量化范围

全12条ON1的1968个有效事件/条中，各有148个事件与B时钟不同，t≥1.8s差异为零。使用同一条ON1记录的W、phi和状态，改变β得到的应用加速度最大绝对差0.0008220567536280132 m/s²。只计算了同状态输出差和单步未投影权重更新差，未传播到后续闭环，不能据此给位置Q因果上界。

pre-ready的通用position_event_beta仍由已经关闭的旧RBF分支填写。DSSM前31个事件未ready，第32个事件t=.320s首次有效；应联合stage1_position_event_inference_valid与stage1_position_event_beta读实际Head时钟，不能据NaN或旧分支beta推断DSSM已输出。

## 最小处理及下一道门

已准备独立目录experiments/position_beta_clock_c2_20261023/，从真实冻结runtime复制，只把有效DSSM的t(k)改成k*dt，向不变的B时钟对齐。主审字节核对恰好一处替换，wrapper字节不变，其他科学输入不变。c固定1，原C1缩放方案保持STOP；不重训、不换mask、不改姿态/Plant。

当前放行的是源码修改及无Plant验证。拟议新闭环只有一个clock-aligned原ON候选、固定12场，B与旧ON1原记录精确复用；先一场probe，再决定11场，最多12个新航次/1GiB，不扩72或TEST。这属于新预算，不能自动恢复旧三轮。具体门、保存实际配置和失败处理见BETA_ALIGNMENT_TASKBOOK_ZH.md；尚未以任何离线拟合或同状态差值宣称该候选性能通过。

若闭环显示影响很小，下一优先工作才是原任务书中的同状态残差与可观测目标鉴别。不能因为发现一个小索引问题，就把所有旧性能弱点归到它上面；也不能跳过这个已确认的比较条件问题继续调模型。

证据：COMMON_POSITION_CHAIN_PARENT_CHECK.json、HISTORICAL72_CFG_OPTS_REVIEW.json、BETA_CLOCK_SAME_STATE_QUANTIFICATION.json、BETA_CLOCK_PARENT_SOURCE_CHECK.json；独立记录与代码审核分别在../c2_comparator_config_audit_20261023/和../c2_comparator_code_audit_20261023/（代码报告用v2，保留v1来源/ready措辞勘误）。
