# CM18 SCREEN4 cache reader 核验

仅使用 peer 已交付的 SCREEN4 manifest 与四个 `.mat` cache 做只读加载核验；没有访问 raw/H5、ALL816 cache、TEST，也没有训练或运行 optimizer。

Manifest `reports/attitude_cm18_a1_20261024/data_preparation_v1/events_screen4_v1/DATASET_MANIFEST_v1.json` SHA256 为 `b36a9027202a15408d69676c5e16f7993652c4c7a82c6a8695a64eb77961ef7c`，记录 4 场全部 `qualified=true/status=PASS`、failed 0；manifest 所列 4 个 cache 的实际 size/SHA 均匹配。

四个 MAT 的实际 SciPy 字段与形状/类型相同：`X18` float64 `(1999,18)`；`target_raw` float64 `(1999,3)`；`event_time_s` float64 `(1999,1)`；`phase_code` uint8 `(1999,1)`；`plant_index` uint16 `(1999,1)`；`scene_id` 和 `split` 为 MATLAB char。X18、target 和 event time 全部有限。时间为 0.01 至 19.99 s，plant index 为 `11,21,...,19991`；phase code取值范围检查为0..5。每行对应同一事件。SciPy `loadmat(..., squeeze_me=False, struct_as_record=False)` 读得 `input_identity` 是 1×1 struct，字段为 `input_manifest_sha256,event_h5_path,event_h5_sha256,event_h5_size_bytes,raw_run_path,raw_run_sha256,raw_run_size_bytes,run_start_path,run_start_sha256,run_start_size_bytes`。`export_meta` 是 1×1 struct，字段为 `schema,scene_id,split,event_count,plant_index_matlab_1based,max_abs_label_delta_vs_h5_rad_s2,max_abs_label_delta_by_axis_rad_s2,axis_rms_label_rad_s2,phase_summary,requested_torque_vs_nominal_minus_applied_max_abs_Nm,true_dynamics_equation_residual_max_abs_Nm,physical_feature_crosscheck,tolerances,failure_reasons,qualified,status`。

| 场景 | split | bytes | cache SHA256 |
|---|---|---:|---|
| DL1018_TRAIN_T1_C00_W00 | TRAIN | 185971 | `bf8a3867519a0ebb475fc1075b93f2a50e878cc37a1774e44de5ab9c0875708c` |
| DL1018_TRAIN_T1_C01_W00 | TRAIN | 198095 | `6ea8ad64bba6a86dbd81d41d1625db4909119fcf152953a883643d0122ffb9e8` |
| DL1018_VAL_T1_C00_W07 | VAL | 181468 | `d76b23f7268bde4e259dcf06d67c8b67fd2a4312862e2f9239567e212342b5ab` |
| DL1018_VAL_T1_C01_W08 | VAL | 200602 | `f0092fb70c8d64f05d8298845e96beeef6e2c76445cb0fbdb98bafb66c432d1e` |

reader 源码 `experiments/attitude_cm18_a1_20261024/cache_reader_cm18_v1.py` SHA256 `a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47`。它要求调用方提供 repo root、manifest相对路径和预期manifest SHA，只接受 TRAIN/VAL，按 manifest 核验 cache 路径、bytes、SHA、变量 shape/dtype、结构身份、有限值、事件索引和时间对齐；返回每场未缩放 `X18/target_raw` 数组，不拼接、不归一化。

实际用此 reader 对 SCREEN4 的 TRAIN、VAL 各做一次加载核验，均通过：每 split 2 场、3998 个事件、`training_or_optimizer_calls=0`。命令使用 `MKL_THREADING_LAYER=SEQUENTIAL`；Torch parity另由 root 运行通过。该核验只证明4个SCREEN4缓存可按协议读取，不替代ALL816清单检查或训练协议审核。
