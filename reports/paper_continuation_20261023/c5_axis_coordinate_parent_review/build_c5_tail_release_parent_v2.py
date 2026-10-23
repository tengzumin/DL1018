"""Release only the versioned, field-corrected C5 tail; preserve the failed v1."""
import importlib.util
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frozen_tail_v1_parent_helpers', HERE / 'build_c5_tail_release_parent.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def normalize(text):
    text = text.replace('C5_TAIL11_FAILURE_V2.json', 'C5_TAIL11_FAILURE.json')
    text = text.replace('matlab_prefdir_tail11_v2', 'matlab_prefdir_tail11_v1')
    return re.sub(r'(?i)(c5_tail11\w*_v)2\b', r'\g<1>1', text)


def main():
    run = h.EXP
    output = run / 'C5_TAIL11_RELEASE_v2.json'
    assert not output.exists()
    assert h.sha(run / 'C5_TAIL11_RELEASE_v1.json') == '4e36f44c1b50a1f703865d751298420545bf169190a8c6a5d8f57490f8b7d2a5'
    ready_path = h.EXEC / 'C5_TAIL11_CODE_READY_v3.json'
    assert h.sha(ready_path) == 'fa614513e2ea86058c0c678c578ad89ff0392a46229bb3e78c39bd96115826e8'
    ready = h.load(ready_path)
    binding = h.load(run / 'C5_TAIL11_SOURCE_BINDING_v2.json')
    contract = h.load(run / 'C5_TAIL11_RUN_CONTRACT_v2.json')
    release_contract = h.load(run / 'C5_TAIL11_PARENT_RELEASE_CONTRACT_v2.json')
    for document in (ready, binding, contract):
        h.verify_tree(document)
    old_binding = h.load(run / 'C5_TAIL11_SOURCE_BINDING_v1.json')
    for key in ('active_source_inventory', 'shared_input_files', 'lock_upstream_refs', 'pilot_refs', 'b72', 'tail_scene_ids'):
        assert binding[key] == old_binding[key], key
    runner = run / 'run_c5_tail11_v2.m'
    old_runner = (run / 'run_c5_tail11_v1.m').read_text(encoding='utf-8-sig')
    assert normalize(runner.read_text(encoding='utf-8-sig')) == old_runner.replace(
        'metaReview.prepared_snapshot_sha256', 'rawReview.prepared_snapshot_sha256')
    launcher = run / 'RUN_C5_TAIL11_EXACT_v2.ps1'
    assert normalize(launcher.read_text(encoding='utf-8-sig')) == (run / 'RUN_C5_TAIL11_EXACT_v1.ps1').read_text(encoding='utf-8-sig')
    for name in ('C5_TAIL11_RUN_CONTRACT', 'C5_TAIL11_PARENT_RELEASE_CONTRACT'):
        old, new = h.load(run / (name + '_v1.json')), h.load(run / (name + '_v2.json'))
        old.pop('created_utc', None)
        new.pop('created_utc', None)
        import json
        assert h.load(run / (name + '_v1.json')).get('candidate') == h.load(run / (name + '_v2.json')).get('candidate')
        assert json.loads(normalize(json.dumps(new))) == old
    failure = h.load(run / 'C5_TAIL11_PREFLIGHT_FAILURE_v1.json')
    assert failure['plant_calls'] == 0 and failure['identifier'] == 'MATLAB:nonExistentField'
    assert h.load(run / 'C5_TAIL11_OS_EXIT_v1.json')['matlab_os_exit_code'] == 1
    release = h.load(run / 'C5_TAIL11_RELEASE_v1.json')
    for field in ('parent_source_review', 'code_ready'):
        release.pop(field)
    roles = {r['role']: r for r in binding['source_files']}
    release.update(schema=release_contract['parent_release_schema'], state=release_contract['required_release_state'],
                   created_utc=datetime.now(timezone.utc).isoformat(),
                   tail_runner_path=str(runner), tail_runner_sha256=h.sha(runner), launcher_sha256=h.sha(launcher),
                   tail_source_binding_sha256=h.sha(run / 'C5_TAIL11_SOURCE_BINDING_v2.json'),
                   tail_run_contract_sha256=roles['tail_contract']['sha256'],
                   parent_release_contract_sha256=roles['parent_release_contract']['sha256'])
    assert set(release_contract['required_fields']) <= set(release)
    for key, value in release_contract['required_values'].items():
        assert release[key] == value, key
    refs = binding['pilot_refs']
    json_paths = {
        'metaReview': refs['metadata_os_review']['path'], 'rawReview': refs['raw_review']['path'],
        'pilot': refs['run_status']['path'], 'osExit': refs['matlab_os_exit']['path'],
        'receipt': refs['execution_receipt']['path'], 'history': refs['outer_invocation_history']['path'],
        'firstRelease': run / 'C5_FIRST_PARENT_RELEASE_v1.json',
    }
    counts = {}
    source = runner.read_text()
    for var in [*json_paths, 'release']:
        data = release if var == 'release' else h.load(json_paths[var])
        fields = set(re.findall(r'\b' + var + r'\.([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)', source))
        counts[var] = len(fields)
        for field in fields:
            if var == 'pilot' and field in ('scene_identity', 'run_start'):
                continue  # Explicitly assigned at the end of verify_c5_first_pilot.
            value = data
            for key in field.split('.'):
                assert isinstance(value, dict) and key in value, var + '.' + field
                value = value[key]
    assert h.load(refs['raw_review']['path'])['prepared_snapshot_sha256'] == release['cfg_opts_snapshot_sha256']
    for sid in release['tail_scene_ids']:
        assert not (run / 'runs_c5_v1' / sid / 'C5_AXIS_MASK_M110/attempt_01').exists()
    for suffix in ('BATCH_STATUS', 'BODY_COMPLETE', 'OS_EXIT', 'PREFLIGHT_FAILURE'):
        assert not (run / ('C5_TAIL11_' + suffix + '_v2.json')).exists()
    h.verify_tree(release)
    review_path = HERE / 'PARENT_C5_TAIL11_SOURCE_REVIEW_v2.json'
    h.write_new(review_path, dict(status='PASS_PARENT_C5_TAIL11_V2_SINGLE_FIELD_REPAIR',
                                verified_unique_files=len(h.CACHE), verified_file_sha256=h.CACHE.copy(),
                                JSON_field_reference_counts=counts, all_actual_JSON_fields_exist=True,
                                normalized_source_diff='Only rawReview snapshot-field correction; tail-only versioned paths/schemas',
                                prior_failed_MATLAB_launches=1, prior_failed_Plant_calls=0,
                                new_Plant_in_this_review=0, TEST_accessed=False))
    release['parent_source_review'] = {'path': str(review_path), 'sha256': h.sha(review_path)}
    release['code_ready'] = {'path': str(ready_path), 'sha256': h.sha(ready_path)}
    h.write_new(output, release)
    print({'status': 'APPROVED_C5_TAIL11_V2', 'release_sha256': h.sha(output), 'files': len(h.CACHE)})


if __name__ == '__main__':
    main()
