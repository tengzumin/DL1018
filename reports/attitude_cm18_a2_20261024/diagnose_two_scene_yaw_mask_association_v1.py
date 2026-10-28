"""Read-only two-scene A1 full-vs-raw-alphaXY-mask yaw association check."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL", OMP_NUM_THREADS="1",
                  MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
A1 = "experiments/attitude_cm18_a1_20261024"
MANIFEST = "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/DATASET_MANIFEST_v1.json"
V2_RESULT = "reports/attitude_cm18_a2_20261024/TWO_SCENE_LABEL_DECOMPOSITION_v2.json"
DEPLOYMENT = f"{A1}/deployment_v1/deployment_parameters_v1.json"
OUTPUT = ROOT / "reports/attitude_cm18_a2_20261024/TWO_SCENE_YAW_MASK_ASSOCIATION_v1.json"
MANIFEST_SHA = "7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271"
V2_RESULT_SHA = "77e25178d0f091be4913736bc33f58d9018efa00ae9ee239c29311177a9a1c00"
DEPLOYMENT_SHA = "ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae"
MODEL_SHA = "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6"
READER_SHA = "a2867cbf516d7ed655a6f50e05b8600ffb7582e0f2164b1ce21d5e647adf2b47"
SOURCE_PINS = {
    f"{A1}/train_cm18_a1_v1.py": "7544a04329bc1e06ff5d7a113a077033a65f0b7c2de8a6f1b25ac54710e62c76",
    f"{A1}/cache_reader_cm18_v1.py": READER_SHA,
    f"{A1}/model_cm18_v1.py": MODEL_SHA,
    f"{A1}/torch_model_cm18_v1.py": "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
}
SCENES = (
    ("DL1018_TRAIN_T1_C15_W14", "TRAIN",
     "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/TRAIN_DL1018_TRAIN_T1_C15_W14.mat",
     "2d87ad8962a243d24c2cb1845e3031e62e723dfa8a8ee0435a01cd90c4368f81"),
    ("DL1018_VAL_T2_C15_W09", "VAL",
     "reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/VAL_DL1018_VAL_T2_C15_W09.mat",
     "29fe6f08c5a1349797bc2ea83c51efc389aa99893e71b91767e2733ace813a49"),
)
PHASES = ((0, "STATIC"), (1, "PRE"), (2, "EXTEND"),
          (3, "HOLD"), (4, "RETRACT"), (5, "RECOVERY"))
TOL = 1e-12


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def metric_rows(f: np.ndarray, m: np.ndarray, d: np.ndarray,
                qwind: np.ndarray, qaction: np.ndarray, phase: np.ndarray) -> list[dict]:
    groups = [("ALL", np.ones(len(d), dtype=bool))]
    groups.extend((name, phase == code) for code, name in PHASES)
    rows = []
    for name, mask in groups:
        n = int(np.count_nonzero(mask))
        row = {"group": name, "event_count": n}
        if not n:
            row.update(full_yaw_rmse_rad_s2=None, masked_yaw_rmse_rad_s2=None,
                       delta_mse_mask_minus_full_rad_s4=None, delta_mse_identity_error=None,
                       counterfactuals={})
            rows.append(row)
            continue
        ff, mm, dd = f[mask], m[mask], d[mask]
        delta = mm - ff
        e = ff - dd
        dmse = float(np.mean((mm - dd) ** 2 - (ff - dd) ** 2))
        identity_rhs = float(np.mean(delta ** 2 + 2.0 * e * delta))
        identity_error = abs(dmse - identity_rhs)
        if identity_error > TOL:
            raise AssertionError(f"{name}: delta-MSE identity failed ({identity_error})")
        counterfactuals = {}
        for key, q in (("wind", qwind), ("old_action", qaction)):
            qq = q[mask]
            d_cf = dd - qq
            cf_dmse = float(np.mean((mm - d_cf) ** 2 - (ff - d_cf) ** 2))
            predicted_shift = float(2.0 * np.mean(delta * qq))
            shift = cf_dmse - dmse
            error = abs(shift - predicted_shift)
            if error > TOL:
                raise AssertionError(f"{name}/{key}: counterfactual delta-MSE identity failed ({error})")
            counterfactuals[key] = {
                "delta_mse_mask_minus_full_rad_s4": cf_dmse,
                "shift_from_original_delta_mse_rad_s4": shift,
                "predicted_shift_2mean_delta_q_rad_s4": predicted_shift,
                "identity_abs_error": error,
            }
        row.update(
            full_yaw_rmse_rad_s2=float(np.sqrt(np.mean((ff - dd) ** 2))),
            masked_yaw_rmse_rad_s2=float(np.sqrt(np.mean((mm - dd) ** 2))),
            delta_mse_mask_minus_full_rad_s4=dmse,
            delta_mse_identity_rhs_rad_s4=identity_rhs,
            delta_mse_identity_error=identity_error,
            mean_delta_squared_rad_s4=float(np.mean(delta ** 2)),
            two_mean_error_delta_rad_s4=float(2.0 * np.mean(e * delta)),
            counterfactuals=counterfactuals,
        )
        rows.append(row)
    return rows


def main() -> None:
    sys.path.insert(0, str(ROOT / A1))
    import cache_reader_cm18_v1 as reader
    import model_cm18_v1 as model

    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    manifest_path, result_path = ROOT / MANIFEST, ROOT / V2_RESULT
    deployment_path = ROOT / DEPLOYMENT
    if sha(manifest_path) != MANIFEST_SHA or sha(result_path) != V2_RESULT_SHA:
        raise ValueError("pinned manifest or v2 decomposition result SHA mismatch")
    if sha(deployment_path) != DEPLOYMENT_SHA:
        raise ValueError("pinned A1 deployment JSON SHA mismatch")
    if sha(Path(model.__file__).resolve()) != MODEL_SHA or sha(Path(reader.__file__).resolve()) != READER_SHA:
        raise ValueError("A1 NumPy forward or cache reader source SHA mismatch")
    for rel, expected in SOURCE_PINS.items():
        if sha(ROOT / rel) != expected:
            raise ValueError(f"A1 deployment source SHA mismatch: {rel}")

    manifest = read_json(MANIFEST)
    if (manifest.get("schema") != "CM18_A1_DATASET_MANIFEST_V1" or
            manifest.get("mode") != "ALL816" or manifest.get("scene_count") != 816 or
            manifest.get("TEST_accessed") is not False):
        raise ValueError("unexpected fixed ALL816 manifest identity")
    deployment = read_json(DEPLOYMENT)
    identity = deployment["identity"]
    if (deployment.get("schema") != "CM18_A1_DEPLOYMENT_PARAMETERS_V1" or
            identity.get("selected_step") != 30000 or
            identity.get("source_files") != SOURCE_PINS or
            identity.get("input", {}).get("dataset_manifest_sha256") != MANIFEST_SHA):
        raise ValueError("unexpected A1 model identity/source pins")
    v2 = read_json(V2_RESULT)
    if v2.get("schema") != "CM18_TWO_SCENE_LABEL_DECOMPOSITION_V2" or v2.get("status") != "PASS":
        raise ValueError("two-scene decomposition is not pinned PASS")
    v2_by_id = {row["scene_id"]: row for row in v2["scenes"]}
    if set(v2_by_id) != {x[0] for x in SCENES}:
        raise ValueError("v2 decomposition scene set differs from the two pinned scenes")
    params = deployment["parameters"]
    results = []
    for scene_id, split, cache_path, cache_sha in SCENES:
        rows = [r for r in manifest["rows"] if r.get("scene_id") == scene_id]
        if len(rows) != 1:
            raise ValueError(f"expected exactly one manifest row for {scene_id}")
        row = rows[0]
        if (row.get("split") != split or row.get("cache_path") != cache_path or
                row.get("cache_sha256") != cache_sha):
            raise ValueError(f"pinned cache row identity mismatch: {scene_id}")
        scene = reader._read_scene(ROOT, row, manifest["input_manifest_sha256"])
        records = v2_by_id[scene_id]["event_records"]
        x = scene["X18"]
        d = scene["target_raw"][:, 2]
        phase = scene["phase_code"].reshape(-1).astype(np.int64)
        idx = scene["plant_index"].reshape(-1).astype(np.int64)
        if len(records) != 1999 or x.shape != (1999, 18) or d.shape != (1999,):
            raise ValueError(f"unexpected event dimensions: {scene_id}")
        if not np.array_equal(np.asarray([r["plant_index"] for r in records]), idx):
            raise ValueError(f"v2/cache plant_index alignment mismatch: {scene_id}")
        if not np.array_equal(np.asarray([r["phase_code"] for r in records]), phase):
            raise ValueError(f"v2/cache phase alignment mismatch: {scene_id}")
        d_v2 = np.asarray([r["target_raw_yaw"] for r in records], dtype=np.float64)
        if np.max(np.abs(d_v2 - d)) > TOL:
            raise ValueError(f"v2/cache target alignment mismatch: {scene_id}")
        qwind = np.asarray([r["components"]["wind"] for r in records], dtype=np.float64)
        qaction = np.asarray([r["components"]["old_compensation_transfer"] for r in records], dtype=np.float64)
        if not np.isfinite(qwind).all() or not np.isfinite(qaction).all():
            raise ValueError(f"non-finite decomposition component: {scene_id}")
        full = model.forward(x, params)["physical_output_rad_s2"][:, 2]
        masked_x = x.copy()
        masked_x[:, 3:5] = 0.0  # raw alpha_BS x/y, before model normalization
        masked = model.forward(masked_x, params)["physical_output_rad_s2"][:, 2]
        results.append({"scene_id": scene_id, "split": split, "event_count": len(d),
                        "cache_path": cache_path, "cache_sha256": cache_sha,
                        "event_alignment": "PASS plant_index, phase_code, and target_raw_yaw",
                        "raw_alpha_xy_mask": "X18 columns 4:5 set to raw zero before normalization",
                        "metrics": metric_rows(full, masked, d, qwind, qaction, phase)})

    report = {
        "schema": "CM18_TWO_SCENE_YAW_MASK_ASSOCIATION_V1", "status": "PASS",
        "interpretation": "Same canonical-double A1 deployed weights; offline two-scene association check, not a deployment model or causal estimate.",
        "delta_definition": "delta = masked_yaw_prediction - full_yaw_prediction; delta_mse = MSE(masked,d)-MSE(full,d).",
        "counterfactual_definition": "q_wind is the v2 full-matrix wind component; q_old_action is the v2 full-matrix old_compensation_transfer component. For each, use d_cf=d-q with unchanged input and weights; delta_mse_cf-delta_mse must equal 2*mean(delta*q). This is an algebraic covariance decomposition, not causality.",
        "identity": {"dataset_manifest_path": MANIFEST, "dataset_manifest_sha256": MANIFEST_SHA,
                     "v2_decomposition_path": V2_RESULT, "v2_decomposition_sha256": V2_RESULT_SHA,
                     "deployment_path": DEPLOYMENT, "deployment_sha256": DEPLOYMENT_SHA,
                     "selected_step": 30000, "checkpoint_sha256": identity["checkpoint_sha256"],
                     "normalizer_sha256": identity["normalizer_sha256"],
                     "deployment_source_files": SOURCE_PINS,
                     "numpy_forward_sha256": MODEL_SHA, "cache_reader_sha256": READER_SHA},
        "scope": {"scene_ids": [x[0] for x in SCENES], "events_per_scene": 1999,
                  "training_or_optimizer_calls": 0, "plant_or_engine_calls": 0,
                  "raw_read": False, "TEST_accessed": False},
        "script_sha256": sha(Path(__file__).resolve()), "scenes": results,
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "PASS", "output": str(OUTPUT.relative_to(ROOT)),
                      "scenes": len(results), "optimizer_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()