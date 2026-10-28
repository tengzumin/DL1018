# 开发证据论文初稿主审

接受当前稿作为开发阶段初稿；不标记论文证据包完成，也不替代独立测试。根已读取完整LaTeX、引用表和T2勘误v2，核对式(B)及浮点补件、配对表数字，并实际目检渲染第4页的表格和数学公式。执行者另报告五页均目检；最终编译日志显示5页，未发现未解析引用或版面警告。

冻结稿：`final_contribution_peer_max/manuscript_dev_v1/main.tex`，SHA-256 `5db7a99d8818bea04aa2caf31f65ef943dbd34d688409fee2d343bdc6bef02b4`；PDF SHA-256 `c26550bf036484391bce2f9d879fcc4d66ec045e16257e45da7ab47da00c6968`。本文是内部短稿，尚未纳入TEST结果与正式隔离耗时。

已修正的实质点：明确理想实数投影界与实际浮点更新之间的delta余项；将8.9e-16仅限实际物理桥接检查，不泛化为所有标签/事件误差；胜数敏感性仅限已核C5对B/NO_PRED/FrozenW0；T2正确为13胜11负，均值近零且区间跨零；ICL期刊年份2019，保留2018在线发表信息。原peer文档与含错误陈述的勘误v1均保留，规范更正以 `PEER_T2_DIRECTION_ERRATUM_v2_ZH.md` 为准。

参考身份复核使用原始来源：[Fisher与Annaswamy的arXiv v3](https://arxiv.org/abs/2204.12634v3)、[DATT作者论文](https://arxiv.org/abs/2310.09053)、[Wiley的ICL期刊条目](https://onlinelibrary.wiley.com/doi/abs/10.1002/acs.2945)。IEEE 2024论文全文访问缺口保留，不作定理级比较。没有增加全文已读或广泛首创主张。

最终稿仍需补：一次独立TEST48与全部六方法配对、安全和耗时；各任务/风单元、XYZ/早后段、所有输场的补充表；包含原corrected DSSM14和KAN14的最终比较；明确W13在开发集中仍较B差，以及有限单seed/理想反馈范围。相关完整开发记录已存在，短稿不应被当作最终完整实验章节。若独立测试失败，按冻结规则如实报告，不据此改候选或重跑测试。
