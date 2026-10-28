# GRU 名义命令残差监督：单因素训练与筛查任务书

主审 /root，Luna xhigh 实施。只批准源码/部署准备，正式训练release初始0、Plant初始0；root审代码后签唯一训练作业。完整论文目标不变，未过筛查不得扩DEV72/TEST。

## 唯一假设与输入身份

余弦日程已修复明显教师拟合偏置，任务姿态六场全胜原恒定lr GRU但仍0/6胜C5，不能继续以模仿教师精度作成功。相同C5状态中教师策略输出与10ms名义残差仍有约0.969 rad/s²向量差。下一项只改变监督Y，检验直接预测名义命令残差是否改善补偿；不预判标签原来错误或新目标必有效。

候选GRU32_STREAM72_NCMD_S2026102001；新训练目录gru_stream_ncmd_v1，新部署目录gru_stream_ncmd_dev_v1。训练源以gru_stream_cosine_c5_teacher_v1为直接对照，运行数学以gru_stream_cosine_dev_v1为直接对照。

固定模型路径为experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_v1/runs/GRU32_STREAM72_NCMD_S2026102001/gru_stream_c5_teacher_weights_v1.mat，同目录导出stream_parity_vector_v1.mat；沿用9个数值字段和原矩阵形状，文件名不随Y语义改变。

X/ID仅取原matched_teacher_data_v1.npz中C5数组，SHA b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f。新Y仅取nominal_command_target_data_v1/nominal_command_target_v1.npz（SHA 88df5c2f2088910a9c5650a5c67efdb7f42d30cabc021d0da83b68b72578ffb7）中的c5_train_y_clipped_float32与c5_val_y_clipped_float32；manifest SHA fc5ed29cfd0a5260a2992f28b8ada21ccd72f7d25c7bbe00831dca7a10e9e0ab。不要误读unclipped数组或旧RBF-Y。内部TRAIN_C5_24其实是DEV24，另一组是VAL48；全部72条均为开发训练，不称独立验证。

## 目标与因果边界

新Y为当前事件e至e+10的名义命令端口残差均值，按现有精确dmax裁剪后、beta之前，单位rad/s²；公式/完整J0/端口依据见ROOT_NOMINAL_COMMAND_TARGET_PREPARATION_v1.md。requested是发给固定名义分配器的命令，标签不使用realized、Jtrue/Jhat/Jdot/Ctrue或真实风/质量；该残差包含分配和动力学等整体不确定性，不是实际瞬时外力。

原72×1999个X的数组SHA、ID顺序与事件时刻不变，未来区间只用作离线Y，绝不作为forward输入。当前合法13维输入、场内持续hidden、场首reset、当拍dmax→beta→固定J0映射均不变。

## 固定训练合同

单层GRU(13,32)+Linear3；fresh init固定seed2026102001，初始化state_dict SHA 82d952ce8f150388015bc2776b8acceb9c9da59814470eb036ec9ca99420e06e。原normalizer字节SHA 612c39d7fd113571f2935eae1e42d3fb4d33705bf9a230c75e5c274db1bfb693，含target_rms仍不重拟合，以免同时改损失权重。

保持cosine lr(s)=1e-5+(1e-3-1e-5)*(1+cos(pi*(s-1)/59999))/2，s=1..60000，Adam其余参数、SmoothL1 beta1、batch4、TBPTT128、固定种子cohort shuffle、hidden carry/detach/reset、最后79有效事件等全部不变。固定一次60000 optimizer steps、final60000唯一模型，不resume/选checkpoint/延长/扫种子；预期29985000累计有效样本。每步lr/scene/cohort/chunk/有效数账本保留，应与cosine直接对照逐步一致。

训练器最小diff应只有Y来源/合同与相应身份核验，训练优化循环不得另改。分开锁定feature NPZ与target NPZ，旧数据Y的hash不能冒充新Y；supervision/teacher_source元数据必须明确改为nominal command residual。selfcheck实际验证新Y数组SHA与输入X完全未变，之后root签唯一正式GPU作业。PowerShell7与已成功的preload numpy/torch/scipy.io→unset子进程KMP→runpy启动方式不变，显式保存Python exit码。单GPU、新训练产物≤2GiB。

## 数值与闭环

MAT导出仍9个数值字段同接口，model hash独立。部署58个数学runtime文件必须与cosine直接对照逐字节相同，只改必要driver/元数据/模型身份，不复制历史runs/raw。不新增head/observer/滤波/输入/时钟/延迟，不改C5 DSSM14/M110位置栈、BS、C0/J0/Jdot0、[Inf Inf 6]、dmax、30°投影、Plant或执行器。

先核实际模型全1999事件Python/MATLAB double输出与hidden各≤1e-8；float32输出≤1e-4rad/s²、hidden≤1e-5，沿用已验证数学并核新model/cfg/which/release0。每个raw必须绑定当场release SHA三处值，Stage快照保留，不用新Stage重审旧raw。

root通过后先T1_C08_W15，稳定、完整、原始trace通过再授权T2_C05_W15/T3_C02_W15/T1_C05_W12/T2_C02_W12/T3_C00_W13（均DL1018_VAL前缀）。B/C5/原constant及cosine GRU结果均复用，不重跑。root可直接监督已审启动命令避免调度等待；代码修改仍Luna执行。

主评分沿用顶层raw.scene.reference构造固定任务SO3及0–20s的20001状态位置Q；inner为20000区间补充，不可替代。复用已经golden核验的评分函数，禁止再手写移植quat或改取log.reference。报告全部输场、风组、逐轴/阶段、峰值/安全/clip/投影/耗时。

六场门仍为宏Q严格好于B且≤1.10×C5、任务SO3宏均严格好于B与C5、W15/HF位置组均不差B；原完整开发/独立测试门槛保留。开环对新目标/旧目标的RMSE和bias都需报告，不能用新目标loss更小代替控制胜负。只有按原门槛通过才考虑扩开发集，当前不授权DEV72/TEST或新Teacher采集。
