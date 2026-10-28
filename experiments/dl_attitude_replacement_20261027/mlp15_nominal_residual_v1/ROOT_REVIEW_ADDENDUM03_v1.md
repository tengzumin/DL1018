# Root review: MLP15 nominal-residual repaired training freeze

Date: 2026-10-27 (Asia/Shanghai)

## Finding and repair

The initial launch failed at the first log interval lookup with `KeyError: 'log_every_steps'` after one optimizer update. It created no model checkpoint, weights, or completed fit receipt. The failed run directory and original logs remain intact; `training_log.jsonl` is zero bytes. This is an implementation/config interface error, not a model performance result.

The repaired trainer is a new file. Code diff against the first trainer is limited to reading a fixed 1000-step logging interval and rejecting non-positive values. The frozen retry config adds `log_every_steps=1000`, points to a distinct `_REPAIR01` output directory, and binds the repaired trainer and incident record. The model, fit arrays, feature definition, seed, optimizer, loss, normalization, CUDA/determinism, batch size, and 60,000-step schedule are unchanged.

## Independent identity and preflight review

- Addendum03 SHA-256: `9f751f17dbf61327b236cff6c75cdac34b8ceb5d25a9e6f631601150e15e66a4`
- Repaired trainer SHA-256: `b697b3afbb56725ca1c12c9fb56734fc73bc0a7430c7e4ffcad5634498f1b848`
- Retry config SHA-256: `e120600428ced22c416a8744861a1f6b6e1f6ac64430f61223e614af67021664`
- Retry freeze manifest SHA-256: `6d5bee445381778e7cc4f181345420826f69d8c724a56995f2115274723ff454`
- TRAIN NPZ SHA-256: `242c86426f48cfe6d37afc25994d67a6c8ff3f0ea25246d50765a831e4458566`
- Original stderr SHA-256: `8c9ae577fd8fadacc8f875b75e53e76d25fba8192a23c3dac3878f88a8c791f3`; original console SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- The retry trainer's own read-only preflight was independently rerun and returned `PREFLIGHT_PASS`: 24 TRAIN scenes, 47,976 rows, fit members `x_train.npy` and `y_train.npy`, all locked input hashes matched, CUDA deterministic probe passed; output did not exist. VAL was not loaded, TEST was not read, Plant was not called.

## Decision

Approve exactly one complete 60,000-update retry under `TASKBOOK_ROOT_v1_ADDENDUM03.md`, using the frozen v1r1 trainer/config/manifest. Preserve the failed first-run folder. No further training retry, closed-loop run, TEST access, or Plant call is approved by this review. After the retry, root review is required before one-shot C5_VAL48 offline diagnostic and Python/MATLAB no-Plant parity deliverables are accepted; closed-loop authorization remains a separate decision.
