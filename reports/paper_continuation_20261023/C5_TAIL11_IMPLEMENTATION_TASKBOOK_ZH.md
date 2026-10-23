# C5尾11：固定机制筛查补齐任务书

批准隔离实现，未批准执行。用户已授权必要新增航次，无需再询问。待主审读取实际尾11源码/绑定并产生明确release后，才可启动11次Plant；不训练、不跑72或TEST、不改任何参数。

首场T2_C00W10实际raw SHA `9115113229c8fe3add21e1337216ceded2f829e06f4eb1d5a4930eb2e87020c4`，主审1968事件及cfg120/opts43/源码身份和自然OS0全部通过，最大差4.43e-13。C5 Q=8.768693mm，低于C3的9.165824mm；Z由3.688510降至2.537401mm，水平没有C4那样明显劣化。C5仍未胜本场B的8.516659mm，不能报成功。首场只作为工程/安全门和机制观察，完整预登记门仍在原12场上执行。

唯一候选和所有模型、normalizer、core/helper/wrapper、cfg/opts完全复用C5 v1准备，固定M110。core SHA `48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c`；input lock `10a7eea144e3574e05eea7b4f7b56112595eac0c81d27b5e8c7a5a41499f84b0`；source binding `8a8a77e3058c58eccaf5156277734567190888dc5806bf210f43dc19844872ac`；snapshot `e417b56e68a73f7af6f40a5e7928631db1b4f3c05de1c3abd24828053760749d`。不得修改上述文件，也不得重新prepare或重复pilot。

优先以已经真实完成的C4 `run_c4_tail11_v3.m` 和其单层PS7 launcher为模板，但C5所有字段/路径必须从实际C5锁和准备对象读取，不用字符串猜文件名或字段。新建独立尾11runner、合同、source binding、PS7 launcher即可；不另造通用运行框架。新runner继承已审C5入口的完整路径/which/配置/模型/输入验证，必须实际核完整准备快照与first parent review。

场景为原C5合同12个scene_ids，按原顺序仅排除T2_C00W10，恰好11个唯一ID。物理输入仍锁定C3的旧B_source；评分对照使用已主审的新B72，明确绑定首场release中的`b72_raw_manifest_path/sha256`和`b72_parent_review_path/sha256`，并核其真实身份。每场首启前重新核active source SHA、物理输入SHA和本场新B raw/status；每场从准备opts/W0重置全部控制状态。

单MATLAB重批次顺序跑、全程持同一共享heavy锁，禁止抢锁/终止任何旧实验。每场raw/status/run_start/attempt/firstPlant marker及source/cfg/opts身份齐全，无覆盖、无自动重试；出错保留已完成和失败现场并停止。自然batch OS0后产生明确共享batch范围的per-scene exit记录，不能写成11个独立进程退出。

C5总预算首场加尾11最多12次Plant、全目录1GiB；每个剩余场预留80MB，预留后可用空间≥30GB；保留原总80GB和UTC2026-10-24T17:01:00截止。启动前以每剩余场180秒另加退出缓冲保守核截止；剩余批次明显不能完成时不启动。运行不得修改原始C3/C4/B、模型、历史MAT、缓存或封存记录。

完整12场门一项不改：两个FIG8高频的Q和Z都低于C3；ALL12平均Q≤C3；HF6和W15三场平均Q≤新B；全部完整安全。判断用未舍入Q和1e-12m容差；记录全任务/组/轴/早晚/峰值/P95/执行器/所有输场。任一门失败不扩72、不调参或换场。

先交CODE_READY、实际diff/SHA、完整确切命令和资源护栏，等待主审release。补录首场实际`exec_command.cmd`的完整调用及stdout/stderr捕获方式；若现有命令txt只覆盖内层调用，另写说明，不能伪造此前未执行的重定向命令。历史启动前误用C4锁文件名的检查失败记录为0 MATLAB/0 Plant，不隐去或当作实际闭环重试。
