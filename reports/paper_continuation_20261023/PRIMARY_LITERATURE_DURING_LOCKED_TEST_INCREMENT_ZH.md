# 固定TEST运行期间的原始文献补查

UTC 2026-10-23。只进行网页和轻量文本核对，没有读取TEST性能、运行外部代码或改变冻结候选/参数/计分。此前文献、访问失败和限定贡献决定保留。本记录用于完善相关工作，不用来反馈调整TEST。

## 更接近的复合学习与指令滤波先例

Jiang等，*Composite-Learning-Based Adaptive Neural Control for Dual-Arm Robots With Relative Motion*，IEEE TNNLS 33(3):1010–1021，2022；先行在线发表为2020-12-23。作者为Yiming Jiang、Yaonan Wang、Zhiqiang Miao、Jing Na、Zhijia Zhao、Chenguang Yang。身份与摘要由[IEEE出版页](https://doi.org/10.1109/TNNLS.2020.3037795)核对；[作者机构记录](https://robot.hnu.edu.cn/info/1032/1071.htm)与[机构PDF](https://robot.hnu.edu.cn/__local/9/ED/C7/44E36AB21A4F7DFA03929198159_5CECB4EB_308954.pdf)提供原始来源。

本次直接打开机构PDF两次超时；检索服务从同一原始PDF返回了第6页正文。因此只计为原文局部核对，不能称全篇或完整证明已经复审。该页的式(44)–(49)给出带遗忘的历史回归积分、预测误差、跟踪与预测联合更新以及投影；定理1明确依赖PPE。结合出版摘要，指令滤波与这种复合学习的组合已有先例。本文没有认证PPE，不可移用其收敛或稳定结论。

根判断：不能把“指令滤波＋NN＋积分历史预测＋tracking＋投影”作为DL1018的原创组合。当前候选可讨论的差异须具体落到冻结M110目标坐标、已完成区间标签与实际离散输出/更新时序，以及同一物理链上的匹配消融和独立测试。它们是否达到投稿新颖性仍需审稿判断；测试收益不能替代该判断。不据此更改已冻结方法或中断测试。

## 两篇2020文章的身份与访问范围

[Guo等的出版社预览](https://www.sciencedirect.com/science/article/pii/S000510981930473X)及[NUS作者实验室记录](https://cde.nus.edu.sg/bme/bioroboticslab/publication/compositelearningcontrolofroboti2020kai/)一致给出Kai Guo、Yongping Pan、Dongdong Zheng、Haoyong Yu，题名 *Composite learning control of robotic systems: A least squares modulated approach*，Automatica 111:108612，2020，DOI 10.1016/j.automatica.2019.108612。预览已足以确认历史预测、跟踪联合更新和伪逆调制的先例；没有取得全文完整推导。部分二级索引的Hai Guo／Dongdong Zhang拼法与原始来源不符，不采用。

[Zhang等的URI机构记录](https://digitalcommons.uri.edu/ele_facpubs/974/)与[出版社预览](https://www.sciencedirect.com/science/article/pii/S092523122030103X)核对为Jingting Zhang、Chengzhi Yuan、Cong Wang、Paolo Stegagno、Wei Zeng，*Composite adaptive NN learning and control for discrete-time nonlinear uncertain systems in normal form*，Neurocomputing 390:168–184，2020，DOI 10.1016/j.neucom.2020.01.052。可核其离散学习、状态/输出反馈与经验复用主题；全文访问缺口仍在，不套用部分激励、权重收敛或输出反馈结论。

2024四旋翼论文DOI 10.1109/TFUZZ.2024.3379510本次仍不能取得全文；不据猜测文档编号或二手摘要作算法对照。2025 TAES DOI 10.1109/TAES.2025.3567440仅检索到相关题录，而IEEE访问需浏览器验证；本记录不作其定理或控制律主张。

本记录不修改已审条件有限路径误差界，也不将它升级为先验Plant稳定性、参数收敛或区间认证。原始文献的具体稳定性假设与本项目的后验路径分析须分开陈述。
