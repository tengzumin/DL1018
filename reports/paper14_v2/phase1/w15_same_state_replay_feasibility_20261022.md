# W15 同状态重放复核

更新日期：2026-10-22。范围为三个固定 VAL W15 场景的 B、当前 corrected DSSM14（PCF-on）与 R3 原始记录；只读 MAT、run-start sidecar、身份表和源码，不运行 MATLAB、Plant、训练或新航次，不访问 TEST。

## 结论

更早版本把“本次 MAT 白名单没有纳入 PCF-on `run_start.mat`”写成了完整重放受配置缺失阻碍。后续逐场核对发现：三场 B、PCF-on DSSM14 和 R3 的 run-start 侧车实际都存在，身份哈希与已有记录相符；B 与当前 DSSM14 的 Plant、位置/姿态反步、命令滤波、限幅和形态配置共有 60 个字段，三场 MATLAB 逻辑数组形状一致，数值在 \(10^{-12}\) 容差内一致。初态、20 ms 时状态、时间轴及六个参考量也逐元素一致。因此，**W15 首个位置请求差异现在可以在同状态下复现**，无需再假设配置不齐。

复算定位到的首个差异与预定控制器替换相符：B 开启位置 RBF 输出/更新；DSSM14 关闭位置 RBF，并在 Head readiness 期间保持零补偿。20 ms 两者的名义位置力完全相同，命令力差逐分量等于 B 的 RBF 补偿力负值，复算残差不超过 \(1.4\times10^{-19}\) N。状态在 21 ms 才首次分离。这说明最早分叉不是当前位置反步公式的实现错误。

这仍**没有定位毫米级 W15 X 轴误差的长期闭环根因**：位置力差很小，离线同状态计算只解释首个请求分叉；不同控制器轨迹在 21 ms 后分离，不能用它们的 20 s RMSE 直接证明该分叉造成或没有造成后续误差。PCF-on 与 R3 的首个位置命令差异在 0.330 s、状态差异在 0.331 s，与 Z 轴 eta-mask 配置差异出现的时序一致；但 R3 相对 PCF-on 的三场 X RMSE 低约 0.001016 mm，这一配对观察不能单独识别 mask 的因果效应。

## 输入与配置身份

脚本对每场六个指定 MAT 文件（B、PCF-on、R3 各一份 raw 和一份 run-start）逐个核验 SHA256：B 与 DSSM raw 哈希来自已审核的重评分表；DSSM run-start 哈希来自 `mechanism_run_start_lineage.csv`；R3 raw/run-start 哈希来自 `round3_attempt_hashes.csv`；B run-start 哈希与既有 W15 原始记录审计表一致。它还锁定五个输入表/manifest 的 SHA256，以及 `position_bs_step.m` 与 `controller_options_dl1018.m` 的源码哈希。CSV 全文件仅用于身份哈希；扫描行时按 `scene_id` 过滤，只有三个固定场景的行进入完整字段解析。未递归搜索 MAT 目录，也未读取模型 checkpoint 或 TEST 文件。

| 场景 | 共同核心配置字段 | B 与 DSSM 配置差异 | B−DSSM 位置命令首差异 | 状态首差异 | 名义力复算最大误差 | \(F_B-F_{DSSM}+F_{RBF,B}\) 最大残差 |
|---|---:|---:|---:|---:|---:|---:|
| HELIX `T1_C08_W15` | 60，0 差异 | 位置 RBF 开/开 vs. 关/关 | 0.020 s，\(5.190\times10^{-9}\) N | 0.021 s | 0 N | \(6.06\times10^{-20}\) N |
| FIG8 `T2_C05_W15` | 60，0 差异 | 位置 RBF 开/开 vs. 关/关 | 0.020 s，\(5.766\times10^{-9}\) N | 0.021 s | 0 N | \(4.38\times10^{-20}\) N |
| SQUARE `T3_C02_W15` | 60，0 差异 | 位置 RBF 开/开 vs. 关/关 | 0.020 s，\(5.856\times10^{-8}\) N | 0.021 s | 0 N | \(1.33\times10^{-19}\) N |

“共同核心配置字段”覆盖 `cfg.plant`、`cfg.control.bs`、命令滤波、控制限幅、形态模式及相关惯量/质量模型字段；脚本分别处理 MAT v5 与 v7.3/HDF5 sidecar，并把 v7.3 反向存储的轴序归一到 MATLAB 逻辑维度，再核对数组形状。数值按 \(10^{-12}\) 绝对容差比对，NaN 配置值会令检查失败，配置中匹配的无穷限值保留为有效值。初态、状态时钟和位置、速度、加速度、偏航、偏航角速度、偏航角加速度六组参考数组在三份 raw 中均逐元素相等。R3 与 PCF-on 的相同状态及参考同样成立。

位置环使用源码中的关系

\[
e=r_p-p,\quad \dot e=r_v-v,\quad z_2=r_v+k_1\odot e-v,\quad
a_{nom}=r_a+k_1\odot\dot e+e+k_2\odot z_2,
\]
\[
F_{cmd}=m a_{nom}-F_{residual}.
\]

脚本按 [position_bs_step.m](../../../matlab/core/position_bs_step.m#L17) 重算 20 ms 名义力与命令力；B 与 DSSM 的日志结果逐位匹配。DSSM 在该时点的 held Head 力与实际补偿力均为零；B 的补偿力来自已启用的 formal position RBF。这是**预先定义的方法比较导致的控制器分支差异**，不是代码计算错误。

## 尚未回答的问题与下一步

- DSSM14/PCF-on 的 W15 场景宏平均 X RMSE 比 B 高约 1.097 mm；这三场中 R3 相对 PCF-on 低约 0.001016 mm。该配对观察不能单独识别 `[1,1,0]` mask 的因果效应。现有数据没有把这段长时误差归因到位置补偿、Head、姿态耦合或 Plant 响应中的单一组件。
- B 的 run-start 含完整数值配置和 `collector_id=B`，但没有逐运行绑定的 `runtime_tree_sha256`。本次复算验证的是日志字段、配置和当前位置环方程，不声称证明历史 B 可执行文件与当前源码逐字节相同。
- 更深的姿态/滤波/力矩/电机逐级重放尚未完成；即使日志能复建这些控制输出，也不能替代不同控制器下的闭环状态反事实。
- 本计划研发额度已达 3/3，因此不再启动候选、72 场扩展或 TEST48。若用户另立研究周期，下一项离线工作应从同一 W15 状态继续核对“位置命令→姿态/推力目标→命令滤波→姿态力矩→分配/电机”链；只有其输出能按日志精度重建，才可据此冻结新的单因素任务书。优先可证伪假设是 readiness 前保留 B 位置 RBF、Head ready 后切换至 DSSM 是否改善早期 X 误差；它目前只是待检验方向，不是因果结论或已授权实验。

## 可复现入口

在项目根目录用 PowerShell 7 执行：

```powershell
python -B reports/paper14_v2/phase1/audit_w15_position_replay.py
```

脚本只读取表内指定的三个 VAL W15 配对组、run-start、重评分/lineage/hash 清单和源码方程；校验 SHA、配置、初态/参考、位置力重算及首个分叉时间。它不写文件、不读取 TEST、不启动 Plant、MATLAB 或训练。
