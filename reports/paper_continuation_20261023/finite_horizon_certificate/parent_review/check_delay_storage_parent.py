"""Independent exact minor check, using permutation determinants rather than elimination."""
import hashlib
import itertools
import json
from fractions import Fraction as Q
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'delay_aware_energy_diagnosis'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def determinant(m):
    value = Q(0)
    for p in itertools.permutations(range(len(m))):
        inversions = sum(p[i] > p[j] for i in range(len(p)) for j in range(i + 1, len(p)))
        term = Q((-1) ** inversions)
        for i, j in enumerate(p):
            term *= m[i][j]
        value += term
    return value


def main():
    expected = {
        'DELAY_AWARE_ENERGY_DIAGNOSIS_ZH.md': 'b53bc4a50ad16b45de0af357b7484f1d41fdb28ecf997ab1efa760607777ff73',
        'verify_delay_storage_exact.py': '7e2dc1a0188e2bb417d7d5fa8418dbcc1f7d35c553829c910a3e5b293dba75c2',
        'DELAY_STORAGE_EXACT_CERTIFICATE.json': 'f785307fc7d6ce20f7a6267b50dfba8dda33dc1d072ea2323c91ea4930f858d7',
    }
    for name, checksum in expected.items():
        assert digest(SOURCE / name) == checksum
    document = json.loads((SOURCE / 'DELAY_STORAGE_EXACT_CERTIFICATE.json').read_text())
    # Independently lift the fixed 1-ms state recurrence and held input ten times.
    A = ((Q(999, 1000), Q(1, 1000)), (Q(-1, 1000), Q(996, 1000)))
    F = [[Q(1), Q(0)], [Q(0), Q(1)]]
    g = [Q(0), Q(0)]
    for _ in range(10):
        F = [[sum(A[i][k] * F[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
        g = [sum(A[i][k] * g[k] for k in range(2)) + (Q(1, 1000) if i == 1 else 0) for i in range(2)]
    assert F == [[Q(v) for v in row] for row in document['F_A10']]
    assert g == [Q(v) for v in document['g_sum_Aj_q_j0to9']]
    alpha, kappa, rho, d0, c = Q(1, 24), Q(1, 2500), Q(1, 100), Q(49999, 50000), Q(3, 25)
    S = [[(sum(F[k][i] * F[k][j] for k in range(2)) - int(i == j)) / 2 for j in range(2)] for i in range(2)]
    v = [sum(F[k][i] * g[k] for k in range(2)) for i in range(2)]
    K = [[Q(0) for _ in range(4)] for _ in range(4)]
    K[0][0], K[1][1] = S[0][0], S[1][1] + (alpha + kappa) * c ** 2
    K[2][2] = sum(u*u for u in g) / 2 - kappa * d0 ** 2 / 4
    K[3][3] = alpha * (rho ** 2 - 2*d0*rho) + kappa * (1 + rho ** 2)
    for i, j, value in ((0, 1, abs(S[0][1])), (0, 2, abs(v[0])/2),
                        (1, 2, abs(v[1]/2 - alpha*c*d0)), (1, 3, alpha*c*rho)):
        K[i][j] = K[j][i] = value
    assert K == [[Q(v) for v in row] for row in document['K_abs_upper_exact']]
    negative = [[-v for v in row] for row in K]
    minors = [determinant([row[:n] for row in negative[:n]]) for n in range(1, 5)]
    assert minors == [Q(v) for v in document['negative_K_leading_principal_minors_exact']]
    margin = Q(1, 25000)
    shifted = [[negative[i][j] - margin * int(i == j) for j in range(4)] for i in range(4)]
    margin_minors = [determinant([row[:n] for row in shifted[:n]]) for n in range(1, 5)]
    assert all(v > 0 for v in minors + margin_minors)
    result = {
        'status': 'PASS_PARENT_EXACT_IDEAL_SUBCASE_ONLY', 'source_sha256': expected,
        'independent_algorithm': 'Ten forward lifts for F/g; Leibniz permutation determinants',
        'negative_K_minors': [str(v) for v in minors],
        'certified_mu': str(margin), 'negative_K_minus_mu_I_minors': [str(v) for v in margin_minors],
        'algebra_parent_review': 'Units, output-before-update, moving memory direction, projection residual and absolute-vector comparison agree with the stated ideal model.',
        'theory_deployment_gate': 'NOT_MET',
        'limitations': ['W*=0 and zero forcing only', 'No first-event rho term when history is absent; startup needs separate bound',
                        'No actual Plant or approximation/filter/sampling/output-limit closed-loop claim'],
        'new_Plant': 0, 'TEST_accessed': False,
    }
    target = HERE / 'PARENT_DELAY_STORAGE_EXACT_REVIEW_v1.json'
    with target.open('x', encoding='utf-8') as f:
        f.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'certified_mu': str(margin), 'theory_deployment_gate': 'NOT_MET'}))


if __name__ == '__main__':
    main()
