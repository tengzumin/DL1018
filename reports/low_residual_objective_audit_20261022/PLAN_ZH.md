# 小残差目标复算：最小实施方案

状态：冻结候选脚本已通过一条TRAIN只读smoke，等待主审放行全TRAIN。

- 输入只用冻结训练index、1536条TRAIN cache、已通过父审gate的W0 raw-pred sidecar；不读raw MAT、事件H5、VAL、DEV或TEST。
- 每条按cache与sidecar记录SHA读前/读后核验，检查run身份、X14/phase/Y_clip逐元素相等；训练端点固定为 `np.arange(31,1999,5)`，394/运行。sidecar `pred_raw_valid`按 `endpoint-31`选取，不碰 `pred_applied_valid`。
- 逐条重放冻结 `teacher_data.EpisodeBank.windows` 的层次权重：double计算，最后转float32。目标用cache的float32 `y`；另用cache `raw`仅作未裁剪标签描述。
- 使用冻结 `fit_models.py` 的 SmoothL1（pred/3、label/3、beta=1、轴均值）重算W0与zero；记录按训练权重的loss、窗口质量、clip/raw RMSE与有符号bias。另记录每运行等权均值，不能和原层次目标混称。
- W0侧车预测为MATLAB等价double导出推理；全TRAIN表为“原损失定义诊断”，不是Torch逐位训练回放。全量固定readout梯度不在这版脚本中，待本轮loss审核后再决定是否另做纯Torch小批梯度核验/成本评估。
- 命令：先 `python -B reports/low_residual_objective_audit_20261022/replay_objective.py --smoke`；全量仅在主审批准后 `python -B reports/low_residual_objective_audit_20261022/replay_objective.py --execute-after-audit`。线程环境固定1。脚本不提供resume，输出目录有同名产物时fail-closed。
- 预计读取约1.16GB缓存+sidecar压缩文件，不复制旧数据；SHA前后与解压成本按保守2–6分钟估，写出派生CSV/JSON预计<20MB，远低于200MiB预算。单条预检结果：首条缓存与sidecar身份SHA匹配，cache X14/phase/y与sidecar X14/phase_code/Y_clip逐元素相等，raw预测1968×3全finite，394个训练端点为31..1996。

