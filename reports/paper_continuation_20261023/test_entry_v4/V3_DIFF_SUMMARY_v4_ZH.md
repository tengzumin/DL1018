# v4 相对 v3 的实现差异

## 保持的行为

- 六方法科学顺序、方法/model/source 身份、初值/W0、控制器数学循环、更新顺序、物理模型、时间边界、统计源码均沿用冻结 v3。入口没有复制生成 TEST 场景或修改旧 reader/score/statistics。
- TEST 阶段只读取 v3 冻结的 48 场景、六方法 cfg/opts、index 与自然 OS0 冻结回执。B48 由 v3 batch/body 固定 SHA 复用，不产生新 B Plant。
- v3 失败目录、原始源码、models、MAT/cache 与其他历史数据不改写、不移动、不删除。

## 必要入口变化

1. 新增 v4 独立入口、PS7 启动器与 v4 contract/manifest；旧 DEV/TEST 生成模式不进入 v4。三个阶段分别校验专属根 release、精确源码 SHA、授权布尔值、NoRetry、预算和自然进程回执。
2. D/K method manifest 与路径绑定各追加 peer 确认的活动 helper `matlab/models/position_filter_realization_pcf_step_v3_5.m`（SHA `b4ae22db5bd444a162d0cd01a3a59a589f2e37077b089bb33693401b660228d0`）。冻结 FEATURE/update/PCF 选项与合法 hover 输入的 helper 预检放在无 Plant 阶段；未启用 PCF updater 不绑定。
3. 显式锁 v3 B 的共享平台文件引用并在 MATLAB `which` 上逐项核身份；D/K 的方法 core/wrapper 仍各自继承 manifest 中的平台锁。
4. `ENGINEERING_DEV2` 用两个已完成同 ID VAL 场景，每个方法一个独立 Plant；选取的历史 run_start 和其相邻 raw 是 v3 manifest snapshot 对应字节，不与 peer 的不同 run_start 混称同一身份。新旧完整 raw 数值逐字段核对，四项纯计时单独报告。
5. 运行模式只执行未进入 Plant 的五方法 x 48，共至多 240 个唯一 Plant；每方法独立 MATLAB 进程，输出固定在 v4 短路径。v3 的 DSSM 失败为历史事实保留，禁止移动/覆盖后重跑。

## DEV2 输入身份

| 方法 | 选用 run_start SHA / raw SHA | 与 peer 存档不同的另一身份（run_start / raw SHA） |
|---|---|---|
| DSSM | `1b6417b4369f5b5618d1ee81ac8595de1bb6d607e0fdd04ad2913748f6986cde` / `e54111ca11559ccb5d1e7c9ca9824db0b225234b2cff3497d5cfe71e1878c8d8` | `3b798c8624cc10cc1ddf3b3b1000099bc62e42e8430af92a42b0fa467385743e` / `231a29949fe0f4ca1a900b909ee8ca9a003f99a71448c14974b68530b45f2b18` |
| KAN | `b10d1de1a0a0307659c3e1bb0f608aa8a4e0da109991493dbc327104404bbda9` / `977a948da36402f869046782344e9a8231f34cc5d982a1ee8c462170fc695c2d` | `0012bf34074ac2f034517fbb65237bd667b31e7e539987601e4d16e0b26c9525` / `e6f704af8dba06cfd25ab401aedfc3866f8f91c06677858ec5b7c0154b8fa54f` |

v3 冻结 shared scenes/cfg-opts/index SHA 分别为 `da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c`、`389fdfabd9fbd350d3bdd6df934cfe718eb7208bef2b7b4af02f1192cbb1b9e4`、`90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68`。实现期间没有执行 MATLAB/Plant；需根静态审代码后分别放行阶段。