# DEV72 英文短稿证据映射

状态：内部限定初稿。根决定仅接受“可在明确限定下继续”的贡献定位；TEST48 尚未执行，本文不作为TEST放行或论文证据包达标结论。

## 论文主张与证据

| 稿件内容 | 证据来源与锁定身份 | 可写范围及限制 |
|---|---|---|
| C5固定方法：DSSM14、seed 2026102001、step 60000、14输入、window 32、W0与normalizer身份、M110 | `experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_INPUT_LOCK_v3.json`，SHA-256 `82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75`；helper `delayed_prediction_step_candidate.m` SHA `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d` | 代码身份固定；不声称网络结构首创。输出在更新前计算；100 Hz事件，首ready事件无旧标签；其余配置按源记录披露。 |
| 预训练目标与在线目标差异 | `ROOT_CAUSE_AND_REMEDY_C5_UPDATE_ZH.md`、`METHOD_AND_EVIDENCE_DRAFT_ZH.md`、固定helper | 预训练目标是物理加速度残差 `a_actual-a_req`；在线监督由已完成10 ms速度区间相对 `a_M=a_req-M r_f` 构成，包含PCF坐标项。Frozen W0是冻结已有网络权重并移除在线更新，不能写成删除网络或网络无价值。 |
| C5 对 B 的完整 DEV72 性能 | `DEV72_METHOD_RESULTS_INCREMENT_ZH.md`；B与C5完整审核和新旧B数值复现的根主审记录；主指标为逐航次20,000个位置状态点 | C5 64胜/8负、Q 11.558928371 vs 17.058080675 mm；HF W09–W14 10.179304496 vs 10.719024064 mm；无风W15 6.334075115 vs 7.647291830 mm。总32.24%是累积差异，不归因于单一预测项或M110。 |
| 匹配消融全量结果 | 全量审计 `C5_MATCHED_ABLATION_DEV72_BOTH_RAW_PARENT_AUDIT_v3.json`，SHA `ec696b9e80a1f22af26b8ef58cb3fcc0a275102ee68b82b286ddf6d54d0a75ba`；独立统计 `MATCHED_ABLATION_DEV72_INDEPENDENT_SUMMARY_v1.json`，SHA `71b5b437b4d2515ef9abf1fa8ab19379a9e6e5520813ca5b499caed749fab9bd`；逐场CSV SHA `9ad962499032826a31ee0f4c3b424ec45793272f411314ab6c35d3356e34e49b` | Freeze W0=34.910909424 mm，C5对其72/72胜；NO_PRED=12.110170832 mm，C5对其54胜、18负。两个对照保持相同PCF、M110、readiness、标签、特征、时钟及其余控制项。 |
| 配对任务/组差异与反向场 | 同一独立统计JSON及全配对CSV；`C5_ALL_18_REGRESSIONS_VS_NO_PRED_v1.csv` SHA `9646266ed06853967ac877e25066b471a4a040fae43cd9df685afafbc4d0b259` | 全部54个C5胜场改善均超过10 μm；18个反向场完整保留。C5−NO_PRED的ALL/HF/W15描述性95%配对scene-bootstrap区间分别为[-0.725160,-0.374423]、[-0.741756,-0.138022]、[-1.775262,-0.856830] mm。T2均值差仅-0.001067120 mm，区间[-0.202649,+0.196672] mm跨0。Bootstrap使用物理scene为单位、10,000次、seed 2026102301；无多重比较调整，不能作独立TEST推断。 |
| T2方向数据更正 | 配对CSV符号独立复算：C5−NO_PRED<−1e−12 m计C5胜，>+1e−12 m计NO_PRED胜；方向勘误及其勘误见 `../PEER_T2_DIRECTION_ERRATUM_v1_ZH.md/json` 和 `../PEER_T2_DIRECTION_ERRATUM_v2_ZH.md/json` | 正确方向为C5 13胜、NO_PRED 11胜、0平。原peer审核表格和正文都把T2方向写反；勘误v1的JSON方向值正确，但其Markdown错误地称原正文正确。勘误v2明确更正此点。当前稿按配对CSV方向写。 |
| 固定坐标干预的效果 | `DEV72_METHOD_RESULTS_INCREMENT_ZH.md` 和独立peer审核的其他表项 | C5 M110相对C3 M111为53胜/19负，总Q仅改善0.200317 mm；HF改善0.440679 mm，W15改善0.008825 mm。支持有限开发集效应，不支持全局最优或将32.24%总收益归给最后坐标改变。 |

## 有限路径理论与数值范围

- 主证明：`BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md`，SHA-256 `48b63a205f27d4ef595fcf6a25ef1c8b45c8169c11251a77d244bc0c66b85406`。只陈述固定比较器、实际tracking/leak项、延迟标签、一次联合盒投影对应的逐路径预测误差不等式；短稿不重写证明。
- 数值补件：`BOX_PROJECTION_BOUND_NUMERIC_SCOPE_ADDENDUM_ZH.md`，SHA `0acccfb690f4757b90b8aa435f8e03ec31a9fb2fe691df45a7673d162244ef2a`。采用`L=1+1e-9`与每元素`1e-10`数值残差包络；普通浮点核验不等同向外舍入区间证书。
- 非作者证明复核：`BOX_PROJECTION_BOUND_NONAUTHOR_REVIEW_v1_ZH.md`，SHA `df4f7c5cfb6e4864d0fcc05bff31fea6801c3d688fc974d6e8ecbdcda9df7b3d`。
- 实际物理映射：`ACTUAL_PHYSICAL_BRIDGE_DEV72_CHECK_v1.json`，SHA `381685296211cbdaf16dafe6e5593711abeb17d6764a11703d09f143d5d91c2c`；72场共1,440,000个递推样本和1,416,240个旧标签采样点的普通浮点复核通过，最大映射残差约`8.9e-16`。它不是Plant先验稳定性、独立TEST或因果消融证据。
- 接受范围：`THEORY_FINITE_PATH_SCOPE_ACCEPTANCE_v2_ZH.md`，SHA `a7d29ad6bd8cb6f5175cced87b181b2ff22317dfb0303428dfd3efa59aaff7ec`。该数学门仅以条件有限路径误差界通过；不证明Plant先验稳定、参数收敛、域不变、跨轨迹性能或机器严格区间界。所报告界较松。

## 文献身份和访问范围

`references.bib` 的身份来自原始arXiv导出BibTeX、Wiley/DOI出版页面和Crossref BibTeX/元数据；正文只用这些已核身份支持背景表述。

| 文献 | 原始身份入口 | 已核范围及用法 |
|---|---|---|
| O'Connell et al., *Neural-Fly Enables Rapid Learning for Agile Flight in Strong Winds*, Science Robotics 7(66), 2022, DOI 10.1126/scirobotics.abm6597 | [arXiv全文](https://arxiv.org/abs/2205.06908)，[原作者代码仓库](https://github.com/aerorobotics/neural-fly) | 原始论文/仓库已核其预训练表示、线性系数与复合适应先例；不把本稿的离散实现与其性能/稳定性结论等同。 |
| Parikh et al., *Integral concurrent learning: Adaptive control with parameter convergence using finite excitation*, IJACSP 33(12), 1775–1787, DOI 10.1002/acs.2945 | [Wiley出版页面](https://doi.org/10.1002/acs.2945)，[作者机构PDF](https://ncr.mae.ufl.edu/papers/IJACSP192.pdf) | 出版身份及摘要/定理相关段落已核；积分监督不是本稿创新。其参数收敛依赖有限激励条件，本稿不借用该结论。 |
| Fisher & Annaswamy, *Discrete-Time Adaptive Control of a Class of Nonlinear Systems Using High-Order Tuners*, arXiv:2204.12634v3 | [arXiv原文](https://arxiv.org/abs/2204.12634v3) | 原始稿身份核实；文献记录已读第2–4页，理解其假设不同，不移用其稳定性定理。 |
| Huang et al., *DATT: Deep Adaptive Trajectory Tracking for Quadrotor Control*, arXiv:2310.09053v3 | [arXiv原文](https://arxiv.org/abs/2310.09053v3)，[原作者代码仓库](https://github.com/KevinHuang8/DATT) | 原文3.3节与作者仓库相关代码已核；仅用于说明学习跟踪与独立扰动估计通道已有先例，不推断给本项目追加估计器的效果。 |
| Zhao et al., *Discrete-Time Adaptive Fuzzy Command Filtered Backstepping Control for Quadrotor Unmanned Aerial Vehicle Systems: Theory and Experiments*, IEEE TFS 32(6), 3618–3628, DOI 10.1109/TFUZZ.2024.3379510 | [IEEE DOI入口](https://doi.org/10.1109/TFUZZ.2024.3379510) | 作者、标题、期刊卷期页由Crossref元数据核对；本次未取得全文，只在正文提示该方向已有论文，不作定理、更新律或结果比较。 |

两篇2020相关论文在`LITERATURE_ACCESS_AND_CLAIM_UPDATE_ZH.md`中只有出版社预览和访问受限记录。它们未列入当前BibTeX，也未用于具体定理比较；提交前仍需获取完整正文、核完整书目信息并补做逐条新颖性审查。参见：<https://www.sciencedirect.com/science/article/pii/S000510981930473X>；<https://www.sciencedirect.com/science/article/pii/S092523122030103X>。

## 尚未完成的证据门

根最新决定和`CURRENT_EVIDENCE_GATE_MATRIX_v2_ZH.md`均记录：TEST0；测试入口代码和无Plant DEV72全输入等价、固定六方法身份等工程门尚需完成并另行审查，未授权解封TEST。本短稿因此没有TEST数字、正式隔离耗时或真实飞行主张。当前仅有一个固定模型训练seed，不能支持跨seed可靠性。论文是否足够新颖或适合投稿仍需人工核对原始文献全文；本稿是候选定位，不保证录用。
