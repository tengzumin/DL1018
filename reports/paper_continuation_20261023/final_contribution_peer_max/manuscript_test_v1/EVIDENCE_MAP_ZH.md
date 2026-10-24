# manuscript_test_v1 证据映射

本目录是从 `manuscript_dev_v1` 派生的独立 TEST48 稿件草案；原 DEV 稿未改动。草案截至 2026-10-24，状态仍为 `NOT_QUALIFIED`，用于主审逐项审核，不表示论文证据门已通过。

## 冻结结果与逐项核验

- 主原始审核为 `../../test_handoff_incident_v1/recovery_v1/raw_review_v5/RECOVERY288_FULL_RAW_AUDIT_v5.json`，SHA-256 `3ae6d02fb36beb6690696c4b34b63106169bd98acd0fc5191140ef39329ab6a2`；冻结统计为 `../../test_handoff_incident_v1/recovery_v1/statistics_v5/RECOVERY288_FINAL_STATISTICS_v5.json`，SHA-256 `d7e3af0215e159a885691c8a4ab755333b90345650afc5370b65814f9498e1a8`。所有 288 行、六方法统计及保留的逐场差值均来自这些冻结输入。
- 根独立性能复算为 `../../test_handoff_incident_v1/recovery_v1/statistics_v5/PARENT_INDEPENDENT_PERFORMANCE_REVIEW_v1.json`，SHA-256 `5315c7cd1cbef22fff407746837c02344e8e4473602da44b9082a2f1fce95f8d`。该复算支持 46/48 的 C5 对 B 胜场、组均值与固定设计区间，不代表跨 seed 推断。
- 根表格复核 `../../test_results_final_v1/PARENT_TABLE_REVIEW_v1.json` 报告 288 行、11,232 个数值单元逐项匹配冻结统计，且图 2 目检无裁切、组别和量级一致；该文件的 SHA-256 写入 `input_identity_v1.json`。这核验转录与图表，不等同科学结论或证据门通过。
- 当前要求检查点 `../../PAPER_EVIDENCE_REQUIREMENTS_AUDIT_CHECKPOINT_v3.json` 标记论文仍为 `NOT_QUALIFIED`。TEST 性能、全量表和 CI 已有证据；贡献审查、最终稿/渲染和复现发布审查仍在进行。
- 完整 48×6 配对长表 `../../test_results_final_v1/paired_complete_48x6_long.csv`（288 行）及全部 comparator 的 C5 输场表 `../../test_results_final_v1/C5_M110_losses_all_comparators.csv` 是逐场结果来源。本文正文列出所有 C5 输场；全部方法指标、路径和哈希在配对表中保留。
- 统计区间固定为每组 10,000 次配对物理场景 bootstrap、seed 2026102301、contrast 间共用索引、线性 2.5%/97.5% quantile。它们是该固定仿真设计的描述性区间，无多重比较校正，也不是训练 seed 的抽样推断。

## 本文术语与证据边界

正文显示名与冻结 `methods_order` 的映射如下：

| 正文名称 | 冻结方法 ID |
|---|---|
| B | `B_TRACEABLE` |
| DSSM14 | `CORRECTED_DSSM14_G12_R32` |
| KAN14 | `CORRECTED_KAN14_G12_R32` |
| C5-M110 | `C5_M110` |
| Frozen W0 | `C5_FREEZE_TRAINED_W0` |
| NoPred | `C5_NO_DELAYED_PREDICTION` |

`../../test_results_final_v1/RESULTS_REPORT_ZH.md` 是这些冻结统计的整理说明，SHA-256 `b6c39771616faea78608db929a3e5c74447299d369bfeae8ab2b87cc08cf94c7`。正文另外引用 `../../test_results_final_v1/axis_early_late_summary.csv`、`task_wind_axis_safety_saturation_timing_summary.csv`、`paired_scene_bootstrap_ci.csv`、`paired_sensitivity_wlt_1_10um.csv`，均由冻结统计整理；未在本稿中重新评分、重新 bootstrap 或运行仿真。

理论部分以 `../../THEORY_FINITE_PATH_SCOPE_ACCEPTANCE_v2_ZH.md`、`../../BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md` 与 `../../BOX_PROJECTION_BOUND_NUMERIC_SCOPE_ADDENDUM_ZH.md` 为准。已经接受的有限范围是：对实际延迟预测、tracking/leak 和盒投影更新构造后验有限路径 Q 界，并在全部 DEV72 已审核轨迹上完成数值实例化。数值比值为 3.740385--31.331274；使用 $L=1+10^{-9}$ 与每元素 $10^{-10}$ 残差包络，普通双精度复核不是向外舍入区间证书。该界不推出先验 Plant 域不变性、闭环稳定、参数收敛、未来误差小或胜过 B；旧局部先验 ISS/domain 证书仍未证明。本文没有把 DEV72 理论结论声称为 TEST48 的理论实例化。

## 保留的审核限制

- 原始 DSSM 的自然进程退出状态为 UNKNOWN，scene32 缺少 `runIdentity`；恢复后的 DSSM tail16 有 OS0 记录，其他方法块有 OS0 记录。旧六进程 OS0 gate 仍为 UNMET，没有重新分类。
- `../../c5_eight_loss_recovery/v2/HISTORICAL_TEST_EXPOSURE_INCIDENT_v1.json` SHA-256 `42f1c2f672091ce46040222f1878cbf537adb647081f342a6378f353ed616c2b` 记录了两个旧 TEST 场景摘要曾被意外展示；记录同时称本分支 C5 模型/选择在此之前已冻结，且与当前 TEST48 的物理重叠为 UNKNOWN。这里仅使用该 incident 事实，未读取旧混合报告或复制其任何分数，也不声称从未接触过历史 TEST 信息。
- 本文仅涉及冻结 C5 与 TEST48 已有审核数据。单一模型 seed、单一仿真 plant/actuator、理想全状态反馈、无真实飞行以及未隔离计时均限制外推；C6不在本文中讨论或作为C5证据。

## 相关工作核验

`../../LITERATURE_PRIMARY_UPDATE_20261024_ZH.md` 记录了主审对原始资料的边界核验。Altawaitan 与 Atanasov 的 arXiv:2604.04039v1 已阅读 IV-A/B 式10--18，支持“离线多步模型 + 在线低秩二阶适应”这一描述；UZH LOTF 项目页支持其残差模型学习与策略优化交替的概述。本文只用于限定宽泛 novelty claim，不主张复现、优先权或完整算法代码比较。文中没有补造未核验的等式级相关工作结论；Zhao 2024 全文仍明确标成无法作等式级对照。

Jiang TNNLS 2022 是最接近的已核结构先例。本稿根据 `../../literature_peer_challenge_v1/PEER_CHALLENGE_JIANG_TNNLS_v1_ZH.md`、其 JSON 审核，以及 `../../literature_primary_increment_v1/Jiang_TNNLS_dualarm_author_copy.pdf` 和文本副本核对原文第 5--7 页：式 (37) 为命令滤波，式 (44)--(47) 构造带遗忘的历史积分与预测误差，式 (48) 合并跟踪/预测权重更新，式 (49) 投影权重；定理 1/式 (59)--(61) 依赖该文 PPE 假设。正文因此明确不把命令滤波、神经近似、跟踪/预测复合适应或投影称为首次，也不迁用该定理。C5 的差别被限定在具体离散时序、PCF坐标目标、完成区间标签和盒投影实现，不能单由差异推得优先权。

四旋翼离散命令滤波相关文献的访问边界由 `../../literature_quadrotor_primary_v1/QUADROTOR_CFB_ACCESS_AND_COVERAGE_v1_ZH.md` 记录：Zhao et al. (2024) 的题录可确认，但未取得可读全文，无法核对其目标/标签方程。因此正文仅将其作为宽泛相关先例并披露等式级比较缺口，不宣称覆盖或不覆盖 C5 特定目标。
## 输出与构建

- `main.tex`、`references.bib`：正文及引用。
- `main.pdf`：9 页渲染稿。
- `rendered_final/page-1.png` 至 `page-9.png`：Poppler 低负载页面渲染，供版式目检。
- `figures/fig1_paired_Q_C5_vs_B.pdf`、`figures/fig2_grouped_Q_comparison.pdf`、`figures/fig3_paired_bootstrap_CI_ALL48.pdf`：从 TEST 结果包复制的三幅图，数值未重新计算。
- `input_identity_v1.json`：DEV 原稿、所有关键冻结输入、图表、本文源文件、PDF 和每页 PNG 的 SHA-256 与相对路径。
- `REVISION_LOG.md` 与 `revisions/pre_jiang_v1/`：Jiang 文献复核前的稿件、文献表和 PDF 快照，以及此次修订边界。

在本目录的 PowerShell 7 中可复现文字排版：

```powershell
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

本稿排版只调用 LaTeX/BibTeX 和 PDF 渲染；未运行 MATLAB、Plant、训练、正式评分或新 bootstrap。`latexmk` 在此机器因缺少 Perl 引擎不可用，已改用 `pdflatex` 与 `bibtex` 直接构建。
