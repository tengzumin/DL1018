# 独立中心化差值审核记录

- 源文件：`reports/attitude_cm18_c524_coverage33_20261025/fit_generalization_v1/primary_scene_metrics.csv`
- 源 CSV SHA-256：`925ca8314647de201b101fac265309f269ce420918d583818223c8700729125d`
- 源数据行数：48；源 split 计数：TRAIN=24、TRAIN_EXTRA=9、HOLDOUT=15。
- 分析分组：TRAIN33=TRAIN+TRAIN_EXTRA 共33场；HOLDOUT15=15场。
- 输出指标：candidate 与 zero_output 各22项（逐轴及向量 physical RMSE/bias、normalized RMSE/bias）；每场值减所属分组的场景等权宏均值。
- 中心化差值 CSV 数据行数：2112（48场 × 2方法 × 22指标）。
- 中心化差值 CSV SHA-256：`1e9a12b6a0fad3266eb99279e742ea4b196db0982da8201d85dc8bb58c605789`
- 处理范围：仅读取上述 primary_scene_metrics.csv；未读取缓存、raw MAT 或 TEST，也未执行 fit/generalization 脚本、模型推理、MATLAB 或 Plant。
- 与源 CSV 既有 `candidate_normalized_vector_nrmse_centered_from_split_macro` 的交叉核对最大绝对差：`0`。
- 与源 CSV 既有 `zero_output_normalized_vector_nrmse_centered_from_split_macro` 的交叉核对最大绝对差：`0`。
