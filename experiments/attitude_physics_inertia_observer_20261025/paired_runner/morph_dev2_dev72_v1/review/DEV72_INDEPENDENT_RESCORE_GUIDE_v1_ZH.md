# DEV72 candidate 对锁定 B72 的离线复评分说明

此工具只读 MATLAB v7.3 raw、JSON 锁/状态与既有复审记录；不启动 Plant、闭环、训练或实验进程，不写入任何 raw。主复算留存在 `DEV72_INDEPENDENT_RESCORE_v1.json/.csv`；补齐任务书指标的复算留存在 `DEV72_INDEPENDENT_RESCORE_v2.json/.csv`；v3 再加入按逐场 `arms/command` 判断的 active-morphing/fixed-geometry 描述组，结果写入 `DEV72_INDEPENDENT_RESCORE_v3.json/.csv`。各版文件已存在时均拒绝覆盖，v2/v3 同时记录评分器自身 SHA。

它提供描述性配对复算，不创建或改变验收门。运行状态、安全停止、饱和、裁剪与 tilt 计数按 raw/status 原样报告。位置 Q 使用未舍入值判胜负，`|candidate−B72|≤1e-12 m` 记平；SO(3) 使用未舍入值，完全相等记平。总组与任务/风组均给出以场景为配对单位的 percentile bootstrap 95% CI；不把时间样本当独立样本。

## 指标

对每场从 raw 读取状态 `state` 与位置参考 `reference.position`，位置误差为 `e_t = p_t - p*_t`。位置指标按 20,001 个状态样本（0–20 s）计算：

`Q = sqrt(mean_t(sum_xyz(e_t^2)))`。同一误差范数另报告峰值和线性插值 P95；XYZ 为各轴 RMSE。早晚段按状态时间 `t < 2.2 s` 和 `t >= 2.2 s` 划分，对应 2,200/17,801 个状态样本。

姿态使用 raw 的 `state(:,7:9)` 与 `filtered_attitude_reference`，按项目使用的 ZYX 欧拉角转换到旋转矩阵。每个 20,000 个 transition 样本上的 SO(3) 测地角为：

`theta_k = atan2(0.5 * ||vee(Rd_k' R_k - R_k' Rd_k)||, clip((trace(Rd_k' R_k)-1)/2, -1, 1))`，`SO3_RMSE = sqrt(mean_k(theta_k^2))`。

每场差值为 candidate RMSE 减去同场 C5 lock 内 `B72_scoring` raw 的 RMSE。SO(3) 同时报峰值、线性插值 P95 和早晚段，按 transition 时间 `<2.2 s` / `>=2.2 s` 划分为 2,200/17,800 个样本。总宏平均、HELIX/FIG8_3D/SQUARE、W00–W15 每个风组以及 W09–W14/W15 汇总组，均为场景等权逐场值的算术平均；95% CI 用固定种子的 percentile bootstrap 按场景重抽样，时间采样点不作为独立样本。控制耗时报告日志中的每场调用时间均值和 P95；该计时口径排除 candidate post-allocator commit，按日志契约原样解释。v3 额外按 `arms/command` 任一非零值将场景分为 commanded-active morphing 与 fixed geometry，仅作描述性分层，不推断形态变化本身带来收益。安全证据按 transition 计数：任一电机位 `motor_saturated` 非零、任一广义控制位 `generalized_clipped` 非零；`tilt_limited` 计非零 transition。

## 路径与身份映射

- 固定 72 场顺序及每场 B raw/status/SHA 取自 `C5_DEV72_INPUT_LOCK_v3.json` 的 `scene_ids_all_72` 与 `scenes[].B72_scoring`。该锁、B traceable lock、DEV58 manifest、screen12 manifest 的固定 SHA 会在运行前核对。
- 58 个新 candidate 取自 `manifest/DEV58_PREPARED_MANIFEST_B72_V2.json`，其顺序必须等于 C5 的 72 场顺序移除 14 个复用场后的原序。每个新 candidate 从传入的 attempt 目录按 runner 的 `NN_<scene_id>_candidate/run_raw.mat` 与 `run_status.json` 读取。
- 12 个 screen12 candidate 与两个历史 DEV candidate（T2、T3）从 `SOURCE_LOCK_MORPH_DEV2_DEV58_V2_FROZEN.json` 的 `reused_candidate_raws` 读取。脚本核对该冻结锁及 A02 root release 的 SHA、release-bound attempt ID；raw/status SHA 需匹配锁记录，其 review 路径和 SHA 还需对应 screen12/T2/T3 已审报告。
- 每个 B raw/status 都按 C5 lock 中 SHA 校验；raw 状态、场景 ID、20,000 transitions、20,001 samples、单次 Plant 调用、`TEST_accessed=false` 和锁定 external identity 均核验。新 candidate 的 `run_status` 与 `scene_audit` 绑定 A02 release、V2 source lock、manifest 和冻结 runner SHA；`pair_XX_audit.json` 绑定 external identity、B 与 candidate raw/status 路径及 SHA、同场 scene SHA、安全门、单次 Plant 调用、零训练和未访问 TEST，并验证 pair scope/status。runner 的 `run_status` 本身不含 external identity 字段，因此该身份从逐场 pair audit 与冻结 manifest 联合核验。Candidate status 的场景/臂/raw SHA/transition 与 raw 状态核验。Candidate 与 B 的 raw 输入数组逐位比较：time、transition_time、initial_state、wind、arms command、位置/速度/加速度/yaw 参考，以及 `rho_true`、`rho_hat`、`rhoDot_true`、`rhoDot_hat` 四条形态长度/速度序列。
- 输出保留 candidate 与 B 的 raw/status 路径、SHA、状态标签、场景 identity、逐场 RMSE/差值和安全计数。C5 锁场景次序就是最终 CSV/JSON 顺序。

## 执行

脚本需要当前 Python 环境的 `numpy` 与 `h5py`。准备阶段可先做轻量历史自校核；它仅读 1 个 screen12、T2、T3 配对 raw，不写报告：

```powershell
python .\experiments\attitude_physics_inertia_observer_20261025\paired_runner\morph_dev2_dev72_v1\review\rescore_dev72_candidate_vs_b_v1.py --self-check
```

58 场 attempt 完成、存在 `batch_status.json` 后，传入固定的 A02 attempt 目录：

```powershell
python .\experiments\attitude_physics_inertia_observer_20261025\paired_runner\morph_dev2_dev72_v1\review\rescore_dev72_candidate_vs_b_v1.py --attempt-dir ".\experiments\attitude_physics_inertia_observer_20261025\paired_runner\morph_dev2_dev72_v1\attempts\DEV58_PHYATT_B72_20261025_A02"
```

完整复算要求 attempt 位于本 runner 的 `attempts` 子目录，且 58 个 candidate raw/status、scene/pair audit 和对应 `batch_status.json` 齐全。输入缺失、SHA 不符、锁定 B status 不符、candidate/B 同场输入不相同或 raw 不是完整 20,000-transition 格式时，脚本报错并不写汇总结果。它不会按性能指标做 PASS/FAIL 判定。

## 未知字段与未解决项

- T2 的既有 candidate `run_status.json` 保留 `FAILED_ENGINEERING` 标签；已审记录认为旧 trace-shape 检查误报。本脚本记录原标签，不覆写或重新解释 runner status。
- 既有 candidate status 文件的字段集合不同，旧状态中缺少的 TEST/training 字段不从 raw 推断。新 DEV58 status 的 batch 记录单独保留。
- 一些 B72 `run_status.json` 没有 `seed` 字段；脚本记录其为空，通过 C5 external identity、候选 manifest/状态和 candidate/B raw 输入逐位相等核对场景。Candidate 的 seed 与有 seed 的候选 manifest 核对。
- 复算验证 B72 文件 SHA 和同场 raw 输入，但不重建 72 个 MATLAB scene payload，也不重新审查完整 20,000 点 observer 因果 trace；T2/T3 的既有因果复审继续作为其独立来源。
- `B72_LINEAGE_INDEPENDENT_REVIEW.md` 保留的 `historical_72_runtime_tree_gap_closed=false` 未由本复算消除；该审查同时说明逐场 C5 B72 raw/status 谱系已闭合。两项范围不同，应并列保留。
