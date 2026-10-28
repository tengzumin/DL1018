# C3 12场离线配对分析

## 口径与核验

对12个冻结场景分别使用C1锁定的B原始文件、C2执行ledger原始文件和C3状态绑定原始文件，共重算36个raw、24个C3配对。B的场景身份以C1 `shared_scenes` 元数据为准；B日志存在 `scene_id` 时同时核对，不存在时由冻结元数据赋值。C2 scene2 的采集状态继续记为 `FAILED_NO_RETRY`，仅按ledger SHA计入已批准恢复的raw。评分器主公式未修改，仅对缺少B日志 `scene_id` 的情况做内存适配。

36个Q、阶段和逐轴RMSE与主审原表逐行复核通过；三种方法的参考轨迹和外生输入哈希在每个场景内一致。主审双host完整固定输入重放有96条host×方法×阶段记录；本分析只独立复算probe、T3_W13和W15各一场，全部与主审结果在1e-12 m/s²内一致。没有新增Plant、训练或TEST访问。

## 主要结果

0–20 s位置RMSE均值为：B 10.349 mm、C2 9.783 mm、C3 9.116 mm。C3相对B胜10/12（83.3%），相对C2胜9/12；按1e-12 m、1 μm和10 μm阈值判断，胜负数相同，没有近零平局。平均改善分别为1.233 mm和0.667 mm。对B的胜率未达到85%，因此这仍是12场机制筛选，不能据此扩展到DEV72或TEST。

| 分组 | n | C3平均Q | C3胜B | C3胜C2 |
|---|---:|---:|---:|---:|
| HF W09–W14 | 6 | 9.254 mm | 4/6 | 4/6 |
| W15 | 3 | 7.526 mm | 3/3 | 3/3 |
| LOW W00–W08 | 3 | 10.432 mm | 3/3 | 2/3 |
| T1 | 4 | 9.400 mm | 4/4 | 3/4 |
| T2 | 4 | 9.369 mm | 3/4 | 2/4 |
| T3 | 4 | 8.581 mm | 3/4 | 4/4 |

所有分组的B/C2/C3平均Q、早晚段Q和补充指标见 `GROUP_Q_AND_SUPPLEMENT_SUMMARY.csv`；36条完整指标见 `ALL36_SUPPLEMENTAL_METRICS.csv`，24组配对差和阈值标记见 `PAIRED_THRESHOLDS.csv`。

## 输场与尾部指标

C3相对B的两场Q退化都来自轴与阶段之间的折衷：

- T2_C00_W10：Q +0.649 mm。早段X/Y分别改善0.161/0.246 mm，但Z恶化1.753 mm；晚段X改善0.357 mm，Y/Z恶化1.425/0.947 mm。峰值低4.574 mm，P95却高10.094 mm。
- T3_C00_W13：Q +1.069 mm。早段X/Y恶化1.401/1.449 mm、Z改善0.083 mm；晚段主要是Z恶化1.427 mm。峰值低5.344 mm，P95高9.671 mm。

相对C2的三场退化为T2_C00_W10（+0.477 mm）、T2_C02_W12（+0.207 mm）和T1_C00_W07（+0.014 mm）。完整所有输场的早晚段、逐轴、peak和P95差值都列在 `LOSING_PAIRS.csv`。这些差异描述配对闭环结果，不单独证明因果机制。

12场平均峰值：B 37.973 mm、C2 30.283 mm、C3 29.956 mm；平均P95：B 21.001 mm、C2 21.354 mm、C3 20.760 mm。所有raw的电机饱和和generalized clipping比例均为0。记录的单次controller call均值为B 0.089 ms、C2 0.121 ms、C3 0.178 ms；各raw内P95调用时间均值为0.209、0.344、0.575 ms。此时间仅是raw日志字段，未作正式实时性能认证。

## 固定输入残差诊断

沿用主审完整12场双host固定输入结果，C3权重在C2 host与C3 host、early/late、x/y/z每个组合上都是12/12场残差RMSE更低。该统计是保存权重在固定特征和区间目标上的局部重放，不是独立样本，也不等同于闭环因果保证。HF晚段Z改善较小（C2 host 0.063585→0.061585、C3 host 0.063179→0.060952 m/s²）；W15早段X改善较大（C2 host 0.049531→0.034455、C3 host 0.054970→0.037494 m/s²）。分组汇总在 `COMMON_INPUT_GROUP_SUMMARY.csv`，三场独立交叉核在 `COMMON_INPUT_KEY_SCENE_CROSSCHECK.csv`。

## 产物

`BINDING_MANIFEST.json`记录输入来源、冻结SHA、状态和全部36个raw路径/SHA；`PRIMARY_Q_CROSSCHECK.csv`与`AXIS_PHASE_CROSSCHECK.csv`记录逐行独立核验。C2 scene2的`FAILED_NO_RETRY`状态及恢复审查保留原样。该目录只包含离线分析产物。
