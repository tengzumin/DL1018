# CM18-A1：一次正式训练任务书 v1

## 决策及范围

主审核依据新数据四场逐事件复算、NumPy/Torch/MATLAB 合成参数一致性和梯度检查，批准准备一份单候选训练实现。当前 ALL816 离线导出继续运行；本任务书不自动放行 optimizer 或 Plant。训练启动还需完整816场合格、缓存与源码身份审核，并由主审核写入独立 release。

目标是替代姿态 RBF 的残差估计，模型为准备任务书中唯一 CM18-A1，不改结构或输入，不加载旧实验权重；位置 C5、C7 暂停状态及历史结果均保持。旧 B 数据生产源码缺口继续披露：这里只能称行为数据上的当前方程重标注，不称新采集或独立测试。

## 固定数据和算法

- 只接受 ALL816 最终 DATASET_MANIFEST，768 TRAIN +48 VAL；拒绝任何失败行、重复场景和 TEST。启动 release 锁定最终 manifest SHA、reader/model/trainer 源码 SHA。
- 每个 TRAIN 场景按事件数组下标 `0,5,10,...,1995` 取400行，共307200行。VAL48使用每场全部1999事件。顺序保持 manifest 中顺序；不按成绩筛场。
- 输入均值、总体标准差（ddof=0）、目标逐轴 RMS 仅由上述 TRAIN 拟合行计算，float64 计算；标准差下界1e-6，目标 RMS 必须严格正。归一化物理输出和标签使用同一保存尺度。VAL不参与拟合归一化。
- 唯一随机种子2026102001。调用已审核 NumPy fresh Xavier-uniform 初始化器获得全部参数，然后载入 Torch；不得采用 Torch 构造器隐含初始化作为正式起点。保留初始参数、实际 float32 起点、normalizer 和哈希。
- 正式训练 float32，单个 CUDA GPU，不启用 AMP/TF32；Torch deterministic algorithms，固定种子；如确定性操作不可用则报错，不自行改算法或设备重启。
- Adam，lr=0.001，betas=(0.9,0.999)，eps=1e-8，weight_decay=1e-5；无调度、无梯度裁剪。batch512；每步由独立 NumPy default_rng(seed) 有放回抽取512个 TRAIN 行，记录采样规则。固定60000 optimizer steps，一次正式启动；出现非有限 loss/梯度/参数时保存失败位置并停止，不换种子重试。
- 损失为归一化预测与标签的 SmoothL1(beta=1)，对batch及3轴取mean。网络仍输出物理值，损失计算前按保存 TRAIN axis RMS 除回归一化值。
- 在step0及每1000步做全部VAL评估，eval/no_grad，分块推理。选型分数为各场 `sqrt(mean_events(sum_axes(normalized_error^2)))` 的场景等权均值；严格更低时更新best，相同则保留早step。step0也可成为best，不隐藏训练退化。报告每场/各轴/phase物理误差以及零预测基线，禁止将标签预测误差当闭环收益。
- 唯一正式运行目录不得覆盖；保留initial/best/final权重、每1000步指标、逐场VAL表、normalizer、训练配置、实际起止时间/optimizer步数/设备/环境版本及失败原因。每100步写轻量进度（实际步数及loss）。产物预算1GiB；不复制raw缓存，不上传checkpoint。

## 启动前检查与后续门槛

实现者仅新增 trainer 源码和对应简明自检入口，不改已冻结导出、reader、model。允许 SCREEN4 只读数据形状/normalizer路径自检和零 optimizer 载参/前向/反向检查；不得运行 optimizer.step、不得读未完成 ALL816 或 TEST。主审核另检查 reader 的最终 manifest 约束与训练输出独立性。

完整数据通过且 ROOT release 锁定后才启动一次训练。启动时确认磁盘剩余至少30GB、没有其他训练GPU作业，不终止任何既有进程。CPU数学库使用已验证的进程局部 MKL_THREADING_LAYER=SEQUENTIAL，OMP/MKL/OPENBLAS_NUM_THREADS=1，禁止 KMP_DUPLICATE_LIB_OK。

CUDA启动前额外设置进程局部 `CUBLAS_WORKSPACE_CONFIG=:4096:8`；这是当前Torch 2.6确定性矩阵操作的环境要求，见[官方说明](https://docs.pytorch.org/docs/2.6/generated/torch.use_deterministic_algorithms.html)，不改变学习算法。Windows WDDM实测会把explorer等桌面C+G进程列入 `--query-compute-apps`，不能将非空列表直接解释为存在训练。ROOT在启动前审核实际GPU行、CIM进程身份及Python任务，将当前批准背景行写入release的 `gpu_background_rows`；trainer只允许实际行属于这份快照，未知新增进程仍拒绝，GPU总利用率高于10%亦不启动。该快照是当次资源核验，不是跨运行通用白名单，不能据此声称后台完全没有GPU使用。

float32的1e-6标准差下界提升回float64时可能略低于1e-6。保留canonical float64归一化原件和实际float32训练buffer两套身份；部署导出使用canonical原件和训练W/b的double提升值，不从float32 buffer恢复canonical尺度，也不修改既有推理验证阈值。部署前量化两种数值路径的输出差，不将其称为逐bit同一模型。

训练结束必须用实际best权重独立复算 VAL 指标、重做 Python/Torch/MATLAB 双精度部署一致性和 float32训练/双精度部署偏差，再决定是否放行固定12场中的第一场工程检查。当前任务书不放行任何航次，不保证模型取代RBF成功。若失败，先诊断误差来源和闭环动作迁移，不自动扩大网络/换输入/搜索种子。
