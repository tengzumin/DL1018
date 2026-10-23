# TEST48 只读准备：身份与运行风险

状态：只读预审；未解封、未生成 TEST 场景、未运行 MATLAB/Plant/训练。严格 DEV72 消融仍未按当前协议闭合，因此本文不构成 TEST 放行。

## 六方法本地身份

机器表 `TEST_METHOD_IDENTITIES_v1.json` 记录六方法的实际路径、锁、SHA 和代表性快照。DSSM14 与 KAN14 的模型文件在本地外部参考包中实际存在，哈希与接受记录相符；不能据 Git 发布包不携带 MAT 文件而误报“模型缺失”。实际 `model.model_id` 是 `DSSM14`/`KAN14`，两者均为 seed `2026102001`、step `60000`、input_dim `14`、window `32`、W0 为 `33×3`；report 中的长语义 ID 不是 MAT 里的 `model_id`。DSSM/KAN 使用同一 train-only normalizer，但有不同的模型 MAT、checkpoint 和 `run_start.mat`。

旧 corrected pair 没有一个跨方法共享的 cfg/opts 快照。现有 cfg/opts 在各场的 `run_start.mat` 中；身份表给出 VAL `T1_C00_W07` 两种方法的真实代表路径和 SHA，另外列出 72 场 scene snapshot index。正式 TEST 应为每种旧模型在新 TEST 输入上建立并冻结自己的 cfg/opts 快照，不能把旧 VAL 快照充当 TEST 输入。

新 B 与 C5 的血缘也要分开：B 的物理场景输入是锁内历史 `B_source`；新 traceable-B 评分 raw 是 B72 scoring 引用。它们不是同一路径。TEST 必须对锁定的共享 TEST 场景分别运行 B 与其他方法，不能要求旧 B 输入文件就是新 B 计分 raw，也不能依赖任何旧 TEST baseline raw。C3 保持 DEV 坐标对照，不加入第七种 TEST 方法。

C5 M110 与两个消融使用相同 DSSM14/W0、场景、PCF、mask `[1,1,0]` 和 C5 core/wrapper；三个预测 helper 的 SHA 不同。M110 保留学习和延迟预测梯度；FREEZE 固定 W0；NO_PRED 保留实际权重更新但关闭预测梯度。表内实际 cfg/opts 快照 SHA 和锁 SHA 均逐项列出。

## 场景生成与源绑定

`matlab/scenes/make_scenes_dl1018.m` 的 `construct_scene` 与 `make_reference` 两段，同外部 corrected fixed generator 的对应代码逐行相同；片段 SHA 分别为 `ccc4babb…8851f` 与 `8260088e…891dc`。全文件 SHA 不同，不能只凭片段一致就宣称生成数组已全部一致。源码读取显示 FIG8 z 加速度项为 `5.6*pi^2*cos(2*th)`；风按场景 spec 以 `biased_dual_sine`、方向、频率/相位、rise time 构造；形态使用冻结 seed、目标/启动/收回覆盖与相同 `tcn0916_morphology_scenario` 调用。

在 DEV 做 TEST 前的独立 no-Plant 等价检查时，应对现有 72 个已用场景，逐场比较 corrected 与当前 GET 的 `time`、初态、reference 的 position/velocity/acceleration/yaw 字段、`environment_wind_I`、arm command/rho/rhoDot 与 schedule/spec/身份字段。数组应逐字段同形、有限，并以逐元素 exact equality 为主；若历史保存时存在明确浮点序列化差，只能按预先书面阈值逐字段报告最大绝对差，不能用总指标替代。该检查不调用 `BUILD`、不改旧缓存/G01，也不打开 TEST 数值数组。现有 `ACTUAL_PHYSICAL_BRIDGE_DEV72_CHECK_v1.json` 是 72 场、1,440,000 转移的普通浮点物理方程映射检查（最大残差约 `8.89e-16`），不是上述生成器全数组等价证明。

GET 的实际调用链有路径风险：`make_scenes_dl1018('GET',...)` 调用 `init_dl1018()`；后者执行 `restoredefaultpath`、`rehash toolboxcache`，再从自身 `mfilename` 位置推项目根并载入该根的 `configs/effective_config.mat`。因此不得在已绑定某方法 core/helper 后穿插调用 GET。最小安全方案是独立 no-Plant 场景阶段只生成并哈希一份共享场景包；之后六方法各用一个全新、顺序运行的 MATLAB 进程，只读相同场景包。每个进程从锁定的短别名根重建 path，先记录并断言 core、wrapper、helper、forward、PCF、options 的 `which -all` 路径和 SHA，再开航次。不要在同一 MATLAB 进程里轮换同名函数；当前旧 pair/C3/C5 多处共用 `run_dl1018_closed_loop`、`run_episode_dl1018`、`position_stage1_model_forward_v2`、`position_only_search_options` 等 basename。独立进程避免 MATLAB 已缓存函数/函数句柄继续绑定旧目录的问题，仍须做 `which -all` 核验。

## 计时、截止与门状态

已审 timer 都覆盖控制器主计算，包含位置/姿态命令、PCF、模型推理及相应更新；在 `allocate_control` 之前停止，因此不包括分配器、执行器推进、Plant RK4 和 MAT 保存。C3/B core 为 `tic` 行 1093、`toc` 行 2498；C5 M110/两消融为 1110/2532；旧 corrected pair 为 1053/2419。不同方法的计时边界接近但源码必须以锁定版本复核，不能把它称作完整 1 kHz 循环或硬实时保证。建议每方法一个 MATLAB 进程、48 场按预先锁定的 ID 顺序执行；记录六方法的块顺序与 CPU 时间漂移限制，不声称消除顺序偏差。计时期间不并发其他重负载，逐场报告均值、p50/p95/p99/max、超过 1 ms 比例并保留 ready/non-ready 与 JIT 样本；记录 MATLAB 版本、线程、CPU/内存、进程快照。

当前实际门状态：`scene_specs.csv` 为 TRAIN 768/VAL 48/DEV 24/TEST 48；dataset plan 的 `test_status=SEALED`，G01 PASS 且 `test_sealed=true`。G06 仍为 `STOP_POSITION_NOT_QUALIFIED`、`next_gate_allowed=false`；`reports/G12_FINAL_TEST.json` 当前不存在。已有封存观察枚举 20,646 个文件名且未发现匹配 TEST 输出，但它不是外部目录或已删除文件从未用过 TEST 的密码学证明。不得改原 G01/G06/G12 或解封状态。

TEST48 草案仍以两组完整 DEV72 消融及主审为前提。消融目前不能自动成为新候选；贡献草案只支持限定的离散控制链机制整合，不支持“首次”、全局先验 Plant 稳定或参数收敛。正式 TEST 新收据须真实写 `TEST_accessed=true`，不能复制 DEV 的 `false`；六方法共用预先封存的 48 场 scene 数组，且不依赖现有 TEST baseline raw。旧 G01 保护必须保持。

PS7 启动器不得照搬二次 Parse：本机 `ConvertFrom-Json` 已把 UTC deadline 解析为 `System.DateTime`；对它再 `[DateTime]::Parse(...).ToUniversalTime()` 会丢 Kind，把 `2026-10-24T17:01:00Z` 错成 `09:01:00Z`。新入口应对 `DateTime` 直接 `.ToUniversalTime()`，仅对字符串用 `DateTimeOffset.Parse(...).UtcDateTime`，并在 PS7 用真实 JSON 分别实测两条路径。长路径新输出应采用短别名并先检查绝对路径长度；现有历史文件只读使用 extended path，不搬移、不改系统设置。

## 未解决项与结论

本轮没有执行 DEV 生成器等价 MATLAB 检查、TEST 场景冻结或任何 TEST 仿真。待确认的最小工程项是：完成两组消融的自然 OS0 与全量主审；完成上述 DEV 全数组 no-Plant 生成器等价；一次性生成/冻结共享 TEST 场景数组并完成六方法独立 path/身份预检；再由主审分别决定是否放行 TEST 输入冻结和后续 288 航次。模型文件本地可用，身份可区分且可追溯；主要运行风险是 GET 的 `restoredefaultpath`、MATLAB 同名函数缓存、旧/新 B 血缘混淆、PS7 deadline 类型和未隔离计时。本文不解除任何门，也不写 release。

## 只读证据身份

任务书 SHA `5c32935ee3f0aa857d15efe233ec88fad76b27e908ad69688f3ccd9053ed6034`；当前协议草案 SHA `42715535e67ecee826dc493bd46a32e29f27d55c28b27b7db8fa04f5bbd05ccd`；贡献范围草案、`TEST_METHOD_IDENTITIES_v1.json`、封存观察和关键源文件身份均记入机器表/命令清单。`READ_ONLY_COMMANDS_v1.txt` 记录本轮只读查询范围；未读任何 TEST raw、metrics、run status 或轨迹数组，也未生成 TEST 场景。
