"""Independent DEV first-flight check; retain the pinned C5 checks except C6's one update term."""
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def main():
    source = ROOT / 'reports/paper_continuation_20261023/test_raw_review_v1/audit_test48_raw_v1.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == '31229d1b9d137ec2847b25b7a32c3d0183e517fac963dc2ed01de74bcde11d45'
    spec = importlib.util.spec_from_file_location('parent_pinned_helpers', source)
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    _, c, _, decoder, pins = v.verify_helpers()
    old = inspect.getsource(c.event_audit)
    before = '- .00002 * wb - .01 * gradient, -60, 60)'
    after = '- .00002 * wb - .01 * beta[:, None, None] * gradient, -60, 60)'
    assert old.count(before) == 1
    updated = old.replace(before, after)
    namespace = dict(c.__dict__)
    exec(compile(updated, str(Path(__file__).resolve()) + ':C6_single_factor', 'exec'), namespace)
    receipt = v.load_json(HERE / 'C6_FIRST_SCENE_EXECUTION_RECEIPT_v1.json')
    ref = receipt['artifacts']['raw']
    raw = Path(ref['path'])
    assert v.sha256_file(raw) == ref['sha256']
    snapshot = ROOT / 'experiments/c5_eight_loss_recovery_20261024/c6_startup_ramp/C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat'
    assert v.sha256_file(snapshot) == 'f6ad61507b1d9027abb6bb2e4f5fc30d8558c0820fe663e0a2deb3a62b84255b'
    cfg = v.mat_section(snapshot, 'cfg', c, decoder)
    w0 = v.mat_section(snapshot, 'W0', c, decoder)
    result = namespace['event_audit'](raw, cfg, expected_w0=w0,
        expected_w0_sha256='88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53')
    result.pop('initial_weight')
    output = {'status': 'PASS_PARENT_C6_FIRST_1968_EVENTS', 'result': result,
        'raw_sha256': ref['sha256'], 'prepared_snapshot_sha256': v.sha256_file(snapshot),
        'inherited_function_sha256': hashlib.sha256(old.encode()).hexdigest(),
        'single_change': {'before': before, 'after': after}, 'helper_pins': pins,
        'prediction_term_norm_log_interpretation': 'Unscaled reference gradient norm; actual update multiplies beta.',
        'TEST_accessed': False, 'tail_authorized': False}
    with (HERE / 'PARENT_FIRST_1968_EVENT_CHECK_v1.json').open('x', encoding='utf-8') as f:
        json.dump(v.json_safe(output), f, ensure_ascii=False, indent=2)
    print(output['status'])


if __name__ == '__main__':
    main()
