# 单次盒投影有限路径界：非作者复核

日期：2026-10-23。仅复核符号、时序、有限路径误差项及已冻结合成检查；未运行 checker、未读取 raw/TEST，未启动 MATLAB/Plant。

## 输入身份

- 主证明 `BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md`：SHA-256 `48b63a205f27d4ef595fcf6a25ef1c8b45c8169c11251a77d244bc0c66b85406`。
- 浮点/范数补充 `BOX_PROJECTION_BOUND_NUMERIC_SCOPE_ADDENDUM_ZH.md`：SHA-256 `0acccfb690f4757b90b8aa435f8e03ec31a9fb2fe691df45a7673d162244ef2a`。
- 冻结 helper `experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m`：SHA-256 `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`。
- 有理数 checker `check_box_projection_bound_exact.py`：SHA-256 `2d210c98a6443b6f62d43ada0760a6d28cffa2ebab6eadd1a377b5947e72ebe6`；其已有结果 `BOX_PROJECTION_BOUND_EXACT_CHECK_v1.json`：SHA-256 `fe896154b6c120dc97572fb6d52a3ab561dda86cbecd05a6827d8b3104230314`。

## 复核结论

(B)正确。对盒内固定比较器 U，投影变分不等式给出
`||W_(q+1)-U||² + ||R_q||² <= ||W_q-G_q-U||²`。
代入 `G_q=rho*g_q+b_q` 并展开，移项后得到 (B) 中的 `-||R_q||²` 和 `-2<b_q,W_q-U>`。二次平方损失的梯度恒等式也正确；它不依赖单位特征范数。

(H)正确。损失在更新前的 `W_q` 计算，已应用的旧区间输出来自 `W_(q-1)`；两者之差为 `(W_(q-1)-W_q)^T psi_q`。平方三角界系数为 `2P+2J`；若 `||psi_q||<=L`，则是 `2P+2L²J`。helper 对 phi 的范数检查容差为 `1e-10`，因此补件要求数值使用向上包络 L，不能把格式化打印值当精确单位范数。

(F)逐项符号正确：`u_j-d0_n = beta_j(z_j-y_j)+(beta_j*y_j-dM_n)+beta_j*c_j+M*r_f,n`，保留了 ramp/区间变化、输出 clip 与物理 `M r_f`。每个旧区间含10个采样，故 H 代入后首项是 `sqrt(20(P+L²J))`。当前 addendum 已把可选粗界一致推广为 `||b_q||<=0.12 L S+0.00002R`、`||G_q||<=rho(R L²+L Y)+0.12 L S+0.00002R`，没有残留的单位范数误用。

索引一致：事件 `n_q=320+10q`，`q=0…1967`；`q=0` 无旧标签；`q=1…1967` 使用旧区间 `j=q-1=0…1966`。其样本为 `320…19989`，每段10点。`0…319` 是 pre，`19990…19999` 是末区间；最后事件产生末区间的应用输出，但没有 `q=1968` 的后续标签/更新。三段合计 20,000 个样本，不重叠。

浮点补件的修正也正确。令理想投影结果 `Z_q=Pi_C(W_q-G_q)`，实际记录下一权重为 `Z_q+delta_q`，展开平方后 (B) 右侧增加 `D_num,q=2<delta_q,Z_q-U>+||delta_q||²`，符号为正；若仅有 `||delta_q||<=eta_q`，盒直径 `2R` 给出 `4R eta_q+eta_q²`。这避免假设原始未投影 candidate 已被保存。普通浮点复算只是数值一致性检查，严格机器证书仍需向外舍入/明确 eta。

已有 JSON 报告 checker `PASS_EXACT_RATIONAL_B_H_F_SYNTHETIC_BOUNDARIES`，18 个理想有理数单步/累计检查且18例投影激活。该结果支持的是精确实数代数式，不能当作 DEV raw 的浮点区间证书、先验闭环界或稳定性证明。现有理论的限制属于范围限制，不是上述投影/损失推导的反例。

## 建议保留的表述边界

可称为“实际联合盒投影更新对应的有限路径预测误差不等式”，后续代入已完成路径时须将结果称为后验有限路径证书。不能从 (B) 单独推出右侧小、误差收敛、Plant 稳定或运行前包络。
