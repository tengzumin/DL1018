# C5 axis-coordinate screen — CODE_READY

状态：代码与输入锁已到 CODE_READY，等待主审审核入口及无 Plant 检查；本阶段没有启动 MATLAB 或 Plant，也没有生成准备快照、首航 release 或 C5 raw。

冻结 taskbook SHA-256：`5c3f19548a5cd1f6e337d20dcd0c48f81560d3907d5a24d20676e9cf62545c38`。唯一候选为 `M=diag(1,1,0)`：延迟模式要求显式三元素 mask `[1;1;0]`；PCF 面按轴计算 `s−Mη`，区间参考在 mask=1 轴直接取 `a_f`、mask=0 轴直接取 `a_req`，保留独立实际 `a_f` 积分。C3 无 mask 的旧方法默认保持 M=I 语义。C4 的 M=0 只在合成公式检查中出现；C5 core 不声称复现 C4 runtime。

相对冻结 C4 core 的实际改动限于 mask 读取/校验与候选合同、逐轴 tracking 面、逐轴区间参考与独立日志；DSSM14、X14/32、33×3 头、helper、调度/投影顺序和其余控制路径未变。`run_episode_dl1018.m` 与 `delayed_prediction_step_candidate.m` 分别逐字节等于已审 C4 文件。主审算法静态审核 PASS：`C5_ALGORITHM_PARENT_REVIEW_v1.json` SHA-256 `2dad45d5f779f753bde0d8f715fa9ad17793425c4a4a65c35d3940e34ed83fec`。

Python fixture 含确定性 W/φ/s/η、M=I/0/110 三组、n=320/330 两事件、11×3 `a_req/a_f`（第 11 行是当前行哨兵）。每组检查 `[320,330)` 十行积分、首事件无伪造历史、当前行不进目标、输出先于更新，以及 helper 的 raw/applied/β/gradient/preprojection/Wnext。Python fixture 在临时文件重生成后与锁定 fixture 字节完全一致，SHA-256 `b59643528318f1053065b6ee2acaf011a016e807084fee3a17918472875c5361`；MATLAB checker 尚未运行。该合成只测公式及未改 helper，不覆盖 C5 core 的闭环布线；后续必须静态复核并由首场完整 raw 复算验证。

准备入口会恢复锁定 runtime 路径、核对 32 个 active source 与 6 个共享输入、用 role 唯一解析 `model_mat`，按 C3 snapshot 的完整结构复制 12 行 scene identity，并要求合成 checker PASS 后才写准备产物。已解码 scene identity 字段为：`B_raw_path, B_raw_sha256, alias_normalized_in_memory, canonical_scene_id, payload_review_sha256, raw_scene_id, scene_id`。runner 仍将旧 C3 `B_source` 仅作为物理场景输入；评分 B 只能使用未来由主审审核并在 release 绑定的完整 B72 manifest/raw/status。

静态校验通过：锁定 32 源（31 个 `.m`+1 个 `.mat`）、6 个共享输入、12 场顺序及 65 条 source-binding 路径 SHA；helper/model role 与 MATLAB basename 唯一性通过；fixture 的 JSON struct 字段形状一致；两个 PS7 launcher 均通过 PowerShell Parser。结果锁 SHA-256 `10a7eea144e3574e05eea7b4f7b56112595eac0c81d27b5e8c7a5a41499f84b0`，source binding SHA-256 `8a8a77e3058c58eccaf5156277734567190888dc5806bf210f43dc19844872ac`。

主要源码 SHA-256：

- `run_dl1018_closed_loop.m`：`48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c`
- `delayed_prediction_step_candidate.m`（与 C4 相同）：`48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d`
- `run_episode_dl1018.m`（与 C4 相同）：`fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330`
- `prepare_c5_axis_coordinate_v1.m`：`05d84458b08085698fbd29e65f87c576700350548bc60625fddb90f64ec51e09`
- `run_c5_axis_coordinate_v1.m`：`0a2030f85931bd91bf073c81f1e1e3477bed3bfe257b6dcbfffee1759c36d3e4`
- `check_c5_axis_coordinate_synthetic_v1.m`：`4f47f8773b69a96456de052e1ccc3453463d0c1deaeb07539c55b8824bf80143`

审阅后唯一准备命令为（PowerShell 7 单层调用；现在未执行）：

```powershell
& 'C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/experiments/position_axis_coordinate_c5_20261023/RUN_C5_NOPLANT_EXACT_v1.ps1'
```

其中 MATLAB batch 固定为绝对路径 `cd(...)`，顺序运行 `check_c5_axis_coordinate_synthetic_v1; prepare_c5_axis_coordinate_v1; quit(0,'force')`，错误进入 catch 后 `quit(1,'force')`；PowerShell 只在 MATLAB 真正返回后写 OS exit。首场 launcher 也已备好，但必须等 B72 72 场 parent audit PASS 和另一个确切首场 release，当前不得调用。
