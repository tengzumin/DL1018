# 固定分轴M的符号范围补充

主审在原`FINITE_HORIZON_CERTIFICATE_TASKBOOK_ZH.md`的纯理论范围内，加入固定C5的`M=diag(1,1,0)`；不授权新Plant、训练或TEST。本补充不覆盖动态M或扫描M。C5机制任务书SHA为`5c3f19548a5cd1f6e337d20dcd0c48f81560d3907d5a24d20676e9cf62545c38`，核心静态审核见`../c5_axis_coordinate_parent_review/C5_ALGORITHM_PARENT_REVIEW_v1.json`。

当前K1/K2与M可交换，因此逐轴状态取`[e; s−M eta]`，固定2×2矩阵A不变，辅助输入改为`[dt M eta; 0]`；残差为`dotv−(aReq−M r_f)`，采样余项的PCF项同样乘M。所有过去区间、输出先于更新、预ready/末窗口边界、clip/ramp及H状态依赖限制沿用原任务书，不得从标量m的推导无说明地跳到动态或非交换矩阵。

仅作固定A代数检查，主审算得两个输入通道的20,000样本绝对L1核和约0.8及0.2；未以此证明forcing统一有界或闭环稳定。构造者应独立核验解析非负核与卷积不等式，并由未撰写证明者复核。
