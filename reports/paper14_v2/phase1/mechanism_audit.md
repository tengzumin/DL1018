# DL1018 corrected14 全72场机制审计（phase 1）

审计日期：2026-10-22。范围为 corrected DSSM14 的 VAL48 + DEV24；只读本任务明确白名单里的 72 个 VAL/DEV raw、对应 run_start 及配对评分/RAW_INDEX。没有扫描或读取 TEST，没有启动训练、Plant、闭环航次或 TEST，没有改动实验数据，也没有删除文件。运行期间未发现正在执行的 MATLAB/Python 仿真实验；未打断任何进程。原始文件及 run_start 均逐项记录读前/读后 size、mtime、SHA256，72/72 一致。

## 结论与决定

1. 全72配对评分为 46/72 胜，scene-equal 平均 Q 从 B 的 0.017058081 m 降至 0.012387218 m，改善 4.671 mm；但未达到计划的 62/72 胜门槛。优势集中在 W00–W08（38/38 胜）；W09–W14 仅 5/28 胜且平均差 +0.526 mm，W15 3/6 胜且平均差 +0.050 mm。因此开发门槛不通过，不解封 TEST。
2. 监督标签、PCF 协调量、执行器应用、在线权重离散更新均可由 raw 字段按实际时间顺序重放。全72没有发现当前候选 runner 的数值实现不一致：标签分解闭合最大差 3.03e-15 m/s²；PCF eta 递推/事件对齐与权重更新重放误差都在双精度舍入量级。当前实际 runner 调用隔离版 `position_stage1_model_forward_v2.m`；不应把未调用的 `_current` 或根目录 head 函数当作本结果运行实现。
3. 在相同 event、相同 φ、相同 β 与限幅下，online-before 和 online-after 对离线目标的残差都小于 W0 prior；更新一步后的改善仍为小量。高频 Z 同态残差由 0.089609 降到 0.089490 m/s²（early 0.000089、late 0.000127 m/s² 的更新增益），故“不良 Z 结果是在线更新令同态拟合变差”不受支持。父审按同一组 paired raw 复核的 W09–W14 闭环 Z 误差仍比 B 高 2.274 mm；同态改善不能推出闭环因果改善，也不能解释该差距。
4. 当前证据不支持“冻结 W0”作为优先修复机制，也没有锁定唯一闭环根因。建议暂不新开航次；先做下文的预登记离线时间块诊断。未通过时就停在机制阶段，不扩模型、不调参、不解封 TEST。

## 数据身份、白名单与复现

配对表为 `reports/corrected14_full72_benchmark_20261021/PAIR14_SCENE_RESULTS_VS_B.csv`，SHA256 `b2264145e9d18896f5764ffe38302576dd08c80e7cce1c277323246092169137`。它含144行（72 DSSM、72 KAN）；本审计按候选 raw SHA 精确选中72个 DSSM 行，再与冻结场景表逐 SHA 对齐。72个候选 raw SHA 唯一；split/task/wind/Q/outcome 全部匹配。

两个只读 RAW_INDEX 分片：`corrected_pair_eval_v1/reports/RAW_INDEX.csv` SHA256 `364367e46ae8e3eb3335efd34a834b984a2a87fc1cef0dd5bf4991bbf342d8b4`，选中61行（40 exact、21 alias）；`corrected_pair_eval_tail21_v1/reports/RAW_INDEX.csv` SHA256 `3527883329ec23f51928d3967071d307a42683adc831cee8958822c7b732d116`，选中11行（8 exact、3 alias）。两表并集按 raw SHA 唯一覆盖72（VAL48、DEV24），合计48个精确 ID、24个显式 `_ACC_FIX_V1` alias。Alias 只在 raw SHA 对应的索引行上按已核实规则接受；没有对源 ID 做隐式规范化。旧的 `runtime_scene_id` 直接按 scene_id 联表会漏24条 alias；漏行发生在该中间联表，当前 `mechanism_by_scene.csv` 及本次 raw-SHA 主键联表仍完整72行。

72个 raw 的 run_start 路径/哈希/配置已写入 `mechanism_run_start_lineage.csv`。run_start 的 model SHA 均为 `6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f0aead9c9b6e`，配置均为 DSSM14、seed `2026102001`、step 60000、输入14维、window/context32、FEATURE head、head/update/PCF enabled、γ=12、κ=1、β scale=1、position sample 0.01s、Plant dt 0.001s。raw 中同字段再次核验一致；`κ·output_W` 与 W0 的 max 差为0。72行的模型数组和 normalizer field-list SHA 分别统一为 `8de4d6548316c7b6f97382ecc9d5fbce8c00dbf6d10dc4187789b34c9205eb26` 与 `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`。模型绑定记录 `PAIR_EVAL_MODEL_BINDING_FORWARD.json` SHA256 `CC5616B3C10DEF65B8CB3636D92219DD5ED4848A1651D4C1F1D81F147FD384AF` 将该 MAT SHA 绑定到 checkpoint `544b018b78187d9d9cbbcbd5c3332244b80ad91cb137f32bd71198a4302dfbf5`；独立64 fixture parity 的最大 φ 误差 `9.69e-8`、输出误差 `6.76e-7`。这属于模型/forward 身份核验，不是闭环因果证据。先前 legacy replay 的 aggregate model-array hash 有两种口径；它们的字段清单把标量元数据纳入方式不同，不能据此判断编码器混用。本次按固定权重字段从 raw 复算为一个身份，未见模型混用。

运行实现身份：隔离 runner `.../corrected_pair_eval_v1/sources/local_runtime/run_dl1018_closed_loop.m` SHA256 `01D83DEC95AEA5D30FEEF3AFD0628A2CE0911F70465F0773A4F568A01B08450B`，实际调用 `position_stage1_model_forward_v2.m` SHA256 `DC803AA102C49D67DD687AE941F8A60BB0C465F74FD01E5AE93AD1EA1A293676`；raw search-head helper `position_only_search_head_step.m` SHA256 `3BD0FE9686C3B75793575E517D4CC5F08DE58AB6A26A2BC7516AA690422BB7DC`；项目 PCF helper `matlab/models/position_filter_realization_pcf_step_v3_5.m` SHA256 `B4AE22DB5BD444A162D0CD01A3A59A589F2E37077B089BB33693401B660228D0`。监督标签 exporter `.../corrected_reference_training_v1/matlab/data/export_position_events_dl1018.m` SHA256 `4506849CC2C888E078129772E6BB1927CB479F02B75C072472778ED32D4CF094`。

完整逐场审计结果：

- `reports/paper14_v2/phase1/mechanism_components_by_scene.csv`：72行；逐场 Q、结果、身份、目标/分解闭合、PCF/weight 重放、每轴位置和同态残差、early/late 指标、raw 文件读前读后身份。
- `reports/paper14_v2/phase1/mechanism_components_summary.csv`：32个 ALL/wind band/split/task/outcome 组；含 scene-equal macro 与 pooled 统计、三轴位置/eta/s_eff/weight-delta 指标。
- `reports/paper14_v2/phase1/mechanism_same_state_groups.csv`：32组，同态 target、W0 prior、在线更新前/后和改善量，含 x/y/z 及分段。
- `reports/paper14_v2/phase1/mechanism_input_lineage.csv`、`mechanism_run_start_lineage.csv`、`mechanism_components_summary.json`：输入 SHA 联表、run_start provenance 与小型摘要。上述产物均是文本/表格，不含 MAT。

本报告由 `reports/paper14_v2/phase1/rebuild_mechanism_audit.py` 生成性脚本所用重放逻辑支持；脚本 SHA256 `4A63B952585E49ED7B3D011B6BFA0FF5068F3CB9EFAFAE33A91DE8992A347281`。最终 PowerShell 7 复算命令退出码0：

```powershell
python -B -c "import ast,pathlib; ast.parse(pathlib.Path('reports/paper14_v2/phase1/rebuild_mechanism_audit.py').read_text(encoding='utf-8'))"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python -B 'reports/paper14_v2/phase1/rebuild_mechanism_audit.py'; $auditExitCode = $LASTEXITCODE; Write-Output "AUDIT_EXIT_CODE=$auditExitCode"; exit $auditExitCode
```

## 方程、时序与单位核验

### 监督目标和真实物理残差

按 exporter 的定义，事件状态处在 raw `log/transition_time` 对应的 1 kHz transition 列；每场记录1999个计划 position event，首末时间0.01/19.99s、MATLAB k=11…19991；其中1968个 event 有在线模型推理有效（context warmup 后）。模型推理先取输出并应用，再更新 W。

令 `R_a` 为 state 中实际姿态矩阵、`R_raw` 为 raw outer attitude 的姿态矩阵，`e3=[0,0,1]^T`，`T_real/T_req` 分别为 realized/controller-clipped generalized thrust，`a_nom/a_applied` 为名义与实际应用位置加速度，则离线标签

`Y = R_a e3 T_real/m − g e3 + wind_I/m − (a_nom − a_applied)`，`target_clip=clip(Y, ±3 m/s²)`。

四项闭合为 `dWind=wind_I/m`；`dAlloc=R_a e3 (T_real−T_req)/m`；`dAtt=(R_a−R_raw)e3 T_req/m`；`dMap=R_raw e3 T_req/m−g e3−(a_nom−a_applied)`，并且 `Y=dWind+dAlloc+dAtt+dMap`。字段来自 raw `state`、`realized_generalized`、`controller_clipped_generalized`、`wind_force_I`、`raw_outer_attitude`、nominal/applied acceleration 和 `rho_true/rhoDot_true`。物理分解四项与 Y 单位全为 m/s²，闭合差仅双精度舍入量级。Y 使用实际 realized 力/风/true plant 参数，仅为离线诊断标签，绝非部署输入；Y 也不是“纯风扰”，不能把 dWind 一项当作整个监督目标。

72场计划事件汇总的 pooled component RMS（m/s²）：ALL dWind 0.3543、dAlloc≈0、dAtt 0.2943、dMap 0.00303；W00–W08 dWind 0.3727/dAtt 0.2236；W09–W14 0.3663/0.3902；W15 0.00217/0.1110。按候选结果，WIN dAtt 0.2210、LOSS 0.3917。它们是同一闭环轨迹的关联描述，不能据 WIN/LOSS 直接推因果。

轴向物理分量限制：当前输出的 dWind/dAlloc/dAtt/dMap 是向量总RMS，group CSV 同时给出场景宏平均和事件 pooled 汇总，但没有按 x/y/z 或 [0,5) / [5,20) 拆分物理分量。因此本报告不能把高频 Z 轴位置差归因到其中某个物理分量；需要主审决定是否补做该项。raw 保存了 a_F，但没有保存独立的 `euler_filtered` 输入，故本审计验证 `r_F=a_req−a_F` 与 eta 递推/事件采样，不声称能从 state 独立重算 a_F 的滤波内部实现。

### PCF 与在线搜索头

raw PCF 字段显示 `r_F=a_req−a_F`（误差 max 0）；1 kHz eta 更新为

`η[k+1]=exp(−K2 Δt)η[k]+diag((1−exp(−K2 Δt))/K2) r_F[k]`，

事件取样 `s_coord=s_original−η_before`，`s_eff=clip(s_coord, ±[7,8,10] m/s)`。η/s/s_eff 单位 m/s；a_req/a_F/r_F 和补偿输出单位 m/s²。所有72行 eta before/after continuity、递推重放、event eta 对齐、协调关系与限幅关系符合记录，误差≤约3e-15（单位随对应字段）。position event 100 Hz；update dt 每场约0.01s；Plant/PCF 为1kHz。

在线应用使用同一事件的 `u(W)=β·clip(W^Tφ, ±3 m/s²)`，`β=clip(t/1.8s,0,1)`。φ 是33维无量纲特征。MATLAB head 的 W 为33×3（HDF5 logger 以3×33存储）；每个事件在输出后执行

`W_after=Proj_[−60,60](W_before + h[−γβ φ s_eff^T − 0.002 W_before])`。

raw event 的 `W_before/W_after/φ/β/s_eff/event_dt/projection` 对该更新完整重放，72场最大差≤2.22e-16，projection mismatch 0。按此物理单位约定，W 与输出单位为 m/s²、W 的连续时间导数 m/s³、s_eff 为 m/s，因此 γ=12 的数值量纲是 s⁻²；泄漏系数0.002为s⁻¹，h为秒，κ/β无量纲。记录的 `position_sample_time=0.01s`、update rate 100Hz、Plant dt0.001s 一致。此处有界投影不等于闭环稳定证明。

### 同态监督残差的定义

所有三种输出在每条有效事件、同一 φ/Y 上比较：`target=β·clip(Y,±3)`；`u0=β·clip(W0^Tφ,±3)`；`ubefore=β·clip(Wbefore^Tφ,±3)`；`uafter=β·clip(Wafter^Tφ,±3)`。表中 prior/online 指标为相应 `u−target` 的 RMSE，after 使用 W 更新后的值但仍在当前事件相同 φ/Y 上计算；不是下一事件的实测闭环输出。每场先在样本上计算 RMSE，组表的 `scene_macro` 再对场景等权平均；`pooled` 是合并有效事件后再算 RMSE。历史列名 `target_rmse` 易误读，实际是 β目标信号自身 RMS，不是残差。

scene-macro 3D 同态 RMSE（m/s²）：ALL72 target0.47372、W0 residual0.27802、online-before0.19667、after0.19600；W00–W08为0.44281/0.25263/0.16468/0.16413；W09–W14为0.59420/0.34292/0.27423/0.27340；W15为0.10717/0.13590/0.03732/0.03666。全部风组在线完整映射拟合优于 W0，但 online-before→after 的单步增益很小。这支持优先保留在线自适应的局部解释，不支持冻结 W0；它仍不是闭环轨迹上的组件因果对照。

逐轴同态数值（m/s²，xyz 顺序；每项为 target / W0残差 / online-before残差 / after同态残差 / update gain）：

| 组 | x | y | z |
|---|---|---|---|
| ALL72 | .53450 / .30337 / .22070 / .21996 / .000740 | .51031 / .31122 / .21771 / .21696 / .000754 | .14624 / .13348 / .07133 / .07090 / .000434 |
| W00–W08 | .52042 / .28274 / .19454 / .19398 / .000561 | .45923 / .27849 / .18256 / .18195 / .000611 | .16021 / .13860 / .06837 / .06764 / .000728 |
| W09–W14 | .64122 / .36224 / .29330 / .29236 / .000942 | .66240 / .38646 / .30304 / .30207 / .000968 | .15700 / .15359 / .08961 / .08949 / .000119 |
| W15 | .12566 / .15929 / .04760 / .04667 / .000931 | .12410 / .16739 / .04210 / .04143 / .000665 | .00748 / .00724 / .00481 / .00476 / .000045 |

高频 Z 更新增益分段为 `[0,5)` 0.0000895、`[5,20)` 0.0001265 m/s²；W15 Z 分别0.0000200、0.0000504；ALL72为0.000379、0.000448。高频在线前后同态Z残差的差值只有闭环高频Z劣势2.274 mm的很小局部量级，不能据此认为目标重构或在线更新是闭环输场原因。

## 全72配对闭环结果与轴向分段

Q 是0–20s三维位置 RMSE；胜负使用未舍入结果、容差1e-12m。表中 Δ=候选−B，负值为候选更好；Q 为每场 Q 的场景等权宏平均。以下没有 TEST 数据。

| 分组 | 场数 | 胜 | 候选Q (m) | B Q (m) | ΔQ (m) |
|---|---:|---:|---:|---:|---:|
| ALL72 | 72 | 46 | .0123872 | .0170581 | −.0046709 |
| VAL | 48 | 32 | .0128230 | .0179928 | −.0051698 |
| DEV | 24 | 14 | .0115156 | .0151885 | −.0036729 |
| W00–W08 | 38 | 38 | .0139696 | .0232149 | −.0092452 |
| W09–W14 | 28 | 5 | .0112445 | .0107190 | +.0005255 |
| W15 | 6 | 3 | .0076977 | .0076473 | +.0000505 |
| FIG8_3D | 24 | 16 | .0121244 | .0168338 | −.0047094 |
| HELIX | 24 | 16 | .0120782 | .0163248 | −.0042466 |
| SQUARE | 24 | 14 | .0129591 | .0180157 | −.0050567 |
| W09–W14: FIG8 / HELIX / SQUARE | 9 / 9 / 10 | 1 / 2 / 2 | .0107675 / .0112971 / .0116265 | .0102151 / .0108680 / .0110384 | +.0005523 / +.0004291 / +.0005881 |
| W15: FIG8 / HELIX / SQUARE | 2 / 2 / 2 | 2 / 1 / 0 | .0072866 / .0086967 / .0071099 | .0083288 / .0082986 / .0063144 | −.0010422 / +.0003981 / +.0007955 |

位置轴向 RMSE scene-macro（mm），每格 x/y/z；Q 表中 Δ 对应 full `[0,20)`，这里严格拆分：

| 组 | `[0,5)` x/y/z | `[5,20)` x/y/z |
|---|---|---|
| ALL72 | 9.793 / 8.569 / 4.184 | 7.120 / 7.307 / 3.281 |
| W00–W08 | 11.099 / 9.252 / 4.626 | 8.276 / 8.751 / 3.276 |
| W09–W14 | 9.512 / 9.159 / 4.453 | 5.785 / 5.719 / 3.876 |
| W15 | 2.835 / 1.492 / 0.126 | 6.031 / 5.579 / 0.536 |

分段定义严格是 `[0,5)`、`[5,20)`。position score 使用 raw `transition_time` 的20,000个1kHz时间戳 `t=0,…,19.999`；t=0初始状态计入，raw额外保留的 terminal t=20.000状态排除。两段分别5000/15000点；不能用含5秒端点或20秒终点的近似口径。PCF/权重分段同样按事件时间 `t` 使用这两个半开区间，online 有效事件各场为468/1500个。

PCF/更新分组量级（每场 RMS 后场景等权，轴为 xyz；η 与 s_eff 单位 m/s，weight delta 单位 m/s²）：

| 组 | η RMS xyz | s_eff RMS xyz | ΔW RMS xyz |
|---|---|---|---|
| ALL72 | .02079 / .02349 / .00324 | .01573 / .01824 / .00728 | .001789 / .002119 / .000814 |
| W00–W08 | .02365 / .02468 / .00291 | .01592 / .01897 / .00977 | .001799 / .002202 / .001119 |
| W09–W14 | .01961 / .02453 / .00428 | .01627 / .01838 / .00531 | .001855 / .002127 / .000556 |
| W15 | .00817 / .01110 / .000553 | .01203 / .01301 / .000689 | .001422 / .001561 / .000088 |

宏平均只用于易读摘要；每场、每轴和每分段指标以及 pooled 版本都在 CSV。高频组 online 更新的 Z 权重增量比低风组小，且 η/s_eff 与真实闭环状态共变；这仍不足以判定小更新造成输场。

## 根因边界与下一步

本轮找到的是一个可核验的局部事实：高频目标包含显著的 dAtt，W09–W14 的 pooled `dAtt RMS≈0.390 m/s²`，高于低风 `.224` 和 W15 `.111`；与此同时同态 Z 残差在线 before/after 有小幅改善，不能把高频 Z 闭环误差称作“预测误差变大”或归咎于在线拟合恶化。每场间探索性 Pearson 相关中，W09–W14 的 dAtt RMS 与候选−B Q 差 `r≈0.46`，在线-before同态残差与 Q 差 `r≈0.46`；样本28、混合任务/状态且受整个闭环轨迹共同影响，仅用于形成可证伪假设，不能当因果证明。

唯一优先待检验假设：高频劣势更可能与 `dAtt` 方向/时序和后续位置误差的块间关系有关，而不是“冻结 W0 能改善局部目标拟合”。不新开航次前，先按 task、phase、loss/win 分层，对现有72条事件序列做预登记的1秒块诊断：以事件同态残差在 `dAtt` 方向的有符号投影为解释量，预测下一块的 Z 误差变化，报告每组样本与置信区间；若各任务/phase 方向不一致或不能预测后块，则拒绝该假设，回到日志/机理检查，不扩模型。即使命中，也只是与数据一致的机制线索；再由主模型冻结一个单因素且可审计的最小验证任务书后，才能决定是否做12场筛查。

复用边界：`experiments/position_causal_repair_v1/reports/FINAL_CAUSAL_REPORT_ZH.md` 的 D4/D5 是 adaptation-aware X14 C2，六场没有通过 C0 Final，报告本身也指出组件不是单因素，不能宣称唯一根因。C1/C2 各4/6胜 Initial；C2 macro Q .035870 m、B .020357 m；C2 0/6胜 B、1/6胜 C0 Final。该资料作为历史边界复用，不重跑、不把旧 KAN 或不同比较条件外推到当前 corrected DSSM14。已知 D5 fixture 的 path reset 由 `init_dl1018()` 清路径造成，是隔离测试夹具问题，不等于本次运行 helper 有生产代码 bug。旧 G06 STOP 不改写。

本阶段决定：**继续离线机制判别；暂不修生产实现、不启动下一轮闭环、不解封 TEST。**

