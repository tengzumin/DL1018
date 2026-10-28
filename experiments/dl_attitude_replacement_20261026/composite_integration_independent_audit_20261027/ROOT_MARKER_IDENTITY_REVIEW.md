# v2 首场 GATE:IdentityLock 根因复核

复核日期：2026-10-27。只读复核 v2 outer driver、DEV72 闭环入口和 identity helper 三个源码文件；未运行 MATLAB、Plant 或任意 driver，也未改 v2/v3 源码。

## 结论

确认 root 提供的因果判断：v2 driver 在建立 `gate_identity_lock` 时尚未给 `opts` 添加 `composite_attempt_marker`；随后把 marker 写入 `prepared.opts` 并将完整 opts 交给 DEV72。DEV 的 exact-options 检查会排除 marker，但其 identity 重算仍把完整 opts 传给 helper。helper 只从待哈希选项中删除 `gate_identity_lock`，所以 marker 路径进入 `geometry.options_sha256`，与 driver 预先锁定的 hash 不同，触发 `GATE:IdentityLock`。

按收到的 T1 `run_failure` 摘要，失败发生在该 identity gate，尚未发生 Plant 积分。源码顺序与此故障位置相符。

## 源码证据

- `mlp15_composite_dev_v2/run_composite_dev_attempt.m:44-50`：driver 用未含 marker 的 `prepared.opts` 计算 identity，并保存 `gate_identity_lock`。
- `mlp15_composite_dev_v2/run_composite_dev_attempt.m:107-111`：写入 run-start 后才添加 `prepared.opts.composite_attempt_marker`，继而调用 DEV loop。
- `mlp15_composite_dev_v2/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m:116-124`：exact-options 检查明确将 `composite_attempt_marker` 列入排除项；但 identity 重算将原始 `opts` 直接传给 helper，随后比较锁定与重算 identity 并报 `GATE:IdentityLock`。
- `mlp15_composite_dev_v2/candidate_runner_work/matlab/runtime/gate_holdout_identity_hashes.m:24-26,35`：helper 只从 `effectiveOptions` 删除 `gate_identity_lock`，并将剩余 options 哈希为 `geometry.options_sha256`。因此 marker 路径会改变该 hash。

## 最小修复建议

仅在 DEV identity 重算前复制用于哈希的 options 并删除运行期 marker：

```matlab
identityOpts=rmfield(opts,'composite_attempt_marker'); % 仅用于 identity hash
    gateIdentityHashes=gate_holdout_identity_hashes( ...
     cfg,opts.stage1_position_runtime.model,identityOpts);
```

保留 `opts` 本身、原 `GATE:IdentityLock` 断言和所有控制字段；marker 仍留在原 opts 中供 marker/attempt 流程使用。不要放宽 identity 相等断言，也不要在 helper 中泛化剔除其他字段。

