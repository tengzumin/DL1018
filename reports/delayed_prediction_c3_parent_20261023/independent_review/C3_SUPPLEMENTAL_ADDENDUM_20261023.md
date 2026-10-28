# C3补充审核 addendum

本 addendum 补记两项已更新证据；原 `C3_SUPPLEMENTAL_AND_DEV72_PEER_REVIEW_ZH.md` 保持不变。

配对重采样现可复现。`reproduce_paired_resampling.py`（SHA-256 `b9bbfdc3aa5c3a90b70f742c71a507266bc0d12e170de26414577eb4e41c6165`）从12行 `PARENT_ALL12_PAIRED.csv`（SHA-256 `bce4a8938416702d993bdcfeb5cd468454aeeb3e380e51bd1ec0a981c0735c20`）构造逐场配对改善量，以固定seed `2026102001` 有放回抽取12个场景、重复10,000次并计算均值的2.5/97.5百分位；分别核对B、C2的均值、区间和1e-12m/1μm/10μm胜幅计数。`PAIRED_RESAMPLING_REPRODUCTION_CHECK.json`（SHA-256 `5ce7d9e2550c3066a23376c6152ed1cc8cb2e5ce08fde284d9fca386c89a4519`）记录`PASS_REPRODUCED_EXISTING_PAIRED_RESAMPLING`，对原结果JSON的均值与区间最大绝对差为0。该检查支持计算可复现性，不改变区间的事后探索属性、目的性12场范围和不外推限制。

DEV72任务书范围文字已消除歧义。当前`NEXT_DEV72_TASKBOOK_DRAFT_ZH.md` SHA-256 `8ca9e44022fdc5c0f6e7882ed94c4132d7979a6f453e721f5aa94e698ea20a1b`明确72指PAIR14中的72个唯一场景（DEV24+VAL48），而`POSITION_DEV.csv`的72行是24个唯一场景的多方法记录；12个C3筛查场景属于VAL子集，不构成独立确认集。最多60次新运行、后续输入锁要求以及旧B运行源码身份缺口均仍保留。此项修订没有把任务书草案转为执行授权。
