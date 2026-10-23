# 两篇指定论文的原文可达性与证据对照

检索限于这两篇指定论文，未访问或运行外部代码。检查了作者/机构记录与出版方页面；出版方页面打开返回 403。下文把可读到的机构元数据、出版方检索预览与全文证据严格分开。

## 1. Zhang 等，Neurocomputing 390 (2020), DOI: 10.1016/j.neucom.2020.01.052

URI DigitalCommons 的机构条目确认题名、作者、期刊卷页，并把“Link to Full Text”指向 DOI；该条目本身没有提供可下载稿件。其 ScienceDirect 落地页打开失败（403）。出版方检索预览可见摘要和“Preliminaries”中的离散系统式 `x(k+1)=f(x(k),k)+d(k)`，并注明 `||d(k)||≤d_M`；预览还显示论文覆盖一般 normal-form 系统、state-feedback 与 output-feedback 两种情形，以及 RBF/deterministic-learning 背景。**未取得或读到论文全文。**因此无法核验该文逐项自适应律、历史特征与预测标签的索引配对、投影/泄漏实现、定理假设与证明步骤；不能据摘要或预览认定它与 C5 的具体更新相同或不同。

可复核位置：URI 条目的作者/刊载信息和 DOI 链接（页面“Document Type”至“Link to Full Text”）；ScienceDirect 检索预览的“Preliminaries”“State-feedback case”“Output-feedback case”标题及系统式片段。[URI 机构条目](https://digitalcommons.uri.edu/ele_facpubs/974/)；[出版方页面/DOI](https://doi.org/10.1016/j.neucom.2020.01.052)。

## 2. Guo 等，Automatica 111 (2020), 108612, DOI: 10.1016/j.automatica.2019.108612

新加坡国立大学 Biorobotics Lab 的作者/机构页面提供作者、月份和期刊元数据，其“Source Document”链接指向 DOI，没有提供作者稿件。山东大学作者主页也确认该论文条目。ScienceDirect 落地页打开失败（403）；因此也**未读到全文或完整稳定性证明**。

出版方检索预览中可见若干正文片段： “Problem formulation”采用 Euler–Lagrange 机器人动力学；“Closed-loop robot dynamics”导出连续时间跟踪误差方程；“LS modulated composite learning law (12)”的解释片段称参数更新含跟踪误差驱动项 `Φ e₂` 和历史预测误差项 `K_w Θ⁺ ε`，并提到投影算子 `P(·)`。预览的摘要/正文片段称无需 IE 可证明闭环渐近稳定，在 interval excitation (IE) 条件下可证明指数稳定与参数收敛。上述是出版方索引预览所支持的概括，未据此补写未看到的增益限制、IE 矩阵条件或 Lyapunov 推导。

可复核位置：NUS 作者实验室页面作者/期刊信息与 DOI “Source Document”链接；ScienceDirect 检索预览的“Problem formulation”“Closed-loop robot dynamics”、更新律 (12) 解释片段及摘要的 IE 稳定性陈述。[NUS 作者实验室条目](https://cde.nus.edu.sg/bme/bioroboticslab/publication/compositelearningcontrolofroboti2020kai/)；[山东大学作者主页条目](https://faculty.sdu.edu.cn/guokai1/en/lwcg/664581/content/328213.htm)；[出版方页面/DOI](https://doi.org/10.1016/j.automatica.2019.108612)。

## 对当前 C5 可作的有限比较

按当前冻结的 C5 更新合同，控制器在离散仿真上每 10 个采样点形成一次过去区间标签；跟踪项在当前事件的 surface/特征上计算，历史预测项使用上一事件留下的特征/区间信息，并有有限幅及泄漏。它在时钟与误差配对上需要单独描述，不能因泛称“composite learning”就等同于上面任一论文。

对第二篇，已读到的预览支持一个有限的共同点：跟踪误差与历史预测误差都参与参数更新。C5 的离散事件/上一窗口标签、单步记忆和限幅泄漏实现，不能直接从该连续时间 Euler–Lagrange 机器人设计或其 IE 结论推出稳定性或参数收敛。对第一篇，只能确认其研究离散时间 normal-form 神经网络学习控制；全文不可达，无法作严谨的更新时序或稳定性逐项对照。

因此，这两篇资料足以提醒：不能把“离散神经网络学习”或“跟踪误差加历史预测误差的复合更新”作为已证明的新颖性，也不能移植其稳定性结论。它们不足以支持“首次”或排除与 C5 更新同构的主张。C5 的有限时域条件式证书仍不等价于实际闭环稳定性定理；需要取得并阅读两篇全文、完成逐式比较并另行证明 C5 的精确离散闭环条件，才可扩展这些结论。

## 检索边界

在限定的检索次数内，没有找到可直接读取的作者/机构/arXiv 全文：URI 页面仅链向 DOI，NUS 页面仅链向 DOI，两个 ScienceDirect 页面打开均返回 403。检索结果虽提供预览片段，但不作为全文证据。本记录不以摘要或二手页面填补缺失的方程和证明。
