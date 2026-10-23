"""Read one completed scene during a live batch; never certify batch OS exit."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def io_path(path):
    """Use an extended-length Windows path only at filesystem I/O boundaries."""
    p = Path(path)
    if os.name != 'nt':
        return p
    raw = str(p.resolve(strict=False)) if not p.is_absolute() else str(p)
    if raw.startswith('\\\\?\\') or len(raw) < 240:
        return Path(raw)
    if raw.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + raw.lstrip('\\'))
    if re.match(r'^[A-Za-z]:\\', raw):
        return Path('\\\\?\\' + raw)
    return p


def sha(path):
    with io_path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(io_path(path).read_text(encoding='utf-8-sig'))


def module(path, name, expected):
    assert sha(path) == expected
    spec = importlib.util.spec_from_file_location(name, io_path(path))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variant', choices=['C5_FREEZE_TRAINED_W0', 'C5_NO_DELAYED_PREDICTION'])
    args = parser.parse_args()
    out = HERE / f'{args.variant}_FIRST_NEW_RAW_NUMERIC_PARENT_v2.json'
    assert not io_path(out).exists()
    base = module(ROOT/'reports/paper_continuation_20261023/c5_dev72_parent_review/audit_c5_dev72_raw_parent_v4.py',
                  'first_new_base', 'd82e089c7d41f39c620daea63d95315632e6fb2f80addf4dc12e6a4603b8e57e')
    decoder = module(ROOT/'reports/paper14_v2/phase1/audit_w15_position_replay.py',
                     'first_new_decoder', '372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af')
    events = module(ROOT/'reports/paper_continuation_20261023/c5_matched_ablation_parent_raw_review/event_audit_c5_matched_ablation.py',
                    'first_new_events', '1a8106ca6df7bb75ecb7a9cf5a09b9f91bc6eaa38547917a1fab677092c3755a')
    scorer = module(ROOT/'reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py',
                    'first_new_scorer', 'c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1')
    review = HERE/'PARENT_DEV72_NOPLANT_SNAPSHOT_REVIEW_v1.json'
    assert sha(review) == '3d4c7c24b0349248d00326821bf144c93a6a4dd3c09b3784b1895551c7896274'
    approved = next(row for row in load(review)['rows'] if row['variant'] == args.variant)
    folder = ROOT/'experiments/position_c5_matched_ablations_dev72_v3_20261023'/args.variant
    lock_path = folder/'C5_ABLATION_DEV72_INPUT_LOCK_v3.json'
    snapshot = folder/'C5_ABLATION_DEV72_PREPARED_CFG_OPTS_v3.mat'
    assert sha(lock_path) == approved['digests']['lock']
    assert sha(snapshot) == approved['digests']['snapshot']
    lock = load(lock_path)
    scene_id = lock['scene_ids_remaining_60'][0]
    row = next(row for row in lock['scenes'] if row['scene_id'] == scene_id)
    status_path = folder/'runs_c5_matched_ablation_dev72_v3'/scene_id/args.variant/'attempt_01/run_status.json'
    status = load(status_path)
    assert status['status'] == 'RUN_COMPLETE_RAW_PENDING_AUDIT' and status['log_status'] == 'STABLE'
    assert status['phase'] == 'REMAINING60' and status['batch_index'] == status['plant_calls'] == 1
    assert status['scene_id'] == scene_id and status['variant_id'] == args.variant
    assert status['transitions'] == 20000 and status['state_samples'] == 20001
    assert not status['TEST_accessed'] and status['training_steps'] == status['optimizer_steps'] == 0
    assert status['actual_weight_update_enabled'] is (args.variant == 'C5_NO_DELAYED_PREDICTION')
    assert status['actual_prediction_gradient_enabled'] is False
    for key in ('raw', 'run_start', 'attempt_started_marker', 'first_plant_step_marker'):
        assert sha(status[f'{key}_path']) == status[f'{key}_sha256']
    start = base.matlab_section_safe(status['run_start_path'], 'runStart', decoder)
    with h5py.File(io_path(snapshot), 'r') as mat:
        pack = {key: base.h5_tree_cell_safe(mat[key]) for key in
                ('cfg', 'opts', 'modelIdentity', 'sceneIdentity', 'sourceIdentity', 'W0')}
    counts = {}
    for key, other, expected in (('cfg', 'cfg', 120), ('opts', 'opts', 43), ('modelIdentity', 'model_identity', 6)):
        counts[key] = base.equal_tree(pack[key], start[other], decoder, ignore_marker=key == 'opts')
        assert counts[key] == expected
    counts['sourceIdentity'] = base.equal_tree(pack['sourceIdentity'], start['source_identity'], decoder)
    assert np.array_equal(np.asarray(pack['W0']), np.asarray(start['W0']))
    identity = base.scene_identity_row(pack['sceneIdentity'], lock['scene_ids_all_72'].index(scene_id))
    base.compare_scene_identity(start['scene_identity'], identity, decoder)
    assert set(identity) == {'B_raw_path', 'B_raw_sha256', 'alias_normalized_in_memory',
                             'canonical_scene_id', 'payload_review_sha256', 'raw_scene_id', 'scene_id'}
    metric = scorer.score({'scene_id': scene_id, 'method': args.variant,
                           'path': status['raw_path'], 'sha256': status['raw_sha256']})
    assert metric['external_identity_sha256'] == row['external_identity_sha256']
    check = events.audit_events(status['raw_path'], start['cfg'], args.variant, np.asarray(pack['W0']), approved['W0_sha256'])
    assert check['event_count'] == 1968
    result = {'status': 'PASS_SINGLE_COMPLETED_RAW_SNAPSHOT_AND_ALL_EVENTS', 'variant': args.variant,
              'scene_id': scene_id, 'status_sha256': sha(status_path), 'raw_sha256': status['raw_sha256'],
              'leaf_counts': counts, 'metric': metric, 'event_check': check,
              'batch_OS_exit_reviewed': False, 'not_a_final_DEV72_verdict': True,
              'checker_sha256': sha(Path(__file__)), 'Plant_started': False, 'TEST_accessed': False}
    with io_path(out).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'out': str(out), 'sha256': sha(out), 'Q_m': metric['Q_0_20_m']}))


if __name__ == '__main__':
    main()
