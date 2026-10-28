# C7 双掩码机制臂独立源码审查

**静态源码结论：通过，可作为单因素机制隔离臂。** 该臂只把预测目标掩码改为 My=000，同时保留 tracking 掩码 Ms=110。结果可检验坐标匹配机制，但不通过方法原创性门。本文档初版时无 Plant 检查尚未登记；后续执行情况见文末追加记录。

冻结任务书 C7_SPLIT_TARGET_EXECUTION_TASKBOOK_v1.json 的 SHA-256 为 2602443a2f2ddab710338387e238187c99d81cf3e6f65725eeabc3ea2a8bc4dc。它固定模型、W0、更新参数与事件周期，列出 12 个 VAL 挑战场景，训练步数为 0，新闭环运行释放数为 0。该 12 场景集包含预先列出的屏幕失败场景，应按固定挑战集机制筛查解读，不能作为 72 场代表性泛化估计。

C7 runtime 相对冻结 C5 runtime 的差异只有六个小区块：新增独立掩码输入与校验、C7 精确掩码约束、tracking 坐标改用 trackingMask、标签参考积分改用 targetMask，以及日志保存两种掩码。它拒绝含糊的旧 position_coordinate_mask，源码不再引用 positionCoordinateMask。预测 helper 与 episode wrapper 和 C5 字节相同。关键位置：24–42、726–727 行为掩码校验；2023 行为 tracking 坐标；2032–2058 行计算完成区间标签；2117 行提交新权重；2274–2279 行积分标签参考；2873–2885 行写出掩码和标签字段。

事件时序保持因果。事件 n=j+10 时，代码用已完成 10 ms 区间的速度变化和参考积分生成标签，并与存储的旧特征 phi_j 配对。未改动的 helper 先用 W_n 计算当前 raw/applied 输出，再计算 W_(n+1)；当前 applied 输出随后保持一个事件区间。C7 在所有轴将标签参考积分设为 a_req，因此延迟标签是已完成区间的 d0 均值。标签使用已完成区间的实测速度变化，不读取当前样本 rf 作为预测输入。

解释时必须保留坐标失配项。由 sc=s−Ms⊙eta 可得 sc_dot=−e−K2 sc+u−d0−Ms⊙rf。若标签 dy=d0+My⊙rf，且理想 beta=1、无输出裁剪、u=dy，则物理 forcing 为 u−d0=My⊙rf，tracking 坐标 forcing 为 (My−Ms)⊙rf。故 C7 在理想条件下让物理 forcing 为零，但在 tracking 坐标中留下 −Ms⊙rf。真实实现还包含 beta ramp、预测误差、输出裁剪、projection、leak 及 10 ms 保持；掩码变化本身不预示 Q 会改善。

根提供的手算 fixture PARENT_HAND_FIXTURE_ORACLE_v1.json（SHA-256 a3bba5a76cc178241cd2119a7626c6bd5ae2e712a37dd9d9737ffac71b4ac93d）数值一致：beta=331/1800；d0=[0.5,-0.25,0.1]；C5 标签为 [0.8,-0.45,0.1]；C7 标签为 d0；s_eff=[0.16,-0.08,0.05]。同特征案例的 W_next 第一行吻合手算，正交特征案例把预测更新放在旧特征行、把 tracking 更新留在当前特征行。该段仅记录手算 fixture；后续 MATLAB/Python 无 Plant 合成执行结果见文末。

静态审查时要求先执行一次 $r_f$ 非零且 $\phi_j$ 与 $\phi_n$ 不同的无 Plant 合成检查；该项已完成，结果见文末追加记录。该检查区分 My=000 的完成区间标签与 Ms=110 tracking 面，并验证事件 $n=j+10$ 的当前输出来自 $W_n$、标签更新只影响 $W_{n+1}$。保留固定 12 场限制、安全门、无自动重试及无扩大场景规则。即使通过，它也只支持本次坐标匹配机制，不构成原创性证据。

C7 runtime SHA-256：9b03b3c979a0402fdcd0f50ff389db9a4dcb72c50537bd4d9bc41bd77ac4c33d。options helper SHA-256：97bf3e34bf3e1b85270aca39b62031934f3724b0c8ff4014216ebf5950f6db87。未改动预测 helper SHA-256：48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d；未改动 episode wrapper SHA-256：fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330。

DEV72 Gram 独立复算脚本 audit_dev72_gram_json_only_v1.py SHA-256 953dc8de5399a707e2b43c47f0ffc30436b7d111b2ec25a1bbff960f0ed0d4f6；结果 receipt DEV72_GRAM_REAGGREGATION_RECEIPT_v1.json SHA-256 711426f04127c91488f4048e72c3ccf497623bd74930fc7b40ea23b10e35e7ca。receipt 只读固定 DEV24+VAL48 响应 JSON，没有重读 raw 场景。此前一次范围过宽的搜索意外显示 TEST 元数据 ID/path/hash，已单独记录在 TEST_METADATA_SEARCH_INCIDENT_v1.json。

## 后续无 Plant 合成验证

2026-10-24 后续执行了固定非零 $r_f$ 手算夹具的 Python 与 MATLAB 检查，没有调用闭环、Plant、训练或 raw 数据。两者均为 PASS_SYNTHETIC_NO_PLANT，最大绝对误差分别为 $4.30\times10^{-16}$ 与 $6.66\times10^{-16}$，低于 $2\times10^{-12}$ 容差。结果文件分别为 C7_SPLIT_TARGET_PYTHON_SYNTHETIC_RESULT_v1.json（SHA-256 a262cb3d812427fde9bb228db24c49935a57137c4ae0f5055de1ace227fdc84c）和 C7_SPLIT_TARGET_MATLAB_SYNTHETIC_RESULT_v1.json（SHA-256 48f2524d6267385171e437eb552ac707ac6e26ba124871a0835c1539fe818785）；合并 OS receipt C7_SYNTHETIC_ONLY_OS_EXIT_v1.json 的 SHA-256 为 06921d67b328229f145738bb8b98f39a32b881a6a6f208775cf87b26bdc6c763。

夹具验证了 My=000 的完成区间标签使用 $a_{req}$、tracking 面仍使用 Ms=110、首个 ready 事件没有虚构旧标签、n=330 的当前输出先于权重更新，以及正交特征时预测梯度落在旧特征行。它通过实现语义检查，不证明闭环性能、真实数据事件审计或方法原创性。Plant 释放仍为 0；后续 raw 审计器尚未对任何 C7 raw 执行。

单文件只读 raw-event auditor `audit_c7_raw_event_v1.py` 已准备，SHA-256 `af888d4314e85ac67a472b03aada2528a80c7000d84a5931fc5b4ddf95e306ca`。它只接受任务书中显式指定的单一 VAL raw 路径、场景 ID 和 runner 锁定的 collector；静态核对了 C5 v7.3 解码方式、20000 transition 日志与 20001 state 行、零基事件时间和一基 MATLAB event_step_index。仅做 AST 语法检查，没有运行审计器、打开 C7 raw、访问 TEST 或启动 Plant。raw 含 W0 而不含冻结 normalizer 数组；审计器将用任务书定义的 little-endian MATLAB double 列主序 SHA 硬核 W0，normalizer 仍须通过冻结 model/snapshot 单独审计。
