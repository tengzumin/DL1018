# Amendment 08 — same-task attitude architecture screen

Date: 2026-10-26 (Asia/Shanghai). This amendment records the user's request to compare alternatives after asking why the attitude candidate was fixed to a small TCN. The frozen v1 taskbook remains preserved; this amendment changes only the offline architecture-screen stage.

## 1. What the earlier five-model work covered

The repository has a five-family position-head comparison: MLP, KAN, TCN, GRU, and DSSM (experiments/teacher_reuse_model_screen_v1/reports/FINAL_REPORT_ZH.md). Its inputs, labels, controller interface, and outcome were for the position loop; attitude B-RBF output was left unchanged. In that screen, GRU14 was selected for the position DEV24 stage (position Q macro 0.015059659 m versus paired B 0.016958918 m, 12/24 scene wins). The early position screen ranked TCN14 below B (0.022572637 m versus 0.020356748 m). These are useful architecture priors, not evidence about replacing the attitude RBF. A separate five-variant MLP/KAN position study (experiments/training_data_structure_compare_v2/reports/FINAL_FINDINGS_ZH.md) also does not transfer its ranking to the current attitude target.

The attitude task had not run an apples-to-apples network-family screen. Its TCN was chosen as a small, causal, MATLAB-deployable sequence model for the RBF teacher's temporal behavior. This was an engineering choice, not a demonstrated architecture winner or a training-speed result. The earlier request allowed omitting KAN, so this screen omits it.

## 2. Interrupted formal TCN run

- Progress stopped at 30,000/60,000 optimizer steps; selected best is step 28,000 with normalized VAL48 scene-macro teacher-action RMSE 0.49274985958882905.
- Read-only independent CPU recomputation passed: 0.4927498612711974, absolute difference 1.6823683557376512e-9; all 48 VAL scenes and 1,999 events per scene were used. TEST and Plant were not read.
- PID 20056 (formal v2), PID 23108 (superseded v1 diagnostic), and PID 22544 (gate monitor) are absent. The progress file remains stale at RUNNING. No final checkpoint, training_config, or optimizer/RNG resume state exists. The trainer refuses to overwrite the existing output directory, so the 30k run is preserved as an incomplete diagnostic and will not be called a completed formal fit.
- A System event records NVIDIA driver Event 153 at 12:12:47 for \Device\Video3 / GPUID 100; the gate monitor last wrote status at 12:12:33. This timing is correlated with the missing processes, but does not prove causation. The Windows uptime/boot record did not reset. The Windows Error Reporting BlueScreen entry points to a minidump last modified on 2026-10-25 22:57:53, so that entry is not treated as proof of a new crash at 12:12. No automatic restart is authorized by this amendment.

## 3. Frozen offline screen

Run four fresh architecture candidates from the same initialization seed and deterministic sampled minibatch schedule:

1. TCN: existing 13-channel, 15-event causal TCN (32 channels; kernel 3; dilations 1/2/4).
2. GRU: 13-channel, 15-event input; hidden width 32.
3. DSSM: 13-channel, 15-event input; 32 diagonal state channels.
4. MLP: flatten the same 15 x 13 causal window, then 64- and 32-unit hidden layers.

All four use only the frozen 13 runtime features and the existing logged B RBF output label. They share the frozen TRAIN 768 / VAL 48 split, TRAIN-only normalization, target RMS, seed 2026102001, 2,000 optimizer steps, batch 512, Adam (1e-3, weight decay 1e-5), and SmoothL1 loss. Each receives the same sequence of TRAIN minibatch scene/time indices. The full VAL48 set is evaluated once at step 2,000 using a batched evaluator; record training and validation wall time separately. The partial step-28k TCN is reported only as an unequal-budget diagnostic, never as an architecture-screen result.

The score is a shortlist metric only: normalized scene-macro teacher-action RMSE, with physical-axis scene-macro RMSE also reported. It is not closed-loop evidence and does not select a final deployment model by itself. The primary model must review the complete metrics and implementation before freezing one candidate for full training. Any selected candidate still requires an independently audited full checkpoint, Python/MATLAB numerical parity, the frozen no-Plant release gate, pilot safety gate, DEV72, and the sealed one-time TEST48 gates. Do not read TEST or run Plant during this screen.

## 4. Isolation and limits

- New script, screen release, reports, and checkpoints live only under experiments/dl_attitude_replacement_20261026/architecture_screen_v1/.
- Do not change, overwrite, resume, or delete the interrupted v2 TCN run or any historical raw/MAT/cache/model.
- Run at most one GPU training process. Screen candidates sequentially. If a new GPU-driver error occurs, stop launching further candidates and record the evidence.
- Runtime candidates still exclude Jhat/Jdot, Plant truth, RBF hidden state, observer, and physical feedforward. Fixed J0 remains only for the already-frozen torque mapping.
- No architecture-screen score may be described as closed-loop or paper-level performance.
