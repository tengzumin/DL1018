# C7 准备与输入锁独立审查

审查为静态只读。未运行 MATLAB/Plant、未载入场景 raw MAT，也未访问 TEST。审查对象及 SHA-256：

- `prepare_c7_split_target_v1.m` — `558f1bad686a3a30145bd66f1f54ed7b1154e1fa82c47a8f06ceea05b04e7cbb`
- `RUN_C7_PREPARE_ONLY_EXACT_v1.ps1` — `cf32379c8d83ddabf3f184c6f878acf47a6ff82f8e36271642e933ca6010963d`
- `BUILD_C7_INPUT_LOCK_v1.ps1` — `12f51048514774f4318afcedac75eed334bcfde9307b197f8853240f9592951c`
- 实际生成的 `C7_SPLIT_TARGET_INPUT_LOCK_v1.json` — `20652a95bd08a0c68b8907af38daade095d75afb5f66cc22521ee5b0a44914be`
- `run_c7_batch_v1.m` — `c1abc75ad35b755f02c2c779ef559a5ff66dec3d420cece7f4b7d7d3cf169913`

输入锁是 `C7_MS110_MY000`，含12行，顺序与锁定scene列表一致，first scene在第5行、tail为11行。逐行独立对照了C5 input lock、C5 prepare的scene identity及B72评分manifest；12/12映射和C5 baseline状态元数据均匹配。三类路径语义明确且12行均互不相同：`B_source`是C7物理scene输入，`B72_scored.raw_path`与`C5_baseline.raw_path`是既有评分输出。后续runner从`B_source.path`载入scene；另两类raw只做哈希核验并保留评分/来源身份，不作为C7物理输入。此次未读取这些raw文件。

锁中14个命名refs、13个C7源码refs及32个继承C5源码refs均存在且SHA复核通过。锁记录 `raw_mat_loaded_during_lock_build=false`、`raw_bytes_hashed_during_lock_build=0`。C7 prepare逐项验refs/source SHA、无Plant合成收据、冻结C5快照、场景映射和唯一写入输出；掩码之外，`c7_split_target_options`将C5 opts与C7 opts作`isequaln`逐字段比较。它直接按MATLAB列主序little-endian double字节重算W0 SHA，并比较model identity中的normalizer摘要、model id和selected step。当前C5 prepare源码还会从锁定model MAT实算W0及`input_mu/input_sigma`摘要，并验证共享输入；C7继承其已锁定的prepare结果和快照。C7自身不再次从normalizer数组重算摘要；根审应继续确认MAT快照与C5 prepare记录相互一致。现有锁定JSON的C5 prepare snapshot SHA与锁定快照SHA一致，C5 model identity与任务书身份一致。

`run_c7_batch_v1`会把冻结C5 `active_paths` 中三个候选核心函数替换为C7路径，对其他MATLAB源码加锁定路径，并在运行时用`which`核对解析路径，记录每个resolved function及SHA。此路径检查尚未执行，属于未来FIRST/TAIL运行门，不是prepare-only结果。当前输入锁未包含TAIL11 runner/launcher；FIRST阶段不受影响，TAIL11应按已规划的单独parent release绑定实际runner与launcher哈希。

审查结论：未发现物理输入误接B72/C5评分raw、C7 opts出现额外变化、锁定refs失配或12场景映射错误。该结论只覆盖准备与输入 provenance；不构成闭环运行、C7科学效果或创新性的通过结论。