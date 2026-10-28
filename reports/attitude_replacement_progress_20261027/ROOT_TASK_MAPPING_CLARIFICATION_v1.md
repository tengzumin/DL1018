# 场景名称与名义模型边界更正

2026-10-27 主审核对 matlab/scenes/make_scenes_dl1018.m:58、137，任务索引顺序为 T1=HELIX（螺旋）、T2=FIG8_3D（三维八字）、T3=SQUARE（平滑平面方形）。此前会话把末场 T3_C00_W13 口头称为三维八字，名称不准确；实际manifest、运行、raw和配对指标均使用正确scene ID，没有交换或重跑场景。后续按原始ID与本映射报告。

controller_morphology_mode=fixed 表示控制器使用固定名义参数，不表示物理Plant不变形。当前GRU六场gate_geometry_arm为ACTIVE；Plant几何仍按原预设命令演化。固定J0/Jdot0和禁止惯量重建约束作用于控制器，不能将其写为固定物理构型试验。EVIDENCE_LEDGER的简写已澄清，原始数据不变。
