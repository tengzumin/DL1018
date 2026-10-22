# Round2 原始文献主模型复核

日期：2026-10-22。复核对象为 theory_and_literature.md 和 theory_literature.csv 中的五篇原始论文。结论：元数据基本相符；Farrell 引用链接来源与期刊记录不一致，已在主报告和 CSV 中修订。其它论述整体可用，但必须保留摘要/版本/适用域的限制。

## 发现并修订的来源错误

Farrell 等人的 IEEE TAC 2009 期刊记录 DOI 为 [10.1109/TAC.2009.2015562](https://doi.org/10.1109/TAC.2009.2015562)。此前主报告把一个作者上传 PDF 当作该期刊原文；逐页核对发现 PDF 内容是同题作者的 ACC 2008 会议稿，而不是 TAC 54(6), 1391–1395 的期刊版本。对应会议版本另有 DOI [10.1109/ACC.2008.4586773](https://doi.org/10.1109/ACC.2008.4586773)。

ACC 2008 版本的 Theorem 1 在 Assumptions 1、4、5 及其控制律 (11) 下证明末级普通误差 x-tilde_n 和补偿误差 v_i 指数收敛；不能写成全部普通跟踪误差收敛。Theorem 2 在 Assumptions 1–4 下给出普通误差与标准反步解的 O(epsilon) 偏差，以及滤波状态相对理想命令/导数的 O(epsilon) 偏差，epsilon=1/omega_n。TAC 期刊全文未能访问，因此报告现在把具体定理限定为 ACC 稿；不可假设 journal 版逐式相同。

## 其余四篇

- Dong et al.，*Command Filtered Adaptive Backstepping*，IEEE TCST 20(3), 566–580 (2012)，元数据相符。IEEE 摘要/作者正式材料支持有限时长初始化、初始化期内信号有界，以及 generalized-parameter strict-feedback 类系统运行期与传统 adaptive backstepping 相同的理论性质。必须限定该系统类别和阶段，不代表同轨迹、当前 DL1018 的完整闭环保证或特定定理编号。
- Choi–Bang，*Adaptive command filtered backstepping tracking controller design for quadrotor unmanned aerial vehicle*，SAGE Part G 226(5), 483–497 (2012)，元数据和摘要相符。摘要支持在线补偿质量、惯量、执行器增益和推力器失准；command filters 用来实现执行器/状态约束；饱和期使用 Lyapunov 中修改的跟踪误差来纳入饱和效应并保证稳定。不能泛化成任意硬饱和处理，也不能替当前代码背书。
- Ioannou–Kokotovic，*Instability Analysis and Improvement of Robustness of Adaptive Control*，Automatica 20(5), 583–594 (1984)，元数据相符。官方摘要把有界/指数残差结论限定到含寄生动态与扰动、主导相对阶为 1 的特定修改控制器与充分条件。不可把它等同于项目的泄漏项理论。
- Cai–de Queiroz–Dawson，*A Sufficiently Smooth Projection Operator*，IEEE TAC 51(1), 135–139 (2006)，元数据和摘要相符。论文提出的投影算子具有任意阶连续可微性质，适用于需多次微分 adaptation law 的鲁棒 backstepping。项目硬盒截断不是该算子。

## 审核依据与界限

Farrell ACC 原文通过作者上传 PDF 核读，会议 DOI/记录用于区分出版版本；IEEE TAC 页被访问限制阻挡。Choi 摘要来自 SAGE 出版页面；Cai 摘要来自 Idaho National Laboratory 正式出版记录；Ioannou–Kokotovic 摘要来自 Elsevier ScienceDirect 出版记录。Dong 期刊全文不可得，本项按 IEEE 摘要/正式作者页面收窄。未声称这是系统综述，也未据此声称存在文献空白。

主报告与 CSV 已同步修订。此复核不改变任何代码、模型、数据或实验决定。
