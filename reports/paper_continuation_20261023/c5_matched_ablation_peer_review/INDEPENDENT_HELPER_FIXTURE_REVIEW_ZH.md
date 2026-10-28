# C5 配对消融 helper / fixture 独立复核

**结论：** 两个 helper 的干预在公式上各自局限于指定因素；C5 runtime core 与 episode wrapper 均与冻结 C5 字节一致。未发现 PCF、M110 目标/特征/历史或输出先于更新的额外变化。此结论是静态源码复核，不构成 MATLAB 运行或 Plant 放行。MATLAB boundary 检查中已由主审指出的 `tol` 实参传递错误仍须修复后才能把 synthetic checker 视为通过；本报告不重复记为新增发现。

## 依据与核对

- 任务边界文件：`C5_MATCHED_ABLATION_CONDITIONAL_TASKBOOK_ZH.md` SHA256 `02cb08b46f41d5f64adea965e4f9704b75c3aa1e48bc7eee57e1dd94afce6ece`；实现放行说明 SHA256 `ceef16ba1188b1c395c531d245828b11ac904e789af57a4280d9ae3bc9520313`。前者第 13–14 行定义两项单因素，第 20 行规定 fixture 覆盖；后者第 7、11 行重申 helper 隔离和验证要求。
- 冻结 C5 helper [delayed_prediction_step_candidate.m](../../../experiments/position_axis_coordinate_c5_20261023/delayed_prediction_step_candidate.m) SHA256 `48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`：第 39–44 行形成旧梯度、当前输出、tracking/leak/预测项及一次联合裁剪。
- `C5_FREEZE_TRAINED_W0` helper SHA256 `aab2a67b17886e5e71460fc972a57a389faef10fed9b30292befc64ab6511eaa`：输入校验和旧目标/残差仍在第 4–39 行；第 41 行将实际梯度置零，第 42 行仍从当前 `W_k` 计算原始/限幅输出，第 43–44 行令实际候选为 `W_k` 并保留原 `[-60,60]` 裁剪。因此当训练初值 W0 位于原投影盒内时，输出前、输出后和后续事件的实际权重保持 W0。
- `C5_NO_DELAYED_PREDICTION` helper SHA256 `390fd63989922e0f252df51c392f18977b9957bec6534e4905634b8c94147248`：保留第 37–39 行对旧特征/旧目标残差的计算；第 41 行只将实际应用梯度清零；第 43 行仍保留 `-h*gamma*beta*(phi*s_eff')`、`-h*lambda*W_k` 和单次 `-rho*predGrad`（其值为零），第 44 行沿用同一联合裁剪。故相对冻结 helper 的 C5 原式，唯一实际更新差为去掉旧预测梯度项。
- 两配置的 `run_dl1018_closed_loop.m` SHA256 均为 `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c`，`run_episode_dl1018.m` SHA256 均为 `fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330`，且两者均与冻结 C5 对应文件逐字节相同。核心第 2025–2061 行沿用 C5 的区间标签、旧 `phi` 与时钟；第 2040–2044 行先从 helper 得到基于当前权重的 `raw/applied` 再提交 `weightNext`；第 2050、2055–2061 行仍记目标范数/事件特征/历史；第 2108、2115–2119、2848 行保存真实更新后权重和事件输出/特征。两个配置目录的运行路径未改这些状态或日志分支。
- Python fixture generator SHA256 `02e453bb8fc6ec7ea76320a02aced66a570abef694e63307e00f0bf6f0efbfe9`：第 43–54 行分别构造冻结候选及“基线候选加回 `rho*gradient`”的无预测候选；第 59–77 行让第二事件接收第一事件实际更新后的权重；第 97–110 行构造只积分 `[320,330)` 的标签并放入当前行 sentinel；第 120–134 行断言输出不变、单因素候选及投影/输出边界。
- 两配置共用的 MATLAB checker SHA256 `d1c0168dc85ab22895c2fe6833c413ddb5eaef6d6d11da98a4f5a084f917e678`，并各绑定独立 fixture SHA：freeze `60d88931d22ee2a61735092f499cf81f4a767f6a4968390277434193a5daf486`，no-pred `a23e7be7e3c1df8d69d441a8a561df52d938e9f9abe37ae60e4f860a60ed42aa`。checker 第 18–53 行核身份、M110 reference/目标、首事件/完成区间；第 66–111 行实际执行对应 MATLAB helper 并比较输出、前后事件权重与 ablation 差值。冻结 C5 原 cross-language 检查已有结果 `PASS_SYNTHETIC_CROSSLANGUAGE_ONLY`，max error `5.551115123125783e-17`，绑定原 helper SHA；本轮没有重跑 MATLAB。

## 范围限制

未运行 MATLAB、Plant、训练或 TEST。没有评估任何尚未交接的 C4 runner/prep，也没有读取消融 raw；因此本复核只确认公式/源码的隔离性及静态 fixture 设计。MATLAB checker 的既知 boundary `tol` 实参问题修复后，仍需由主审实际跑两份无 Plant checker 与同一 runner preflight，再另行决定是否发布航次。

