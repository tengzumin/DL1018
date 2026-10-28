"""Batch C3 raw audit; refuses to open candidate raws until the batch is terminal."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPORT = ROOT / 'reports' / 'delayed_prediction_c3_parent_20261023'
C3 = ROOT / 'experiments' / 'position_delayed_prediction_c3_20261023'
LOCK = C3 / 'C3_SOURCE_LOCK.json'
CONTRACT = C3 / 'C3_RUN_CONTRACT.json'
RELEASE = C3 / 'C3_CONTINUE_RELEASE_v2.json'
RUNNER = C3 / 'run_c3_continue_v2.m'
V1_FAILURE = C3 / 'C3_CONTINUE_ATTEMPT_01.json'
PREPARE = C3 / 'C3_PREPARE_RESULT.json'
SNAPSHOT = C3 / 'C3_PREPARED_CONFIG_OPTS.mat'
PROBE_AUDIT = REPORT / 'PROBE_RAW_AUDIT.json'
C2_SCENE2_RECOVERY = ROOT / 'reports' / 'c2_comparator_code_audit_20261023' / 'C2_SCENE2_RECOVERY_REVIEW.json'
C2_SCENE2_RECOVERY_SHA = '2105f1eb4b6ce0ee29dab04066e06c3fde47f3ec8e298293f6b945f3495a4ec4'
VERIFIER = REPORT / 'verify_c3_raw.py'
VERIFIER_SHA = '275de5a3e56fd3c1e41f62f6a2a5f5ad95d44416dc022a4f6daace1e46f77b96'
OUT = HERE / 'C3_CONTINUE_BATCH_REVIEW.json'
OUTDIR = HERE / 'c3_continue_scene_audits'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def same_path(a, b):
    return Path(a).resolve().as_posix().casefold() == Path(b).resolve().as_posix().casefold()


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2, allow_nan=False)
        f.write('\n')


def main():
    assert not OUT.exists() and not OUTDIR.exists(), 'refusing to overwrite prior review outputs'
    lock, contract, release = read(LOCK), read(CONTRACT), read(RELEASE)
    lock_sha, release_sha = sha(LOCK), sha(RELEASE)
    assert sha(RUNNER).lower() == release['runner_sha256'].lower()
    assert lock_sha.lower() == release['source_lock_sha256'].lower()
    assert sha(PREPARE).lower() == release['prepare_result_sha256'].lower()
    assert sha(SNAPSHOT).lower() == release['cfg_opts_snapshot_sha256'].lower()
    assert sha(C3 / 'C3_PROBE_RELEASE.json').lower() == release['probe_release_sha256'].lower()
    assert sha(PROBE_AUDIT).lower() == release['probe_raw_audit_sha256'].lower()
    assert sha(VERIFIER).lower() == VERIFIER_SHA
    assert release['schema'] == 'C3_DELAYED_PREDICTION_CONTINUE_RELEASE_V2'
    assert release['state'] == 'APPROVED_C3_CONTINUE' and release['plant_authorized'] is True
    assert release['max_new_sorties'] == 11 and release['probe_sorties_already_run'] == 1
    assert release['total_sortie_cap'] == 12 and not release['full72_authorized'] and not release['TEST_authorized']
    assert release['training_steps'] == release['optimizer_steps'] == 0 and not release['gain_or_seed_search']
    assert release['formal_timing_qualified'] is False and release['no_automatic_retry'] is True
    assert same_path(release['prior_failed_attempt_path'], V1_FAILURE)
    assert sha(V1_FAILURE).lower() == release['prior_failed_attempt_sha256'].lower()
    prior = read(V1_FAILURE)
    assert prior['outcome'] == 'FAILED_PREFLIGHT_BEFORE_CONTINUATION_PLANT'
    assert prior['plant_calls_in_this_attempt'] == 0
    assert prior['continuation_attempt_markers'] == prior['continuation_first_plant_markers'] == 0
    assert prior['automatic_retry'] is False
    assert sha(C3 / 'C3_CONTINUE_RELEASE.json').lower() == prior['release_sha256'].lower()
    old_release = read(C3 / 'C3_CONTINUE_RELEASE.json')
    assert prior['runner_sha256'].lower() == old_release['runner_sha256'].lower()
    assert same_path(lock['run_contract_path'], CONTRACT)
    assert sha(CONTRACT).lower() == lock['run_contract_sha256'].lower()
    assert sha(lock['c2_source_lock']['path']).lower() == lock['c2_source_lock']['sha256'].lower()
    assert sha(lock['c1_source_lock']['path']).lower() == lock['c1_source_lock']['sha256'].lower()
    assert sha(lock['c2_release']['path']).lower() == lock['c2_release']['sha256'].lower()
    assert sha(lock['c1_release']['path']).lower() == lock['c1_release']['sha256'].lower()
    assert sha(C2_SCENE2_RECOVERY).lower() == C2_SCENE2_RECOVERY_SHA
    recovery = read(C2_SCENE2_RECOVERY)
    recovered_scene = 'DL1018_VAL_T2_C02_W12'
    assert recovery['scene_id'] == recovered_scene
    assert recovery['collection_status_original'] == 'FAILED_NO_RETRY'
    assert recovery['collection_success'] is False and recovery['raw_usable_for_scoring'] is True
    assert recovery['raw_runtime_checks']['runtime_status'] == 'STABLE'
    assert recovery['raw_runtime_checks']['transition_count'] == 20000
    assert recovery['raw_runtime_checks']['valid_event_count'] == 1968

    progress_path, summary_path = C3 / 'C3_CONTINUE_PROGRESS.json', C3 / 'C3_CONTINUE_SUMMARY.json'
    progress = read(progress_path) if progress_path.is_file() else None
    summary = read(summary_path) if summary_path.is_file() else None
    success = bool(progress and summary and progress.get('status') == summary.get('status') ==
                    'ALL_11_COMPLETE_RAW_PENDING_AUDIT')
    if not success:
        assert progress and progress.get('status') == 'FAILED_NO_RETRY', \
            'continue is still running/incomplete; no candidate raw was opened'
        write_new(OUT, {
            'status': 'FAILED_NO_RETRY_RAW_NOT_AUDITED',
            'failure': progress.get('failure', {}),
            'completed_scene_count': progress.get('completed_scene_count', 0),
            'completed_runs': progress.get('runs', []),
            'release_sha256': release_sha, 'source_lock_sha256': lock_sha,
            'raw_files_opened': 0,
        })
        return

    c1lock = read(lock['c1_source_lock']['path'])
    ledger_path = Path(lock['c2_execution_ledger']['path'])
    assert sha(ledger_path).lower() == lock['c2_execution_ledger']['sha256'].lower()
    ledger = read(ledger_path)
    scenes = list(lock['scene_ids'])
    assert scenes == [x['scene_id'] for x in c1lock['shared_scenes']]
    assert progress['scene_ids'] == summary['scene_ids'] == scenes[1:]
    assert progress['scene_indices_1based'] == summary['scene_indices_1based'] == list(range(2, 13))
    assert progress['completed_scene_count'] == summary['completed_scene_count'] == 11
    probe = read(PROBE_AUDIT)
    assert probe['status'] == 'PASS_RAW_AUDIT' and probe['metrics']['scene_id'] == scenes[0]
    assert probe['metrics']['raw_sha256'].lower() == release['probe_raw_sha256'].lower()

    scene_rows, audits = [], []
    for index, scene in enumerate(scenes[1:], start=2):
        lock_rows = [r for r in lock['c2_baseline_runs'] if r['scene_id'] == scene]
        ledger_rows = [r for r in ledger['run_rows'] if r['scene_id'] == scene]
        b_rows = [r for r in c1lock['shared_scenes'] if r['scene_id'] == scene]
        assert len(lock_rows) == len(ledger_rows) == len(b_rows) == 1
        cr, lr, br = lock_rows[0], ledger_rows[0], b_rows[0]
        recovered = scene == recovered_scene
        if recovered:
            five = recovery['five_file_identity']
            assert cr['status'] == lr['status'] == 'FAILED_NO_RETRY'
            assert cr['raw_sha256'].lower() == recovery['raw_sha256'].lower() == five['raw']['sha256'].lower()
            assert same_path(cr['raw_path'], five['raw']['path'])
            assert cr['run_start_sha256'].lower() == five['run_start']['sha256'].lower()
            assert same_path(cr['run_start_path'], five['run_start']['path'])
        else:
            assert cr['status'] == lr['status'] == 'STABLE'
        assert cr['raw_sha256'].lower() == lr['raw_sha256'].lower()
        assert cr['run_start_sha256'].lower() == lr['run_start_sha256'].lower()
        attempt = C3 / 'runs_c3' / scene / contract['candidate_condition_id'] / 'attempt_01'
        status_path = attempt / 'run_status.json'
        st = read(status_path)
        assert st['status'] == 'RUN_COMPLETE_RAW_PENDING_AUDIT' and st['log_status'] == 'STABLE'
        assert st['scene_id'] == scene and st['global_scene_index_1based'] == index
        assert st['condition'] == contract['candidate_condition_id'] and st['plant_calls'] == 1
        assert st['training_steps'] == st['optimizer_steps'] == 0 and not st['TEST_accessed']
        assert st['source_lock_sha256'].lower() == lock_sha.lower()
        assert st['continuation_release_sha256'].lower() == release_sha.lower()
        assert st['C2_raw_sha256'].lower() == cr['raw_sha256'].lower() == lr['raw_sha256'].lower()
        assert same_path(st['C2_raw_path'], cr['raw_path'])
        assert st['C2_run_start_sha256'].lower() == cr['run_start_sha256'].lower()
        assert st['B_raw_sha256'].lower() == br['b_raw_sha256'].lower()
        assert same_path(st['B_raw_path'], br['b_raw_path'])
        raw, start = Path(st['raw_path']), Path(st['run_start_path'])
        marker = Path(st['first_plant_step_marker_path'])
        assert same_path(raw, attempt / 'raw_run.mat') and same_path(start, attempt / 'run_start.mat')
        assert same_path(marker, attempt / 'first_plant_step.marker')
        assert start.is_file() and sha(start).lower() == st['run_start_sha256'].lower()
        assert marker.is_file() and sha(marker).lower() == st['first_plant_step_marker_sha256'].lower()
        assert (attempt / 'attempt_started.marker').is_file() and not (attempt / 'C3_CONTINUE_FAILURE.json').exists()
        assert [x for x in progress['runs'] if x['scene_id'] == scene] == [st]
        assert [x for x in summary['runs'] if x['scene_id'] == scene] == [st]
        scene_rows.append((scene, st, raw, br, cr, lr))

    attempts = [p for p in (C3 / 'runs_c3').glob('**/attempt_*') if p.is_dir()]
    assert len(attempts) == 12
    assert len(list((C3 / 'runs_c3').glob('**/attempt_started.marker'))) == 12
    assert len(list((C3 / 'runs_c3').glob('**/first_plant_step.marker'))) == 12
    assert not list((C3 / 'runs_c3').glob('**/attempt_02'))

    # Terminal progress+summary are required above, so no raw can still be written by this runner.
    OUTDIR.mkdir()
    for index, (scene, st, raw, br, cr, lr) in enumerate(scene_rows, start=2):
        recovered = scene == recovered_scene
        before = raw.stat()
        assert sha(raw).lower() == st['raw_sha256'].lower()
        out = OUTDIR / f'{index:02d}_{scene}.json'
        cmd = [sys.executable, '-B', str(VERIFIER), str(raw), str(out),
               '--candidate-sha256', st['raw_sha256'], '--c2-raw', cr['raw_path'],
               '--c2-sha256', lr['raw_sha256']]
        subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
        after = raw.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        assert sha(raw).lower() == st['raw_sha256'].lower()
        audit = read(out)
        assert audit['status'] == 'PASS_RAW_AUDIT' and audit['metrics']['scene_id'] == scene
        assert audit['event_count'] == 1968
        assert audit['metrics']['raw_sha256'].lower() == st['raw_sha256'].lower()
        audits.append({
            'scene_id': scene, 'task': br['task'], 'wind_band': br['band'],
            'C2_collection_status': cr['status'],
            'C2_raw_scoring_status': 'RECOVERED_STABLE_RAW' if recovered else 'STABLE',
            'C2_recovery_review_sha256': C2_SCENE2_RECOVERY_SHA if recovered else '',
            'raw_sha256': st['raw_sha256'], 'raw_audit_sha256': sha(out),
            'run_status_sha256': sha(C3 / 'runs_c3' / scene / contract['candidate_condition_id'] / 'attempt_01' / 'run_status.json'),
            'run_start_sha256': st['run_start_sha256'],
            'first_plant_step_marker_sha256': st['first_plant_step_marker_sha256'],
            'c2_raw_sha256': lr['raw_sha256'], 'external_identity_sha256': audit['external_identity_sha256'],
            'event_count': audit['event_count'], 'checks': audit['checks'], 'metrics': audit['metrics'],
            'motor_saturated_fraction': audit['metrics']['motor_saturated_fraction'],
            'generalized_clipped_fraction': audit['metrics']['generalized_clipped_fraction'],
            'timing_qualification': audit['timing_qualification'],
        })

    all_rows = [{'scene_id': scenes[0], 'task': c1lock['shared_scenes'][0]['task'],
                 'wind_band': c1lock['shared_scenes'][0]['band'],
                 'raw_sha256': probe['metrics']['raw_sha256'],
                 'raw_audit_sha256': sha(PROBE_AUDIT), 'external_identity_sha256': probe['external_identity_sha256'],
                 'event_count': probe['event_count'], 'checks': probe['checks'], 'metrics': probe['metrics'],
                 'motor_saturated_fraction': probe['metrics']['motor_saturated_fraction'],
                 'generalized_clipped_fraction': probe['metrics']['generalized_clipped_fraction'],
                 'timing_qualification': probe['timing_qualification'], 'raw_audit_status': probe['status']}] + audits
    groups = {}
    for row in all_rows:
        key = (row['task'], row['wind_band'])
        g = groups.setdefault(key, {'task': key[0], 'wind_band': key[1], 'scene_ids': [],
                                    'all_raw_audits_pass': True, 'max_motor_saturated_fraction': 0.0,
                                    'max_generalized_clipped_fraction': 0.0})
        g['scene_ids'].append(row['scene_id'])
        g['all_raw_audits_pass'] &= row.get('raw_audit_status', 'PASS_RAW_AUDIT') == 'PASS_RAW_AUDIT'
        g['max_motor_saturated_fraction'] = max(g['max_motor_saturated_fraction'], row['motor_saturated_fraction'])
        g['max_generalized_clipped_fraction'] = max(g['max_generalized_clipped_fraction'], row['generalized_clipped_fraction'])
    result = {
        'status': 'PASS_12_SCENE_BATCH_RAW_AUDIT', 'release_sha256': release_sha,
        'runner_sha256': release['runner_sha256'], 'source_lock_sha256': lock_sha,
        'contract_sha256': sha(CONTRACT), 'prepare_result_sha256': sha(PREPARE),
        'snapshot_sha256': sha(SNAPSHOT), 'probe_audit_sha256': sha(PROBE_AUDIT),
        'c2_ledger_sha256': lock['c2_execution_ledger']['sha256'],
        'scene_count': len(all_rows), 'new_raws_audited': len(audits), 'failed_scenes': [],
        'C2_collection_failures_with_scoring_recovery': [{
            'scene_id': recovered_scene, 'collection_status_original': recovery['collection_status_original'],
            'raw_usable_for_scoring': recovery['raw_usable_for_scoring'],
            'raw_sha256': recovery['raw_sha256'], 'recovery_review_sha256': C2_SCENE2_RECOVERY_SHA,
        }],
        'optimizer_steps': 0, 'TEST_accessed': False, 'timing_qualification': 'NONISOLATED_NOT_FORMAL',
        'scenes': all_rows, 'task_wind_groups': list(groups.values()),
        'interpretation_limit': 'Verifies raw identity, safety fields, event targets, applied output and discrete updates; it does not establish causal performance improvement or formal timing qualification.'
    }
    write_new(OUT, result)


if __name__ == '__main__':
    main()
