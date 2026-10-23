"""Curate closed DEV72 evidence; never stages Git or includes active TEST code."""
from pathlib import Path
import hashlib
import json
import os
import re

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
OUT = BASE / 'GIT_CLOSED_FULL_ABLATION_MANIFEST_v1.json'
PATHS = BASE / 'GIT_CLOSED_FULL_ABLATION_PATHS_v1.txt'
assert not OUT.exists() and not PATHS.exists()
def extended(p):
    return '\\\\?\\' + str(p.resolve()) if os.name == 'nt' else str(p)

folders = [ROOT / 'experiments' / n for n in (
    'position_c5_matched_ablations_dev72_20261023',
    'position_c5_matched_ablations_dev72_v2_20261023',
    'position_c5_matched_ablations_dev72_v3_20261023')]
folders += [BASE / n for n in (
    'c5_matched_ablation_execution', 'c5_matched_ablation_dev72_parent_review',
    'test_readiness_readonly')]
allowed = {'.m', '.py', '.ps1', '.json', '.md', '.csv', '.patch', '.pdf', '.png', '.marker', '.log'}
paths = {ROOT / '.gitattributes'}
for p in BASE.iterdir():
    if p.is_file() and p.suffix in allowed and not p.name.startswith('GIT_'):
        paths.add(p)
for folder in folders:
    assert folder.is_dir(), folder
    for parent, dirs, files in os.walk(extended(folder)):
        dirs[:] = [d for d in dirs if not any(s in d.lower() for s in ('prefdir','fixture','__pycache__','.git'))]
        for name in files:
            raw = str(Path(parent) / name)
            if raw.startswith('\\\\?\\'):
                raw = raw[4:]
            p = Path(raw)
            if p.suffix.lower() in allowed and not any(s in name.lower() for s in ('fixture','prefdir','__pycache__')):
                paths.add(p)
for n in ('PEER_REVIEW_v1_ZH.md', 'PEER_REVIEW_v1_ZH.json'):
    paths.add(BASE / 'final_contribution_peer_max' / n)
entries = []
for p in sorted(paths):
    data = Path(extended(p)).read_bytes()
    assert len(data) < 20_000_000, (p,len(data))
    assert p.suffix.lower() not in {'.mat','.npz','.pt','.pth','.ckpt','.pem','.key'}
    assert not any(s in str(p.relative_to(ROOT)).lower() for s in ('prefdir','fixture','__pycache__'))
    if p.suffix.lower() not in {'.pdf','.png'}:
        assert not re.search(rb'-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----',data),p
    entries.append(dict(path=p.relative_to(ROOT).as_posix(),size=len(data),sha256=hashlib.sha256(data).hexdigest()))
manifest=dict(scope='Closed DEV72 full matched ablations and failures, root theory/physical bridge/contribution decisions and read-only TEST readiness. Active TEST implementation excluded.',files=entries,file_count=len(entries),bytes=sum(x['size'] for x in entries),TEST_accessed=False,Plant_started=False,excluded_mat_checkpoint_cache_fixture_prefdir=True)
OUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
PATHS.write_text('\n'.join(x['path'] for x in entries)+'\n'+OUT.relative_to(ROOT).as_posix()+'\n',encoding='utf-8')
print(json.dumps(dict(files=len(entries)+1,bytes=manifest['bytes'],manifest=str(OUT),pathspec=str(PATHS))))
