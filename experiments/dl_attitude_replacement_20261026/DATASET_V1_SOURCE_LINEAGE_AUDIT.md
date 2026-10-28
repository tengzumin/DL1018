# Dataset v1 source-lineage issue

Date: 2026-10-26. Dataset v1 is preserved as an audit artifact and is **not valid for training**.

`prepare_tcn_dataset_v1.py` originally resolved every scene from `DATASET_MANIFEST_v1.json`'s `original_a1_source`. That is correct for the 544 reused A1 scenes but wrong for the 272 T2 scenes whose `source_action` is `REBUILD_FROM_CORRECTED_T2_B_RAW`. The repaired manifest gives their authoritative corrected raw and run-start paths under `corrected_source`; the original T2 raw is explicitly not the repaired label source.

For example, `DL1018_TRAIN_T2_C00_W00` must use corrected raw SHA `8306453bc0ae517729f2816c5010866f0269b7f8b1e2e5084a7abc5f797fbc29` and corrected run-start SHA `99e686d7eb387d1d97773f5f0e07fa8c8b9623029fc185949322be688b7b6bc8`. The initial exporter instead read the original A1 raw. No training process was started and no Plant run used this dataset.

Correction: the exporter now joins the repaired dataset manifest to `B_REF_REPAIRED_SOURCE_MANIFEST_v1.json`, verifies exact source action/path/hash/size, and selects corrected T2 files. A corrected-source dry run passed for a reused TRAIN, corrected T2 TRAIN, and VAL scene. A full `dataset_v2_corrected` build then reached all TRAIN rows but stopped on the 16 corrected T2 VAL run-start files, whose MATLAB 7.3 wrapper stores `cfg` at the file root rather than under `runStart`; it wrote no NPZ and started no training. The reader now handles both audited wrapper layouts, and the next output is `dataset_v3_corrected/`. Dataset v1 and the incomplete v2 directory remain untouched for provenance.
