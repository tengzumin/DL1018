# C6 代码与离线检查交接

状态：CODE_ONLY，通过代数及三个已审DEV host的同状态回放；尚未运行MATLAB/Plant/训练/GPU，尚不能宣称修复八个输场。冻结C5与正式TEST的源码/模型/流程均未修改。

## 公平条件先核清

- 当前B锁与C5锁的32个活动源均按实际文件核对SHA；31个完全同字节，唯一不同是核心中已冻结的M110/混合参考/诊断。位置BS、姿态BS、命令滤波、分配、Plant/积分、模型forward/helper等共享。具体源/哈希和完整核心差异在上级 SOURCE_FAIRNESS_v1.json、B_C5_CORE_SOURCE_ONLY_v1.diff。NO_PRED helper只有预测梯度置零的科学差异，见 C5_NO_PRED_HELPER_ONLY_v1.diff。
- 三host的名义位置BS、预网络X14、M110/eta、label过去区间、beta、输出先更新、联合更新都已实际独立重建，最大差4.98434626905464e-13。同一源码并不代表不同闭环中的状态相同；本次反事实回放始终固定每一条host自己的状态/输入。
- 旧全胜DEV32的默认配置源码SHA与历史preflight before完全相同，入口直接default_config，源链命令滤波角加速度限为[8,8,6]；当前实际由effective_config.mat加载并强断言为[Inf,Inf,6]。这也是历史与当前条件差异，不能从当前default_config仍写[8,8,6]误判实际运行配置。此为旧源码链证据，没有追加逐运行cfg解码。
- 旧全胜为不同cubic八字/N_KAN包的5–20s 32/32；0–20s为31/32，0–5s为0/32。不能把它移植成当前C5的全程全胜，或只以B-Q差归因。详见上级 FIRST_FACTS_v1_ZH.md。

## 唯一优先假设

当前没有确证部署bug。完整C5相对NO_PRED的全72早0–5s平均Q差+0.247089mm、后5–20s差−1.052711mm；T2对应+0.524253mm、−0.304006mm。预测项有阶段/任务取舍，不能直接删除。

待验证机制：ready到beta饱和期间tracking乘beta，而prediction未乘beta；相对权重及方向竞争有瞬态偏置。C09_W10的Y轴0.32–1.8s在C5 host上61.2%事件预测/跟踪步反向，独立NO_PRED host为63.9%；W15代表同阶段为0%。方向反向不是有害的充分条件，需真实单因素干预。

## C6唯一改动

candidate = W - h*gamma*beta*(phi*s_eff') - h*lambda*W - rho*beta*predGrad

只给原预测项乘既定beta。h=.01、gamma=12、lambda=.002、tau=1、rho=.01、首ready n=320、beta=(n+1)*.001/1.8上限1、输入/输出、联合投影±60、输出clip±3、模型/W0/normalizer、PCF M110均保留。MATLAB helper和Python reference的diff各只有一行科学改动。

- MATLAB helper SHA256：53e5c2fa8098769b84952c93469625eae9abedccb199a1c57d3746b8005bd067
- Python reference SHA256：0ad47c691f5411e36d75ab5f1f78ecb0a945564371ecfb2fc18066b47ae2bcac
- 绑定/源SHA：C6_SOURCE_BINDING_v1.json
- 最小差异：MATLAB_C5_TO_C6_v1.diff、PYTHON_C5_TO_C6_v1.diff
- 检查代码：experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp/check_c6_code_only_v1.py

Python reference保留冻结C5原自检及历史注释，新增C6执行证据只以本目录 C6_CODE_ONLY_REVIEW_v1.json 和执行收据为准，不把继承的历史注释算本轮失败。

## 实际验证

真实命令 python -B experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp/check_c6_code_only_v1.py 自然exit0，UTC2026-10-23T17:35:45.926666+00:00输出。未执行MATLAB，因此MATLAB结论限于与冻结helper只有一行差异的静态核验。

首ready无历史完全一致；输出先于更新、输入权重不被原地改写；beta=1同W/输入的输出及更新相同；preprojection(C6−C5)=rho*(1−beta)*predGrad；联合clip双边界与“不得提前分段clip”检查；8类NaN/形状/时间/缺失历史输入拒绝，全部PASS。synthetic精确差最大7.3346e-17，三个host原输出parity最大6.6613e-16、逐步差式最大2.2165e-16。

只复用先前已读的三host：C09_W10 C5、C09_W10 NO_PRED、DEV_T1_C01_W15 C5。C6阶段仅重读六个事件字段，未重新整文件哈希或解码其它raw；整文件SHA引用先前审计，新增字段读取前后stat/大小不变。C6_FORCED_STATE_TRADEOFF_v1.csv保存全部XYZ、三个阶段的代数/拟合/输出取舍。

C09_Y启动期同W的预测步RMS从.00221280降至.00170868，单步prediction loss平均增加1.2693e-4，而tracking面乘读出改变量均值为−6.3848e-6 m²/s³；无风代表该tracking量为+1.3780e-7，暴露可能损坏既有胜场的机制：削弱与tracking同向的有效残差校正。强制状态C09_Y残差拟合RMS从.222031升至.232434，不能隐瞒该代价或把读出变化称为位置Q改善。

beta>=1仅保证同状态公式相同；C6较早的权重差会保留到后段，回放后段读出已非完全相同，更不能声称后段闭环保持原样。上一版分析CSV中列名mps3的乘积量实际单位应为m²/s³，数值未变；本C6表已正确命名。

## 给根审核的最小闭环方案（未获运行授权）

建议沿用已有ROUND_SCREEN_12_SCENES.csv的固定12场/原顺序，不新挑八个输场。已复制为 PROPOSED_SCREEN12_SCOPE_v1.csv，原SHA176ed5770824a241b5c41b9c786f2110b730a7783414152875181985d497a32e。合法复用同场C5/B，唯一新增候选C6，至多12个新Plant、0训练、0新B、0TEST。根须另行冻结隔离core/wrapper、cfg/opts、源绑定、无Plant放行和资源时机；本helper包不是全闭环入口。

预登记要区分的结果：T2早0–5s、Y轴/首beta阶段的启动代价是否减小；同时保留全12全程Q、HF/W15与其它任务的回退。原screen不支持完整72或独立测试结论。若机制方向不成立或必要预测校正受损，应否定此候选，不追加beta指数、tau/gamma搜索。若初筛通过，是否验证整个原DEV72由根决定，不能只报八输场。

所有后续轻量numpy命令须显式 OPENBLAS_NUM_THREADS=1、MKL_NUM_THREADS=1、OMP_NUM_THREADS=1，并顺序执行；本次4.15秒检查已自然结束，无本执行者后台进程/session。正式冻结验证重负载优先。

上级v1历史表列名错误和v1回放夹具g=9.81错误均保留，后者修正为实际contract g=9.8后通过；都不是部署bug。历史混合报告意外暴露事件另见上级v2/HISTORICAL_TEST_EXPOSURE_INCIDENT_v1.json，不复制或使用其性能数字，也不声称已证明它与当前TEST物理独立。
