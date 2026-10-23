"""Check feasibility of the existing sufficient domain certificate, not stability."""
import hashlib
import importlib.util
import json
from fractions import Fraction as F
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
decoder_path = ROOT / 'reports/paper14_v2/phase1/audit_w15_position_replay.py'
snapshot = ROOT / 'experiments/position_axis_coordinate_c5_20261023/C5_AXIS_COORDINATE_PREPARED_CFG_OPTS_v1.mat'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(decoder_path) == '372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af'
assert sha(snapshot) == 'e417b56e68a73f7af6f40a5e7928631db1b4f3c05de1c3abd24828053760749d'
spec = importlib.util.spec_from_file_location('frozen_domain_decoder', decoder_path)
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
w0 = np.asarray(decoder.matlab_section(snapshot, 'W0'))
assert hashlib.sha256(np.asarray(w0, dtype='<f8').tobytes(order='F')).hexdigest() == '88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53'
alpha, kappa, d0 = F(1, 24), F(1, 2500), F(49999, 50000)
c_squared = (alpha-kappa)/(alpha*d0*d0)
assert 0 < c_squared < 1
axis = np.linalg.norm(w0, axis=0)
assert axis[0] > 4 and axis[1] > 4
result = dict(
    status='EXISTING_ISOTROPIC_FIRST_STEP_SUFFICIENT_CERTIFICATE_INFEASIBLE_FOR_ANY_COMPARATOR',
    W0_axis_norms=axis.tolist(), W0_frobenius=float(np.linalg.norm(w0)),
    c_squared_exact=str(c_squared), c_squared=float(c_squared),
    U0_initial_weight_storage_lower=float(alpha-kappa)*float(np.square(w0).sum()),
    U0_Vloc=float(alpha-kappa)*9,
    argument='If u_star<3 and the current V1 upper bound <= Vloc, alpha*d0^2*||W0-U||_F^2 <= (alpha-kappa)*(3-u_star)^2. Hence ||W0-U||_F <= c*(3-u_star), c<1. Triangle inequality gives every ||W0_axis|| <= u_star+c*(3-u_star)<3, contradicting the frozen W0 first two column norms >4. If u_star>=3, the sufficient criterion is inapplicable by definition.',
    scope='Only the published scalar first-step upper-bound plus uniform unit-feature sufficient domain criterion; not the exact trajectory energy, directional reachable-feature domain, or alternative certificates.',
    stability_conclusion='NONE; does not imply actual clipping or instability',
    no_parameter_changes=True, Plant_calls=0, TEST_accessed=False,
    refs=[dict(path=str(p),sha256=sha(p)) for p in (snapshot,decoder_path,Path(__file__))])
out=HERE/'INITIAL_DOMAIN_FEASIBILITY_REVIEW_v1.json'
with out.open('x',encoding='utf-8') as f:
    json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False)
    f.write('\n')
print(json.dumps(result))
