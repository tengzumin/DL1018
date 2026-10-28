# 当前续跑状态（2026-10-25）

用户最新要求：**所有后续 subagent 只用 GPT‑6‑Luna、xhigh；主模型负责审核和决策。** Sol执行代理已撤回，撤回未终止OS实验；历史已完成/中断agent不再唤醒执行。当前两名Luna分别为 `dev3_monitor_luna`（接下述新入口实施）和 `c00_residual_diagnosis_luna`（仅离线新raw诊断）。

DEV3_A01真实批次已结束，MATLAB PID19860退出，原session24428关闭。`dev3_v1/attempts/DEV3_20261025_A01/batch_status.json` 为STOPPED_ON_FAILURE：2次runner、2次已确认Plant、40000 transitions、unknown0、training0；4次后续航次NOT_RUN。未中断运行；是原性能门槛触发正常停止。当前不得重启旧attempt或修改旧release/锁/STATE/39源。

root已用独立h5py+SciPy读两新raw，Q/SO3计分与原记录一致，源码/输入/receipt/raw SHA问题数0。见 `root_review_v1/DEV3_A01_INDEPENDENT_REVIEW_v1.json`（SHA `9bd3e49290ec4222a29155c7187a487f7bf122cfef66b307e7264438095e4020`）。candidate相对baseline：Q +2.5209584565179244e-7m（+0.003058%）；SO3 +1.3424258495955109e-6rad（+3.7408%）；两臂均完整STABLE，sat/clip/tilt均0。旧筛查FAIL保持不变。

已观测：C00无形变/真实wind torque接近1e-18Nm，candidate估计约1e-12Nm；旧RBF误差面更新仍输出约1e-7Nm。命令滤波半隐式参考相对连续ZOH加速度轨迹有精确0.5dt²a离散项。尚不能由这些事实宣称唯一闭环因果；Luna正在同记录全事件残差、LPF/投影与求积核验。禁止凭幅值或不同闭环状态直接断言组件因果。

新任务书 `MORPH_DEV2_DIAGNOSTIC_TASKBOOK_v1_ZH.md` 仅授权隔离实施/静态检查，**尚无新Plant授权**。目的为在原计划剩4次内诊断未跑的三维八字C02/W15和方形C10/W11的主动形变价值；39源/model/cfg/参数全不变，旧C0失败共同报告。只工程/安全失败停止后续，性能正负均记录；这是预先定义的应用域诊断，不是把旧DEV3改判PASS。新产物预算2GiB、磁盘底线30GiB；不训练、不调参、不读TEST、不删数据。

新文件仅写 `morph_dev2_diagnostic_v1/`；其wrapper/launcher、静态结果、完整候选锁由root实际审阅，且离线诊断无实质实现bug后，root才可冻结并写独立新release。当前没有可直接执行的新Plant命令，不可使用旧release启动新scope。目标仍为主动变形应用创新的论文证据包，不以全新自适应控制方法为自动研发门槛；远未完成，不标记goal complete。
