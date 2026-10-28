# Full24 DC-penalty deployment model reproducibility

This is one deterministic full24 deployment fit using the predeclared four-fold DC-penalty recipe. It is not a validation or OOF result. Teacher deltas are training supervision only; inference does not load teacher labels.

Training: GRU(14,32) → Linear(32,3), Adam 1e-3, 300 steps, seed 20261028. Objective weights are 0.5 teacher normalized MSE, 0.5 position normalized MSE, and 0.5 per-scene DC action-mean penalty. The full24 training-only DC scale is 0.1×the full24 teacher-delta RMS.
X14 normalizer and all three objective scales use only the 24 authorized TRAIN_C5_24 scenes. No VAL/TEST data were read; no Plant call or inertia reconstruction was made. No validation score was generated.

## Artifacts

- PyTorch checkpoint: `DEPLOYMENT_MODEL_v1.pt` — SHA-256 `4da29824058e47217876f26e68889000b32a8a9efafc3f4f2f281c66b39aaa79`
- NumPy weight export: `DEPLOYMENT_WEIGHTS_v1.npz` — SHA-256 `b250b8122c8ca23f7740a1bb2039f7afb4784b52f92c9dd2ffb9a76ead2ae756`
- MATLAB weights: `DEPLOYMENT_MODEL_v1.mat` — SHA-256 `a59ee6cc35db749d5b67ffb0f87daef0431436e3eb9fd9e3af2e456e802e8870`
- Model manifest: `MODEL_MANIFEST_v1.json` — SHA-256 `84292e913f7cf97b564e6ff84e30de9e809442f8fce0a181da9572fa6016b984`
- Training config: `PREDECLARED_FULL24_CONFIG_v1.json` — SHA-256 `8801805e327761e663d1e0bf4487576ba82097c1fd45e216518d83e3f0520380`
- Training script: `train_full24_dc_penalty_deployment_v1.py` — SHA-256 `e4a4c5562de4ee9e6d4d2a2c717d1f3787269ee46bf7bd676e3eda3014942fb0`
- Training source lock: `FULL24_SOURCE_LOCK_v1.json` — SHA-256 `6b6db29922bd84a2f0cfc89cba3a2c0e991ade2ceee18041b557b4ad16f2258b`
- Training result/log: `FULL24_TRAINING_RESULT_v1.json` — SHA-256 `c8b7c54199074e52cf6dd7dc3b68f9531fef21f409bc627c6d9180e76a5061b5`

## Runtime contract

At each 100-Hz event, input the causal X14 vector in logged order, carry the 32-value hidden state within a scene (reset it to zero at scene start; advance during warm-up), and pass the current C5 acceleration action, event time, and readiness flag. Normalize using the MAT/checkpoint mean and standard deviation; apply PyTorch GRU gate order reset/update/new; clip delta to ±0.5 m/s²; apply the 1.8-s ramp and total action clip ±3 m/s². Teacher labels are absent from this interface.
