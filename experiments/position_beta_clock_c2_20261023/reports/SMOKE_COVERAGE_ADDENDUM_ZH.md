# 无 Plant smoke 覆盖补记

该补记不改写或重跑 `OFFLINE_SMOKE_NO_PLANT.json`。一次性 MATLAB smoke 已于 2026-10-22 16:40:58.059Z 启动、16:41:19.397Z 退出，PID 77548、exit 0；实际执行的 smoke 源 SHA 为 `f511770ed1c626c6e66431f31e8e83ff6914cd050292cb1972b492dcbc2c6945`，锁文件 SHA 为 `390888537a0138f36a0d9b3a1e1fc607ecdc57939a38dabb66db79c0887aca87`。

执行版本没有遍历 `C1_SOURCE_LOCK_v2.json` 的 `frozen_plant_files`，也没有把 `simulation_parameters`、`controller_parameters`、`arm_mass_properties`、`allocation_matrix` 的 MATLAB `which` 路径写入结果。独立 peer 在同一轮审阅中报告 31 个冻结源码 SHA 全部匹配；随后本目录的只读复核亦验证 31/31 匹配，证据见 `POSTRUN_LOCKED_SOURCE_HASH_AUDIT.json`（SHA `46ce67225f13654e63d2e9e88a9454dda5cc6a0d2aec14eea44a61f2b1495215`）。这项后置文件哈希复核不等同于 smoke 内部的函数路径断言。

smoke 已实际通过其余已记录的源锁、候选 runtime 本地路径、cfg/model/normalizer 身份、ON1 c=1 options、beta 时钟边界、Head 输出先于更新数值和源码 checkcode。过程未调用 `run_episode` 或 Plant 动力学、未访问 TEST、未训练或使用 GPU。该结果仅为一次无 Plant 工程 smoke；C2 新闭环仍未获授权。
