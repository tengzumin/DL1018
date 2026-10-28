# 旧DEV标识语义修复任务书 v4

继承v3任务书（SHA `2099a4c2c262bc8f3b98aa7e7cfaef631e276d360d1152e390b940d04ccf54c9`）及v2科学范围、三步放行、预算和硬截止。当前仅代码授权，禁止MATLAB、Plant、训练或TEST评分。

v5准备自然OS0且主审核过六cfg/opts/model/normalizer/W0身份、142方法绑定、168共同绑定，全部通过。首个DEV2在Plant前因错误比较标识而自然OS1；无新raw、run_start或Plant marker，KAN未启动。旧文件原位保留，不能把该OS1改成成功。主审实物核验记录为 `test_engineering_dev2_parent_review/PARENT_DEV_LABEL_SCHEMA_FACTS_v1.json`，SHA `4b79417fa9778a82e95bd0a9d31bbe16d36d77398266a7787cf55b7a6094e3fc`。

两份旧raw的 `log.method` 都是名义控制器 `B2-RBF-Full-SPLIT`，外部DSSM/KAN身份存于各自 `run_start.meta.method_id`。锁定wrapper使用该名义控制器和各候选opts调用core，再附加 `log.scene_id`、`log.collector`。旧完整raw恰好没有这两个wrapper身份字段；它们不属于动力学数值。

仅将v5四个静态文件复制到 `experiments/c5_test48_v6/`、`reports/paper_continuation_20261023/test_entry_v6/`，保留原文件基本名及V4数据schema。禁止复制MAT、缓存、日志、prefdir或运行目录。允许的逻辑变化严格如下：

- DEV2前置检查用旧 `run_start.meta.method_id` 精确核外部collector；另要求旧 `log.method` 精确为 `B2-RBF-Full-SPLIT`。禁止把候选名与名义控制器标签混用。
- 新旧raw比较精确核两者 `log.method` 都为该名义标签，核新 `log.collector==collector`、`log.scene_id==sceneId`。单独报告两个新wrapper身份字段，并只把这两个已核实旧记录缺失的字段从旧新struct字段集合比较中排除。其余原字段仍完整严格比较；四个纯计时字段按原规则单列，数值容差仍1e-12，状态/控制/权重/事件和物理输入不删减。
- 按新目录和本任务书/CODEONLY授权更新身份；预算累计原baseline和v3/v4/v5/v6所有入口/报告目录。manifest可增加v5失败与主审事实记录链接。其他科学对象、路径绑定、只读which核验、正式TEST runloop、模型/normalizer/参数/Plant/计时/score/statistics一字不改。

实施者须先用实际旧字段和wrapper逐一检查所有DEV2断言，禁止继续凭字段名猜值。另一执行者独立复核该适配。交四SHA和短diff后停止，待主审分别放行无Plant准备、尚未消耗的最多两场DEV工程复现、最后240个未进入Plant的TEST组合。不新增B或训练，不读TEST分数，不扫参，不改旧门和缓存保护。

所有启动、包括零Plant失败仍入账。此次为标识语义故障第一次有证据的隔离修复，不自动重试。PowerShell7、单重负载、2026-10-24T17:01:00Z截止、周期新增80e9 bytes及预留后30e9 bytes下限保持。
