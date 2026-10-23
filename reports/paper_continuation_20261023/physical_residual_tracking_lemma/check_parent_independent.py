"""Independent exact basis check; no experiment data or author code execution."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
out = HERE / 'PARENT_INDEPENDENT_CHECK_v1.json'
assert not out.exists()
manifest = json.loads((HERE / 'SOURCE_IDS.json').read_text(encoding='utf-8-sig'))
verified = []
for entry in manifest['sources'] + manifest['artifacts']:
    path = ROOT / entry['path']
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == entry['sha256'], str(path)
    verified.append({'path': entry['path'], 'sha256': digest})

h = F(1, 1000)
a, d = 1-h, 1-4*h
assert a+d == F(399, 200)
assert a*d+h*h == F(199001, 200000)
disc = (a+d)**2-4*(a*d+h*h)
assert disc == F(1, 200000)
assert (2*a-a-d)**2 > disc and 2*a-a-d > 0
assert (a+d)**2 > disc and a+d > 0 and a < 1
det = (1-a)*(1-d)+h*h
assert (1-d)/det == 800 and h/det == 200

# Verify all basis columns of the deployed one-step equations. Alpha/beta are
# treated as arbitrary exact values; additional cases detect accidental Euler
# substitution. rho_eta MUST be generated from eta/rf, not an independent input.
count = 0
for mask in (F(0), F(1)):
    for alpha, beta in ((F(249,250),h), (F(17,19),F(3,29)), (F(1),F(0))):
        for col in range(7):
            e, s, eta, rp, rs, eps, rf = [F(i == col) for i in range(7)]
            reta = (alpha-d)*eta+(beta-h)*rf
            y = s-mask*eta
            e_next = a*e+h*y+h*mask*eta+rp
            y_next = -h*e+d*y+rs-mask*reta+h*eps
            eta_next = d*eta+reta+h*rf
            assert eta_next == alpha*eta+beta*rf
            assert e_next == a*e+h*s+rp
            assert y_next+mask*eta_next == -h*e+d*s+rs+h*(eps+mask*rf)
            count += 1

# Independent coefficient expansion of the PCF cancellation numerator:
# beta*(z-d)-beta*(alpha-d)-(beta-h)*(z-alpha).
for alpha,beta in ((F(17,19),F(3,29)),(F(1),F(0)),(F(249,250),h)):
    coefficients = (beta-(beta-h), -beta*d-beta*(alpha-d)+(beta-h)*alpha)
    assert coefficients == (h,-h*alpha)

result = {
    'schema': 'PHYSICAL_RESIDUAL_TRACKING_PARENT_REVIEW_V1',
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'PASS_EXACT_BASIS_AND_RATIONAL_CONSTANTS_WITH_MANUAL_PROOF_REVIEW',
    'basis_columns_checked': count,
    'all_input_and_artifact_hashes_verified': verified,
    'manual_review': [
        'BS a_nom=rddot+de+e+4s=rddot+5s uses deployed k1=1.',
        'Resolvent initial term and input delays agree with unilateral transform.',
        'a>lambda_plus>lambda_minus>0 makes kernel11 positive and kernel12 nonnegative; inverse sums 800/200 are absolute l1 gains.',
        'Young bound uses vector sequence norm and sqrt(20000), keeping all cross terms.',
        'PCF pole cancels only after retaining rho_eta and restoring physical sigma.',
        'Physical forcing is epsilon_M+M*rf on the SAME trajectory, without counterfactual attribution.'
    ],
    'theory_scope': 'Exact sampled error identity and conditional finite-horizon error bound accepted; actual Plant uniform forcing/domain closure NOT established.',
    'TEST_accessed': False, 'Plant_started': False, 'training_started': False,
}
out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'basis_columns':count,'verified_files':len(verified),'result':str(out)}))
