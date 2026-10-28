# 两场 yaw 输入屏蔽关联诊断

定义 `ΔMSE = MSE(mask,d) − MSE(full,d)`，负值表示 masked 输出误差较低。full 与 mask 使用相同的 A1 step 30000 canonical-double 参数；mask 在归一化前把 X18 的 raw alphaBS x/y 置零。wind/oldAction 列是把同场同事件标签分别改作 `d−q` 的代数反事实，输入和权重保持不变；恒等式核验通过。该分解说明关联，不识别因果。

| 场景 | full yaw RMSE | masked yaw RMSE | ΔMSE | ΔMSE (d−wind) | ΔMSE (d−oldAction) |
|---|---:|---:|---:|---:|---:|
| TRAIN T1 C15 W14 | 0.180425 | 0.285182 | 0.048776 | -0.029892 | 0.055542 |
| VAL T2 C15 W09 | 0.065341 | 0.119104 | 0.009916 | 0.006639 | 0.013155 |

在 HOLD phase，减去 wind 分量后两场 ΔMSE 都反号：TRAIN 0.115225 → -0.142227，VAL 0.022259 → -0.003257。其他 phase 的方向并不一致，因此这只支持 wind 项与 HOLD 中两模型误差差异相关，不能解释全部阶段或 A2 offline VAL 退化。减去 oldAction 后两场 ALL ΔMSE 反而增大，未支持“full 输入优势主要依赖 oldAction”。这两场结果否定直接采用硬 alphaXY mask 的依据。

scope：固定 TRAIN T1 C15 W14 与 VAL T2 C15 W09，各 1,999 cache events；只读两 cache、v2 分解结果和 A1 deployment JSON。未读 raw/TEST，未训练、未调用 optimizer、Plant 或 engine。CSV 含 ALL 和六个 phase 的 full/mask RMSE、ΔMSE 与两组恒等式残差。

身份：v2 分解 JSON SHA256 `77e25178d0f091be4913736bc33f58d9018efa00ae9ee239c29311177a9a1c00`；A1 deployment JSON SHA256 `ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae`；诊断脚本 SHA256 `6d09c42fd200f1d12095e9239e28d3292aa71218af366de87c0c80263c322c52`。结果文件 SHA256 `f81b7365e483f5e998c61de241a91d7116c7e7d324ebccbb9e9dc6049732a291`。
