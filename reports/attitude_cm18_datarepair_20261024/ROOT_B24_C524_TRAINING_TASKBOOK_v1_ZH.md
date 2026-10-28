# B24 / C5-24 配对训练诊断任务书 v1

状态 IMPLEMENTATION_ONLY：批准隔离 reader、trainer、零步自检源码实现；未批准数据汇编实际批次、正式训练或任何新增闭环。Root 审核后单独放行。当前 TRAIN24 实际采集继续。

唯一因素为训练轨迹来源 B-position 与冻结 C5-position；二者姿态教师均保持在线 RBF。目标同为固定方程直接 Cstar/beta，不得把旧 behavior-residual 当标签。

## 固定数据与共同身份

- 24 canonical TRAIN IDs 与顺序严格等于 ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json 的 scene_rows 数组顺序，SHA 88d7312087025a331dd532410b0ef31ed2dcb7dd3175239ad1d47bc68dd65f0b。两分支每场取 zero-based 0,5,...,1995 的400行，总9600行，场内索引是 event ordinal，不是 plant index。保存 ordered (canonical scene,event ordinal,plant index) row-map SHA；分支相同。
- B24 从冻结 Cstar ALL816 TRAIN 中按此顺序取同24场，不扩读 DEV/TEST，不把 B768当等规模对照。原 Cstar manifest reports/attitude_cm18_datarepair_20261024/cstar_all816_v1/CSTAR_RELABEL_ALL816_v1.json，SHA 421298399aacf2d7f82031f2bdecc39eacacc28196c7b872b925866655d211a6；reader experiments/attitude_cm18_datarepair_20261024/read_cstar_split_v1.py SHA ced4251719f986d762f29ccced04fb80208a28e7aed1e2fe12d3b504955a4096。复用其验证/读取纯函数，不改冻结源。新 C5-24 必须等待全24实际完成、独立算术与因果特征审计通过，并绑定每场raw/start/cache/export源码身份。
- C5 VAL48 必须等待新的直接 Cstar 重标注与审核通过；B VAL48 来自同冻结 B Cstar ALL816。两套VAL仅诊断，禁止训练、checkpoint选择或称新独立测试。
- 共同 normalizer 来源 experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json SHA 23e8432f4a1c3f71bfaaa4e3a7b07c4b9f6b0201842e35ba3bcb032ac61fd781；直接使用 input_mean_float64、input_std_float64、train_axis_rms_rad_s2_float64，canonical三数组SHA 12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a。不从float32反推、不重拟合、不剪裁标准化输入。该共同尺度含B全TRAIN768先验，须如实披露，并统计两分支标准化输入/目标范围。
- 共同初始六组 W/b 取 experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/initial_parameters.npz SHA 1f3a469eeb648345bacf6f6aa3be906e10efebc91e24442914fd32e880439cb2。仅取 W1,b1,W2,b2,W3,b3，不能用训练后 step40000权重。模型纯模块保持原 CM18 2456参数与zero-basis精确零输出，numpy/torch纯模块SHA分别 ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6、bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0。

## 唯一一对训练

每个分支独立重新初始化与optimizer；seed2026102001，固定60000 optimizer steps，batch512，NumPy default_rng(seed)在9600 ordered rows上有放回均匀抽样。两分支实际抽样流逐batch更新SHA并必须相同。Adam lr.001,betas(.9,.999),eps1e-8,weight_decay1e-5；SmoothL1 beta1、三轴与batch平均，target/common_axis_RMS。float32 CUDA deterministic，无AMP/TF32、无seed搜索、无额外步数、无resume。一次仅一个GPU作业。固定最终60000步作为唯一候选，不以VAL/DEV切checkpoint。

仅初始/最终checkpoint和每1000步进度/loss日志，记录真实启动、完成optimizer步数、耗时与失败；不覆盖已有输出。正式两次训练及零步自检均需Root release。零步自检不得调用optimizer.step；核24场/400行/事件映射/共同float64normalizer、float32初始state、zero-basis、有限前后向及Python纯模型一致。

## 评分与判断

两个模型分别在同一组 C5 VAL48 输入与直接目标上配对算：raw输出误差、cStar action误差，以及部署 beta*clip(prediction) 的线性物理残差 E0-G*action。另在同一B VAL48输入/目标上做另一域参照。G存储顺序须按各cache显式schema解释，B旧column-major与C5新row-major不能混用。逐scene/task/wind/axis/phase/zero-basis与clip情况均保留，不丢难例。主汇总为逐场向量RMS的等权均值，HF=W09-W14、无风=W15分别报告；normalized训练loss不是跨域性能结论。

预登记：C5-24若C5 VAL整体物理残差严格降低，且HF及W15组均不高于B24，才支持进入固定12场闭环筛查；任一不满足则先审核失败模式，不自动扩采768、不调seed或checkpoint。该门只是机制筛查，不是论文验收。闭环任务书另行冻结，离线改善不等于闭环改善。由于24场仅含C00/C15和四风组，负结果也不能直接否定所有matched数据方案；共同B normalizer及姿态RBF教师与CM18部署差异须保留解释。

## 路径与保护

新代码 experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1/；新报告同名reports子目录；不改历史trainer/cache/模型、不读TEST、不改C5/C7、不启动Plant。新产物上限1GiB、磁盘下限30GiB。reader与manifest契约需与VAL重标注执行者明确对接，最终源码/数据/审计全部SHA由Root填release，不猜字段、不绕过缺失身份。
