# Position RBF 与 KAN Head：更新尺度审计

代码核对：Position RBF有35个高斯基，gamma=1.2×5=6，面限幅[7,8,10]、beta渐入1.8秒、leak=.002、权重±60、输出±3 m/s²。X14 KAN的33维归一化特征范数恒为1；Head更新为 `-beta·phi·s_eff'`，输出还乘beta。RBF更新为 `-Phi·gamma·s_eff'`，输出乘beta。两者保留相同的误差限幅/泄漏/投影/输出上限。

六场原日志实际显示：RBF更新范数和beta来自B原始日志；RBF前8个事件的Phi由冻结配置重建且范数逐项匹配日志。KAN使用全部ready事件的真实Phi、Head更新前后权重、beta及有效dt。每场的输入变化与参数更新对当前raw输出的影响分列在`OUTPUT_ADAPTATION_SCALE.csv`。RBF从首个位置事件更新；KAN经过32个真实事件后约0.32秒就绪。

忽略clip、leak、投影且固定相同误差面时，单步raw更新系数是RBF `gamma||Phi||²` 与KAN `beta||phi||²`；施加到命令后的系数分别再乘beta，因此为 `beta gamma||Phi||²` 与 `beta²||phi||²`。六场全程记录的raw局部系数中位比约 **15.09×**。这是实际参数与日志上的局部尺度，不是闭环带宽证明；姿态、滤波、beta、饱和、轨迹状态和在线Head共同决定实测响应。PCF协调面差值见CSV；B的虚拟协调态只沿其记录轨迹重建。

更新尺度差异值得作为结构/训练背景，但相同position update律早已存在于旧版RBF与新KAN对照中，不能单独归因为新旧性能反转。本轮主训练对照保持原Head增益与控制条件不变。
