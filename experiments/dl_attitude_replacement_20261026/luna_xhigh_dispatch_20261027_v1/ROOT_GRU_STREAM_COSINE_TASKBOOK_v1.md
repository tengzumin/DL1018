# GRU_STREAM 单因素优化日程验证

主审 /root，Luna xhigh 实施。2026-10-27 冻结。本任务检验有限步数的优化日程是否留下可修复拟合偏置，不认定学习率为唯一根因，不更换最终论文/性能目标。

## 决策证据

现有 GRU_STREAM 六场位置胜 B 5/6，宏 Q 比 B 低7.337%、比C5高1.386%，任务姿态胜C5为0/6；原版本关闭，不扩DEV72/TEST。完整72条训练序列的同状态教师拟合均值偏差为[+0.8600456,-0.4984014,-0.0410935] rad/s²。固定hidden下，实际16-chunk等权 SmoothL1 对输出bias梯度为[+.0356261,-.0179316,-.0222788]，非零且与event等权结论一致。不是只看所选6场。该梯度不重构Adam历史，也不证明单调降低训练loss能改善闭环。

依据 reports/gru_stream_target_fit_diagnosis_20261027_v1 的同状态A/B/C证据，暂不重标教师。姿态参考可行性报告说明主任务与内环参考不同，但不能替代原SO(3)门槛或解释无风下全部退化。

## 唯一改动与训练

候选 GRU32_STREAM72_COSINE_S2026102001；新训练目录 gru_stream_cosine_c5_teacher_v1。复用 gru_stream_c5_teacher_v1 的已审实现、完全相同72条C5数据/normalizer/初始参数，GRU(13,32)+Linear3、TBPTT128、batch4、scene cohort顺序、尾段79有效事件、SmoothL1 beta1、Adam weight_decay1e-5和确定性设置均不变。仍合法13维输入、post-DMAX/pre-beta RBF标签，禁止Jhat/Jdot/惯量重建/Plant truth部署输入。

仅将恒定lr=1e-3改为预定余弦日程：第s次optimizer update（s=1..60000）采用 lr(s)=1e-5 + (1e-3-1e-5)*(1+cos(pi*(s-1)/59999))/2，首步1e-3、末步1e-5；在该次update之前设置，逐步记录真实lr。无warmup、无重启、无plateau触发、无早停/选checkpoint。一次fresh-init、固定seed2026102001、固定60000步，final60000唯一产物；不接着旧checkpoint训练，不延长/扫种子。预定初始state_dict SHA应与原82d952ce8f150388015bc2776b8acceb9c9da59814470eb036ec9ca99420e06e相同。

先准备source/data/command与release0、无optimizer自检；root审核最小diff后签唯一正式训练，不等用户再次确认。源文件与旧产物保留原位。单GPU任务，新增训练产物上限2GiB。PowerShell7，沿用原成功的依赖预载后unset子进程KMP变量再runpy启动，MKL_THREADING_LAYER=SEQUENTIAL、OMP/MKL=1、CUBLAS=:4096:8，记录实际命令及exit码，不再重复已定位环境启动失败。

## 离线与闭环判读

正式训练后复算全72教师拟合的all/mature/late RMSE、bias，以及event等权/实际chunk等权输出bias梯度。预期比恒定lr模型减少偏差与梯度；未观察到则如实否定此机制，不能因loss下降宣称控制改善。

部署新目录 gru_stream_cosine_dev_v1。数学runtime必须与已审 gru_stream_dev_v1 字节相同；仅模型身份/目录/元数据与必要driver候选名称绑定改变。无新增在线head，无新输入/滤波/延迟；位置C5 DSSM14/M110和BS/J0/Jdot0/[Inf Inf 6]/dmax/30°投影/Plant/执行器保持。不要复制历史runs/raw。模型字段保持同一GRU MAT接口。

核实际模型完整1999事件Python-double/MATLAB-double输出与hidden误差各≤1e-8；float32输出≤1e-4 rad/s²、hidden≤1e-5，场首reset/未来因果/当拍dmax→beta→J0、真实cfg/which与零预算拒绝检查。只替换模型，不以toy通过代替实际模型通过。

root核验后先仅DL1018_VAL_T1_C08_W15；工程安全/原始trace通过再授权其余五场：T2_C05_W15、T3_C02_W15、T1_C05_W12、T2_C02_W12、T3_C00_W13（均完整DL1018_VAL前缀）。B、C5、原恒定lr GRU六场全部复用。不得因汇总或审计错误重跑已完成航次。每阶段release单独snapshot，不用新release重审旧raw。

主指标、配对规则及六场判断沿用ROOT_GRU_STREAM_PILOT_TASKBOOK_v1.md：宏Q优于B且≤1.10×C5，任务SO(3)宏均严格优于B和C5，W15/HF位置组均不差于B；完整报告各轴/阶段/峰值/安全/投影/耗时与所有输场，inner不替代任务SO(3)。六场通过不等于论文或独立泛化。当前不授权DEV72或TEST。新训练日程和闭环成败均入账；无需达到旧候选某指标就修改门槛。
