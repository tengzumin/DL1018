# GRU32 持续场景状态：下一项单候选任务书

2026-10-27，root主审，Luna极高实施。状态：只批准准备/静态与无Plant验证；正式训练release初始0、Plant初始0。用户后续研发授权有效，主审通过后再签一次正式训练。不因本任务宣称根因已定或论文达标。

## 已有证据和唯一假设

one-event-delay六场工程PASS但三项宏平均均FAIL，关闭、不扫延迟/增益。目标时钟差异和tracking破坏预测都未被支持为主因。ARCHITECTURE_MEMORY_SCOPE确认所有attitude比较实际是15事件窗口，GRU/DSSM每窗口重置；原RBF隐权重却跨1999事件递推。待检验假设是短窗口策略蒸馏不足以表示教师的长期内部状态，而非“GRU天生优于MLP”。

## 固定候选与数据

新目录 gru_stream_c5_teacher_v1，候选名GRU32_STREAM72_S2026102001。复用旧GRU15的单层GRU(13,32)+Linear(32,3)结构与PyTorch gate定义；不扩宽/加层/加新输入，不加新在线权重更新。新网络权重训练后冻结，仅自身hidden state在一场内持续更新，每场初始化0、每10ms只处理一次当前13维输入，不重放滑动窗口历史。明确这不是在线权重自适应头。

只读matched_teacher_data_v1.npz的C5 TRAIN24+VAL48_AS_DEV_TRAIN两部分，72场各1999事件；按原顺序保留时间。输入13维白名单及post-DMAX/pre-beta rbf_output_raw标签不变。直接复用旧GRU full72 normalizer的mean/std/target_rms及SHA，不重新拟合统计；仅读C5数组，不用B24值或TEST。禁Jhat/Jdot、真实惯量/质量/风、RBF权重/隐状态、observer等部署输入。

## 唯一正式训练合同（当前尚未授权）

seed2026102001，一次fresh-init训练，最多且固定60000 optimizer steps，final60000唯一发布，不做checkpoint选择/种子搜索/延长。Adam lr1e-3、weight_decay1e-5、SmoothL1 beta1.0，与旧训练一致。新因素是场内持续状态的序列训练/推理协议。

固定TBPTT128事件、batch4条场景流：同批4场从首事件开始顺序推进，场内hidden跨chunk携带、每chunk边界detach，场结束才reset0；场景cohort按固定seed洗牌，不跨场串hidden。1999最后79个有效事件，若padding至128，只对有效样本算loss且末hidden丢弃，不让padding跨场。明确梯度最长128事件，并非全20s反传；hidden值可覆盖完整历史。每optimizer step的有效样本数和累计数真实记录，不把padding算数据量。正交输入/输出状态reset、无未来标签进入forward，训练中断不悄悄重启另算同一job。

先准备trainer、source/data/model身份、release0和toy dry-run（无optimizer.step），不训练。root审核后authorized_jobs=1才启动唯一GPU作业；前100步估时是正式训练的一部分，继续至60000，不因此调参。最终保存pt/MAT/normalizer/逐步日志/receipt/准确命令，旧模型与数据只读。产物预算2GiB，单GPU任务。

## 数值与接口验证

重用现有GRU门计算/export数学；先CPU toy或固定输入对比整序列forward与逐事件carry逐点一致、场景reset可复现、未来输入扰动不改变过去输出、padding不影响有效前缀、detach不会跨场。MATLAB新stream forward/step显式hidden入/出，不沿用会重置的GRU15窗口接口。部署更新顺序保持current measured feature->GRU hidden->当前输出，β/dmax处理一次，不加上一试验的10ms输出延迟。

最终模型的Python-double与MATLAB-double逐事件输出/hidden目标max1e-8；另报告训练float32差异（阈值预定output1e-4 rad/s²,hidden1e-5），完整1999输入序列及reset/未来扰动核验；失败先定位而非放宽。权重和normalizer合法性、非有限和shape检查、source hash与实际which路径必验。

## 后续闭环准备边界

位置固定C5 DSSM14/M110，BS/固定J0/Jdot0/C0/滤波[Inf Inf6]/dmax/max_tilt/Plant/执行器均不变，姿态RBF输出更新关闭，无惯量重建。新模式应明确GRU_STREAM，不能把GRU权重冒充MLP参数。可复用旧GRU15经核验的gate/options/导出校验，但实际DEV必须基于已验证run_mlp15_dev72_closed_loop，不能误接GHP7 generic入口。控制新增仅限新GRU stream分支、必要模式规格/模型验证、forward/step；不引入通用框架。

第一阶段先完成trainer和release0交root，控制集成可在训练期间单独准备但不启动Plant。root通过训练/数值/真实入口审核后，再发首T1_C08_W15工程pilot与原6场DEV机制筛查任务书；不自动跑DEV72/TEST。B/C5继续复用；若需证明记忆协议本身作用，先核可复用的同场GRU15-window结果，缺失时再单独授权比较，不能把与MLP不同架构的胜负当纯记忆因果。

所有阶段PowerShell7，显式R2025b，单重Plant/单GPU；MKL_THREADING_LAYER=SEQUENTIAL，OMP/MKL线程1，禁KMP_DUPLICATE_LIB_OK。新目录写入，旧产物不覆盖/删，不推Git模型/MAT。不改变Q/姿态评分、胜负容差或最终B/C5门槛。
