# 姿态替代器的条件误差界草稿（待非作者复核，不构成理论验收）

本推导来自当前 matlab/core/attitude_bs_step.m 与 vehicle_derivative.m 的实际坐标变换。适用于主动变形应用的误差解释，不要求发明新的控制算法。尚未覆盖实际采样与RK4数值实现，因此不能将其表述为实际闭环稳定证明。

## 坐标与局部适用域

在Euler ZYX紧域且源码的pitch clamp严格未激活（|theta|<pi/2-1e-4）、角度误差不跨wrap分支、参考二阶可微且所用导数与参考一致时，令 e=eta_d-eta（选定同一连续分支），z=eta_dot_d+K1 e-eta_dot。实际BS虚拟Euler加速度为 v=eta_ddot_d+K1 e_dot+e+K2 z；实际源码先计算 alpha_BS=T^{-1}(v-Tdot omega)，再形成 J0 alpha_BS+gyro0+Jdot0 omega。

令实际连续时间body角加速度等于 alpha_BS+delta。此处delta包括模型近似、真实外力矩、学习误差、beta/clip、分配和执行器影响；不是假设它们自动很小。由 eta_ddot=T omega_dot+Tdot omega，得到 e_dot=z-K1 e，z_dot=-e-K2 z-T delta。

以下按固定SI单位数值坐标及1秒基准时间作无量纲化后记号书写，e与z平方项不可不加约定地当成同量纲物理能量。V=(||e||²+||z||²)/2，K1,K2为源码正对角增益，a=min(lambda_min(K1),lambda_min(K2))>0。若在整个轨迹上能独立建立 ||T delta||<=D，则
V_dot=-e^T K1 e-z^T K2 z-z^T T delta <=-a V+D²/(2a)。
故 V(t)<=exp(-at)V(0)+D²/(2a²)(1-exp(-at))，limsup||(e,z)||<=D/a。
该结论只在轨迹留在上述域且假设持续成立时有效，不能用它反过来无条件证明轨迹不离域。可另用子水平集边界不变性及初值/扰动足够小建立局部闭合，但当前尚未给出可验证常数。

## 与直接补偿目标的关系

在理想执行器、分配器线性且无限幅的实际事件状态上，令 G=Jtrue^{-1}[Ct C0^{-1}(0;J0)]torque，E0为移除补偿时相对alpha_BS的偏差，则 delta=E0-G c_applied。若可逆，c*=G^{-1}E0，delta=G(c*-c_applied)。令模型raw输出f，c_applied=beta clip(f)，训练raw目标y*=c*/beta（beta>0），则精确分解：
delta=G[beta(y*-f)+beta(f-clip(f))]。
这解释了为何旧行为残差目标与当前直接施加接口不一定相同，也明确原始输出拟合误差与限幅项均影响实际补偿。beta=0须显式处理，不能定义y*除零。

## 仍缺少的部分

实际系统100Hz输出、1kHz Plant及零阶保持，delta必须加入两事件之间的保持误差；与当前alpha_BS的偏差不能只用事件点误差替代。Euler参考由位置闭环生成，参考导数误差需明确进入扰动。RK4离散误差、数值更新和限幅导致的映射误差需要独立界；不能将连续时间V_dot式直接声明为离散实现证明。学习误差与G/T上界必须在规定域建立，有限样本RMSE或权重裁剪都不提供这样的统一界。

四场已验证的c*代数闭合仅支持事件点公式和接口可行性，不证明D小、不证明域不变、更不证明闭环改善。部署只有X18，真几何/风只用于离线诊断与标签，不能作为部署已知量使用。

## 非作者复核处理

已接受非作者对pitch clamp适用域的修正：clamp激活后，源码用未饱和T_theta计算Tdot，不能沿用这里的精确运动学等式；须另列clamp mismatch或限制clamp严格不激活。也补充SI数值坐标及基准时间约定。非作者确认局部连续时间误差动力学、Young界和直接目标分解代数正确；这仍不等于实际采样系统理论验收通过。v1保留。
