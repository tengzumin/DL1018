# 第一份事实摘要：旧八字全胜与当前 C5 八输场

本轮任务书 SHA256 ee89381640ca0c001812c1a612b4e60bd7d38d9b81f537e5438f8fb041b77897 一致。0 MATLAB、0 Plant、0 训练、0 GPU；仅写隔离目录，未修改控制律。当前 C5 TEST 性能未读取。旧混合报告意外显示历史 TEST 行的事故单列，不能声称本轮从未接触任何历史 TEST；不得用于模型或参数选择。

| 真实产物 | 范围/时段 | 同场 B → 候选平均 Q/mm | 胜 B |
|---|---|---:|---:|
| DL1009 position_advantage_stage1_v1，final N_KAN | DEV32，5–20s 主列 B_Q/C_Q | 34.324223 → 24.400462 | 32/32 |
| 同一表、同一运行 | DEV32，0–20s B_full/C_full | 35.414683 → 31.246963 | 31/32 |
| 同一表、同一运行 | DEV32，0–5s B_early/C_early | 38.182918 → 45.528465 | 0/32 |
| DL1018 old_kan_fig8_transfer_compare_v1，OLD_G12_R32 | DEV T2 八场，0–20s | 20.805219 → 18.438791 | 7/8 |
| DL1018 teacher_reuse SMALL_DSSM14 | TRAIN 八字两场，0–20s | 26.172465 → 22.512326 | 1/2 |
| 当前冻结 C5 M110 | DEV+VAL72，0–20s | 17.058081 → 11.558928 | 64/72 |

**真实全胜表：**
C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1009/RBF-BS0/experiments/position_advantage_stage1_v1/reports/paired_metrics_DEV.csv
SHA256 e0f82696d2f3dbfbd7ff179c718f778b102455532ab6c4c5f2481369ace7ddfb。

同项目 methods/stage1_metrics.m 明确定义 Q 为 5<=t<20、full 为 0<=t<20、early 为 0<=t<5，均为 sqrt(mean(sum(position_error.^2,2)))。全部32场调用同一个无条件 FIG8 参考，只有构型/时序/风改变，非混合轨迹。16行 canonical DEV J1 与训练J1复用同物理输入，另16行J2为不同实现；这不是32个都未见的独立场景。0–20s唯一输场 DEV_C11_123_J2；当前八输场无相同ID，尚未证明物理输入相同，不能映射到某一当前输场。

**源方程与控制合同：**

- 旧DEV32源码 .../position_advantage_stage1_v1/methods/stage1_scenes.m，make_reference：h=3s²−2s³，θ=2πh，p=[1.5sinθ,sin2θ,0.5(1−cosθ)]。
- 当前 matlab/scenes/make_scenes_dl1018.m：u=10s³−15s⁴+6s⁵，θ=2πu，p=[1.5sinθ,sin2θ,0.4u+0.35(1−cos2θ)]。Z几何和时间参数化均不同。
- 旧DEV32为20261013 final N_KAN（6epochs，75648 train windows，12608 val windows），自己的normalizer/W0；不是后来的 repair N_KAN，也不是当前corrected DSSM14。旧head W_next=Proj(W−hβφsᵀ−h·0.002W)，无PCF/延迟预测；当前C5 tracking系数12、PCF M110及延迟预测。两者各自B都保留原位置RBF，候选换掉位置RBF；位置BS和B姿态RBF保留。入口已核实两者位置/姿态事件均100Hz、Plant1kHz，不能误称当前400Hz。
- 旧G12八场包源自 DL1009 kan_position_attitude_followup_v2/models/repair/N_KAN，成套normalizer/W0；它与旧DEV32 final N_KAN来源不同。唯一输场 DL1018_DEV_T2_C09_W10。原精度旧8/当前8比较见 v2/OLD8_CURRENT8_COMPARISON_v1.csv，明确不声称跨年代物理输入一致。
- 当前C5和corrected DSSM14共享新DSSM14 final60k模型/W0/normalizer，W0 SHA88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53，normalizer arrays SHA533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0。不能混成legacy DSSM。

**加速度因子2修复：**

DL1018原参数二阶导 puu=[−6π²sinθ,−8π²sin2θ,2.8π²cos2θ]；
正确 puu=[−6π²sinθ,−16π²sin2θ,5.6π²cos2θ]；
a=puu·ud²+pu·udd，p/v没变。

独立修复归档 FIG8_ACC_FIX_CAUSAL_20261021_010512 的零Plant预检记录 local 2026-10-21 01:31:10，原源码SHA42c8dcf94b9bd52ab16abe7991326dfcfccdcdf15810bb4b19a6d7a87e67a13f，修复SHA454106ad22f44ebf5a2210fbd50a7672b5508e550ebfc80c16158e5cdbee544a；这是文件内记录时刻，不声称精确提交时刻。三场既有预检逐字段报告只变sceneID及accY/accZ，其余位置/速度/构型/风字段相同。随后完整8场既有因果审查核对32对配置/模型合同、64条raw、48次W0初始化，PASS。2026-10-22接入活动源码并加参考合同/旧缓存防混用门，见 reports/integration_next14_v1/engineering/A_CORRECTED_REFERENCE_CACHE_GUARD_ZH.md。本轮尚未重解这些历史raw，保存的是现有审查来源和哈希。

同条件8场修复使NEW KAN相对B差距8/8缩小，但修后仍仅3/8胜。它识别参考修复的局部作用，不证明旧/新包差距全由它造成。B-Q不同本身不构成组件归因。

**当前判断和下一步：**

尚无确证部署bug。旧5–20s全胜不能替代当前0–20s全胜，亦不能解释当前全部失败；根已复核当前8输场中4场后段仍输。下一步仅在当前同一DEV记录的φ/s/PCF状态/过去区间标签上回放完整C5与去预测项，检查输出先于更新、ready、beta、符号、区间和梯度竞争。完整72配对表保留NO_PRED的T2收益及其它任务/无风代价；不按8场改gain，不把不同闭环状态作组件因果。

复算脚本 experiments/c5_eight_loss_recovery_20261024/historical_dev_facts_v2.py 实际退出0；v1因误猜列名失败，原代码/部分输出/失败记录全保留，v2更正已核列名且另存输出。完整来源哈希 v2/HISTORICAL_DEV_FACTS_v1.json；暴露事故 v2/HISTORICAL_TEST_EXPOSURE_INCIDENT_v1.json。
