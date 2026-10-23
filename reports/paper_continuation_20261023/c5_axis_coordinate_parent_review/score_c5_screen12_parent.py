"""Parent recomputation of every fixed C5 screening scene and preregistered gate."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RUN = ROOT / 'experiments/position_axis_coordinate_c5_20261023'
TOL = 1e-12


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def write_csv(path, rows, fields=None):
    with path.open('x', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    output = HERE / 'screen12_parent_review'
    assert not output.exists(), 'Preserve prior screening evidence'
    contract_path = RUN / 'C5_AXIS_COORDINATE_RUN_CONTRACT_v1.json'
    contract = load(contract_path)
    ids = contract['scene_ids']
    assert len(ids) == len(set(ids)) == 12
    checker_path = HERE / 'check_c5_raw_parent.py'
    first_release = load(RUN / 'C5_FIRST_PARENT_RELEASE_v1.json')
    assert sha(checker_path) == next(r['sha256'] for r in first_release['parent_review_and_validation_refs']
                                    if Path(r['path']).name == checker_path.name)
    checker = module(checker_path, 'frozen_c5_all_event_checker')
    decoder = module(ROOT / 'reports/paper14_v2/phase1/audit_w15_position_replay.py', 'frozen_c5_mat_decoder')
    release_path = RUN / 'C5_TAIL11_RELEASE_v2.json'
    release = load(release_path)
    release_sha = sha(release_path)
    assert release_sha == '4f6dc42467bc0ea5acd0b392d1d947f81f5bc4f4bf52d2e9933564de759b49a3'
    exit_path = RUN / 'C5_TAIL11_OS_EXIT_v2.json'
    exit_record = load(exit_path)
    assert exit_record['matlab_os_exit_code'] == exit_record['launcher_exit_code'] == 0
    assert exit_record['completed_scenes'] == exit_record['plant_calls'] == 11
    assert exit_record['shared_matlab_process_count'] == 1 and exit_record['per_scene_exit_record_count'] == 11
    assert exit_record['parent_release_sha256'] == release_sha and not exit_record['finalization_error']
    body_path = RUN / 'C5_TAIL11_BODY_COMPLETE_v2.json'
    body = load(body_path)
    assert body['shared_matlab_os_exit_code'] == 0 and body['matlab_process_count'] == 1
    assert body['completed_scenes'] == body['plant_calls'] == 11
    assert body['tail_release_sha256'] == release_sha
    body_rows = {r['scene_id']: r for r in body['per_scene_exit_records']}
    assert list(body_rows) == release['tail_scene_ids']
    c4_path = HERE.parent / 'c4_coordinate_parent_review/screen12_parent_review/SUMMARY.json'
    assert sha(c4_path) == '616e70afbb3b2d07b7837641c3f6ef579a1e03888fa5014b30627805eccfc44b'
    c4_rows = {r['scene_id']: r for r in load(c4_path)['audits']}
    audits, metrics, pairs = [], [], []
    for sid in ids:
        status_path = RUN / 'runs_c5_v1' / sid / 'C5_AXIS_MASK_M110/attempt_01/run_status.json'
        status = load(status_path)
        audit = checker.verify(status_path)
        if sid != contract['first_scene_id']:
            rec = body_rows[sid]
            assert rec['run_status_sha256'] == sha(status_path)
            assert rec['raw_sha256'] == status['raw_sha256']
            assert rec['batch_scope'] == 'ONE_SEQUENTIAL_MATLAB_PROCESS' and rec['shared_matlab_os_exit_code'] == 0
            assert status['tail_release_sha256'] == release_sha
            assert status['source_binding_sha256'] == release['tail_source_binding_sha256']
            identity = decoder.matlab_section(Path(status['raw_path']), 'runIdentity')
            start = decoder.matlab_section(Path(status['run_start_path']), 'runStart')
            for section in ('source_identity', 'model_identity', 'scene_identity', 'W0'):
                a, b = decoder.flatten(identity[section]), decoder.flatten(start[section])
                assert a.keys() == b.keys() and all(decoder.same_value(a[k], b[k]) for k in a), (sid, section)
            for section in ('tail_release_sha256', 'source_binding_sha256', 'run_start_sha256', 'scoring_B72_raw_sha256'):
                assert identity[section][2] == (status['scoring_B72_raw_sha256'] if section == 'scoring_B72_raw_sha256'
                                               else status[section]), (sid, section)
        audits.append(audit)
        for method in ('C5', 'C3', 'B'):
            metrics.append(dict(audit[method + '_metrics']))
        c4 = c4_rows[sid]['C4_metrics']
        assert c4['external_identity_sha256'] == audit['C5_metrics']['external_identity_sha256']
        metrics.append(dict(c4))
        delta = audit['Q_C5_minus_B_m']
        pairs.append(dict(scene_id=sid, Q_C5_m=audit['C5_metrics']['Q_0_20_m'],
                          Q_C3_m=audit['C3_metrics']['Q_0_20_m'], Q_B_m=audit['B_metrics']['Q_0_20_m'],
                          Q_C4_m=c4['Q_0_20_m'], Q_C5_minus_B_m=delta,
                          Q_C5_minus_C3_m=audit['Q_C5_minus_C3_m'], Z_C5_minus_C3_m=audit['Z_C5_minus_C3_m'],
                          C5_vs_B='WIN' if delta < -TOL else 'LOSS' if delta > TOL else 'TIE'))
        print(json.dumps({'scene_id': sid, 'event_audit': audit['status'], 'Q_C5_minus_B_m': delta}), flush=True)
    sets = {'ALL12': ids, 'HF6': [s for s in ids if 9 <= int(s[-2:]) <= 14],
            'W15': [s for s in ids if s.endswith('W15')]}
    sets.update({'T' + str(t): [s for s in ids if '_T' + str(t) + '_' in s] for t in (1, 2, 3)})
    sets.update({wind: [s for s in ids if s.endswith(wind)] for wind in sorted({s[-3:] for s in ids})})
    assert len(sets['HF6']) == 6 and len(sets['W15']) == 3
    groups = {}
    for name, selected in sets.items():
        selected_pairs = [r for r in pairs if r['scene_id'] in selected]
        groups[name] = dict(n=len(selected), **{m: float(np.mean([r['Q_' + m + '_m'] for r in selected_pairs]))
                                               for m in ('C5', 'C3', 'C4', 'B')},
                            C5_wins_vs_B=sum(r['C5_vs_B'] == 'WIN' for r in selected_pairs))
    fig8 = [r for r in audits if r['scene_id'] in ('DL1018_VAL_T2_C00_W10', 'DL1018_VAL_T2_C02_W12')]
    assert len(fig8) == 2
    gates = {
        'both_FIG8_HF_Q_and_Z_strictly_lower_than_C3': all(r['Q_C5_minus_C3_m'] < -TOL and r['Z_C5_minus_C3_m'] < -TOL for r in fig8),
        'ALL12_mean_Q_no_higher_than_C3': groups['ALL12']['C5'] <= groups['ALL12']['C3'] + TOL,
        'HF6_mean_Q_no_higher_than_B': groups['HF6']['C5'] <= groups['HF6']['B'] + TOL,
        'W15_mean_Q_no_higher_than_B': groups['W15']['C5'] <= groups['W15']['B'] + TOL,
        'all_12_complete_finite_STABLE_full_event_audits': all(r['status'] == 'PASS_C5_RAW_ALL_EVENTS' for r in audits),
    }
    summary = dict(status='C5_SCREEN_PASS' if all(gates.values()) else 'C5_SCREEN_FAIL_NO_DEV72_EXTENSION',
                   gates=gates, groups=groups, wins_vs_B=sum(r['C5_vs_B'] == 'WIN' for r in pairs),
                   wins_with_improvement_gt_1um=sum(r['Q_C5_minus_B_m'] < -1e-6 for r in pairs),
                   wins_with_improvement_gt_10um=sum(r['Q_C5_minus_B_m'] < -1e-5 for r in pairs),
                   tolerance_m=TOL, event_count=sum(r['event_count'] for r in audits),
                   max_raw_check_abs_error=max(max(r['checks'].values()) for r in audits),
                   B_identity_status='PARENT_AUDITED_NEW_TRACEABLE_B72', timing_qualification='NONISOLATED_NOT_FORMAL',
                   new_Plant_in_audit=0, training=0, TEST_accessed=False,
                   refs=[dict(path=str(p), sha256=sha(p)) for p in (contract_path, checker_path, Path(__file__), release_path, exit_path, body_path, c4_path)],
                   audits=audits)
    output.mkdir()
    (output / 'SUMMARY.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    write_csv(output / 'ALL48_METRICS.csv', metrics)
    write_csv(output / 'ALL12_PAIRS.csv', pairs)
    write_csv(output / 'ALL_LOSSES_VS_B.csv', [r for r in pairs if r['C5_vs_B'] == 'LOSS'], fields=list(pairs[0]))
    print(json.dumps({k: summary[k] for k in ('status', 'gates', 'groups', 'wins_vs_B', 'event_count')}), flush=True)


if __name__ == '__main__':
    main()
