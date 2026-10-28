# FULL72 GRU score：B/C5 原始来源与完整性只读审计

## 结论

- 逐场通过：72/72；失败：0/72。已对引用的 B/C5 DEV/VAL raw 与 status 文件重算 SHA-256，并与 GRU score 清单、B manifest、C5 parent audit 逐场交叉核对。
- B：72/72 raw SHA、status SHA 匹配；72/72 均为 `RUN_COMPLETE_RAW_PENDING_AUDIT`、`STABLE`；既有 B parent review 通过 72/72 场各 33 个数值数组精确等同历史 B。B 可作为有条件的数值比较基线。
- C5_M110：72/72 raw SHA、status SHA 匹配；60 条新 raw 的事件复核通过，12 条复用 screen 场的 parent audit 引用也通过。GRU score 写的“60 pending”已过时：对应 60 场在现有 C5 parent review 中均已通过。
- 论文证据仍需限定：GRU score 的训练与评分场景重叠 72/72，属于 in-sample DEV/VAL screen；B 的历史 runtime identity 仍未闭合。且 score 自己的 frozen DEV72 总门为 FAIL（Q 对 B 68/72 胜，但 task SO(3) 对 B 仅 41/72 胜）。不能把当前 score 写成独立验证或泛化结论。

## 逐场检查

所有 72 个场景均通过 B 与 C5 的逐场 hash/manifest/audit 对齐。明细、每场 raw/status 当前 SHA 与原始 pending 标记见 `SCENE_SOURCE_AUDIT.csv`。

## 现存准确缺口

1. B parent review 明确保留一个复用的 B1 场景及历史 runtime identity 缺口；exact 33-array reproduction 证明数值可复现，不证明历史运行当时的完整源码身份。
2. `FULL72_PAIRED_SCORE_v1.json/.md` 仍称 C5 有 60 场待 parent audit，但同一 C5 M110 source lock 下的 `C5_DEV72_RAW_PARENT_REVIEW_v3.json` 已审核 60 场新 raw，并引用既有 12 场 screen audit。score 报告未绑定该审核，建议另发新版 score/补充索引，不改旧产物。
3. 本 score 是 72/72 场训练内评估，独立验证与泛化证据缺失。
4. C5/B 旧 parent review 与 GRU paired scorer 使用不同 scorer（C5 parent `metric_scorer_sha256=c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1`；GRU scorer `6baf689802f4d73ead813449e52a8fe85cb0be92c3185850c93646da2d54dd16`）。论文表格需以本 score 的固定 scorer 与输出为准，或另行一致重算。

## 证据文件

- GRU score：`experiments\dl_attitude_replacement_20261026\gru_stream_cosine_tracking_head_full72_v1\audits\FULL72_PAIRED_SCORE_v1.json` (SHA-256 `d197cd0e7fc580b6b575ec193571dc595a4527f3bbba2c0e7e0b48daf021b0ff`).
- B parent review：`reports\paper_continuation_20261023\baseline_b_dev72_parent_review\PARENT_B72_RAW_REVIEW.json` (SHA-256 `d74725ef3b1e4957b7c813486a2ae95cc1f1ec13e82370545f7ec3c54d5b029e`).
- C5 M110 parent review：`reports\paper_continuation_20261023\c5_dev72_parent_review\C5_DEV72_RAW_PARENT_REVIEW_v3.json` (SHA-256 `bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab`).
- B traceable raw manifest：`reports\paper_continuation_20261023\baseline_b_dev72_parent_review\PARENT_TRACEABLE_B72_MANIFEST.json`.
- C5 input lock / batch status：`experiments\position_axis_coordinate_c5_dev72_20261023\C5_DEV72_INPUT_LOCK_v3.json` / `experiments\position_axis_coordinate_c5_dev72_20261023\C5_DEV72_BATCH_STATUS_v3.json`.

审计仅访问上述 DEV/VAL 相关 raw/status/manifests/locks 与既有报告；未访问 TEST、未启动 MATLAB/Plant、未重跑 B/C5，也未修改任何旧结果或锁。
