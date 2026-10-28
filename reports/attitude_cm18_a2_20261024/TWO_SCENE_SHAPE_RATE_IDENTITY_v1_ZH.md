# 两场真实形态与形态率重建

结果为 PASS。TRAIN T1 C15 W14 与 VAL T2 C15 W09 的 `rho_true` 可由 `z[0]=0; z[k+1]=z[k]+dt[k]u[k]` 和初值 0.15 重建，`rhoDot_true` 可由 `u` 重建。两场从非零命令样本反推的形变速率都为 0.05 m/s；臂长积分最大误差分别为 `1.105e-14 m` 与 `1.107e-14 m`，形态率最大误差为 0。每场共有 20,001 个状态采样，命令取值为 −1、0、+1。

本检查只读两个已由 ALL816 manifest pin 的 raw 文件中的 `scene.time`、`scene.arms.command`、`rho_true`、`rhoDot_true`。没有读 raw `log`、状态或 TEST；也没有打开 event cache。cache SHA 仅从已核对的 dataset manifest 记录。raw 和 run_start SHA、逐场数值与范围见同名 JSON。

因此，对这两场而言，X18 的 `z/u` 已足以确定真实形态和形态率，不支持“alphaBS_xy 用于补回未观测形态”的解释。结论只限这两场，不推广到全部数据或有滞后的真实硬件。
