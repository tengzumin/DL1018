# 历史 MAT 清理报告

清理时间：2026-10-20T12:13:21.698251+00:00
扫描到 MAT：6362 个；逐文件保留：5348 个；删除计划：1009 个；实际删除：1009 个；跳过：5 个。
保留 MAT 逻辑大小：102.124 GiB。
删除计划逻辑大小：22.431 GiB；实际删除逻辑大小：22.431 GiB。
C: 清理前可用空间：181.252 GiB；清理后：203.685 GiB；卷可用空间实增：22.433 GiB。
逻辑文件大小与卷可用空间实增分别统计；两者可能因压缩、硬链接、卷记账和并行系统活动不同。

## 保留范围

教师 TRAIN/VAL 原始 MAT、已有 Student TRAIN/VAL 清单中的原始/起始/缓存 MAT、全部 DEV 原始记录、正式模型导出、有效配置和 MATLAB fixtures 均保留。
指定 GRU14/DSSM14 原包 DEV24 与四个锁定 Student 候选 DEV24 原始记录均保留。
历史闭环 MAT 仅在同场 `metrics.json` 明确记录 STABLE/COMPLETE/PASS，且路径逐项通过项目边界、重解析点与 KEEP/DELETE 不相交检查后删除；报告、CSV、代码和非 MAT 文件均未删除。

## 尚未删除

跳过 5 项。每项原因见 `SKIPPED_MAT.csv`；包括来源不明、结果非稳定、无逐场完整指标、文件占用或重解析点。

## 保留文件索引

逐文件保留依据见 `KEEP_MAT_MANIFEST.csv`。

## 删除文件索引

逐文件计划与成功记录见 `DELETE_MAT_PLAN.csv` 和 `DELETED_MAT.csv`。
