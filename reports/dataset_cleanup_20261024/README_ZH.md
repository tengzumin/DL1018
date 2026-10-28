# DL1009 / DL1018 数据清理清单

盘点日期：2026-10-24。本文是供用户亲自删除的清单，尚未执行删除。1,335 个候选文件已逐项确认存在、大小与盘点一致，总计 61,516,581,187 字节（57.292 GiB）。

## 删除范围

| 工程 / 数据组 | 文件数 | 可释放 GiB |
|---|---:|---:|
| DL1009 / position_advantage_stage1_v1 | 277 | 10.511 |
| DL1009 / k1_command_filter_update_coordination_v3_5 | 304 | 13.144 |
| DL1009 / k1_position_attitude_fusion_v3 | 128 | 5.141 |
| DL1009 / kan_position_attitude_followup_v2 | 98 | 4.055 |
| DL1009 / attitude_kan_legal_input_reuse_upgrade_v3_6 | 95 | 4.189 |
| DL1018 / P_INIT_STUDENT 历史 raw | 426 | 19.048 |
| DL1018 / training_data_structure_compare_v2 的 NPY 缓存 | 7 | 1.204 |
| **合计** | **1,335** | **57.292** |

DL1009 共 902 个文件、37.040 GiB：896 个已完成且稳定的旧仿真 raw_run.mat，以及 6 个与保留版本 SHA-256 完全一致的聚合 CSV 副本。

DL1018 共 433 个文件、20.252 GiB：426 个旧初始学生的高频仿真轨迹，以及 7 个可确定性重建的 NPY 缓存。

## 如何按清单删除

桌面入口：`C:\Users\35326\Desktop\清理_DL1009_DL1018.cmd`。用户双击后会调用本目录的 `CLEANUP_APPROVED.ps1`，先全量核验，再永久删除已确认清单中的文件。无需管理员权限。窗口会显示进度并停留，完成日志写入本目录的 `EXECUTION_MANUAL_*.csv` 和 `MANUAL_RESULT_*.json`。

脚本将两个允许根路径、1,335 文件数、总字节数及清单 SHA-256 固定在代码中。每个文件删除前重新检查路径范围、普通文件类型、所有目录祖先无链接、大小和修改时间。重复 CSV 还会再次核验与保留副本的 SHA-256。文件变化就停止，不扫描新增候选，不删除目录，不使用递归删除。

已实际运行 `CLEANUP_APPROVED.ps1 -CheckOnly`：退出码 0，核验 1,335 个文件 / 57.292 GiB，通过；此模式没有删除文件，也没有写执行日志。代理没有启动正常删除模式。桌面入口是按用户明确要求创建、供用户亲自执行的文件。

- `DELETE_MANIFEST.csv`：精确的 1,335 条路径，含工程、分类、大小、删除理由、重建方式和重复 CSV 的保留副本。以 `path` 列为准。
- `DL1009_DELETE_PATHS.txt` / `DL1018_DELETE_PATHS.txt`：仅列完整文件路径，便于逐项查找。
- `groups/`：按实验拆分的精确路径清单。

**只删清单列出的文件，不要直接删除表格中的整个实验目录。** 同一个 `runs` 目录里还混有正在使用的 DEV 对照、复用基线、失败证据及运行配置；清单已经排除这些文件。

## 关键保留项

所有源码、模型、归一化器、配置、已有 run_start.mat、指标和报告均保留。Stage1 原设计没有逐次 run_start.mat，其 ledger、场景清单、源码和模型仍保留。

DL1009 另外保留：

- Stage1 `runs/DEV`，以及 DEV J1 实际复用的 16 份 `runs/TRAIN/*_J1/B` 原始轨迹。
- v3.5 `runs/DEV` 全部，供历史对照和复核使用。
- v2 `pdev_diagnostic` 的 B 基线。
- 硬停、D0 故障及其相关同输入证据；X29 V39 OFF parity 固定原始数据。
- 关键训练数据 `TRAIN_REPAIR_MIX_V2.csv`、`TRAIN_FINAL_EVENTS.csv`，以及 INITIAL/STUDENT/VAL 的 STABLE 聚合 CSV。

DL1018 另外保留：

- B / POS_OFF 的 TRAIN、VAL 原始数据；全部 DEV 原始轨迹。
- 所有 position / attitude 事件 H5 和 D4_SEQUENCE_CACHE NPZ。
- 当前 `c5_test48_v9`、`c5_eight_loss_recovery_20261024` 及其模型、DEV、B72、修正参考依赖链。
- P_INIT_STUDENT 的全部 432 份事件 H5、432 份 D4 NPZ、432 份 run_start，均已逐份检查齐全且结构合理。
- P_INIT_STUDENT 的 6 份代表 raw：train 的 T1_C00_W00、T2_C00_W00、T3_C00_W01；val 的 T1_C00_W07、T2_C00_W10、T3_C00_W13。完整路径见 `DL1018_PINIT_AUDIT.json` 的 `retained_samples`。

## 删除后的影响与恢复

旧初始学生模型仍可直接使用保留的 H5 / NPZ 离线复训。H5 / NPZ 并不是完整高频 raw 的可逆压缩；如果将来需要重新评分完整 20,000 步历史轨迹，须按保留的配置、场景、模型和源码重新运行仿真，不保证逐字节相同。旧索引中的 raw_path 会指向已经主动清理的路径，不能将该状态当成完整原始轨迹归档。

6 个重复 CSV 可从 `DUPLICATE_CSV_VERIFICATION.json` 中的 `retained_path` 复制回 `deleted_path`，精确恢复。

7 个 NPY 位于 `experiments/training_data_structure_compare_v2/derived`：

```text
TRAIN_X10_HISTORY_32.npy
VAL_X10_HISTORY_32.npy
BATCH_ORDER_N605184_SEED2026101911.npy
BATCH_ORDER_N605184_SEED2026101912.npy
BATCH_ORDER_N756480_SEED2026101911.npy
BATCH_ORDER_N756480_SEED2026101912.npy
MICRO_SHARED_BATCH_ORDER.npy
```

这些 NPY 的源 NPZ、identity、normalizer 和构建函数均保留。需要时在 DL1018 根目录开启一个 Python 进程，仅调用构建函数：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("experiments/training_data_structure_compare_v2/scripts").resolve()))
import d4_official_fits as f
for split in ("train", "val"):
    eps = f.load_episodes(split)
    f.ensure_history_cache(split, eps, f.offsets_for(eps))
for n in (605184, 756480):
    for seed in (2026101911, 2026101912):
        f.build_order(n, seed)
```

再单独开启一个 Python 进程重建 micro 顺序，避免两个模块重复设置 torch interop threads：

```python
import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path("experiments/training_data_structure_compare_v2/scripts").resolve()))
import d4_micro_fit as m
np.save(m.OUT / "derived/MICRO_SHARED_BATCH_ORDER.npy", m.build_order(4728))
```

上述调用只重建数据，不调用训练入口 `main()`，不重新训练或运行 Plant。

## 审计文件与执行状态

`DIRECTORY_INVENTORY_BEFORE.csv` 为两工程目录/扩展名占用汇总；`INVENTORY_BEFORE.json` 为盘点快照，完整遍历无读取错误；`PROTECTED_SOURCES_MODELS_CONFIGS_BEFORE.csv` 保存 5,594 个源码、模型、配置及 run_start 的 SHA-256 快照。两工程的 Git 数据均未列入清理范围。

DL1009 候选经过另一代理独立复核：全量路径和大小一致，跨 5 个实验抽查 10 份实际 MAT，均为稳定完整轨迹；与当前 TEST v9 来源清单及 recovery 明确输入路径交集为 0。`PREFLIGHT.json` 记录合并清单的校验结果。

用户已经明确确认清理这份具体清单。执行工具仍三次返回 `blocked by policy`，未给进一步原因，删除命令均未启动。因此截至此清单交付时，代理实际删除 0 个文件、释放 0 字节；所有候选仍存在。用户随后要求创建桌面入口供其亲自点击；代理只运行了无删除的检查模式，不再尝试执行删除。
