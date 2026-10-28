"""Prepare isolated one-call copies; release each only after its predecessor passes."""
from pathlib import Path
import json
import shutil
import sys

from helper_parity_v2 import sha
from score_call_v2 import SCENES, SCORE_SOURCE, CONSTANTS

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, doc):
    if path.exists():
        raise RuntimeError(f'Refusing to overwrite {path}')
    path.write_text(json.dumps(doc,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def verify_no_plant():
    r=read(HERE/'RELEASE.json')
    lock=HERE/'SOURCE_LOCK_v2.json'
    assert r['authorized_Plant_calls']==r['Plant_calls']==r['potential_budget_calls']==0
    assert sha(lock)==r['source_lock_sha256']
    for item in read(lock)['files']:
        assert sha(Path(item['path']))==item['sha256'], f"No-Plant source changed: {item['path']}"
    for scene in SCENES:
        audit=read(HERE/'audits'/f'{scene}_no_plant.json')
        assert audit['status']=='PASS_FULL_RUNNER_NOPLANT_BOUNDARY' and audit['Plant_calls']==0
        assert audit['source_lock_sha256']==sha(lock) and audit['release_sha256']==sha(HERE/'RELEASE.json')


def initialize():
    verify_no_plant()
    assert not any((HERE/f'r{i}').exists() for i in range(3))
    src=HERE/'candidate_runner_work'
    prepared=(src/'matlab/runtime/prepare_causal_n4_scene_no_plant.m').read_text(encoding='utf-8')
    replacements=[
        ('function prepared=prepare_causal_n4_scene_no_plant(sceneId)', 'function prepared=prepare_causal_n4_scene_single_call(sceneId)'),
        ("'DL1018_CAUSAL_N4_GATE_NOPLANT_V2'", "'DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2'"),
        ("'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT'", "'RELEASED'"),
        ('numel(authorized)==3', 'numel(authorized)==1'),
        ('any(strcmp(authorized,sceneId))&&release.authorized_Plant_calls==0&&release.Plant_calls==0&& ...',
         "any(strcmp(authorized,sceneId))&&strcmp(release.fixed_scene_id,sceneId)&&release.authorized_Plant_calls==1&&release.Plant_calls==1&& ..."),
        ('opts.no_plant_boundary_check=true;', 'opts.no_plant_boundary_check=false;'),
        ("opts.composite_attempt_marker=fullfile(studyRoot,'audits',[sceneId '_marker.json']);", "opts.composite_attempt_marker='';"),
    ]
    for old,new in replacements:
        assert prepared.count(old)==1,old
        prepared=prepared.replace(old,new)
    for i,scene in enumerate(SCENES):
        case=HERE/f'r{i}'
        case.mkdir()
        shutil.copytree(src,case/'candidate_runner_work')
        runtime=case/'candidate_runner_work/matlab/runtime'
        (runtime/'prepare_causal_n4_scene_single_call.m').write_text(prepared,encoding='utf-8',newline='\n')
        shutil.copy2(HERE/'run_causal_n4_single_call.m',runtime/'run_causal_n4_single_call.m')
        (case/'bindings').mkdir()
        shutil.copy2(HERE/'bindings'/f'{scene}.json',case/'bindings'/f'{scene}.json')
    print('Initialized three identical isolated runners; no Plant called.')


def release_one(scene):
    verify_no_plant()
    assert scene in SCENES
    i=SCENES.index(scene);case=HERE/f'r{i}'
    assert case.is_dir() and not (case/'RELEASE.json').exists() and not (case/'SOURCE_LOCK_SINGLE_v2.json').exists()
    assert not (case/'runs').exists()
    previous=[]
    for k in range(i):
        prev=HERE/f'r{k}'
        score=prev/'SCORE_v2.json';result=read(score)
        assert result['scene_id']==SCENES[k] and result['status']=='PASS_FIXED_CAUSAL_GATE_SCENE'
        raw=prev/'runs'/SCENES[k]/'attempt_01/raw_run.mat'
        status=prev/'runs'/SCENES[k]/'attempt_01/run_status.json'
        assert sha(raw)==result['raw_sha256'] and sha(status)==result['run_status_sha256']
        previous.extend((score,raw,status))
    source=HERE/'candidate_runner_work';copy=case/'candidate_runner_work'
    for orig in source.rglob('*'):
        if orig.is_file():
            duplicate=copy/orig.relative_to(source)
            assert duplicate.is_file() and sha(duplicate)==sha(orig), f'Copied no-Plant source differs: {orig}'
    sources={p for p in copy.rglob('*') if p.is_file()}
    sources.add(case/'bindings'/f'{scene}.json')
    sources.update(Path(item['path']) for item in read(HERE/'SOURCE_LOCK_v2.json')['files'])
    prior=HERE/'audits'/f'{scene}_no_plant.json'
    sources.update({HERE/'SOURCE_LOCK_v2.json', HERE/'RELEASE.json',prior,HERE/'CALL_PROTOCOL_v2.json',
        HERE/'run_causal_n4_single_call.m',HERE/'setup_calls_v2.py',HERE/'score_call_v2.py',SCORE_SOURCE,CONSTANTS})
    sources.update(previous)
    files=[{'path':str(p.resolve()),'sha256':sha(p)} for p in sorted(sources,key=lambda p:str(p).lower())]
    lock=case/'SOURCE_LOCK_SINGLE_v2.json'
    write(lock,{'study_id':'causal_n4_gate_v2','scene_id':scene,'files':files})
    release=read(HERE/'RELEASE.json')
    release.update({'schema':'DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2','status':'RELEASED',
        'fixed_scene_id':scene,'authorized_scenes':[scene],'authorized_Plant_calls':1,'Plant_calls':1,
        'potential_budget_calls':1,'source_lock_sha256':sha(lock),
        'prior_no_plant_preflight_path':str(prior.resolve()),'prior_no_plant_preflight_sha256':sha(prior),
        'call_protocol_sha256':sha(HERE/'CALL_PROTOCOL_v2.json')})
    write(case/'RELEASE.json',release)
    print(json.dumps({'scene_id':scene,'release_sha256':sha(case/'RELEASE.json'),
        'source_lock_sha256':sha(lock),'locked_files':len(files),'authorized_Plant_calls':1},indent=2))


if __name__=='__main__':
    if sys.argv[1:]==['--init']:
        initialize()
    elif len(sys.argv)==3 and sys.argv[1]=='--release':
        release_one(sys.argv[2])
    else:
        raise SystemExit('usage: setup_calls_v2.py --init | --release <scene>')
