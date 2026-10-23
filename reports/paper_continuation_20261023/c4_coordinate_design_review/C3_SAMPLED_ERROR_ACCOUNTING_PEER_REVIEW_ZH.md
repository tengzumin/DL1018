# C3 sampled-error accounting：独立公式审查

**结论：公式和表格口径通过，作为固定轨迹的 forcing 分解有效；不构成去除 eta 后的反事实，也不构成 Plant 闭环稳定证明。** 此证据支持 C4 的坐标干预有可区分的通道，但不能预测 C4 的 Q 会如何变化。

任务书定义 (x_n=[e_n,s_n-\eta_n]^T)，(A=\begin{bmatrix}I-hK_1&hI\\-hI&I-hK_2\end{bmatrix})。(\rho_p=\Delta r-h\dot r_n-(\Delta p-hv_n)) 的符号给出 (\Delta e=h( s_n-\eta_n+\eta_n-K_1e_n)+\rho_p)，故首行 forcing 是 (h\eta_n+\rho_p)。令 (\rho_\eta=\Delta\eta-h(-K_2\eta_n+r_{f,n}))，因 (s_c=s-\eta)，其差分中 PCF 离散余项确为 **(-\rho_\eta)**；和 (\rho_s) 合成第二行 `rho_s-rho_eta`，符号正确。用 (\bar Y_n=(v_{n+1}-v_n)/h-a_{req,n})、(d_{c,n}=\bar Y_n+r_{f,n})，forcing (h(u_{applied}-d_c)) 也与 `position_bs_step` 的请求加速度符号一致。这里 (a_{req}) 是含当步 Head 补偿的请求量，未将它冒称为 realized/Plant 加速度；(\bar Y) 是精确采样增量，不是瞬时测量。

脚本按20001个状态/reference样本与20000条转移量对齐，`rho_p/rho_s/rho_eta` 及四个响应分量与任务书递推相符。汇总表的组行是**9个场景的逐场统计等权平均**：RMS列是逐场响应 RMS 的均值，MSE列是逐场 MSE 的均值；两者不要求满足“组均值RMS平方=组均值MSE”。T2-HF9 的 Z 组，位置 RMSE均值3.704 mm，eta、残差和采样响应 RMS均值分别2.738、1.646、0.016 mm；eta×残差交叉MSE均值为 (+2.66585\times10^{-6}\,m^2)。按每场MSE加全部交叉项后，组均值闭合至约 (9.8\times10^{-16}\,m^2)。因此不得把这些RMS直接相加，也不能忽略正交叉项。主审登记的全72位置重建最大误差为 (1.09\times10^{-12}\) m；本审仅审脚本/汇总CSV/JSON，没有重读raw或重跑计算。

该线性 (A) 的离散Lyapunov收缩只界定**给定 forcing 序列**的状态响应。C4改变 (m) 后，Head、请求加速度、速度、(r_f) 和采样余项都会随闭环状态变化；冻结C3轨迹上的 forcing 分解不能假定这些项保持不变，不能推出C4性能或吸收反馈的完整闭环定理。它能说明 eta 通道在指定组的重要性并构成可检验假设，不能证明它是退化的唯一原因。

复核输入：任务书 SHA `104B9DA52F2885BD53C2D122BA84ED09ED121D79AF6215F9E59593C0EEF0E606`；复核脚本 SHA `EFC242504268521A68A1D642B9089B4D434C9DC256DEA4C6BC1025EBB24B5ADD`；`GROUPS.csv` SHA `E51A39BC4E2E612A8E81DD3A3B30F9DEB8FD6E945AEA802F179118396AA6763B`；结果 JSON SHA `B7DA21D5E7B0C0B331BF8053376BD180F5B8F2E4C4C6D95C1E9D50F4C898B4A0`。公式复核期间未运行 MATLAB/Plant、训练或新诊断。