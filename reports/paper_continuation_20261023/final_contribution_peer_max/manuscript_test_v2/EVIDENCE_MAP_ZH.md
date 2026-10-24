# manuscript_test_v2 证据映射

状态：内部证据稿，等待根最终裁决。本修订不改算法、候选、评分规则或任何冻结数值；manuscript_test_v1 完全保留。

## v2 变更与数据来源

初始复制仅包含 v1 的 main.tex、references.bib 和三张 figure PDF；没有复制 LaTeX 中间文件、缓存或旧渲染图。v2 新增两处限定说明，PDF和页面PNG由本目录重新编译渲染生成。

1. **DEV M111→M110 单因素开发对照。** 冻结的 72 场配对指标显示：M111/C3 scene-equal mean Q 为 11.759244913 mm，M110/C5 为 11.558928371 mm，配对均值差 −0.200316542 mm；M110 在 53/72 场较低、19 场较高。高频 DEV 组 mean Q 降低 0.440678602 mm，文中按六位小数报告为 0.440679 mm。该结果用于开发/选型。TEST48 的六方法中没有 C3/M111 mask-only arm；因此它不是独立 TEST mask 消融，且不把 C5 相对 B 的全部 TEST 收益归因于 mask。

   输入：C5_DEV72_RAW_METRICS_v3.csv，SHA-256 3986e5ed42986c317b64fecfa508d5791709812f5c8443bf04cbce52e04a3a4c；C5_DEV72_RAW_PARENT_REVIEW_v3.json，SHA-256 bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab；C5_AXIS_COORDINATE_SCREEN_TASKBOOK_ZH.md，SHA-256 5c3f19548a5cd1f6e337d20dcd0c48f81560d3907d5a24d20676e9cf62545c38；C5_CONTRIBUTION_SCOPE_DRAFT_ZH.md，SHA-256 b42f74a17ffef3028a05b7fc3a3d2a4f219c76ee025b1820acf5d7fdd609a604。

2. **历史 TEST 重叠的后续元数据核验。** 原 incident 仍保留：当时两条旧 TEST 摘要的展示事实不变，且当时与当前 TEST48 的物理重叠记录为 UNKNOWN。之后对两个已识别旧 ID（TEST_C10_34_J1/J2）的四份旧 config/执行快照，与当前48场在12个共有外生字段上作了2,304项比较；未发现任一旧 ID 与当前场景的完整共有字段匹配，七个核心字段（位置/速度/加速度参考、arms command、rho_true、rhoDot_true、wind）各为0/48匹配。旧源缺少 arms/rho_hat 与 arms/rhoDot_hat，故无法核对完整14字段相等。此结论只覆盖这两个已识别 ID 和可用元数据，不证明所有历史 TEST 场景均无重叠；incident及历史曝光披露继续保留。重叠核验元数据明确未读旧报告正文、历史成绩或轨迹日志，未调用 scorer。

   输入：HISTORICAL_TEST_OVERLAP_METADATA_v1.json，SHA-256 f836edb1049e2fb92c1e1d5320949da959d7cf34adcd64eaf3a7e850e2ac11d8；PARENT_EXTERNAL_OVERLAP_REVIEW_v1.json，SHA-256 9b5fab37332fe0e67ffb9401d060d1219929fc012ebdea158d12c3e4431041c7；原历史暴露 incident JSON，SHA-256 42f1c2f672091ce46040222f1878cbf537adb647081f342a6378f353ed616c2b。

## 构建与边界

从此目录使用 PowerShell 7 构建：
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex

final main.pdf 与 rendered_final/page-1.png 至 page-9.png 为本版编译/渲染输出。无未定义引用或 Overfull/Underfull 行。输入副本与最终输出 SHA-256 见 input_identity_v2.json；身份清单自身 SHA 另行报告以避免自引用。

方法和分数仍来自冻结的六方法 TEST48 审核与统计；v2 没有增加 TEST 仿真或 TEST mask 单因素实验。历史 overlap 判断不能消除曝光，也不能扩张为全历史集合盲测结论。