# 执行任务书：预测与跟踪共同驱动的姿态神经在线头

2026-10-27。主决策：root；执行者必须 GPT-6-Luna、xhigh、default service tier。用户授权主模型监督、Luna 修改代码，方法可继续尝试；不做时变惯量重建。

## 为什么安排本项

真实在线头 v1 六场优于冻结 MLP，但最终 B/C5 双重门失败：位置胜 B 2/6，姿态胜 B 2/6、胜 C5 0/6。放宽权重界和去掉预训练先验没有离线证据，未运行其闭环。共享基底回放也未过门（2.856 vs 原2.566 rad/s²），故不修改归一化特征。

现有头只利用过去残差预测误差；本项唯一新增当前 BS 姿态跟踪误差的更新项。目的是改善闭环跟踪，而非继续只优化动作拟合。通用复合适应结构已有文献（Neural-Fly），不声称全新算法，也不转移其位置环证明到本项目。

## 唯一控制变更

创建 `experiments/dl_attitude_replacement_20261026/mlp15_composite_head_v1/` 独立目录。复制 v1 控制源码和必要小型配置，不复制 raw、模型或缓存；历史只读。相对 `mlp15_causal_head_v1` 的实际控制差分限于 MLP step 和事件入口。forward、模型、网络归一化、神经13维输入/15事件、C5 DSSM14/M110位置栈及其在线头、固定J0/C0、BS、Plant、执行器、beta、dmax、30°上限均不变。禁止惯量/惯量导数重建、真实臂长/风/扰动力矩、RBF权重/隐状态进入控制器。

沿用 `67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b` 模型；P0=10I、forgetting=.999、修正权重界20、单位范数隐藏特征phi全部保持。beta成熟后才更新，过去残差配对上一事件特征；当前输出仍使用当前更新前权重。

在原残差RLS更新与Joseph协方差更新之后、权重投影之前，新增

`tracking_drive = -(P_after * phi_current) * (beta_current * (target_rms .* (T_current' * s_current)))'`

`D_after = D_after_RLS + actual_event_dt * tracking_drive`

`T_current=ai0.euler_rate_map`，`s_current=ai0.surface`，仅由当前测量姿态/角速度和已知BS参考计算。系数固定1，不扫描增益，不新增surface裁剪。它们是更新信号，不增加网络13维输入；历史角速度与已发力矩仍只用于过去残差标签。P_after 为同一次Joseph更新后的协方差。随后仍按20投影D。记录tracking_drive、surface、T及更新前后权重，保持当前输出不受当前更新影响。

符号来源：以 e=desired-actual、z=BS surface，理想误差交叉项为 `z' T beta S Dtilde' phi`，上述负号在参数度量P^-1下抵消该项。必须针对该恒等式验证符号/维度；这不是完整闭环证明，采样、近似误差、投影、P变化和实际Euler域仍须保留为理论边界。

## 执行者本次可做及硬边界

授权实现、独立Python数值参考、MATLAB无Plant检查、源码差分、准备输入/release。**本次执行者新增Plant预算为0，不得启动闭环/训练/DEV72/TEST。** 首个真实航次必须等root实际读码及报告审核后修改新release；准备release状态必须硬拒绝Plant，authorized_Plant_calls=0。不自行放行或扩方法。

只写上述新目录。只用PowerShell7，MATLAB显式R2025b路径；不要使用用户profile里的旧R2022b alias。不终止或打断任何已有进程，不解锁、不删除、不改写历史目录，不git批量暂存/提交/推送。

## 必须交付的验证

1. 保留v1零头/关闭头的冻结forward一致性。构造至少300事件的独立Python/MATLAB参考，含beta成熟、残差更新、跟踪更新、Joseph SPD、权重投影及dmax分支。
2. 当前观测、当前跟踪信号的更新不能改变当前输出；只影响后续输出。过去区间端点/命令索引必须与v1一致。验证正/负号交叉项相消，不能只自调用实现。
3. 新trace和独立raw replay审核器要从实际state、filtered_attitude_rate、filtered_attitude_reference重建T和s；K1从锁定cfg读取并写入release，禁止用Plant truth或RBF学习信号。保留v1先于首次修正输出的完整状态一致性核验。
4. 新copied runtime的Code Analyzer与v1比较：允许既有ALIGN消息内随插入改变的行号，不能忽略新诊断。运行源树差分只包含预期控制改动，记录SHA。
5. 复用已有六场B、C5、冻结MLP及v1 prediction-only raw。除原冻结对照外，manifest还需绑定v1 raw SHA、同一物理scene arrays；独立报告新增 `prediction_only` 对照指标，用于判断唯一新增跟踪项的作用。
6. 准备三场W15先T1、root审核后另两场。三场全部安全且Q、外部任务SO3、内环跟踪误差宏平均均优于v1 prediction-only，才建议完成原三场W12/W13；最终仍按用户B/C5标准，不把方向门称为最终成功。
7. 保存可复现命令、所有无Plant失败/修复、NO_PLANT_CHECK、待root release/source lock、源码diff及 `LUNA_COMPLETION.md`。报告真实产物路径/结果和未完成项，不以“准备好”代替实际检查。

根目录和输入都在当前DL1018工作区，模型/原始MAT只读复用。本项不需要网络调研或新依赖。工作结束后把控制权交还root审核。
