# 新 B 单场 runner：独立静态复核

**结论：代码/锁/合同静态审核通过，未发现首场必然走错源或方法的阻塞。尚不能放行 Plant：无 Plant prepare JSON 与 cfg/opts 快照尚未产出；主审须先核其实际 SHA、零 Plant 调用、32 项库存解析和完整 B options，再签 release。** 本审不重跑历史场景，也未执行 MATLAB。

- 固定输入锁 `B_TRACEABLE_INPUT_LOCK.json`：SHA `0BAA4A16765AF16C333CD65617C94308DD328021A12DD2B9BDE23204867D03C1`；contract：`9D90A20222865BB962E614201A743A305FEA8E984DEA1B58EC778158367D47CC`；runner：`4FCF15D68AE4129AEB417B0ADDEEDF50EC295C55976E171D608B3CF518E136C5`；prepare：`0C655B69975C220E11FBB007710551284514A8B3BEC9B0D2948A58B367525C73`。锁内四者的路径/SHA与当前文件一致，固定 scene、C3 input/source lock、DEV72 scene 行、scene raw 与 external identity 均有 SHA 引用；库存为 31 个 `.m` 加 1 个 cfg MAT。
- prepare 从冻结 C3 cfg snapshot 读 cfg，并以 `controller_options_dl1018(cfg,'B')` 从头构造 B opts；`init_dl1018` 也返回相同 B opts。它校验位置/姿态 RBF 输出与更新开启、两组频率100Hz、关闭候选字段，并对 cfg/完整 opts/source identity 做快照。B 构造器的 B 分支保留默认 RBF，未附加 stage1、search、PCF 或 delayed-prediction字段。
- runner 再次重建并与 prepare 快照逐项 `isequaln`，校验活动 `.m` 的 `which` 路径与 SHA，校验场景身份、无旧 attempt/marker、共享重负载锁及授权 release。它只调用一次 wrapper；wrapper 第二参是 collector 标签，但内部固定执行 `B2-RBF-Full-SPLIT`，故不是把标签错当控制器方法。B 的运行期 marker 字段在快照比较之后才注入，随后完整 cfg/opts 与来源身份写入 run_start。
- 失败状态保留 raw、禁止自动重试；成功状态要求 STABLE、20000转移/20001状态点及有限状态/参考/时间。单场 runner 的启动余量检查目前只有1MB，不能独立保证128MiB总产物限额；本次不构成代码阻塞，但 release 前主审应按已授权余量核对真实目录占用与预计产物空间（任务书冻结最低磁盘余量30GB）。

**放行条件：** 等 A 的 no-Plant prepare 自然完成并保留实际退出码；核对 `B_TRACEABLE_PREPARE_RESULT.json`、`B_TRACEABLE_PREPARED_CFG_OPTS.mat` 的 SHA 和内容，确认 `plant_calls=0`、`run_episode_called=false`、cfg等于C3快照、B opts完整且与新构造相等、32项来源与 `which` 无 shadow。此后才由主审把精确 SHA 写入单场 release。首场raw还须按任务书独立比较状态、参考、Q与轴指标；该比较是入口复现判定，不会补回旧72场未封存的 B runtime 身份。