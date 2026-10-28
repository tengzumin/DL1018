# B 基准身份与 12 场 pilot 复算

审计日期：2026-10-25。范围仅为已锁定的 DEV/VAL 72 场，不读取 TEST 场景记录或 TEST raw。

## B 是否为原始 B

- 主输入来自 `experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json`，SHA-256：`8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452`。C5 DEV72 锁把 72 个 B72 raw/status 路径、SHA 和 scene ID 逐场绑定到同一 cohort。
- 冻结 runner 的 SHA 与输入锁相同；runner 使用 `controller_options_dl1018(cfg,'B')`，拒绝 C3/C5 候选选项，并要求原 B 位置 RBF 输出与更新开启。对应的 no-Plant prepare 另行断言原 B 姿态 RBF 输出与更新开启、两套 RBF 均为 100 Hz、`v1_adaptive=false`。核验位置见 `run_b_traceable_dev72_v3.m:127-130, 161-164` 和 `prepare_b_traceable_dev72_v3.m:168-175`。
- 对 C5 锁中的 72 个 B72 条目逐项复核 raw/status 文件存在与 SHA：72/72 匹配，scene ID 唯一数 72，Plant calls 72，所有日志 `log_status=STABLE`、`last_transition=20000`、`transitions=20000`、`state_samples=20001`、`plant_calls=1`、训练步数 0，`TEST_accessed=false`。B wrapper 状态为 `RUN_COMPLETE_RAW_PENDING_AUDIT`，因此本审计不把 wrapper 状态误称为已做过整体 parent audit；raw 是本轮重新评分的依据。
- B72 raw 总量约 2.776 GiB，原位复用；未复制或改写。

## 已完成的 candidate 对 B pilot

脚本 `rescore_screen12_against_b_v1.m` 从屏幕 12 场 candidate raw 与 C5 锁定的同场 B72 raw 独立重算 0–20 s 位置 RMSE 和滤波姿态参考下的 SO(3) geodesic RMSE。Candidate 分数再次与先前独立 raw audit CSV 对到 `1e-12`；12 个 B raw/status SHA 均重验，且 B 状态日志均为稳定完整 20,000 transitions。

| 指标 | Candidate | B | Candidate − B |
|---|---:|---:|---:|
| 12 场等权位置 Q RMSE (m) | 0.00790729995761238 | 0.0103489233151874 | -0.00244162335757499 |
| 12 场等权 SO(3) RMSE (rad) | 0.0083944886965119 | 0.0137816532328753 | -0.0053871645363634 |

高频 W09–W14 六场的 Q、SO(3) 差分别为 `-0.00133838575853247 m`、`-0.00493261279791757 rad`；W15 三场分别为 `-0.00365929341373411 m`、`-0.00848577828272772 rad`。逐场 Q 赢 10/12、SO(3) 赢 9/12。结果与逐场 raw SHA 记录保存在 `SCREEN12_CANDIDATE_VS_B_RAW.csv/json`。

## 决定

此 pilot 足以支持按修订后的任务书扩到剩余 58 场 candidate-only 开发验证。它不支持最终论文结论。完整 DEV72 必须将 58 个新 candidate 与 14 个已审 candidate 逐一配对 B72 raw 独立评分；主门改为位置和姿态 macro 均优于 B，并报告高频与无风组，候选对 C5 的位置回退不是失败门。
