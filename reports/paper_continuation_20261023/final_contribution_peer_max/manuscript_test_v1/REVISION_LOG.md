# 修订记录

## Review-driven revision: Jiang TNNLS precedent

- **保留的前一稿：** `revisions/pre_jiang_v1/main_pre_jiang.tex`、`references_pre_jiang.bib`、`main_pre_jiang.pdf` 与 `input_identity_pre_jiang.json`。该快照对应首次 9 页 TEST48 编译稿，数值与当前稿相同；SHA-256 见该快照的文件哈希与前版身份清单。
- **新增文献边界：** 增引 Jiang et al., *Composite-Learning-Based Adaptive Neural Control for Dual-Arm Robots With Relative Motion*, IEEE TNNLS 33(3):1010--1021 (2022; online 2020), DOI 10.1109/TNNLS.2020.3037795。依据本地作者机构副本原文第 5--7 页/式 (37)、(44)--(49)、定理 1 与式 (59)--(61)，明确它已覆盖命令滤波、RBF 神经控制、跟踪/历史预测复合更新和投影；同时写清其连续时间双臂机器人、遗忘历史矩阵、PPE 假设与范数球投影，与 C5 离散四旋翼、固定 PCF 坐标、10-ms 完成区间标签和逐元素盒投影的具体差异。未移植 Jiang 的 PPE 或定理结论。
- **结论修订：** 将“46 场平均 RMSE 较低”的歧义改成“46/48 场景级 $Q$ 较低，且组等权平均 $Q$ 较低”。冻结数据、图、CI、输场清单和所有数值均未更改。
- **渲染校验：** 修改后用 `pdflatex`/`bibtex` 重新编译并渲染 9 页；最终 `main.log` 无未定义引用、`Overfull` 或 `Underfull` 报告。
