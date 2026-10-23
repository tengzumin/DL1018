"""Verify the frozen pathwise perturbation certificate without rewriting author outputs."""
import hashlib
import json
from fractions import Fraction as Q
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE.parent / 'delay_storage_perturbation'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ids = json.loads((SOURCE / 'SOURCE_IDS.json').read_text())
    refs = [ids['taskbook'], *ids['frozen_sources'], *ids['deliverables']]
    for ref in refs:
        assert sha(ROOT / ref['path']) == ref['sha256'].lower(), ref['path']
    cert = json.loads((SOURCE / 'PERTURBATION_EXACT_CERTIFICATE.json').read_text())
    ideal = json.loads((HERE.parent / 'delay_aware_energy_diagnosis/DELAY_STORAGE_EXACT_CERTIFICATE.json').read_text())
    parent = json.loads((HERE / 'PARENT_DELAY_STORAGE_EXACT_REVIEW_v1.json').read_text())
    assert Q(cert['fixed_margin_mu']) == Q(parent['certified_mu']) == Q(1, 25000)
    F = [[Q(x) for x in row] for row in ideal['F_A10']]
    g = [Q(x) for x in ideal['g_sum_Aj_q_j0to9']]
    alpha, kappa, c, d0, rho, zeta = Q(1, 24), Q(1, 2500), Q(3, 25), Q(49999, 50000), Q(1, 100), Q(1, 50000)
    nu = alpha * (1 - d0**2)
    Lx = sum(abs(v) for row in F for v in row) + sum(abs(v) for v in g)
    Lm = d0 + rho + c
    Cz, Bw = kappa * Lm + 2*alpha*c, 2*alpha*(d0+rho)
    expected = {
        'Lx_upper_for_norm_Fx_plus_g_beta_a': Lx,
        'LX_upper_for_delayed_memory_scalar_vector': Lm,
        'Cz_memory_plus_weight_z_cross': Cz, 'Bw_weight_w_cross': Bw,
        'C_dx_squared': Q(1, 2) + Lx**2/(2*zeta),
        'C_dw_squared': alpha + Cz**2/(2*zeta) + Bw**2/(2*nu),
    }
    for name, value in expected.items():
        assert Q(cert['norm_bounds'][name]) == value, name
    assert Q(cert['remaining_state_dissipation_mu_minus_zeta']) == zeta
    assert Q(cert['remaining_weight_dissipation_after_Young_nu_w_over_2']) == nu/2
    result = dict(status='PASS_PARENT_PATHWISE_PERTURBATION_ALGEBRA_ONLY',
                  verified_source_refs=len(refs), Cx=float(expected['C_dx_squared']), Cw=float(expected['C_dw_squared']),
                  parent_review='Signs of old target residual, translated projection, separate first event, held ramp/output clip, summed state cross budget and Q indexing consistent.',
                  limitations=['Forcing still depends on the actual path; no prior Plant stability certificate',
                               'Current ideal sampled target telescopes exactly: xi=0 apart from floating accumulation; no diagnosed physical label error',
                               'Conservative coefficients not numerically instantiated here; no new raw reads'],
                  theory_deployment_gate='NOT_MET', new_Plant=0, TEST_accessed=False,
                  report_sha256=sha(SOURCE/'DELAY_STORAGE_PERTURBATION_BOUND_ZH.md'),
                  certificate_sha256=sha(SOURCE/'PERTURBATION_EXACT_CERTIFICATE.json'))
    with (HERE / 'PARENT_PERTURBATION_REVIEW_v1.json').open('x', encoding='utf-8') as f:
        f.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
