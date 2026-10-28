# CM18-A1固定首航：准备任务书

## 当前决策

仅批准准备源码及无Plant预检，不批准实际航次。实际训练已自然完成60000步，按预登记VAL规则选step30000；完整VAL独立复算与三组实际权重MATLAB推理一致性通过。SCREEN4同状态动作重放仍待实际执行和ROOT审核，不得跳过这一门槛。

## 固定候选与首场

候选为全新CM18-A1固定权重姿态补偿 + 原C5位置算法/模型/初始化。模型JSON `experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json`，SHA `ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae`；对应best checkpoint SHA `105585385157da3f1b404ab24606d0717287638e4a1ca710790633cd16d233a4`。不能换Head、切轴、换step或添加在线学习。

新引擎为 `run_cm18_closed_loop_v1.m`，SHA `4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a`；相同目录的延迟位置helper必须与C5父源字节一致。首场只能是已有SCREEN12清单中的 `DL1018_DEV_T1_C01_W15`，20秒、1ms转移、100Hz事件，实际放行额度最多1航次，不能自动运行其余11场。

直接复用该场已封存C5 raw中的scene，核其SHA `b61f01ab5920de766b8596512490b596e3959fa87368cd40a3b30758831fe651`。固定cfg/opts从原C5 `C5_DEV72_PREPARED_CFG_OPTS_v3.mat`加载，SHA `842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a`。原DEV72输入lock/source inventory仅用于核对其真实依赖和设置，不修改历史contract/release或其deadline，不冒用旧C5授权执行新候选。

## 无Plant准备

新增最小准备与首场runner，可写在独立A1目录；不得改engine、训练、forward、历史工程或已有配置。重新建立原C5有效依赖路径，核完整active_source_inventory文件身份。新增引擎使用唯一函数名，禁止调用旧episode wrapper。延迟位置helper名称覆盖仅允许新副本与父字节相同且which指向新目录；其余C5位置Head/forward依赖必须保持原有效路径及SHA。

opts只允许三个姿态RBF flag改为显式logical false，新增cm18_attitude_v1.enabled/model，以及本次独立marker路径。将这些允许差异反向还原后，应与snapshot原opts isequaln；cfg完全相同，原位置W0、mask[1;1;0]、PCF、延迟预测开关、全部位置模型参数/更新常数不变。全model/normalizer身份均来自已审部署JSON，不加载旧KAN姿态输入/权重。

准备结果保存准确cfg/opts/scene/source/model身份和可复算SHA，记录实际which/函数handle来源、20s时间与场景初态/风/形态命令身份。可以加载/解析/校验，不得调用引擎、RK4或episode。ROOT另核无Plant结果后才可能写首航release；runner缺少准确release或身份不符须在Plant前终止。

## 未来首航执行约束

实际启动时仅一个重负载闭环作业，不结束、抢锁或打断任何既有进程。磁盘至少30GB余量，本场新产物预算100MiB，不自动删除。新目录不得覆盖；执行前写attempt/start及源码输入身份，第一真实转移marker由引擎现有first-step接口写，完成/失败原始日志均保留，外层据真实status和完整转移数判定，不得只依OS0。

原物理安全、执行器、有限性阈值保持。运行完整后核20000转移/20001状态、1999事件、模型固定、全部CM18输入因果重建、raw/clipped/beta/J0/held torque/nominal-minus-comp闭合、RBF输出/更新关闭、C5位置配置相同及零/非事件保持。首航只作工程安全和机制检查，不把单场胜出称论文结果。

计分沿用0–20s三维位置RMSE，未舍入值及1e-12m容差；新增姿态SO(3)RMSE/峰值和运输至实际body坐标的角速度误差，报0–5s与5–20s、逐轴、clip/sat、安全和原始状态。先与同场C5+原姿态RBF配对，不把零估计离线基线称为RBF对照。所有退化项保留。首场后由ROOT独立复算，另决定是否批准原清单其余11场。

C7继续暂停，C5 DEV/TEST/消融和历史论文证据保持冻结，不访问旧TEST作研发。本阶段不进行新的模型搜索或训练，不上传任何MAT/模型/缓存。
