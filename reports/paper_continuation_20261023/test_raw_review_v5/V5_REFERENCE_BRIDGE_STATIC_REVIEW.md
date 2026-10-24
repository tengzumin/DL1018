# v5 reader 引用桥接静态复核

保留已交 v4 reader（SHA `5d394bf133d9700dd0852aa43d1da780195557efe4e3a8e3aeece67fa2137fe5`）及全部产物。v5 reader SHA `1c7380abd2b1f29e0f7045017abaeef87f54d751ad74a710bfbdbdac504730ff`，完整 v4→v5 diff 为 `V5_REFERENCE_BRIDGE_DIFF.patch`（SHA `80bf94ab82c62bb7ab75334c26527d3617b904af94d1fb5b98d59e645f85ad06`）。

唯一代码修复：D/K 的 source_refs 中旧、新 cfg_opts_snapshot 引用各必须唯一，role/path/SHA 各自精确匹配已验证的 method snapshot。仅在临时列表中用新 metadata 引用替换这一条旧引用，再调用原封不动的 assert_only_filter_helper_added；没有忽略 .mat、角色或其它 source。真实 manifest 与冻结 cfgpack 均未修改。另仅更新 CLI 输出目录说明文字为 v5，实际目录仍由 __file__ 推导。

实际轻量元数据检查 PASS：validate_method_lineage、verify_v4_code_and_manifest、verify_v4_run_release、verify_v3_failure_history、verify_v4_failure_and_path_diagnostic_history、verify_v5_v8_history、verify_stage_preconditions。结果 `V5_METADATA_ONLY_CHECK_v1.json`（SHA `5a3a8466a7f9ebf93b2af37fd2328e82219521065be648bead50dea9afe4ae3e`）。BLAS/OMP/MKL/NUMEXPR 限为 1；未运行 reviewer CLI/run_review；h5py.File 与 np.load 被禁止调用，TEST runs/input MAT 文件打开被 I/O guard 禁止，实际违规尝试为 0。只读 JSON/源码与其 SHA（包含授权的历史 DEV raw 字节 SHA）；未解码任何 MAT，未读 TEST raw 或成绩。

AST/compile 通过；除 validate_method_lineage 与 CLI 文件夹文案外，函数 AST 相对 v4 不变。评分/事件/native/数字闭合代码块与 v4 逐字相同，SHA `1c17a6ad8e583d27cc16acf2ccbac0db44a6daf590c137af02f8b77475c88906`。所有 tolerance、模型、公式和统计不变。待根审查且全部六方法自然 OS0 后另放行真实 raw CLI。
