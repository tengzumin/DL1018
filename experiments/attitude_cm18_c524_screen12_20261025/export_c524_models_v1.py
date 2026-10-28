"""Export the two frozen 60k CM18 branches to MATLAB structs and parity fixtures."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import torch
from scipy.io import savemat


ROOT = Path(__file__).resolve().parents[2]
BASE = Path("experiments/attitude_position_context_probe_20261024/b24_c524_paired_v1")
OUTPUT = ROOT / "experiments/attitude_cm18_c524_screen12_20261025/models"
NORMALIZER = ROOT / "experiments/attitude_cm18_datarepair_20261024/training_a1t_v1/normalizer.json"
SCORE = ROOT / "reports/attitude_position_context_probe_20261024/b24_c524_paired_v1/postselection_scores/final60000_paired_v1/B24_C5_24_FINAL_SCORE_v1.json"
BRANCHES = ("B24", "C5_24")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)


def parameters(state: dict, norm: dict) -> dict[str, np.ndarray]:
    mapping = {
        "W1": "fc1.weight", "b1": "fc1.bias",
        "W2": "fc2.weight", "b2": "fc2.bias",
        "W3": "fc3.weight", "b3": "fc3.bias",
    }
    result = {key: state[source].detach().cpu().numpy().astype(np.float64) for key, source in mapping.items()}
    result.update({
        "input_mean": np.asarray(norm["input_mean_float64"], dtype=np.float64),
        "input_std": np.asarray(norm["input_std_float64"], dtype=np.float64),
        "train_axis_rms_rad_s2": np.asarray(norm["train_axis_rms_rad_s2_float64"], dtype=np.float64),
    })
    shapes = {"W1": (32, 18), "b1": (32,), "W2": (32, 32), "b2": (32,),
              "W3": (24, 32), "b3": (24,), "input_mean": (18,), "input_std": (18,),
              "train_axis_rms_rad_s2": (3,)}
    for key, shape in shapes.items():
        if result[key].shape != shape or not np.isfinite(result[key]).all():
            raise ValueError(f"invalid {key} shape/value: {result[key].shape}")
    return result


def forward(x: np.ndarray, p: dict[str, np.ndarray]) -> np.ndarray:
    x_norm = (x - p["input_mean"]) / p["input_std"]
    h1 = np.tanh(x_norm @ p["W1"].T + p["b1"])
    h2 = np.tanh(h1 @ p["W2"].T + p["b2"])
    coeff = (h2 @ p["W3"].T + p["b3"]).reshape(-1, 3, 8)
    basis = np.concatenate((x[:, 11:15] / 2.0, x[:, 7:11]), axis=1)
    return np.einsum("nck,nk->nc", coeff, basis) * p["train_axis_rms_rad_s2"]


def main() -> None:
    score = json.loads(SCORE.read_text(encoding="utf-8"))
    if score.get("status") != "PASS" or score.get("scope", {}).get("TEST_accessed") is not False:
        raise ValueError("the pinned post-selection VAL score is not PASS/TEST-clean")
    norm = json.loads(NORMALIZER.read_text(encoding="utf-8"))
    if norm.get("canonical_float64_sha256") != "12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a":
        raise ValueError("canonical normalizer identity mismatch")
    rng = np.random.default_rng(20261025)
    probe = rng.normal(size=(64, 18)).astype(np.float64)
    probe[0, 7:15] = 0.0  # exact zero-basis check
    receipt: dict = {"schema": "CM18_B24_C524_SCREEN12_EXPORT_V1", "status": "PASS",
                     "score_result_sha256": sha(SCORE), "normalizer_sha256": sha(NORMALIZER),
                     "exporter_sha256": sha(Path(__file__)), "branches": {}}
    expected: dict[str, np.ndarray] = {}
    for branch in BRANCHES:
        run = ROOT / BASE / f"training_{branch}_v1"
        checkpoint_path = run / "final.pt"
        train_receipt = json.loads((run / "run_receipt.json").read_text(encoding="utf-8"))
        score_pin = score["runs"][branch]
        if (train_receipt.get("status") != "COMPLETED" or train_receipt.get("candidate_frozen") is not True
                or train_receipt.get("optimizer_steps_completed") != 60000
                or train_receipt.get("TEST_accessed") is not False
                or sha(checkpoint_path) != score_pin["checkpoint_sha256"]
                or train_receipt.get("final_checkpoint_sha256") != score_pin["checkpoint_sha256"]):
            raise ValueError(f"{branch} terminal checkpoint is not the scored frozen 60k model")
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        if checkpoint.get("kind") != "final" or checkpoint.get("optimizer_step") != 60000:
            raise ValueError(f"{branch} checkpoint schema/step mismatch")
        p = parameters(checkpoint["state_dict"], norm)
        expected[branch] = forward(probe, p)
        if not np.array_equal(expected[branch][0], np.zeros(3, dtype=np.float64)):
            raise ValueError(f"{branch} violates exact zero-basis output")
        mat_path = OUTPUT / f"{branch}_model.mat"
        mat_buffer = io.BytesIO()
        savemat(mat_buffer, {"model": p}, do_compression=True, long_field_names=True, oned_as="row")
        write_new(mat_path, mat_buffer.getvalue())
        receipt["branches"][branch] = {
            "checkpoint_sha256": score_pin["checkpoint_sha256"],
            "final_float32_state_sha256": train_receipt["final_float32_state_sha256"],
            "model_mat_path": str(mat_path.relative_to(ROOT)).replace("\\", "/"),
            "model_mat_sha256": sha(mat_path),
            "matlab_parameter_order": "CM18-A1 forward v1; fc3 flat outputs reshape as 3x8 row-major coefficients",
            "probe_max_abs_reference": float(np.max(np.abs(expected[branch]))),
        }
    fixture = io.BytesIO()
    savemat(fixture, {"X18": probe, "B24_expected": expected["B24"], "C5_24_expected": expected["C5_24"]},
            do_compression=True, long_field_names=True)
    fixture_path = OUTPUT / "matlab_parity_fixture.mat"
    write_new(fixture_path, fixture.getvalue())
    receipt["fixture_path"] = str(fixture_path.relative_to(ROOT)).replace("\\", "/")
    receipt["fixture_sha256"] = sha(fixture_path)
    receipt["probe_rows"] = int(probe.shape[0])
    write_new(OUTPUT / "export_receipt.json", (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"status": "PASS", "branches": receipt["branches"],
                      "fixture_sha256": receipt["fixture_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
