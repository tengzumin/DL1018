# v7 code-only diff

v7 binds the DSSM/KAN corrected templates to corrected_pair_eval_v1 r002/r001. Manifest and contract engineering_dev2.v3_cfg_opts_snapshot_sha256 retain the actual prior v3 hashes (DSSM 1b6417b4...; KAN b10d1de1...), while run_start_sha256 binds the corrected references. The superseded v3/v6 paths and hashes and the genuine v6 DSSM mismatch/raw remain recorded.

DSSM uses run_start SHA 3b798c8624cc10cc1ddf3b3b1000099bc62e42e8430af92a42b0fa467385743e and raw SHA 231a29949fe0f4ca1a900b909ee8ca9a003f99a71448c14974b68530b45f2b18; historical meta.method_id is CORRECTED_TRAIN_DSSM14_G12_R32.

KAN uses run_start SHA 0012bf34074ac2f034517fbb65237bd667b31e7e539987601e4d16e0b26c9525 and raw SHA e6f704af8dba06cfd25ab401aedfc3866f8f91c06677858ec5b7c0154b8fa54f; historical meta.method_id is CORRECTED_TRAIN_KAN14_G12_R32.

The corrected pre-Plant gate compares the complete old opts model to the frozen model with isequaln, and compares old weight/W0 elementwise to double(model.output_W). It preserves old opts and checks the historical method label plus source/runtime scene IDs separately from the new collector.

Both launcher and MATLAB budget guards account for v3-v7 output directories. The six frozen models, v3 input hashes, model_refs, platform/shared refs, Plant loop, numeric comparison, timing exclusions, and protected binding/which functions remain unchanged.

Validation: PowerShell AST parse and both JSON parses passed; method and engineering arrays have uniform key sets. run_one_method, compare_raw_tree, compare_engineering_raw, bind_method_path, and verify_global_platform_which exactly match v6. No MATLAB, Plant, TEST, training, or reader was run.

Frozen v7 static SHA256:
entry: e78f64c315ebd174676489213650906d4cd027ff71ce47c173d9e456542c4582
launcher: 92b78af579c02613278ed8b83a31d7483be5776a340065a18927b43c689632a5
contract: 07c2a723823f9da5cf7140f828bf18841a95f91bfb7b383b7e0555ec0df17d9a
manifest: 43278c6143b5aad1271df3e68596c32c02cb4255748504320279c573e34e0663
