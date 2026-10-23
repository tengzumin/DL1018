"""Exact 3-D M110 restoration check; no simulation or author checker execution."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
OUT = HERE / "PARENT_M110_EXACT_CHECK_v1.json"
assert not OUT.exists()
proof = HERE / "PHYSICAL_RESIDUAL_TRACKING_LEMMA_ZH.md"
assert hashlib.sha256(proof.read_bytes()).hexdigest() == "ba5db2bfe3a99b949b11d266755f6b8202bb812d7a0cb1e8177500b8e3a1c179"
h, alpha = F(1, 1000), F(17, 19)
beta, a, d = F(3, 29), 1-h, 1-4*h
mask = (1, 1, 0)
for column in range(21):
    vectors = [[F(3*j+i == column) for i in range(3)] for j in range(7)]
    e, sigma, eta, rho_p, rho_s, epsilon, rf = vectors
    for i, m in enumerate(mask):
        y = sigma[i]-m*eta[i]
        rho_eta = (alpha-d)*eta[i]+(beta-h)*rf[i]
        next_e = a*e[i]+h*y+h*m*eta[i]+rho_p[i]
        next_y = -h*e[i]+d*y+rho_s[i]-m*rho_eta+h*epsilon[i]
        next_eta = d*eta[i]+rho_eta+h*rf[i]
        assert next_eta == alpha*eta[i]+beta*rf[i]
        assert next_e == a*e[i]+h*sigma[i]+rho_p[i]
        assert next_y+m*next_eta == -h*e[i]+d*sigma[i]+rho_s[i]+h*(epsilon[i]+m*rf[i])
result = {
    "status": "PASS_EXACT_THREE_AXIS_M110_21_BASIS_COLUMNS",
    "basis_columns": 21, "coordinate_mask": list(mask),
    "alpha_beta_scope": "Arbitrary exact non-Euler example; scalar parent checker covers additional pairs.",
    "proof_sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
    "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "Plant_started": False, "TEST_accessed": False,
    "scope": "Masked algebra only; no new closed-loop stability or Plant-bound claim.",
}
with OUT.open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(result))
