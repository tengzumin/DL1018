# Position-applied low-pass candidate: HF6 paired screen

Six fixed DEV/VAL scenes; development screening only, not independent validation.

| Method | Q (m) | task SO(3) (rad) | inner SO(3) (rad) |
|---|---:|---:|---:|
| B | 0.0112657697 | 0.0576186242 | 0.0161929971 |
| C5 | 0.0105837878 | 0.0612040974 | 0.0164247501 |
| Parent_Cosine_GRU | 0.0101411273 | 0.0611989934 | 0.014410202 |
| Delayed_Start_Candidate | 0.0109986132 | 0.0602141073 | 0.0143223597 |
| Position_Applied_Lowpass_tau0p1 | 0.0121886936 | 0.0587722443 | 0.0143662234 |

Candidate minus each baseline (% of baseline mean; negative is lower error):

| Baseline | Q | task SO(3) | inner SO(3) |
|---|---:|---:|---:|
| B | +8.19% | +2.00% | -11.28% |
| C5 | +15.16% | -3.97% | -12.53% |
| Parent_Cosine_GRU | +20.19% | -3.97% | -0.31% |
| Delayed_Start_Candidate | +10.82% | -2.39% | +0.31% |

Candidate source generations:

- Pilot scene: generation 1, release `7aa3010ad8876cde8804c6632f82f5b1647fb7daec2a1bf15d676a39b35afd55`, source lock `3564cf7eee7d3f8abe99f4f3c2091ee3ab12f3fdd60e70ca2e6fc6a98de9a3d1`; old lock/manifest bytes were not archived.
- Remaining scenes: generation 2, release `9aae8f32a219dd290f041a78ea87d543fd74e19d654e404916ab686f86acc65c`, source lock `f6d8f3769a7c01cd74c62748759d06238a0c33a97604f46f1fb852b7ccc4914e`; 70 source files verified.

Per-scene results:

| Scene | Gen | Q (m) | task SO(3) (rad) | inner SO(3) (rad) | Safe |
|---|---:|---:|---:|---:|---|
| DL1018_VAL_T3_C01_W14 | 1 | 0.0111632651 | 0.0621343889 | 0.0164223938 | yes |
| DL1018_DEV_T1_C10_W09 | 2 | 0.0109749029 | 0.0429045444 | 0.0201410156 | yes |
| DL1018_DEV_T2_C09_W10 | 2 | 0.0142208203 | 0.0688706495 | 0.00979360465 | yes |
| DL1018_DEV_T3_C09_W09 | 2 | 0.0108186937 | 0.0601479393 | 0.00950948712 | yes |
| DL1018_VAL_T1_C07_W14 | 2 | 0.0131718042 | 0.0641377632 | 0.0225172171 | yes |
| DL1018_VAL_T2_C04_W14 | 2 | 0.0127826757 | 0.0544381807 | 0.00781362194 | yes |

The pilot generation-1 source-lock snapshot gap is retained in the audit record. HF6 is a fixed development screen; a winner still requires fresh holdout evidence.
