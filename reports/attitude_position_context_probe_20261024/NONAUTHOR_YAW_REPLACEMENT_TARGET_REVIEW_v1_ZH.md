# Yaw 替代目标独立复核

复核结论：在分解文件标明的四场适用条件下，现有旧行为残差 `d_old` 一般不是将补偿量直接置于“nominal minus compensation”部署接口时的理想 yaw 标签。该结论是同一记录状态上的代数比较；它不说明重新训练后闭环表现会怎样，也不构成稳定性证明。

设旧日志补偿力矩 `tau_comp_old` 对应 `c_old = J0^{-1} tau_comp_old`，固定名义加速度为 `alpha_BS`。事件导出实现以 `tau_nom - tau_comp_old` 形成虚拟名义加速度，再将实际加速度与其相减作为标签（`export_matched_position_probe_events_v2.m:164-175`）。在 yaw 解耦、无 yaw 限幅、无执行器时滞且 requested 与 realized yaw 一致时，令 `g = J0_zz/J_zz`，并把不含本次补偿项的名义/物理项合并为 `E0`，则

```text
d_old = alpha_true - (alpha_BS - c_old) = E0 + (1-g)c_old
alpha_new - alpha_BS = E0 - g c_new
c_star = E0/g
```

所以，若替代补偿器在同一状态上完美输出旧残差 `c_new=d_old`，它留下的加速度误差为 `E0-g*d_old = g(c_star-d_old)`；这通常不为零。两个量仅在该事件 `g=1` 或 `c_old=c_star` 时相等。只有在这些点态条件成立时，旧残差才同时等于该简化方程下的理想替代补偿量。

这里区分“克隆旧补偿动作”和“拟合旧 residual label”：旧动作量是 `c_old`，导出的 residual target 是 `d_old`；若固定 RBF 的目标只是逐状态重现旧动作，应以 `c_old` 表述。上述数值结论针对把 residual target 当作新部署补偿量的情形。

独立复算从固定源 JSON 的 1,999 个事件逐项重算 `E0=d_old-(1-g)c_old`、`c_star=E0/g` 与 `E0-g*d_old`，并交叉验证等价式 `E0-g*d_old=(1-g)(E0-g*c_old)`。四场与已存结果各字段的最大数值差不超过 `1.11e-16`；公式闭合误差在 `2.22e-16` 至 `4.44e-16`。结果如下，单位均为 rad/s²：

| 航次 | g 范围 | 旧行为残差 RMS | 理想同状态补偿 RMS | 标签与理想量之差 RMS | 若精确输出旧标签后的误差 RMS | 理想量越过 yaw clip |
|---|---:|---:|---:|---:|---:|---:|
| T1_B | 0.552520–1.000000 | 0.570144 | 0.693082 | 0.211914 | 0.119683 | 0/1999 |
| T1_C5 | 0.552520–1.000000 | 0.640678 | 0.863869 | 0.321113 | 0.181985 | 0/1999 |
| T3_B | 0.552520–1.000000 | 0.777798 | 0.946601 | 0.280670 | 0.159254 | 0/1999 |
| T3_C5 | 0.552520–1.000000 | 0.827894 | 1.072207 | 0.366555 | 0.206977 | 0/1999 |

四场源分解均标记 `simple_formula_applicable=true`：名义 `Jdot0=0`、真 yaw inverse 与 x/y 解耦、名义和真实分配 yaw 行一致、controller/allocator yaw clip 均未触发、motor time constant 为零，且请求/实现 yaw 差约 `1.3–1.5e-14` rad/s²。这里的 `E0` 仍包含记录状态下的惯量、角速度、风和参考作用；理想量用到了线下真值，不能直接作为可部署输入。

该复核只比较四条已记录轨迹上的同状态标签与补偿量，没有重新积分系统、比较下一状态或检验训练后的泛化。它不能证明把标签改成 `c_star` 会提升指标，也不能证明闭环稳定或优于固定 RBF。当前结果只支持“旧 residual 标签不等价于直接替代补偿接口的理想标签”这一条件性判断。

复核依据：

- 分解源 `MATCHED_POSITION_LABEL_DECOMPOSITION_v2.json`，SHA256 `2c98a3e6ce6915bb03e00c4a74db1415ac1f71c2515773b48b3e4fa173f60093`。
- 部署减号与 target 定义见 `export_matched_position_probe_events_v2.m:164-175`；该源码 SHA256 `ddb1684b1d720d9bee80b3bcda2c95bf855faee1220fc54e9ba764695c5a54a9`。
- 根侧计算脚本与结果 JSON SHA256 分别为 `005162c198276c28c504828db9be79c24c84ad64a4661ce790f399784f30c9f2` 和 `d5b4d6c7e0034e2cf30c9aadd666ada920357cdef07cd269b4586897de4fe35c`；本复核使用只读 JSON 逐事件重算，不读取 raw。
