"""Check the exact isolated launcher repair and its original probe identity."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / 'experiments/position_beta_clock_c2_20261023'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old = (EXP / 'run_c2_beta.m').read_bytes()
    expected = old
    replacements = [
        (b'function summary = run_c2_beta(mode)', b'function summary = run_c2_beta_v2(mode)'),
        (b"mode=upper(char(mode)); assert(ismember(mode,{'PROBE','CONTINUE'}),'C2:Mode','Mode must be PROBE or CONTINUE.');",
         b"mode=upper(char(mode)); assert(strcmp(mode,'CONTINUE'),'C2:Mode','v2 runner only allows CONTINUE.');"),
        (b"releasePath=fullfile(here,'C2_RELEASE_v1.json');", b"releasePath=fullfile(here,'C2_RELEASE_v2.json');"),
        (b"['C2_' mode '_APPROVAL.json']", b"['C2_' mode '_APPROVAL_v2.json']"),
        (b'verify_completed_probe(probeSummaryPath,probeSummarySha,here,lock,release,contract);',
         b'verify_completed_probe(probeSummaryPath,probeSummarySha,here,c1lock,release,contract);'),
        (b"['preflight_c2_' lower(mode) '.json']", b"['preflight_c2_' lower(mode) '_v2.json']"),
    ]
    for before, after in replacements:
        assert expected.count(before) == 1
        expected = expected.replace(before, after)
    assert expected == (EXP / 'run_c2_beta_v2.m').read_bytes()
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    lock = read(EXP / 'C2_SOURCE_LOCK.json')
    c1 = read(Path(lock['c1_source_lock']['path']))
    assert 'shared_scenes' not in lock
    sid = c1['shared_scenes'][0]['scene_id']
    probe = read(EXP / 'reports/C2_PROBE_SUMMARY.json')
    assert probe['status'] == 'PROBE_COMPLETE' and probe['completed_runs'] == 1
    assert probe['release_sha256'] == sha(EXP / 'C2_RELEASE_v1.json')
    row = probe['run_rows']
    assert row['scene_id'] == sid and row['status'] == 'STABLE'
    for prefix in ['raw', 'run_start', 'run_status', 'r2e_first_plant_step_marker']:
        assert sha(Path(row[prefix + '_path'])) == row[prefix + '_sha256']
    out = {'status': 'PASS_EXACT_SIX_EDITS_AND_ORIGINAL_PROBE_IDENTITIES',
           'runner_v2_sha256': sha(EXP / 'run_c2_beta_v2.m'),
           'repair': 'pass verified c1lock containing shared_scenes to probe verifier',
           'original_probe_scene_id': sid, 'new_Plant': 0}
    target = Path(__file__).with_name('C2_RESUME_REPAIR_PARENT_CHECK.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(out, stream, indent=2)
    print(json.dumps(out))


if __name__ == '__main__':
    main()
