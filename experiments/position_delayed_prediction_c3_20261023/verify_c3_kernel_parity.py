import json
import pathlib
import sys
import numpy as np

repo = pathlib.Path(__file__).resolve().parents[2]
proposal = repo / "reports" / "delayed_prediction_proposal_20261023" / "construction" / "delayed_prediction_kernel.py"
sys.path.insert(0, str(proposal.parent))
import delayed_prediction_kernel as py

base = pathlib.Path(__file__).resolve().parent
result = json.loads((base / "matlab_kernel_result.json").read_text(encoding="utf-8"))
W = np.reshape(np.sin(np.arange(1, 100)) * 0.2, (33, 3), order="F")
phi = np.zeros(33); phi[0] = 1.0
old_phi = np.zeros(33); old_phi[1] = 1.0
s = [1.0, -2.0, 3.0]; y = [0.3, -0.2, 0.1]
expected = [
    py.delayed_prediction_step(np.zeros((33, 3)), phi, [0, 0, 0], 320, 0.32),
    py.delayed_prediction_step(W, phi, s, 330, 0.33, phi_prev=old_phi, y_prev=y,
                               previous_index=320, previous_time_s=0.32),
]
for key, exp in zip(("first", "second"), expected):
    got = result[key]
    assert got["has_previous"] == exp["has_previous"], key
    for field in ("raw", "applied", "beta", "previous_raw", "previous_residual",
                  "prediction_gradient", "preprojection_candidate", "W_next"):
        a, b = got[field], exp[field]
        if b is None:
            assert a is None or np.asarray(a).size == 0, (key, field, a)
            continue
        assert a is not None, (key, field)
        assert np.allclose(np.asarray(a), np.asarray(b), rtol=0, atol=1e-12), (key, field)
check = py.self_check()
assert result["checkcode_count"] == 0, result["checkcode_ids"]
print(json.dumps({"status": "PASS_MATLAB_PYTHON_KERNEL_PARITY_NO_PLANT",
                  "compared_cases": 2, "checkcode_count": result["checkcode_count"],
                  "python_self_check": check["status"]}, indent=2))
