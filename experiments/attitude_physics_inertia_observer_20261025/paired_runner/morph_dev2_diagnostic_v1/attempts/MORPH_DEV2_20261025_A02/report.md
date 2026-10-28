# MORPH_DEV2_DIAGNOSTIC: STOPPED_ON_FAILURE
Runner calls: 2 / 4; confirmed runs: 2; transitions: 40000; unknown invocations: 0.
Performance changes are descriptive and do not gate the next preregistered scene.
DL1018_DEV_T2_C02_W15: Q 0.0054129689086669193 -> 0.0042704429641144031 (d -0.0011425259445525162), early d 4.993681044411849e-09, late d -0.0012130847704906233 m; SO3 0.013187128978901275 -> 0.0085213522905267583 (d -0.0046657766883745171), early d 1.5348575424413701e-08, late d -0.0049457134186785823 rad; candidate FAILED_ENGINEERING.
DL1018_DEV_T3_C10_W11: pair incomplete; baseline NOT_RUN, candidate NOT_RUN.
Failure: 输入参数的数目不足。  出错 run_morph_dev2_diagnostic>csv_metric (第 654 行) if index>0    ^^^^^ 出错 run_morph_dev2_diagnostic>write_results_csv (第 611 行)     values={csv_text(r.scene_id),csv_text(r.arm),csv_text(r.status),csv_metric(r,'wall_seconds')};                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 出错 run_morph_dev2_diagnostic (第 310 行) try,write_results_csv(fullfile(attemptDir,'results.csv'),results);     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
