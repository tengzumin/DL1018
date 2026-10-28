# Erratum: earlier TRAIN-prefixed raws are the wrong cohort

The earlier files in this directory analyzed `data/raw/train/DL1018_TRAIN_T1_C10_W09` and `DL1018_TRAIN_T3_C09_W09`. Those are legacy TRAIN-prefixed records, not the current physical `TRAIN_C5_24` cohort used by the active experiment.

The current physical TRAIN24 manifest contains canonical IDs `DL1018_DEV_*`. The relevant exact scenes are `DL1018_DEV_T1_C10_W09` and `DL1018_DEV_T3_C09_W09`; their B, C5, and frozen GRU-parent raw comparison is reported in the sibling directory `hf_definition_train24_dev_pairs_audit_v1`.

Do not cite the legacy numerical results for the active experiment. They are retained under `LEGACY_WRONG_COHORT_*` names only as an audit trail. One earlier broad text search also hit TEST-labeled summary text, and the old pass read the combined scene-spec table while selecting legacy TRAIN rows. The corrected paired spectral pass is limited to the exact DEV TRAIN24 records and DEV-only source manifests; no TEST raw or score was opened in that pass.
