from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "experiments/attitude_kan29_c5_replacement_20261024/artifacts"
OUT = ART / "PYTHON_REFERENCE_A_KAN29_v1.json"
SRC = Path(r"C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1009\RBF-BS0\experiments\attitude_kan_legal_input_reuse_upgrade_v3_6")

EXPECTED = {
    "A_KAN29_V3_6.mat": "46335d925277631d139c594c2fe6796a9d74cb335c9f21ece680f0d4ce68f5d7",
    "A_KAN29_V3_6_PARITY_FIXTURES.mat": "ebd6ddbeac31f261ac7bc5e57fd700d03626d49ed1401dc3dd26ef6ae92e1b05",
    "A_KAN29_DEV_FREEZE_V3_6.json": "fa3cb13892d565026090165d1c1a0d3773d516bca6ad744d5c3824a8eaa3eb71",
    "TRAIN128_NORMALIZER_X29_V3_6.npz": "344fababbaee719f021badd269026d46da035de8b0caaa5f9fb4fef53b9a9f3c",
    "DATA_REUSE_MANIFEST_V3_6.csv": "354c9fc22fa8f2a10efc3057de5306e16cb2cfe232a886cecb22fcb9e97efb60",
    "A_KAN29_DEV_SCENES_V3_6.csv": "f63e4805d02fff7e3c4fb2bf93b31d3b6ed8c2ff871c467cdb626600669255b9",
    "A_KAN29_FIT_V3_6.json": "c0953cca42a327f16bda9e87ef0db2638bb90557cbc92564e40a0f5703646140",
}
SOURCE_PINS = {
    "experiments/position_axis_coordinate_c5_dev72_20261023/C5_DEV72_PREPARED_CFG_OPTS_v3.mat": "842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a",
    "experiments/position_axis_coordinate_c5_dev72_20261023/run_dl1018_closed_loop.m": "48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c",
    "matlab/models/attitude_model_feature_x29_v39.m": "8e34c28c81b2b1a4c0917325eb98aeb522a7baff32543a84299a41dd544a9f28",
    "matlab/models/attitude_kan_head_step_v39.m": "f4d6a5f1fcd113415705558b0ed9d03d6299524e0d6b296615021b033efe35f0",
    "matlab/core/attitude_bs_step.m": "cf6b20ffc4df2625d9316a80340d69542e380d14feaed66ef8498e793fdaccbc",
    "matlab/core/simulation_parameters.m": "962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae",
    "matlab/core/controller_parameters.m": "4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398",
    "matlab/core/rbf_event_scheduler_step.m": "cc5a71c5c87af0598c310bae5be170c505c7674b115446d826b074d21a049618",
}


def sha(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def cubic_basis(x: float, knots: np.ndarray) -> np.ndarray:
    b = ((x >= knots[:-1]) & (x < knots[1:])).astype(np.float64)
    for degree in range(1, 4):
        count = knots.size - degree - 1
        nxt = np.zeros(count, dtype=np.float64)
        for i in range(count):
            left = knots[i + degree] - knots[i]
            right = knots[i + degree + 1] - knots[i + 1]
            if left > 0:
                nxt[i] += (x - knots[i]) / left * b[i]
            if right > 0:
                nxt[i] += (knots[i + degree + 1] - x) / right * b[i + 1]
        b = nxt
    if x == knots[-1]:
        b[:] = 0
        b[-1] = 1
    return b


def predict(model: dict, window: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = (window - model["input_mu"]) / np.maximum(model["input_sigma"], 1e-6)
    cur = np.clip(x[:, -1], -4.0, 4.0)
    basis = np.stack([cubic_basis(float(cur[j]), model["knots"]) for j in range(29)])
    p = model["params"]
    z = np.sum(p["spline_W"] * basis[None, :, :], axis=(1, 2))
    z = z + p["linear_W"] @ (cur / (1.0 + np.exp(-cur))) + p["feature_b"].reshape(-1)
    h = np.tanh(z)
    phi = np.concatenate((h, [1.0])) / np.sqrt(1.0 + np.sum(h * h))
    w0 = p["readout__weight"].T
    return w0.T @ phi, phi


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUT}")
    hashes: dict[str, str] = {}
    for name, expected in EXPECTED.items():
        staged, source = ART / name, SRC / ("models/initial/" + name if name.endswith(".mat") else
            "configs/" + name if name.startswith("A_KAN29_DEV_FREEZE") or name.startswith("TRAIN128") else
            "reports/" + name)
        assert staged.is_file() and source.is_file(), name
        hs, ho = sha(staged), sha(source)
        assert hs == ho == expected, (name, hs, ho, expected)
        hashes[name] = hs
    for rel, expected in SOURCE_PINS.items():
        got = sha(ROOT / rel)
        assert got == expected, (rel, got, expected)
        hashes[rel] = got

    freeze = json.loads((ART / "A_KAN29_DEV_FREEZE_V3_6.json").read_text(encoding="utf-8-sig"))
    assert freeze["status"] == "FROZEN_BEFORE_PLANT" and freeze["fit_id"] == "A_KAN29"
    assert freeze["split"] == "DEV" and freeze["information_condition"] == "X29"
    assert freeze["input_dim"] == 29 and freeze["lambda"] == 1
    assert freeze["model_sha256"] == hashes["A_KAN29_V3_6.mat"]
    assert freeze["normalizer_sha256"] == hashes["TRAIN128_NORMALIZER_X29_V3_6.npz"]
    assert freeze["data_reuse_manifest_sha256"] == hashes["DATA_REUSE_MANIFEST_V3_6.csv"]
    assert freeze["scene_manifest_sha256"] == hashes["A_KAN29_DEV_SCENES_V3_6.csv"]
    assert freeze["plant_calls_before_freeze"] == 0

    raw_model = loadmat(ART / "A_KAN29_V3_6.mat", squeeze_me=False, struct_as_record=True)
    assert all(k in raw_model for k in ("architecture", "input_dim", "input_mu", "input_sigma", "dmax", "knots", "params"))
    assert str(raw_model["architecture"][0, 0][0]) == "KAN"
    assert int(raw_model["input_dim"][0, 0]) == 29
    ps = raw_model["params"][0, 0]
    model = {
        "input_mu": np.asarray(raw_model["input_mu"], dtype=np.float64).reshape(29),
        "input_sigma": np.asarray(raw_model["input_sigma"], dtype=np.float64).reshape(29),
        "dmax": np.asarray(raw_model["dmax"], dtype=np.float64).reshape(3),
        "knots": np.asarray(raw_model["knots"], dtype=np.float64).reshape(12),
        "params": {key: np.asarray(ps[key], dtype=np.float64) for key in ps.dtype.names},
    }
    assert model["params"]["spline_W"].shape == (32, 29, 8)
    assert model["params"]["linear_W"].shape == (32, 29)
    assert model["params"]["feature_b"].size == 32
    assert model["params"]["readout__weight"].shape == (3, 33)

    norm = np.load(ART / "TRAIN128_NORMALIZER_X29_V3_6.npz", allow_pickle=False)
    np.testing.assert_array_equal(model["input_mu"], norm["mu"].astype(np.float64))
    np.testing.assert_array_equal(model["input_sigma"], norm["sigma"].astype(np.float64))
    np.testing.assert_array_equal(model["dmax"], norm["dmax"].astype(np.float64))
    assert int(norm["input_dim"]) == 29

    fixtures = loadmat(ART / "A_KAN29_V3_6_PARITY_FIXTURES.mat", squeeze_me=False, struct_as_record=True)
    windows = np.asarray(fixtures["input_windows"], dtype=np.float64)
    expected = np.asarray(fixtures["expected_applied_rad_s2"], dtype=np.float64)
    assert windows.shape == (29, 32, 148) and expected.shape == (3, 148)
    np.testing.assert_array_equal(np.asarray(fixtures["dmax"], dtype=np.float64).reshape(3), model["dmax"])
    rows = []
    max_fixture_residual = 0.0
    for idx in range(windows.shape[2]):
        raw, _ = predict(model, windows[:, :, idx])
        applied = np.clip(raw, -1.0, 1.0) * model["dmax"]
        residual = float(np.max(np.abs(applied - expected[:, idx])))
        max_fixture_residual = max(max_fixture_residual, residual)
        assert residual <= 1e-5, (idx, residual)
        rows.append({"raw_normalized": raw.tolist(), "applied_rad_s2": applied.tolist()})

    result = {
        "schema": "C5_A_KAN29_PYTHON_REFERENCE_V1",
        "model_identity": {"fit_id": "A_KAN29", "input_dim": 29, "lambda": 1, "status": freeze["status"]},
        "fixture_count": 148,
        "max_fixture_applied_residual_rad_s2": max_fixture_residual,
        "source_sha256": hashes,
        "fixtures": rows,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"status": "PASS", "fixture_count": 148,
                      "max_fixture_applied_residual_rad_s2": max_fixture_residual,
                      "output": str(OUT), "sha256": sha(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
