# TEST48独立入口：仅实现与DEV无Plant检查准备

状态：CODE ONLY；本书不授权MATLAB、Plant、训练、TEST场景生成或解封。实施者为Luna xhigh，根主审。只新增 `experiments/c5_test48_v1/` 和 `reports/paper_continuation_20261023/test_entry_v1/`；不修改当前消融或任何历史文件。只用PS7。实现前必须实际读取只读准备报告并解决其中的输入身份缺口；不得以发布包不含MAT推断本地模型不存在。

## 科学身份与最小实现

六个方法固定为B_TRACEABLE、原corrected DSSM14、corrected KAN14、C5 M110、C5_FREEZE_TRAINED_W0、C5_NO_DELAYED_PREDICTION。逐个从实际已审开发运行找出源码/模型/normalizer/cfg/opts；实际文件存在、实核SHA和模型数组后才建立输入清单。无训练、参数搜索、模型重导出或未经证明的源码替换。旧B物理场景来源与新B计分来源分列。C3是既有开发坐标对照，不增加第七种TEST方法。

复用已审core、wrapper和helper，科学正文保持字节一致；新代码仅负责隔离准备、生成/封存场景、重置状态、运行和记录。需要复制便只复制到短路径source包，建立原路径/新路径/同SHA表。MAT/模型只在本地引用或必要时本地复制，绝不写入Git清单。若旧方法实际输入缺失，明确停止该方法准备，禁止自行训练替代模型。

为避免多个同名core/helper的缓存混用，六方法各用一个独立、顺序MATLAB进程，每进程48场；不得开六并行进程。顺序为上表顺序，场景ID字典序，固定单线程参数；同一方法每场重置模型状态、W0及控制器，不继承学习权重。wrapper实际函数句柄与which首路径逐项绑定到冻结清单。此选择替代尚未冻结草案中的逐场轮换；计时报告披露方法块顺序，不能声称已消除系统时间漂移或硬实时保证。

## 分离三种权限，不越过当前阶段

1. **DEV_INPUT_EQUIVALENCE_ONLY**：源码/模型/配置检查，使用原72个开发ID调用被封存的GET生成器，比较已用物理B输入。禁止BUILD、TEST ID和Plant调用。代码先写好，待根审后才能启动此无Plant模式。
2. **TEST_INPUT_FREEZE_ONLY**：只有另行根签发的输入生成放行书存在，且完整DEV消融/贡献/限定理论和六方法/计分/统计均已通过并冻结，才可生成原封存48个TEST场景并保存唯一共享场景MAT和逐场哈希。此模式0 Plant，TEST_accessed=true；当前不得调用。读取/生成数组前检查权限，不先GET再判断。TEST48列表来自原设计元数据，不新建测试集。
3. **LOCKED_TEST48_PARENT_APPROVED**：只有下一份独立Plant放行书引用输入冻结自然OS0、共享MAT/逐场哈希、全部方法身份及计分统计，才可运行最多288个唯一(场景,方法)组合。当前不得调用。禁止复用任何TEST baseline raw或依赖它生成其他方法输入。每方法进程由PS启动并记录真实自然OS退出；父进程不代写未发生的成功。

不创建任何放行书。允许把未来模式实现为缺少正确放行即立即报错的代码；没有根签发文件不得生成TEST数组或调用episode。无条件/调试旁路均禁止。

## DEV生成器等价检查的真实字段

封存 `make_scenes_dl1018.m`、init/effective_config和实际依赖；GET会restoredefaultpath，完成生成后必须重新绑定方法路径，禁止解除旧G01/参考缓存保护。比较20001点time、初始12状态、全部reference字段、风、arms.command/rho_true/rhoDot_true/rho_hat/rhoDot_hat。命令/维度/离散ID严格相等；浮点数组报告逐项最大绝对差与bit相等标志，上限1e-12（按各数组原单位），不在失败后扩大容差。仅允许既有ACC_FIX_V1场景别名的明确规范化，不忽略物理数组差异。生成器差异若超阈值即停并交根定位，不运行Plant证明“差不多”。

## 工程与记录要求

新输出的实际绝对路径逐项预检<240字符，方法目录用冻结的短别名映射；历史长路径仅用只读extended前缀，不移动产物或改系统策略。PS日期保留ConvertFrom-Json的DateTime类型；根已实测二次Parse会把17:01Z提前8小时。读真实schema再写断言，禁止根据文件名v号猜schema、假定sceneIdentity有C3路径或external SHA。

每场保存真实输入/源码/模型/normalizer/cfg/opts身份、run_start、开始及first-Plant标志、raw/status与SHA、实际重置证明、安全/完整性、已启动调用数。保留失败和未自然返回状态，禁止自动重试、覆盖、静默补跑。DEV模式TEST_accessed=false，两个TEST模式必须true。原G06/G12/封存记录原位保留，新版本自行记录位置环协议。

controller_call_time_s计时正文不改，实际核对六方法边界；正式计时期间不并发其他重负载或全量审计/压缩/绘图/Git维护。记录机器、版本、线程和进程。预算/磁盘/原截止2026-10-24T17:01:00Z均启动前与逐场检查；不足30 GB或本周期80 GB产物余量不足则不启动、不删除数据。单场按已实测约24秒、至少180秒保守预算启动检查；明确区分实测估计与门限。

交付实际代码、源与输入小型清单、真实schema摘要、PS7语法检查及三个权限的静态调用顺序说明。根审前不运行MATLAB或任何模式，不修改STATE/Git。全量消融自然完成后的独立复算仍由根执行，不由本任务替代。
