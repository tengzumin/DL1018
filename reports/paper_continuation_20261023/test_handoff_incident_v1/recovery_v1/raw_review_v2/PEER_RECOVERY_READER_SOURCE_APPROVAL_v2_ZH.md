# Recovery288 reader v2 状态字段独立复核

复核对象：raw_review_v2/audit_test48_raw_recovery288_v2.py，SHA-256 1a92b4dcdc33f1d74cdb98516e2c7e06a67072ba5694a945c01be7aa2bf249d4。冻结 v9 writer 为 experiments/c5_test48_v9/test48_entry_v4.m，SHA-256 b9906578088319c8108a360c140c163b8af9080f311613489a20a48a8f609fd1。

结论：前一份状态元数据审查指出的 run_status_path 误读已修复，reader v2 对应实际 writer schema；未发现该路径修复造成的其他状态字段错配。

冻结 writer 在 run_status_v4.json 状态对象中写四个 artifact 路径：raw_path、run_start_path、attempt_started_marker_path、first_plant_step_marker_path。它不写状态文件自己的 run_status_path 或 run_status_sha256；这两个字段由 batch record 持有。此前读取的四方法192份状态元数据字段集合完全一致，并都符合此分工。

v2 在 verify_v4_method_block 中将检查拆成两个用途明确的 helper：validate_v4_record_path_bindings 对 batch record 检查全部五个路径，随后仍用记录中的路径和 SHA 验证五个文件；validate_v4_status_path_bindings 只检查 status 对象实际拥有的四个 artifact 路径。状态 SHA 比对也仅覆盖 writer 写入状态对象的四项；run_status_sha256 仍由 batch record 核验。synthetic_v4_status_path_check 构造不含自路径的状态对象，检查四个错误状态路径均拒绝，并检查 batch record 的错误 run_status_path 会拒绝。对应负例逻辑已静态核对；未执行自检，根将另行运行 guarded self-check。

此前其余状态消费者已核对：场景32和DSSM首31读取 writer 已定义的 status 字段；DSSM tail 使用独立 RECOVERY208_DSSM_TAIL_RUN_STATUS_V1。未发现第二个缺失字段引用。

本次仅核对源码与既有192份状态元数据；未读取或打开 MAT、评分文件或其他 raw，未运行 reader CLI、评分器或 MATLAB，也未修改源码。
