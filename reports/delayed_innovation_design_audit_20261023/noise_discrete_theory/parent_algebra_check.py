"""Deterministic algebra checks, no model/optimizer/controller execution."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def clip(x, bound=3.0):
    return max(-bound, min(bound, x))


def check(name, weight, ideal_weight, beta, target):
    residual = beta * clip(weight) - target
    gradient = beta * float(abs(weight) < 3) * residual
    inner = (weight - ideal_weight) * gradient
    # Directional derivative along minus-gradient, not an optimizer step.
    eps = 1e-6
    def objective(w):
        return .5 * (beta * clip(w) - target)**2
    numeric = (objective(weight-eps*gradient)-objective(weight+eps*gradient))/(2*eps)
    assert abs(numeric + gradient**2) < 1e-9
    return {'name': name, 'weight': weight, 'physical_ideal_weight': ideal_weight,
            'beta': beta, 'target': target, 'residual': residual, 'gradient': gradient,
            'parameter_error_gradient_inner_product': inner,
            'prediction_loss_derivative_along_minus_gradient': -gradient**2,
            'half_parameter_energy_derivative_along_minus_gradient': -inner,
            'finite_difference_directional_derivative': numeric}


def main():
    rows = [check('PHYSICAL_TARGET_NOT_BETA_SCALED', 1.5, 1., .5, 1.),
            check('MATCHED_BETA_SCALED_TARGET_DIFFERENT_ASSUMPTION', 1.5, 1., .5, .5),
            check('SATURATED_ESTIMATE_ZERO_INNOVATION', 4., 0., 1., 0.)]
    assert rows[0]['prediction_loss_derivative_along_minus_gradient'] < 0
    assert rows[0]['half_parameter_energy_derivative_along_minus_gradient'] > 0
    assert rows[1]['half_parameter_energy_derivative_along_minus_gradient'] < 0
    assert rows[2]['residual'] != 0 and rows[2]['gradient'] == 0
    # Projection inequality requires comparator in the projection set.
    outside_ideal, unprojected = 61., 61.
    projected = clip(unprojected, 60.)
    outside_before, outside_after = (unprojected-outside_ideal)**2, (projected-outside_ideal)**2
    assert outside_after > outside_before
    result = {'status': 'PASS_DETERMINISTIC_ALGEBRA_ONLY', 'cases': rows,
              'projection_outside_comparator_example': {
                  'box_bound': 60., 'ideal': outside_ideal, 'unprojected': unprojected,
                  'projected': projected, 'distance_squared_before': outside_before,
                  'distance_squared_after': outside_after},
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'resource_scope': {'Plant': 0, 'MATLAB': 0, 'training': 0, 'optimizer': 0,
                                 'gain_search': 0, 'accumulated_weight_updates': 0,
                                 'raw_reads': 0, 'TEST': 0},
              'limits': 'Scalar constructed cases can embed into a unit-feature 33x3 head. They disprove unconditional claims, not establish causes or improvements in logged trajectories.'}
    with (HERE / 'PARENT_ALGEBRA_CHECK.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(result['status'])


if __name__ == '__main__':
    main()
