#!/usr/bin/env python3
"""Verify the matching cosine-GRU parent raw task target/filter chain before fitting."""
from __future__ import annotations

import json
from pathlib import Path

from task_aware_common import load_locked_inputs, sha256


OUT = Path(__file__).resolve().parent
JSON_OUT = OUT / "PARENT_TASK_FILTER_REPLAY_AUDIT_v1.json"
MD_OUT = OUT / "PARENT_TASK_FILTER_REPLAY_AUDIT_v1.md"


def main() -> None:
    if JSON_OUT.exists() or MD_OUT.exists():
        raise RuntimeError("Refusing to overwrite existing parent replay audit")
    bundle = load_locked_inputs()
    audit = bundle["audit"]
    manifest = bundle["manifest"]
    fold_summaries = []
    all_holdout: list[str] = []
    all_ids = set(bundle["arrays"]["scene_ids"].astype(str).tolist())
    for fold in manifest["scene_folds"]:
        train_ids = fold["train_scene_ids"]
        hold_ids = fold["holdout_scene_ids"]
        if (len(train_ids) != fold["train_scene_count"] or
                len(hold_ids) != fold["holdout_scene_count"] or
                set(train_ids) & set(hold_ids) or set(train_ids) | set(hold_ids) != all_ids):
            raise RuntimeError(f"Invalid whole-scene fold partition: {fold['fold_id']}")
        fold_summaries.append({"fold_id": fold["fold_id"],
                               "train_scene_count": len(train_ids),
                               "holdout_scene_count": len(hold_ids),
                               "train_scene_ids": train_ids,
                               "holdout_scene_ids": hold_ids})
        all_holdout.extend(hold_ids)
    if len(all_holdout) != 24 or set(all_holdout) != all_ids:
        raise RuntimeError("The four folds do not hold out every scene exactly once")
    if [f["holdout_scene_count"] for f in fold_summaries] != [6, 8, 4, 6]:
        raise RuntimeError("Unexpected four-fold holdout sizes")
    audit["folds"] = fold_summaries
    audit["task_aware_training_protocol"] = {
        "four_whole_scene_folds": True,
        "scene_holdout_counts": [6, 8, 4, 6],
        "fold_ids": [f["fold_id"] for f in fold_summaries],
        "normalizer": "fit per fold from that fold's training scenes only, all 1999 causal X14 rows",
        "model_hidden_state": "reset to zero independently for each scene",
        "real_wind_input_or_measurement": False,
        "val_or_test_raw_read": False,
    }
    JSON_OUT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    err = audit["maximum_replay_errors"]
    lines = [
        "# Cosine-GRU parent task/filter replay audit",
        "",
        f"- Matching TRAIN_C5_24 scenes checked: {len(audit['scenes'])}; data SHA `{audit['dataset_sha256']}`.",
        f"- Reconstructed outer target max error: {err['outer_target_wrapped_rad']:.3e} rad.",
        f"- Python 1 ms filter replay max Euler error: {err['filtered_reference_wrapped_rad']:.3e} rad.",
        f"- Requested/applied filter acceleration max errors: {err['filter_requested_acceleration_rad_s2']:.3e} / {err['filter_applied_acceleration_rad_s2']:.3e} rad/s^2.",
        f"- 100 Hz event action hold max error: {err['event_action_hold_mps2']:.3e} m/s².",
        "- The runtime maps roll/pitch with current yaw, replaces target yaw with reference yaw, and logs the pre-update filter state. Limits are read from the hash-locked parent configuration: Inf/Inf/6 rad/s².",
        "- All four manifest folds are whole-scene partitions with 6/8/4/6 holdout scenes. No wind measurements, VAL/TEST raws, new Plant calls, or inertia reconstruction were used.",
        "",
    ]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
