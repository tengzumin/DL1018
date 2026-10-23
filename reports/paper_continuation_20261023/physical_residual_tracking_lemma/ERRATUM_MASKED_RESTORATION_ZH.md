# 掩码恢复公式勘误与复核范围

原证明 `PHYSICAL_RESIDUAL_TRACKING_LEMMA_ZH.md`（SHA-256 `ba5db2bfe3a99b949b11d266755f6b8202bb812d7a0cb1e8177500b8e3a1c179`）保持原位，不修改冻结内容。

“把第二、三行相加”应读作“第二行加上 M 乘第三行”，因为物理变量为 `sigma = y + M eta`。对于实际 `M=diag(1,1,0)`，Z 轴不加 PCF 状态。原增广矩阵、余项和传递函数已保留正确的 M；此处修正文句，不改变方程或算法。

非作者复核见 `../physical_residual_tracking_peer_review/PHYSICAL_RESIDUAL_TRACKING_LEMMA_PEER_REVIEW_v1_ZH.md`（SHA-256 `49e87afe5c6aa3360a26415917cc94389e7d818da9615b2f3d907b9b13079c84`）。原独立 checker 的 42 次检查是标量 M=0/1 的基向量检验，不称为直接运行 M110 向量检查。补充脚本 `check_parent_m110_exact.py` 对实际三轴 M110 的 21 个基向量作精确有理数检验，输出独立记录，不读取仿真 MAT 或启动 Plant。

审核接受的范围仍是精确采样误差恒等式与条件有限时域误差界。该勘误和向量检查没有证明实际 Plant 的统一 forcing 上界、闭环不变域或全局稳定性，也没有单独满足最终理论与贡献验收。
