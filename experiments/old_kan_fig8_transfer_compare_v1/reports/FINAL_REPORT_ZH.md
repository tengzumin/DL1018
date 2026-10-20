# 旧 KAN 获胜包复现与当前八字迁移对照

## 执行概况

- 当前八场完成率：34 Plant 调用；总调用上限 48。未访问 TEST、未训练模型。
- 零 Plant 预检：PASS；8 个已有 B 均与官方生成器逐数组一致，20,000 transitions。
- 历史两场复现：

  - `PDEV_DIAG_D1_C01_1` PASS，Q0-5 0.022051 m，Q5-20 0.016737 m，Q0-20 0.018211 m，最大历史差 3.47e-17 m。
  - `PDEV_DIAG_D1_C12_124` PASS，Q0-5 0.066293 m，Q5-20 0.032813 m，Q0-20 0.043660 m，最大历史差 1.39e-17 m。

## 统一 readiness=32 的主矩阵

| 配置 | 宏 Q0-20 (m) | 相对 B 改善 | 胜 B | 最差退化 (m) | 完整场数 |
|---|---:|---:|---:|---:|---:|
| OLD_G1_R32 | 0.028404 | -36.52% | 1/8 | 0.016288 | 8/8 |
| NEW_G1_R32 | 0.043343 | -108.33% | 0/8 | 0.033360 | 8/8 |
| OLD_G12_R32 | 0.018439 | 11.37% | 7/8 | 0.005568 | 8/8 |
| NEW_G12_R32 | 0.024118 | -15.92% | 2/8 | 0.008454 | 8/8 |

同一 Gamma 下新包减旧包的宏 Q 差：Gamma=1 为 0.014939 m，Gamma=12 为 0.005679 m。
旧包 Gamma12−Gamma1 宏 Q 差 -0.009965 m；新包 -0.019225 m；package×Gamma 差分 -0.009260 m（负值表示新包对增大 Gamma 的改善相对更强）。

## readiness 对照

同一新共享 KAN14、Gamma12：既有 ready1 宏 Q 0.024116 m，统一 ready32 宏 Q 0.024118 m；ready32−ready1 为 0.000002 m。既有包每场 1,999 次推理，当前 ready32 预计/实测每场 1,968 次，首个有效时刻 0.32 s。
这只识别同一新包启动合同改变的差值；不会把旧/新包之间的差异单独归因于 readiness。

## 轨迹/风桥接

预注册门槛状态：`SKIPPED_OLD_PACKAGE_RECOVERED`。
按冻结规则跳过：至少一个旧包 Gamma 在 8/8 完整、宏改善 >=10%、胜 B >=6/8 三项同时过门槛。

## 证据结论

历史复现检验旧包是否仍可在原 V3.5 快照上达到原 Q；当前矩阵在相同场景、相同 DL1018 Plant/控制合同下比较包身份与 Gamma。若两者同场差异稳定，证据支持“模型包整体在当前任务上的闭环行为不同”；它不能指出 normalizer、encoder、W0 或训练历史中的哪个单一部件是根因。

旧/新八字参考轨迹、环境风与构型的变化不能再被混成一个“数据分布不同”结论。桥接只支持 C09 上参考整体与外部风频对旧包相对 B 的敏感性；不证明新包训练失败由其中某一项造成。Gamma 的结果也只用于当前 DEV 诊断，不是未见测试的胜者声明。

### 文件索引

- `ZERO_PLANT_PREFLIGHT.json`
- `HISTORICAL_REPRODUCTION.csv`
- `TRANSFER_ALL_RUNS.csv`
- `FIG8_MODEL_GAMMA_PAIRED.csv` / `FIG8_MODEL_GAMMA_SUMMARY.csv`
- `READY_REFERENCE_COMPARISON.csv`
- `PHASE_AXIS_COMPARISON.csv`
- `ONLINE_DIAGNOSTICS.csv`
- `RESOURCE_LEDGER.csv`
