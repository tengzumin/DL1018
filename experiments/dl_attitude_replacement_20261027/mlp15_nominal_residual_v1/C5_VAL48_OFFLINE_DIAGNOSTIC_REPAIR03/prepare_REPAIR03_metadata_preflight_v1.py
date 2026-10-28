from __future__ import annotations
import csv, hashlib, importlib.util, io, json, os, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
STUDY=ROOT/'experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1'
DIAG=STUDY/'C5_VAL48_OFFLINE_DIAGNOSTIC_v1'
REPAIR01=STUDY/'C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR01'
REPAIR02=STUDY/'C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR02'
ADAPTER_PATH=REPAIR01/'metadata_identity_adapter_REPAIR01_v1.py'
BASE_SCORER_PATH=DIAG/'score_c5_val48_once_v1.py'
BASE_LOCK_PATH=DIAG/'C5_VAL48_SCORE_LOCK_v1.json'
DERIVED_LOCK_PATH=HERE/'C5_VAL48_SCORE_LOCK_REPAIR03_v1.json'
AUDIT_PATH=HERE/'C5_VAL48_METADATA_AUDIT_REPAIR03_v1.json'
MAPPING_PATH=HERE/'C5_VAL48_IDENTITY_MAPPING_REPAIR03_v1.csv'
RECEIPT_PATH=HERE/'C5_VAL48_PREFLIGHT_RECEIPT_REPAIR03_v1.json'
HASHES_PATH=HERE/'REPAIR03_PREPARATION_HASHES_v1.json'
PARITY=HERE/'matlab_parity'


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
    return h.hexdigest()

def load_json(path: Path): return json.loads(path.read_text(encoding='utf-8-sig'))
def canonical_path(path: Path) -> str: return os.path.normcase(os.path.normpath(str(path.resolve())))
def load_module(name: str,path: Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise ImportError(path)
    module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module

def require(ok: bool,msg: str):
    if not ok: raise RuntimeError(msg)

def main():
    import numpy as np, h5py, torch
    outputs=[AUDIT_PATH,MAPPING_PATH,RECEIPT_PATH,HASHES_PATH]
    require(not any(p.exists() for p in outputs),'refusing to overwrite existing REPAIR03 preparation artifacts')
    # Derive from the original frozen lock; only the three parity paths change.
    base=load_json(BASE_LOCK_PATH); derived=json.loads(json.dumps(base))
    old='experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/C5_VAL48_OFFLINE_DIAGNOSTIC_v1/matlab_parity/'
    new='experiments/dl_attitude_replacement_20261027/mlp15_nominal_residual_v1/C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR03/matlab_parity/'
    def move_path(path):
        require(path.startswith(old),f'unexpected frozen parity path: {path}')
        return new+path[len(old):]
    derived['matlab_parity_manifest_path']=move_path(base['matlab_parity_manifest_path'])
    derived['matlab_parity_report_path']=move_path(base['matlab_parity_report_path'])
    for i,item in enumerate(base['matlab_parity_artifacts']): derived['matlab_parity_artifacts'][i]['path']=move_path(item['path'])
    expected=json.loads(json.dumps(base)); expected['matlab_parity_manifest_path']=derived['matlab_parity_manifest_path']; expected['matlab_parity_report_path']=derived['matlab_parity_report_path']
    for i,item in enumerate(base['matlab_parity_artifacts']): expected['matlab_parity_artifacts'][i]['path']=derived['matlab_parity_artifacts'][i]['path']
    require(derived==expected,'derived score lock changed fields beyond the three parity path fields')
    manifest=PARITY/'MATLAB_PARITY_HASHES_v1.txt'
    require(sha(manifest)==base['matlab_parity_manifest_sha256'],'copied parity manifest SHA mismatch')
    manifest_entries={}
    for line in manifest.read_text(encoding='utf-8-sig').splitlines():
        parts=line.strip().split(None,1)
        if len(parts)==2 and len(parts[0])==64: manifest_entries[parts[1].strip()]=parts[0].lower()
    require(len(manifest_entries)==8,'parity payload count mismatch')
    parity_hashes={}
    for rel,expected_sha in manifest_entries.items():
        target=PARITY/rel
        require(target.is_file() and sha(target)==expected_sha,f'copied parity payload mismatch: {rel}')
        parity_hashes[target.relative_to(ROOT).as_posix()]=expected_sha
    if DERIVED_LOCK_PATH.exists():
        require(load_json(DERIVED_LOCK_PATH)==derived,'existing derived score lock differs from frozen base lock')
    else:
        DERIVED_LOCK_PATH.write_text(json.dumps(derived,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

    adapter=load_module('metadata_identity_adapter_REPAIR01_v1',ADAPTER_PATH)
    audit=adapter.audit_all()
    require(audit.get('status')=='PASS_METADATA_ONLY_IDENTITY_ADAPTER' and audit.get('source_scene_count')==48,'metadata identity audit did not PASS')
    require(audit.get('raw_status_run_start_byte_hashes_revalidated') is True,'source identity byte hashes were not revalidated')
    require(audit.get('numeric_log_or_command_arrays_opened') is False and audit.get('numeric_VAL_features_or_labels_read') is False,'audit opened numerical VAL data')
    context=adapter.load_context()
    sys.path.insert(0,str(STUDY))
    import prepare_train_data_v1 as train_builder
    train_builder.verify_run_identity=adapter.builder_verifier(context)
    scorer=load_module('score_c5_val48_once_v1_frozen',BASE_SCORER_PATH)
    scorer.OUT=HERE
    old_sha=scorer.sha
    cache={canonical_path(Path(p)):v for p,v in audit['hash_cache_for_preflight'].items()}
    def sha_with_verified_cache(path):
        key=canonical_path(Path(path))
        return cache[key] if key in cache else old_sha(Path(path))
    scorer.sha=sha_with_verified_cache
    captured=io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(captured):
        scorer.run(STUDY/'TRAINING_CONFIG_v1r1.json',STUDY/'TRAINING_FREEZE_MANIFEST_v1r1.json',DIAG/'C5_VAL48_SOURCE_FREEZE_v1.json',DIAG/'C5_VAL48_IDENTITY_CHECK_v1.json',DIAG/'C5_VAL48_EVAL_RULES_v1.json',DERIVED_LOCK_PATH,preflight_only=True)
    result=json.loads(captured.getvalue().strip().splitlines()[-1])
    require(result.get('status')=='PREFLIGHT_PASS' and result.get('source_scenes')==48 and result.get('identity_files_checked')==144 and result.get('all_identity_hashes_match') is True,'base scorer metadata preflight failed')
    require(result.get('numeric_VAL_arrays_read') is False and result.get('score_start_marker_created') is False,'base scorer preflight read VAL numbers or created marker')

    with MAPPING_PATH.open('x',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(audit['rows'][0].keys())); writer.writeheader(); writer.writerows(audit['rows'])
    AUDIT_PATH.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    receipt={
      'schema':'DL1018_MLP15_C5_VAL48_METADATA_PREFLIGHT_RECEIPT_REPAIR03_V1','status':'PASS_METADATA_ONLY_PREFLIGHT_REPAIR03',
      'source_scene_count':48,'identity_files_checked':144,'schema_counts':audit['schema_counts'],'acc_fix_alias_count':audit['acc_fix_alias_count'],
      'reused_scene_count':audit['reused_scene_count'],'fresh_batch_scene_count':audit['fresh_batch_scene_count'],
      'all_raw_status_run_start_hashes_match':True,'base_scorer_preflight':result,
      'environment':{'python':sys.version.split()[0],'executable':sys.executable,'numpy':np.__version__,'h5py':h5py.__version__,'torch':torch.__version__,'conda_env':'TCN0906'},
      'numeric_VAL_arrays_read':False,'numeric_log_or_command_arrays_opened':False,'checkpoint_weights_loaded_by_base_preflight':True,
      'score_start_marker_created':False,'scoring_started':False,'TEST_accessed':False,'Plant_called':False,'training_run':False,'closed_loop_run':False}
    RECEIPT_PATH.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def info(p): return {'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
    HASHES_PATH.write_text(json.dumps({'schema':'DL1018_MLP15_C5_VAL48_REPAIR03_PREPARATION_HASHES_V1','derived_score_lock':info(DERIVED_LOCK_PATH),'metadata_audit':info(AUDIT_PATH),'identity_mapping':info(MAPPING_PATH),'preflight_receipt':info(RECEIPT_PATH),'parity_bundle_sha256':parity_hashes},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':receipt['status'],'source_scenes':48,'identity_files_checked':144,'schema_counts':audit['schema_counts'],'alias_count':audit['acc_fix_alias_count'],'base_preflight':result.get('status'),'numeric_VAL_arrays_read':False,'marker_created':False,'receipt_sha256':sha(RECEIPT_PATH),'derived_lock_sha256':sha(DERIVED_LOCK_PATH)},indent=2))

if __name__=='__main__': main()
