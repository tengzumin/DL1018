from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from scipy.io import savemat

HERE = Path(__file__).resolve().parent
N = 1999
DT = np.float64

def make_model():
    rng = np.random.default_rng(20261027)
    return {
        'input_mean': rng.normal(0.0, 0.08, 13).astype(DT),
        'input_std': rng.uniform(0.65, 1.45, 13).astype(DT),
        'target_rms': np.array([8.0, 8.0, 2.0], dtype=DT),
        'gru_weight_ih': rng.normal(0.0, 0.045, (96, 13)).astype(DT),
        'gru_weight_hh': rng.normal(0.0, 0.04, (96, 32)).astype(DT),
        'gru_bias_ih': rng.normal(0.0, 0.012, 96).astype(DT),
        'gru_bias_hh': rng.normal(0.0, 0.012, 96).astype(DT),
        'head_weight': rng.normal(0.0, 0.045, (3, 32)).astype(DT),
        'head_bias': np.array([7.0, -6.0, 3.0], dtype=DT),
    }

def forward_one(feature_norm, hidden, model, dtype=np.float64):
    cast = dtype
    x = np.asarray(feature_norm, dtype=cast).reshape(13)
    h = np.asarray(hidden, dtype=cast).reshape(32)
    wih = np.asarray(model['gru_weight_ih'], dtype=cast)
    whh = np.asarray(model['gru_weight_hh'], dtype=cast)
    bih = np.asarray(model['gru_bias_ih'], dtype=cast).reshape(96)
    bhh = np.asarray(model['gru_bias_hh'], dtype=cast).reshape(96)
    gi = wih @ x + bih
    gh = whh @ h + bhh
    reset = cast(1) / (cast(1) + np.exp(-(gi[:32] + gh[:32])))
    update = cast(1) / (cast(1) + np.exp(-(gi[32:64] + gh[32:64])))
    new_state = np.tanh(gi[64:96] + reset * gh[64:96])
    next_hidden = (cast(1) - update) * new_state + update * h
    out = (np.asarray(model['head_weight'], dtype=cast) @ next_hidden +
           np.asarray(model['head_bias'], dtype=cast).reshape(3)) * np.asarray(model['target_rms'], dtype=cast).reshape(3)
    return out, next_hidden

def stream(features, model, dtype=np.float64):
    cast = dtype
    hidden = np.zeros(32, dtype=cast)
    outputs = np.empty((len(features), 3), dtype=cast)
    states = np.empty((len(features), 32), dtype=cast)
    mean = np.asarray(model['input_mean'], dtype=cast)
    std = np.asarray(model['input_std'], dtype=cast)
    for i, feature in enumerate(features):
        normalized = (np.asarray(feature, dtype=cast) - mean) / std
        outputs[i], hidden = forward_one(normalized, hidden, model, dtype=cast)
        states[i] = hidden
    return outputs, states

def main():
    rng = np.random.default_rng(3701027)
    t = np.arange(N, dtype=DT)
    features = rng.normal(0.0, 0.22, (N, 13)).astype(DT)
    features += (0.08 * np.sin(0.009 * t[:, None] + np.arange(13)[None, :] * 0.31)).astype(DT)
    model = make_model()
    output, hidden = stream(features, model)
    output_repeat, hidden_repeat = stream(features, model)
    assert np.array_equal(output, output_repeat) and np.array_equal(hidden, hidden_repeat)
    beta = np.minimum((np.arange(1, N + 1, dtype=DT) * 0.01) / 2.2, 1.0)
    dmax = np.array([45.0, 45.0, 4.7124], dtype=DT)
    J0 = np.array([[0.003257553333333334, 0.0, 0.0],
                   [0.0, 0.0032575533333333334, 0.0],
                   [0.0, 0.0, 0.006360648333333333]], dtype=DT)
    clipped = np.clip(output, -dmax, dmax)
    torque = (J0 @ (beta[:, None] * clipped).T).T
    perturbed = features.copy()
    perturb_index = 1000
    perturbed[perturb_index] += np.linspace(-0.8, 0.9, 13)
    changed_output, changed_hidden = stream(perturbed, model)
    prefix_output_error = float(np.max(np.abs(output[:perturb_index] - changed_output[:perturb_index])))
    prefix_hidden_error = float(np.max(np.abs(hidden[:perturb_index] - changed_hidden[:perturb_index])))
    assert prefix_output_error == 0.0 and prefix_hidden_error == 0.0
    output32, hidden32 = stream(features, model, dtype=np.float32)
    float32_output_error = float(np.max(np.abs(output - output32.astype(DT))))
    float32_hidden_error = float(np.max(np.abs(hidden - hidden32.astype(DT))))
    assert float32_output_error < 1e-4 and float32_hidden_error < 1e-5
    max_hold_carry_error = float(np.max(np.abs(hidden[1:] - hidden[:-1])))
    # One scene starts from zero; a second run resets to the identical first event.
    assert np.array_equal(stream(features, model)[0], output)
    fixture = HERE / 'toy_gru_fixture_v1.mat'
    mat_model = {key: np.asarray(value).reshape(1, -1) if key in ('input_mean', 'input_std', 'target_rms', 'gru_bias_ih', 'gru_bias_hh', 'head_bias') else value for key, value in model.items()}
    savemat(fixture, {**mat_model,
        'input_features_raw': features,
        'expected_output_raw_rad_s2': output,
        'expected_hidden_double': hidden,
        'expected_torque_Nm': torque,
        'expected_beta': beta.reshape(-1, 1),
        'fixed_J0': J0,
        'dmax': dmax.reshape(1, -1),
        'future_perturbed_features_raw': perturbed,
        'future_perturb_index_zero_based': np.array([[perturb_index]], dtype=np.int32),
        'scene_id': 'TOY_RESET_CAUSALITY_ONLY',
    }, do_compression=True, oned_as='row')
    report = {
        'status': 'PASS_PYTHON_TOY_GRU_REFERENCE',
        'training_started': False, 'Plant_calls': 0, 'TEST_read': False,
        'fixture_path': str(fixture), 'fixture_sha256': __import__('hashlib').sha256(fixture.read_bytes()).hexdigest(),
        'sequence_events': N, 'feature_dim': 13, 'hidden_dim': 32,
        'weights_are_toy_only': True, 'per_event_hidden_carry_checked': True,
        'scene_reset_repeat_exact': True,
        'future_input_prefix_output_max_abs': prefix_output_error,
        'future_input_prefix_hidden_max_abs': prefix_hidden_error,
        'float32_vs_double_output_max_abs': float32_output_error,
        'float32_vs_double_hidden_max_abs': float32_hidden_error,
        'double_hidden_trajectory_shape': list(hidden.shape),
        'saturated_acceleration_sample_count': int(np.count_nonzero(np.any(np.abs(output) > dmax, axis=1))),
        'applied_torque_order': 'J0 * (beta * clip(rawResidual,-dmax,+dmax))',
    }
    report_path = HERE / 'TOY_PYTHON_REFERENCE_v1.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()