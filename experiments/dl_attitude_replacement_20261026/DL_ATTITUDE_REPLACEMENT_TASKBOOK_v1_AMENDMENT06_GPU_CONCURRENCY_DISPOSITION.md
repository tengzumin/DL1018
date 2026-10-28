# Taskbook Amendment 06 — disposition of the concurrent-training deviation

Date: 2026-10-26 (Asia/Shanghai).
Status: frozen process-deviation disposition. This amendment does not authorize Plant calls, change the model/data/optimizer, or authorize another training job.

## Deviation

The corrected teacher-action training process (PID 20056, `train_tcn_teacher_v2.py`) started while the earlier residual-target diagnostic process (PID 23108, `train_tcn_v1.py`) was still using the same GPU. This violated Amendment 02's required single-GPU sequence. The deviation is real and is not erased by this disposition.

At the review snapshot (2026-10-26 08:30 Asia/Shanghai), both processes were responsive. The formal v2 run was at 16,000/60,000 steps, best step 15,000; the v1 diagnostic was at 26,000/60,000. No TCN Plant run marker or pilot release existed, and TEST remained unread.

## Evidence relevant to numerical integrity

- Both scripts set Python, NumPy, and Torch seeds to `2026102001`; set `CUBLAS_WORKSPACE_CONFIG=:4096:8`; enable `torch.use_deterministic_algorithms(True)` and deterministic cuDNN; disable cuDNN benchmarking and TF32.
- The runs use distinct frozen dataset/release identities and distinct output directories. v1 trains the superseded plant-residual target; v2 trains the frozen B-RBF teacher-action target. They do not share model state, optimizer state, RNG state, or output files.
- The v2 checkpoint at best step 15,000 independently reproduced its VAL48 metric on CPU within `8.2e-10`; checkpoint and audit report are archived. This validates the checkpoint against its recorded validation metric, but it is not a second training run and does not establish cross-run reproducibility.
- No OOM, non-finite loss, determinism exception, or checkpoint/hash mismatch has been observed in the formal v2 progress to date. GPU contention affects wall time; the available evidence does not show altered arithmetic. It cannot prove the counterfactual single-process weights would be byte-identical.

Dataset identities at review:

| Run | Manifest SHA-256 | NPZ SHA-256 | Target | Output |
|---|---|---|---|---|
| v1 diagnostic | `A16C18214F552B8286DCFA09D5858B74E0D26B6BF777ADE6F968D4BE8F249ED1` | `07622EB59821404BF57ED943936A6A805C98A3B4B29F832F388AE2F5F89478CD` | superseded physical-residual label | `training_v1_retry01` |
| v2 formal | `4A98548618D799B01B96809EA274B6A4FFCF5EDED0E24F2FDE5401619FFC442D` | `33E35C5B1AEB474EE038E0E86E6DDB841C71D25A3AFC59ACE4FD91522A1A6171` | logged B `rbf_output_raw` teacher action | `training_v2_teacher_distill` |

## Decision

1. Do not interrupt either live process. The invalid-target v1 run remains diagnostic-only and is excluded from candidate selection, Plant evaluation, and paper performance tables.
2. Retain v2 as the single formal candidate run; do not start a second training solely to recreate the intended GPU schedule. The evidence shows isolated deterministic workloads and no observed numerical failure, while the frozen plan allows only one formal training. This is a documented engineering judgment, not proof of independent training repeatability.
3. Do not launch any additional GPU job while either process remains active. Continue the existing frozen v2 run, audit every new best checkpoint on CPU, then complete the frozen Python/MATLAB parity gate before any Plant call.
4. Disclose this scheduling deviation in the final experiment ledger and manuscript limitations. Do not claim cross-run or cross-seed reproducibility. If the final checkpoint fails the independent validation audit, Python/MATLAB parity, or any frozen release check, withhold the candidate and investigate; this amendment does not waive any gate.

