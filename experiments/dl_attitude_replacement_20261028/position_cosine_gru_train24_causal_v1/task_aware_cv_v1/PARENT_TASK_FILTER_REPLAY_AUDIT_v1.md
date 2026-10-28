# Cosine-GRU parent task/filter replay audit

- Matching TRAIN_C5_24 scenes checked: 24; data SHA `15d689f08fd6d8a53a64c59dbdf62b33f9b8e8a12ce083fb12834cd106df2eeb`.
- Reconstructed outer target max error: 1.388e-16 rad.
- Python 1 ms filter replay max Euler error: 8.049e-16 rad.
- Requested/applied filter acceleration max errors: 1.030e-13 / 1.030e-13 rad/s².
- 100 Hz event action hold max error: 0.000e+00 m/s².
- The runtime maps roll/pitch with current yaw, replaces target yaw with reference yaw, and logs the pre-update filter state. Limits are read from the hash-locked parent configuration: Inf/Inf/6 rad/s².
- All four manifest folds are whole-scene partitions with 6/8/4/6 holdout scenes. No wind measurements, VAL/TEST raws, new Plant calls, or inertia reconstruction were used.
