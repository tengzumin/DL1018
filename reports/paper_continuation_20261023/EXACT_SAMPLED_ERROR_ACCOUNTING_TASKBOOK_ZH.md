# C3实际采样误差的同轨迹分解核验

范围固定为已封存C3全部72场；不读TEST、不训练、不Plant、不改候选。主审独立复算，用于核对C4草案中的坐标作用，不将分解视为移除组件后的真实闭环结果。

设h=.001、e_n=r_n-p_n、s_n=rdot_n+K1 e_n-v_n、x_n=[e_n;s_n-eta_n]。K1=I、K2=4I均从冻结cfg读取。直接利用相邻采样，定义

```
rho_p = (r[n+1]-r[n]-h*rdot[n]) - (p[n+1]-p[n]-h*v[n])
rho_s = (rdot[n+1]-rdot[n]-h*rddot[n]) + K1*rho_p
Ybar = (v[n+1]-v[n])/h - a_req[n]
d_c = Ybar + r_f[n]
rho_eta = eta_after[n]-eta_before[n] - h*(-K2*eta_before[n]+r_f[n])
A = [[I-h*K1,h*I],[-h*I,I-h*K2]]
b_eta = [h*eta_before;0]
b_residual = [0;h*(u_applied-d_c)]
b_sampling = [rho_p;rho_s-rho_eta]
```

逐样本核对 `x[n+1]=A*x[n]+b_eta+b_residual+b_sampling`，含终点eta_after；a_req还须与实际BS公式及u_applied相等。所有量只作离线核验，Ybar是**精确采样增量定义**，不能冒称瞬时物理加速度测量，也不进入部署。

按稳定矩阵A分别传播初值、eta、残差误差、采样余项，检查它们之和重建实际位置误差。输出逐场逐轴RMS、各自MSE与全部交叉项，以及ALL72/HF28/W15/T2-HF9的场景等权摘要。不得直接将RMS相加，不比较不同闭环状态作组件因果。

A的谱半径和离散Lyapunov矩阵可给出在给定forcing序列下的条件响应界；这不证明forcing对状态的反馈可吸收，更不自动证明原Plant闭环稳定。有限数据分解及线性响应的数值恒等式只用于解释误差路径，不作为论文理论门通过。

产物只写本目录下 `sampled_error_accounting`；拒绝覆盖已有结果。先验证身份与公式，出现不一致即停，不放宽位置胜负容差。原始文件不修改，磁盘与截止约束沿用。
