# Root 审核：C5 同源输入预检通过，尚未放行 Plant

2026-10-25。主审实际读取源、运行记录并独立复算后，决定：**通过完整输入无 Plant 预检，继续实施 DEV3 执行入口；尚不授权任何 Plant 航次。**

本轮发现并修复的是三项工程问题，不是方法性能结论：PowerShell 空进程列表被展开为 null；隔离 forward 错用缺少 `DSSM` 分支的旧版；准备入口使用 default cfg 而非实际 C5 cfg。旧源、旧静态审计、首次失败输出与任务书均保留。当前 forward 是 C5 锁定源的原字节副本，SHA `dc803aa102c49d67dd687ae941f8a60bb0c465f74fd01e5ae93ad1ea1a293676`；其余38个部署源与修复前相同。有效 cfg 直接取已锁 C5 v3 snapshot，附加 J0 后除此字段完全相同。

实际运行目录为 `preflight_v1/runs/full_input_preflight_20261025T140223_0872c2df/`。MATLAB PID14664、launcher session7245 均已正常结束；退出0，stderr为空。receipt SHA `f770cfe55688314b104848ae1b7176245dd2ffc5592726be813c412897619bd6`；候选锁 SHA `ce6e671d8174ab5204581923a56548c697a8ef703d8b50b43eb9421af23cd1b2`。主审重新计算了39个隔离源及17个输入的当前SHA，对照运行前/后记录零差异，receipt→candidate引用及stdout/stderr哈希均匹配。36条checkcode诊断的ID为AGROW/ALIGN/DEFNU/INUSD/ISCL/MSNU/NASGU/NOSEMI/PREALL，未发现语法错误诊断。

实际 MATLAB 已执行并通过：DSSM14/DSSM、seed2026102001、step60000、X14/window32；W0 SHA `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`；normalizer数组SHA `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`；人工DSSM和冻结模型的合成输入推理；原C5 options全等、paired baseline仅新增显式身份/零初值、candidate仅改变预注册姿态RBF开关；J0和fixed controller矩阵/哈希一致。三场均20001状态时间点、有限零初态、完整有限参考/风/形态数组，W15风速RMS及峰值均严格0。

| scene ID | seed | scene SHA |
|---|---:|---|
| DL1018_DEV_T1_C00_W03 | 2026121803 | ac971bf76852b5494d9cb7162f5a16fa9f188a5e7d46ba49c52c7ebf6a70afc0 |
| DL1018_DEV_T2_C02_W15 | 2026122847 | f3d28311289d25b3faea55d92f9a47214418d5dadc57c107818c592126e87188 |
| DL1018_DEV_T3_C10_W11 | 2026123971 | e06aa4dde902603f390554f4d8b022760b44a450b2c9868d68344d44ea5a809f |

scene payload未保存；这些内容哈希由已审代码在实际MATLAB中生成，主审核验代码、运行断言、stdout/candidate一致性与来源身份，没有声称独立重新生成过payload。仅此“scene-only预检失败→full input preflight”阶段的资源为launcher2次、真正MATLAB1次、Plant0次、训练0次；此前synthetic和一次root只读checkcode另见历史记录，不混作整个研究的总次数。root曾在旧scope的source inventory盘点中对effective_config.mat做hash-only读取、未解析变量，已在完整输入任务书披露。

下一入口任务书为 `DEV3_EXECUTION_ENTRY_TASKBOOK_v1_ZH.md`。它只批准wrapper/launcher和最终锁的隔离实现及静态检查；最终source lock须纳入这些真实执行入口，再由root审核并创建独立release，才能至多按原3场顺序运行6航次。当前候选锁保持NOT_FROZEN、closed_loop_runs_authorized=false、executed=false。此次成功是工程/身份预检，不是闭环性能、理论稳定性或论文证据包通过。TEST和历史结果原样保留，目标继续有效。
