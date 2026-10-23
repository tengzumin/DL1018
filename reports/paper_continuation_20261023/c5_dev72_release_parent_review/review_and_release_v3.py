"""Root-only verification and exact release; no MATLAB/Plant invocation."""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'experiments/position_axis_coordinate_c5_dev72_20261023'
HERE = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def ref(path):
    return dict(path=str(path), sha256=sha(path))


def write(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def main():
    release_path = RUN / 'C5_DEV72_RELEASE_v3.json'
    assert not release_path.exists()
    lock_path = RUN / 'C5_DEV72_INPUT_LOCK_v3.json'
    contract_path = RUN / 'C5_DEV72_RUN_CONTRACT_v3.json'
    binding_path = RUN / 'C5_DEV72_SOURCE_BINDING_v3.json'
    prep_path = RUN / 'C5_DEV72_PREPARE_RESULT_v3.json'
    snap = RUN / 'C5_DEV72_PREPARED_CFG_OPTS_v3.mat'
    rc_path = RUN / 'C5_DEV72_PARENT_RELEASE_CONTRACT_v3.json'
    lock, contract, binding, prep = map(load, (lock_path, contract_path, binding_path, prep_path))
    ready_path = ROOT / 'reports/paper_continuation_20261023/c5_dev72_execution/C5_DEV72_NOPLANT_OS_EXIT_v3.json'
    ready = load(ready_path)
    refs = []

    def check_tree(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                assert sha(value['path']) == value['sha256'], value['path']
                refs.append(value)
            for v in value.values():
                check_tree(v)
        elif isinstance(value, list):
            for v in value:
                check_tree(v)

    check_tree(lock['source_files'])
    check_tree(lock['upstream_refs'])
    check_tree(lock['active_source_inventory'])
    check_tree(lock['shared_input_files'])
    check_tree(ready)
    for key, path in [('input_lock', lock_path), ('run_contract', contract_path)]:
        assert binding[key + '_sha256'] == prep[key + '_sha256'] == sha(path)
    assert binding['release_contract_sha256'] == sha(rc_path)
    assert prep['source_binding_sha256'] == sha(binding_path)
    assert prep['snapshot_sha256'] == sha(snap)
    assert prep['status'] == 'PREPARED_C5_M110_DEV72_NO_PLANT_WAIT_PARENT_RELEASE_V3'
    assert (prep['cfg_leaf_count'], prep['opts_leaf_count'], prep['which_checks'],
            prep['scene_identity_count'], prep['status_jsons_checked']) == (120, 43, 31, 72, 156)
    assert prep['plant_calls'] == prep['training_steps'] == prep['optimizer_steps'] == prep['new_B_sorties'] == 0
    assert not prep['run_episode_called'] and not prep['TEST_accessed']
    os_ref = ref(ready_path)
    os_record = load(os_ref['path'])
    assert os_record['matlab_os_exit_code'] == 0 and os_record['matlab_called_once']
    assert os_record['prepare_result_sha256'] == sha(prep_path)
    assert os_record['snapshot_sha256'] == sha(snap)
    assert os_record['source_binding_sha256'] == sha(binding_path)
    c3 = load(lock['upstream_refs']['c3_input_lock']['path'])
    ids, reuse = c3['scene_ids_all_72'], lock['scene_ids_reuse_12']
    new = [s for s in ids if s not in set(reuse)]
    assert len(ids) == len(set(ids)) == 72 and len(new) == 60 and len(reuse) == 12
    assert reuse == [s for s in ids if s in set(reuse)]
    for obj in (lock, binding, prep):
        assert obj['scene_ids_all_72'] == ids and obj['scene_ids_new_60'] == new
        assert obj['scene_ids_reuse_12'] == reuse
    assert contract['scene_ids_new_60'] == new
    assert [r['scene_id'] for r in lock['scenes']] == ids
    status_count = 0
    for row in lock['scenes']:
        for kind in ('C3_reference', 'B72_scoring', 'C5_reuse'):
            item = row[kind]
            if kind == 'C5_reuse' and not item['reused']:
                continue
            assert sha(item['run_status_path']) == item['run_status_sha256']
            status = load(item['run_status_path'])
            assert status['scene_id'] == row['scene_id'] and status['status'] == 'RUN_COMPLETE_RAW_PENDING_AUDIT'
            assert status['raw_sha256'] == item['raw_sha256']
            assert status['training_steps'] == status['optimizer_steps'] == 0 and not status['TEST_accessed']
            status_count += 1
    assert status_count == 156

    decoder_path = ROOT / 'reports/paper14_v2/phase1/audit_w15_position_replay.py'
    assert sha(decoder_path) == '372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af'
    spec = importlib.util.spec_from_file_location('frozen_decoder', decoder_path)
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    old_snap = Path(lock['upstream_refs']['c5_prepared_snapshot']['path'])
    leaves = {}
    for section, count in [('cfg', 120), ('opts', 43), ('W0', 1), ('modelIdentity', None)]:
        actual = decoder.flatten(decoder.matlab_section(snap, section))
        previous = decoder.flatten(decoder.matlab_section(old_snap, section))
        assert actual.keys() == previous.keys(), section
        assert all(decoder.same_value(actual[k], previous[k]) for k in actual), section
        if count is not None:
            assert len(actual) == count
        leaves[section] = len(actual)
    w0 = decoder.matlab_section(snap, 'W0')
    assert hashlib.sha256(np.asarray(w0, dtype='<f8').tobytes(order='F')).hexdigest() == contract['model']['W0_sha256']
    screen_ref = lock['upstream_refs']['c5_screen_summary']
    screen = load(screen_ref['path'])
    assert screen['status'] == 'C5_SCREEN_PASS' and all(screen['gates'].values())
    peer_path = ROOT / 'reports/paper_continuation_20261023/c5_dev72_execution/C5_DEV72_V2_TO_V3_SOURCE_DIFF.patch'
    assert peer_path.is_file()
    runner_preflight_path = RUN / 'C5_DEV72_RUNNER_PREFLIGHT_RESULT_v3.json'
    pf = load(runner_preflight_path)
    assert pf['status'] == 'PREFLIGHT_PASS_WAIT_PARENT_RELEASE_V3' and pf['plant_calls'] == 0
    assert pf['release_presence_and_release_contract_validation_skipped']
    assert ready['runner_preflight_sha256'] == sha(runner_preflight_path)
    for key, path in [('input_lock',lock_path),('run_contract',contract_path),('prepare_result',prep_path),
                      ('snapshot',snap),('source_binding',binding_path),('runner',Path(binding['runner_path']))]:
        assert pf[key+'_sha256'] == sha(path), key
    assert not (RUN / 'runs_dev72_v3').exists()
    assert not (RUN / 'C5_DEV72_BATCH_STATUS_v3.json').exists()
    assert 'scene_ids_all_72' in load(rc_path)['exact_scene_order_source']['field']
    errata = [dict(v1='OS1 before Plant: missing runner local leaf_count',
                   v2='OS1 without Plant: copied leaf_count missing function end',
                   v3='Only orchestration repair: complete local helper, split mode guard, SHA-bound actual runner preflight; prepared main function name corrected before first v3 MATLAB',
                   prior_failures_preserved=True, actual_scientific_candidate_changed=False)]
    audit = dict(schema='C5_DEV72_ROOT_PREPARE_REVIEW_V3', status='PASS_RELEASE_FIXED_60',
                 created_utc=datetime.now(timezone.utc).isoformat(), no_plant_natural_exit=0,
                 compared_snapshot_leaf_counts=leaves, status_jsons_checked=status_count,
                 exact_order_source=lock['upstream_refs']['c3_input_lock'],
                 exact_order_field='scene_ids_all_72', documentary_errata=errata,
                 refs=[ref(p) for p in (lock_path, contract_path, binding_path, prep_path, snap, rc_path,
                                       ready_path, peer_path, runner_preflight_path, Path(__file__))],
                 verified_source_and_upstream_refs=len(refs),
                 new_Plant_in_review=0, training_steps=0, TEST_accessed=False,
                 theory_gate='CONDITIONAL_ALGEBRA_PEER_PASS_DEPLOYMENT_SCOPE_ASSESSMENT_PENDING',
                 paper_evidence_status='NOT_QUALIFIED')
    audit_path = HERE / 'PARENT_PREPARE_REVIEW_v3.json'
    write(audit_path, audit)
    release = dict(schema='C5_AXIS_COORDINATE_DEV72_PARENT_RELEASE_V3',
                   state='APPROVED_C5_M110_DEV72_V3', plant_authorized=True, max_new_Plant=60,
                   parent_release_contract_sha256=sha(rc_path), candidate=contract['candidate'],
                   coordinate_mask=[1, 1, 0], input_lock_sha256=sha(lock_path),
                   run_contract_sha256=sha(contract_path), prepare_result_sha256=sha(prep_path),
                   prepared_snapshot_sha256=sha(snap), source_binding_sha256=sha(binding_path),
                   runner_sha256=binding['runner_sha256'], runner_preflight_result_sha256=sha(runner_preflight_path), launcher_sha256=binding['plant_launcher_sha256'],
                   scene_ids_new_60=new, c5_screen_summary_sha256=screen_ref['sha256'],
                   b72_manifest_sha256=lock['b72_scoring_manifest_sha256'], training_steps=0,
                   optimizer_steps=0, parameter_or_seed_search=False, new_B_sorties=0,
                   TEST_accessed=False, automatic_retry=False, parent_review=ref(audit_path),
                   no_plant_os_record=os_ref, documentary_errata=errata,
                   deadline_utc='2026-10-24T17:01:00Z',
                   created_utc=datetime.now(timezone.utc).isoformat())
    assert set(load(rc_path)['required_fields']).issubset(release)
    write(release_path, release)
    print(json.dumps(dict(status=audit['status'], review=ref(audit_path), release=ref(release_path))))


if __name__ == '__main__':
    main()
