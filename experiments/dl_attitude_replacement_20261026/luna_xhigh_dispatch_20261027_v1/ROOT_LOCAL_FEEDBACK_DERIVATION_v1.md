# 主审：固定姿态/参考/记忆时的角速度局部导数

2026-10-27。此为待数值核验的局部推导，不是Plant或完整离散闭环稳定性证明。

令T为Euler速率映射，A=∂T/∂roll，B=∂T/∂pitch，u=T第一行、v=T第二行。姿态固定，Tdot(ω)=(uω)A+(vω)B，H(ω)=Tdot(ω)ω。

DH = outer(Aω,u)+(uω)A+outer(Bω,v)+(vω)B。

固定J0、Jdot0=0、参考及姿态时，BS名义力矩对body omega的导数为

J_BS = J0 @ inv(T) @ (-diag(K1+K2) @ T - DH) - skew(J0@ω) + skew(ω)@J0。

该式应与同一BS公式的中心差分吻合。参考加速度是已知常量，在这个偏导中消去；原点力矩仍须用日志实际滤波加速度独立重建。

当前网络13维特征对ω的导数是竖向拼接[zeros(3,3);eye(3);J_BS;zeros(4,3)]；归一化后只占15事件窗口最后13个元素，过去14事件保持固定。两层SiLU以及normalized hidden+bias特征都需正确求导，D使用输出前权重，禁止即时执行更新。

净力矩导数 J_net=J_BS-J0*beta*G_clip*J_residual，G_clip为未越dmax轴上的1/其他0；阈值附近应标非光滑，不当作精确梯度。中心差分epsilon两值仅核验数值一致性，不是控制调参。

Sym(-J_net)的符号只表征当前冻结记忆的局部瞬时增量作用。陀螺项、补偿实际需求、Euler域和完整动态可能改变解释；不能从单个正/负特征值推出闭环稳定/不稳定或主要根因。

## 成功RBF参照的解析局部导数

RBF输入是[e1,s1,e2,s2,e3,s3]，不是[e;omega]。固定姿态/参考，s=etaRateDesired+K1*e−T*omega，因此Jz/omega的MATLAB第2/4/6行为−T三行，其他行为0。

高斯基函数偏导：dPhi_n/dz_l=Phi_n*(center_l,n−z_l/input_scale_l)/(sigma²*input_scale_l)。当前配置无width/basis_override、linear_dim=0。

固定当拍RBF W_before时，J_comp=J0*beta*G_clip*W_before.T*Jphi_z*Jz_omega；J_net=J_BS−J_comp。与原RBF输出先于更新的合同相符。成熟W必须经全事件正向重放验证，不能从范数逆推。相同局部解释边界与MLP一致。
