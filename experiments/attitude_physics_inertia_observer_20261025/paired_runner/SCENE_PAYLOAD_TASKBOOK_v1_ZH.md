# 三场 DEV scene payload 封存任务书 v1

日期：2026-10-25。root 仅批准三场 DEV 场景的 MATLAB R2025b、无 Plant 身份生成；不批准闭环 runner、航次、训练或 TEST。不得读取 TEST、MAT、raw。只用隔离的 `configs/scene_specs_dev3.csv` 与 receipt。

## 固定操作

1. 启动前只读检查 MATLAB/Octave 进程，不得结束既有进程；若 MATLAB 已运行，等待空闲后再继续。只用 PowerShell 7 的 `-NoProfile` launcher 启动 R2025b。
2. `restoredefaultpath` 后只激活 `paired_runner` 隔离树；以 `default_config()` 构造 scene 几何配置，并用 `bind_paired_fixed_j0` 记录与真实固定控制器一致的 J0。逐一、仅一次调用三个固定 DEV ID 的 `make_paired_dev_scene(id,cfg)`。该调用只生成参考、风与形态命令，不调用闭环 runner、Plant 或数据加载器。
3. 对每场分别将 `out.spec`、`out.scene`、`out.metadata` 规范化为 JSON UTF-8 字节并计算 SHA-256；输出只保存哈希、行数/尺寸、任务/风/形态摘要与身份字段，不保存 scene payload。记录输入 CSV/receipt、隔离生成器及依赖、cfg/J0、MATLAB release 的 SHA/身份。候选清单状态保持 `NOT_FROZEN`、`closed_loop_runs_authorized=false`、`executed=false`。
4. 使用不可覆盖的新目录文件保存准确命令、stdout、stderr、exit code 与短 receipt；校验 ID、seed、全部 scene 长度 20,001、time 为 0:0.001:20、W15 零风、三场各自规格 hash。不得从 ID 推导任何字段。

## 停止条件与后续门槛

任一来源/hash/身份/shape/有限性/时间轴检查失败，或发现读取非隔离数据、MAT/Plant/runner 调用，即保留日志并停止。完成后 root 独立复核 scene hashes、数据边界和代码身份；这只完成 payload 输入准备。姿态 paired runner 的完整模型/权重/config/source lock 仍待锁定，六个 fresh DEV 配对航次须另由 root 审核后放行。TEST 继续封存。
