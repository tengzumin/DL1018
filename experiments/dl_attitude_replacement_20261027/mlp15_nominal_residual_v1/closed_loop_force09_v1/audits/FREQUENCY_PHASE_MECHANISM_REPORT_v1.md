# HF 双环频率与相位机制审计

只读分析匹配 HF W09–W14 DEV/VAL raw；未运行 Plant、未读 TEST、未用真惯量/Jdot或将风真值作为部署输入。机器可读明细见 [JSON 报告](FREQUENCY_PHASE_MECHANISM_REPORT_v1.json)、[频谱与命令回放](HF_C5_PRESERVING_COUPLING_AUDIT_v1.json) 和 [GRU tracking逐事件审计](../../../gru_tracking_force09_v1/audits/GRU_TRACKING_HF_TRACE_AUDIT_v1.json)。

## 主要证据

- 原 MLP HF6 的 task→未滤波 command-filter target 同迹线指标为 **80.929 mrad**，task→记录的filtered reference为 **63.832 mrad**，实际task误差为 **61.355 mrad**（B为 **57.619 mrad**）。滤波同时改变幅值和相位，不能将差异只说成延迟。提高command-filter带宽追未滤波target没有得到当前证据支持。
- 低通回放使用单一 `fc=18/(2π)=2.865 Hz`，其中18 rad/s只锚定配置的roll/pitch `command_filter.wn`名义尺度；它不是姿态内环带宽，也不是command filter二阶传递函数的等价替代。该一阶LP同记录filtered-reference/task指标为 **61.986 mrad**，仍比B实际HF task高 **4.367 mrad**。此类同迹线值不是可达误差下界/上界，也不能预测新闭环的Q；LP收益有限，当前不优先做闭环LP试验。
- 原MLP补偿力多数能量在10 Hz以下：0.1–1 Hz **0.0498 N**、1–2.865 Hz **0.1011 N**、2.865–10 Hz **0.2711 N**。该LP对相应频带保留约 **99.5% / 83.2% / 62.7%**，说明它会削弱有用低频补偿，并非只去掉高频纹波。
- 全局把位置NN补偿力缩为0.9，MLP HF6 task由 **61.355→60.502 mrad**，Q由 **10.825→12.250 mm**；GRU HF6 task由 **61.199→60.303 mrad**，Q由 **10.141→11.717 mm**。均改善少量task但显著损失位置，不能作为共同解。
- B/C5的1–2.865 Hz同迹线分析中，位置误差与task姿态误差相干度/相位（横向两轴）为B **0.824/0.814**, **+2.5°/+8.7°**，C5 **0.934/0.915**, **+26.9°/+37.8°**。仅作离线解释、扣除记录风力后，加速度误差与姿态误差相位在两者都接近0°。这说明跨环相位关联受扰动与外环响应影响，不能作因果归因；风力不应作为运行时输入。
- GRU tracking force09的6场逐事件审计通过：每场1999次更新、平均间隔 **10 ms**，`filtered reference − actual ZYX Euler`误差参考、body-rate输入、实际ZYX `T`与`Tᵀ surface`坐标、输出前权重/更新后状态、`q_raw→clip→beta→J0`及`nominal−estimateTorque`符号最大重放差 **7.1e−15**。无姿态残差触发dmax裁剪；tracking源hash与parent一致。位置缩放alpha在RELEASE、run_start、run_status和解码后的raw身份字段均为 **0.9**，没有发现GRU tracking的符号、坐标、参考、事件时距或参数不一致。

## 下一项可检验结构

保留C5名义BS力与完整位置补偿（α=1），在现有14维位置DSSM接口上增加命令滤波角速率和PCF realization状态η（约20维输入），保留3维力残差输出，并尝试预测下一个10 ms事件的残差。这里的状态是可部署的滤波/实现状态；相位是否因此改善仍是待测假设。应先对照历史C5高频位置修复接口，再决定是否冻结候选。当前诊断不证明位置—姿态耦合不可改善。

审计更正：raw中的`position_nn_compensation_scale`是MATLAB `uint16`字符数组；首稿误把字符`'0'`码点48读作数值。现已解码并与release、run_start、run_status绑定为0.9。只改了审计读取与说明，没有改runtime、release或raw。
