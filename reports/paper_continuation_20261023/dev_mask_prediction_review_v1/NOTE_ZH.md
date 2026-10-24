# 物理误差预测驱动坐标分配：只读批判备忘

日期：2026-10-24。未运行 Plant、未扫参、未用 TEST 或真实风/Plant oracle。结论针对数学可行性与创新性，不是运行批准。

## 独立复算：目标误差下降由交叉项主导，不是物理 Q 证据

从诊断 JSON 的 72 个 per-scene 汇总重新求和，ALL72 全时段 \(E_{\rm phys}=36987.588745\)、\(E_{\rm coord}=24616.493667\)、\(\sum c^2=27574.977201\)。由 \(E_{\rm coord}-E_{\rm phys}-\sum c^2\) 独立算得交叉项 \(-39946.072279\)，与逐场景 cross 项求和相同；恒等残差约 \(3.6\times10^{-12}\)，能量比 \(0.66553389\)。

早段 Y 轴 \(E_{\rm phys}=2417.100219\)、\(E_{\rm coord}=1339.420369\)、\(\sum c^2=2772.718408\)、cross \(=-3850.398257\)，比值 \(0.55414350\)；HF W09–14 早段 Y 比值 \(0.56783417\)（\(1652.296052+2199.825865-2913.891763=938.230154\)）。逐场景早段 Y 有 \(62/72\) 较低，但反例包含 DEV T2 C02 W15、VAL T2 C05 W15；W15 早段 Y 比值为 \(11.411530/10.704035=1.066096\)，W15 全时段三轴总比值为 \(0.975204\)。这证实历史 W0 在冻结 C5 轨迹上更易拟合 \(y_M\) 的聚合相关性，不代表替换 mask 后的闭环 Q。诊断明确是同记录状态、冻结 W0 且不含 beta、在线适应、输出裁剪的离线分解。

## 两事件时序与闭式雏形

源码在事件 \(q\) 先按旧 \(W_q\) 算 \(u_q=\beta_q\,\mathrm{clip}(W_q^T\phi_q,\pm3)\)，然后以当前 tracking 面和前一已完成区间标签构造 \(W_q^+\)，并将 \(u_q\) 保持 10 ms；\(W_q^+\) 到下一事件才用于 \(u_{q+1}\)，再保持整个下一个 10 ms。故从被拟合区间 \(q-1\) 的起点到更新输出生效有两个 100 Hz 间隔。未计这两段保持会错置 mask 的物理作用时刻。

在单输出轴、\(s-m\eta\) 未触发 surface clip、权重投影未触发时，helper 精确给出
\[
W^+_{q,i}(m)=a_i+m b_i,\quad
b_i=0.12\beta_q\phi_q\eta_{q,i}+0.01\phi_{q-1}\bar r_{f,q-1,i},
\]
其中 \(m\in[0,1]\) 同时用于当前 tracking 坐标及对已完成区间标签 \(y^0_{q-1}+m\bar r_{f,q-1}\) 的重坐标。当前输出 \(u_q\) 不随本次 \(m\) 变化；下一事件候选输出必须是
\[
u_{q+1}(m)=\beta_{q+1}\,\mathrm{clip}((W_q^+(m))^T\phi_{q+1},\pm3).
\]
若再假设 \(\phi_{q+1}=\phi_q\)、把上一已完成区间标签 \(\hat d^0_{q-1}\) 当成两段内固定的 \(d^0\)、状态模型线性且不随输入改变，则雏形保留当前保持段后写为
\[
x_{q+1}=A_Hx_q+B_H(u_q-\hat d^0_{q-1}),\quad
x_{q+2}(m)=A_Hx_{q+1}+B_H(u_{q+1}(m)-\hat d^0_{q-1})=p+m g .
\]
在 \(P\succeq0\)、\(g^TPg>0\) 下，\(\arg\min_{m\in[0,1]}x_{q+2}^TPx_{q+2}=\mathrm{clip}(-g^TPp/(g^TPg),0,1)\)。这是合法的单变量名义二次优化；加入实际 surface clip、box projection、output clip 后为分段二次，可枚举断点。它仍只是该理想模型下的 terminal-cost 极小化。

## 根本的因果模型缺项

原雏形把旧标签 \(\hat d^0\) 对候选 \(u\) 当常数，因而把物理 forcing 的导数当 \(I\)。但源码 \(a_{req}=a_{nom}-u\)，而 \(d^0=\bar a_{\rm actual}-\bar a_{req}\) 是输入相关的观测残差。若只作为**名义局部模型**假定 \(\bar a_{\rm actual}\approx C_0+J_0\bar a_{req}+\bar w\)，其中 \(J_0=\partial\bar a_f/\partial\bar a_{req}\) 是跨整个 10 ms、含姿态转换和 command filter 的平均 realization 灵敏度，且 \(\bar w\) 短时不变，则
\[
\hat d^0(u)\approx d^0(u_{\rm old})+(I-J_0)(u-u_{\rm old}),\qquad
\partial(u-\hat d^0)/\partial u\approx J_0.
\]
所以用 \(u-\hat d^0\) 作预测时，不能把它对候选输出的导数取为 \(I\)。若用旧 \(d^0\) 当常数，漏掉的名义项正是 \(B_H(I-J_0)\Delta u\)。应以该 \(J_0\) 更新当前段和下一段预测，并给未建模 plant/wind 变化留显式不确定项；仅有 PCF 命令 realization 的 \(J_0\) 不等于实际飞行加速度的雅可比，故不能推出真实 Q 保证。C0/J0 线性化只能给名义或带误差集的 predictor，不能消除未知的未来 \(\phi\) 与 \(d^0\)。

也不能不加说明地逐轴优化：position_bs 的目标力经 yaw 相关 ZYX 力到姿态变换、推力范数、倾角裁剪，再经角度滤波及完整旋转矩阵生成 \(a_f\)；这会形成轴间耦合。若误差态取 \([e_p,e_v]\)，两部分分别是 m 与 m/s，\(B_H\) 的加速度输入映射和 \(P/Q\) 必须给定一致的归一化/量纲。未定义尺度的 \(x^TPx\) 不是可比较的物理 Q。mask 每事件切换还要显式处理同区间标签坐标跳变 \(\Delta M\,\bar r_f\) 及 surface 变化 \(\mathrm{clip}(s-M_q\eta)-\mathrm{clip}(s-M_{q-1}\eta)\)（未裁剪时为 \(-\Delta M\,\eta\)）。

## 判定

动态 \(m\) 选择在功能上不同于 C3/C4/C5 的固定坐标臂，但 \(m\in[0,1]\) 是连续坐标混合/增益调度。用延迟标签、实际 clip/projection 和名义 \(C_0/J_0\) 形成两步预测器，在数学上可以定义；其名义目标在固定模型下不高于纳入候选集的固定 mask，只是优化可行集包含固定点的直接结果。补上 \(J_0\) 是防止错误输入灵敏度的必要修正，却仍是常规 delay-aware MPC / gain scheduling。现有证据没有提供可靠的 future-\(\phi,d^0\) 不确定集、真实轴耦合 Q 推导或新的保证，因此目前没有可审核的新科学候选，也不建议据此启动运行。

## 可复核来源

- DEV72 分解 JSON SHA-256 0FE0527636230D438AEC4B6CEDF4061E9F5C1EF8AC9B3DB72FBEB6036EC38C0C；生成脚本 SHA-256 91657BE6027631033C556ECB5ADE7E92CD411719116A1698C9B2793DD71C4D90。
- C5 事件顺序/held output：experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m:2023–2045, 2108, 2126–2138, 2250–2271；SHA-256 48350037B66EFE00301B138068F187C62CF92583F0F9BA2FABC9B24F248A963C。
- 候选更新/投影/输出裁剪：experiments/position_axis_coordinate_c5_dev72_20261023/delayed_prediction_step_candidate.m:37–43；SHA-256 48FEEBF934B8EB90B4424F2286AA857C48213D229714F30AF99AACF53329549D。
- \(a_{req}=a_{nom}-u\)：matlab/core/position_bs_step.m:17–27, 55–61；SHA-256 EA533C3AE97CBC552208287E7F8D9B0A0F5A018F36FB5C8BD45520E19E73C681。
- 非线性 force/attitude 与滤波/PCF：matlab/core/baseline_force_to_attitude.m:15–24, matlab/core/command_filter_step.m:10–24, matlab/models/position_filter_realization_pcf_step_v3_5.m:9–21；对应 SHA-256 EF42D1D08AF24ED82DA307A4D886B0C205E28E754177765A2584E3E9BB0CD039, 15C7EB27162E1971A1164304830F4AFD3AF35EB9BD709291E969DBFEFD0D262B, B4AE22DB5BD444A162D0CD01A3A59A589F2E37077B089BB33693401B660228D0。
