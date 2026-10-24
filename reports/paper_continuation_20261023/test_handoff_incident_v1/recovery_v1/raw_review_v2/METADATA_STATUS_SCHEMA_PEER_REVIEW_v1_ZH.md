# v9 run_status_v4 元数据字段独立复核

## 结论

冻结 v9 writer 的每份 run_status_v4.json 都没有 run_status_path 或 run_status_sha256 自字段；这两个身份字段由批次记录保存。reader v1 以及当前 raw_review_v2 未交付副本，在 verify_v4_method_block 的路径循环中把 run_status_path 也当作状态 JSON 自字段读取，因此会拒绝有效状态文件。这是本次发现的唯一状态字段路径误读。

## writer 与192份状态元数据

冻结 writer：experiments/c5_test48_v9/test48_entry_v4.m，SHA-256 b9906578088319c8108a360c140c163b8af9080f311613489a20a48a8f609fd1。RUN_STATUS struct 在第702行定义并在第738行更新；第745–748行的批次 rec 单独写入 run_status_path 和 run_status_sha256。状态对象本身包含 raw_path、run_start_path、attempt_started_marker_path、first_plant_step_marker_path 及对应已有身份字段，但不含自身路径或自身摘要。

只读取了四个正式方法的 run_status_v4.json 元数据，未打开其引用文件：KAN、C5M110、C5FREEZE、C5NOPRED 各48份，共192份。每方法48个唯一场景和完整batch_index 1–48；四方法场景集合一致。每个方法字段集合一致，全部为 TEST48V4_RUN_STATUS_V1 / RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT，plant_calls=1、training_steps=0、optimizer_steps=0、TEST_accessed=true、log_status=STABLE，transition计数为20,000且state样本数为20,001。192份均不存在 run_status_path 和 run_status_sha256 字段。

实际状态字段共28项：schema、status、method_id、alias、scene_id、batch_index、TEST_accessed、plant_calls、training_steps、optimizer_steps、raw_path、run_start_path、attempt_started_marker_path、first_plant_step_marker_path、started_utc、completed_utc、method_source_manifest_sha256、method_cfg_opts_snapshot_sha256、parent_release_sha256、input_index_sha256、last_transition、transition_count、state_sample_count、log_status、raw_sha256、run_start_sha256、attempt_started_marker_sha256、first_plant_step_marker_sha256。

## reader消费者核对

当前 raw_review_v2/audit_test48_raw_recovery288_v2.py 的SHA仍为 a709201623d9e9f0e4b312946a1db35021bd5aa379c9f7ca04af3147e4be79d0，与 v1 完全相同；该文件是作者尚未交付的复制稿，未运行也不视为修复版。

在 verify_v4_method_block 第1501–1509行，reader先从batch row验证五条路径及摘要，包含 run_status_path/run_status_sha256；第1511–1520行再验证 status 对象的状态、方法、场景、计数与完成字段。问题在第1523–1524行：它用全部五个 expected_paths 键索引 status，因而要求不存在的 status.run_status_path。应只对状态对象实际拥有的四个路径字段做比较；批次记录已负责核验状态文件自身的路径和摘要。

其余当前 status 消费者使用字段与各自 writer schema 相符：原始 DSSM status 检查 writer 已写出的 raw/run_start/first-Plant 路径及运行状态字段；首31记录读取已定义的状态、计数和时间序列字段；DSSM tail 使用独立的 RECOVERY208_DSSM_TAIL_RUN_STATUS_V1 schema。没有发现第二个同类缺字段引用。

本审查仅读取 writer/reader 源码、scope/release JSON 和192份 run_status_v4.json 元数据；未打开 MAT、评分文件或其他 raw，未运行评分器、reader CLI 或 MATLAB，也未修改源码。
