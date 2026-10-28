# 配对位置分支探针：首轮源码审核

状态：待作者修正并重新审核；未放行 Plant。2026-10-24。

已读取准备脚本、运行脚本、冻结任务书，以及 C5 parent engine 的初始化、调度和 episode wrapper。任务仍是两条固定 TRAIN 场景、四个前瞻配对航次，不训练，不访问 TEST。

发现并已通知作者：

1. prepare 与 runner 对自身源码调用 mfilename('fullpath') 后直接 hash，没有 .m 扩展名，可能在正式准备/启动前 fopen 失败。改为明确的脚本文件路径。
2. verify_c5_sources 使用 evalin('base','cfg') 且要求 cfg 不相等，产生不必要的 base 工作区依赖及反向验证。改为显式正向核对或移除该无关比较。
3. failure.plant_calls_started 以 attempt_started.marker 判断，会把真正进入 Plant 前的失败计为物理航次。应核 first_plant_step.marker，并区分启动尝试与实际 Plant 转移。
4. 初始化说明中的 filter.euler 应固定为 3x1，与 command_filter_init(initialEuler(:)) 一致。

这些是新探针脚本的工程问题，不是已经确认的历史控制器根因。作者修复后再进行无 Plant 准备和非作者审核，不因脚本已存在而提前放行。

只读资源检查：未发现 MATLAB 或研究训练 Python 进程；可见 Python 均为 SolidWorks MCP。C 盘剩余约 207.8 GiB。没有结束任何进程。
