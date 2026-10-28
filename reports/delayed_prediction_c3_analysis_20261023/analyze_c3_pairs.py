from __future__ import annotations
import csv, hashlib, importlib.util, json, math, statistics, sys
from pathlib import Path
import numpy as np
import h5py

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXP = ROOT / 'experiments/position_delayed_prediction_c3_20261023'
PARENT = ROOT / 'reports/delayed_prediction_c3_parent_20261023'
SCORER = ROOT / 'reports/c2_deployable_residual_parent_20261023/score_c2_beta_recovered.py'
C3_LOCK = EXP / 'C3_SOURCE_LOCK.json'
C3_SUMMARY = EXP / 'C3_CONTINUE_SUMMARY.json'
C2_RECOVERY = ROOT / 'reports/c2_comparator_code_audit_20261023/C2_SCENE2_RECOVERY_REVIEW.json'
RECOVERY_SID = 'DL1018_VAL_T2_C02_W12'
TOL = 1e-12


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_csv(path: Path, rows):
    assert rows
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def check_hash(path: Path, expected: str):
    assert path.is_file(), f'missing: {path}'
    actual = sha(path)
    assert actual == expected, f'SHA mismatch {path}: {actual} != {expected}'
    return actual


def scorer_module():
    src = SCORER.read_text(encoding='utf-8-sig')
    target = "row = {'scene_id': text('scene_id'), 'raw_path': str(path), 'raw_sha256': expected_sha}"
    replacement = "row = {'scene_id': (text('scene_id') if 'scene_id' in g else None), 'raw_path': str(path), 'raw_sha256': expected_sha}"
    assert src.count(target) == 1
    ns = {'__name__': 'c3_readonly_scoring_adapter', '__file__': str(SCORER)}
    exec(compile(src.replace(target, replacement), str(SCORER), 'exec'), ns)
    return ns['score_raw'], sha(SCORER), 'In-memory one-line adapter permits B files lacking log/scene_id; labels are then assigned only from frozen C1 shared_scenes metadata. Primary scoring formulas unchanged.'


def timing(path: Path):
    with h5py.File(path, 'r') as f:
        a = np.asarray(f['log/controller_call_time_s']).ravel().astype(float)
    assert len(a) == 20000 and np.isfinite(a).all() and np.all(a >= 0)
    return {'controller_time_sum_s_nonformal': float(a.sum()),
            'controller_time_mean_ms_nonformal': float(a.mean() * 1000),
            'controller_time_p50_ms_nonformal': float(np.quantile(a, .50) * 1000),
            'controller_time_p95_ms_nonformal': float(np.quantile(a, .95) * 1000),
            'controller_time_max_ms_nonformal': float(a.max() * 1000)}


def main():
    assert not any((OUT / n).exists() for n in ('ALL36_SUPPLEMENTAL_METRICS.csv','PAIRED_THRESHOLDS.csv','SUMMARY.json')), 'Preserve prior analysis outputs; choose a new output directory if rerunning.'
    lock = load(C3_LOCK); summary = load(C3_SUMMARY)
    c1path = Path(lock['c1_source_lock']['path']); c2ledgerpath = Path(lock['c2_execution_ledger']['path'])
    check_hash(C3_LOCK, '863328963959c63d4628060fcff21e01d5322c487d077b5c20721d24ed9314a2')
    check_hash(c1path, lock['c1_source_lock']['sha256'])
    check_hash(c2ledgerpath, lock['c2_execution_ledger']['sha256'])
    c1 = load(c1path); ledger = load(c2ledgerpath)
    c1rows = {x['scene_id']: x for x in c1['shared_scenes']}
    c2rows = {x['scene_id']: x for x in ledger['run_rows']}
    assert list(lock['scene_ids']) == [x['scene_id'] for x in c1['shared_scenes']]
    assert set(c1rows) == set(c2rows) == set(lock['scene_ids'])
    assert summary['scene_ids'] == lock['scene_ids'][1:]
    cont = {x['scene_id']: x for x in summary['runs']}
    assert len(cont) == 11 and lock['probe_scene_id'] not in cont
    score_raw, scorer_sha, adapter_note = scorer_module()
    assert scorer_sha == '320755d6e570abb14c66a2abf2c3350a007f9c2cc4db750b0246de48837eddba'

    recovery = load(C2_RECOVERY)
    assert recovery['raw_usable_for_scoring'] is True
    assert recovery['raw_sha256'] == c2rows[RECOVERY_SID]['raw_sha256']
    scenes = []
    for sid in lock['scene_ids']:
        meta = c1rows[sid]; c2row = c2rows[sid]
        c2base = Path(ledger['project_root']) / ledger['run_template'].replace('<scene_id>', sid)
        c2raw = c2base / 'raw_run.mat'
        assert c2row['raw_sha256']
        assert check_hash(c2raw, c2row['raw_sha256'])
        c2status_path = c2base / 'run_status.json'
        c2status = load(c2status_path)
        c2collection = c2row['status']
        if sid == RECOVERY_SID:
            assert c2collection == 'FAILED_NO_RETRY'
            assert c2status['status'] == 'FAILED_NO_RETRY'
            assert c2status['partial_raw_sha256'] == c2row['raw_sha256']
        else:
            assert c2collection == 'STABLE' and c2status['status'] == 'STABLE'
        if sid == lock['probe_scene_id']:
            c3base = EXP / 'runs_c3' / sid / 'C3_DELAYED_PREDICTION_TAU1_RHO001' / 'attempt_01'
            c3raw = c3base / 'raw_run.mat'; c3statuspath = c3base / 'run_status.json'
            c3expected = summary['probe_raw_sha256']
            bpath = Path(meta['b_raw_path']); bexpected = meta['b_raw_sha256']
        else:
            c3entry = cont[sid]
            assert c3entry['source_lock_sha256'] == sha(C3_LOCK)
            c3raw = Path(c3entry['raw_path']); c3statuspath = Path(c3entry['run_status_path'])
            c3expected = c3entry['raw_sha256']
            assert c3entry['C2_raw_sha256'] == c2row['raw_sha256']
            assert Path(c3entry['C2_raw_path']).resolve() == c2raw.resolve()
            bpath = Path(meta['b_raw_path']); bexpected = meta['b_raw_sha256']
            assert c3entry['B_raw_sha256'] == bexpected, f'C1 B SHA differs from C3 status binding: {sid}'
        c3actual = check_hash(c3raw, c3expected)
        bactual = check_hash(bpath, bexpected)
        c3status = load(c3statuspath)
        assert c3status['scene_id'] == sid and c3status['log_status'] == 'STABLE'
        assert c3status['raw_sha256'] == c3expected
        if sid != lock['probe_scene_id']:
            assert c3status['source_lock_sha256'] == sha(C3_LOCK)
        scenes.append(dict(scene_id=sid, task=meta['task'], band=meta['band'],
            B_path=str(bpath), B_sha256=bactual, C2_path=str(c2raw), C2_sha256=c2row['raw_sha256'],
            C2_collection_status=c2collection, C2_status_path=str(c2status_path),
            C3_path=str(c3raw), C3_sha256=c3actual, C3_status_path=str(c3statuspath),
            C3_status_record_sha256=sha(c3statuspath)))

    methods = {}
    allrows = []
    for scene in scenes:
        sid = scene['scene_id']; refs=[]; ext=[]
        for method, pathkey, hashkey, checkcand in [('B','B_path','B_sha256',False),('C2','C2_path','C2_sha256',False),('C3','C3_path','C3_sha256',False)]:
            p=Path(scene[pathkey]); row, ref, external = score_raw(p, scene[hashkey], checkcand)
            rawid = row.get('scene_id')
            if method == 'B':
                assert rawid is None or rawid == sid, f'B scene identity differs from C1 metadata: {sid} {rawid}'
            else:
                assert rawid == sid, f'raw scene identity mismatch {sid} vs {rawid}'
            refs.append(ref); ext.append(external)
            row['raw_log_scene_id'] = rawid
            row['scene_id'] = sid
            row['task'] = scene['task']; row['band'] = scene['band']; row['method'] = method
            row['raw_path'] = str(p); row['raw_sha256'] = scene[hashkey]
            row['metadata_identity_source'] = ('C1_SOURCE_LOCK.shared_scenes; raw log absent' if rawid is None else 'C1_SOURCE_LOCK.shared_scenes + matching raw log') if method == 'B' else 'raw_log.scene_id + C1 metadata crosscheck'
            row['collection_status'] = scene['C2_collection_status'] if method == 'C2' else 'STABLE'
            row.update(timing(p))
            methods[(sid,method)] = row; allrows.append(row)
        assert np.array_equal(refs[0],refs[1]) and np.array_equal(refs[1],refs[2]), f'reference mismatch {sid}'
        assert len(set(ext)) == 1, f'exogenous inputs mismatch {sid}'

    paired=[]
    pair_metrics=['Q_0_20_m','Q_0_5_m','Q_5_20_m']+[f'rmse_{a}_{p}_m' for p in ('0_20','0_5','5_20') for a in 'xyz']+[
        'peak_m','p95_m','motor_saturated_fraction','generalized_clipped_fraction',
        'controller_time_sum_s_nonformal','controller_time_mean_ms_nonformal','controller_time_p95_ms_nonformal']
    for s in scenes:
        for base in ('B','C2'):
            c=methods[(s['scene_id'],'C3')]; b=methods[(s['scene_id'],base)]
            d=c['Q_0_20_m']-b['Q_0_20_m']
            pr={k:s[k] for k in ('scene_id','task','band')}
            pr.update(comparator=base, comparator_collection_status=b['collection_status'],
                delta_Q_0_20_m=d, result='WIN' if d < -TOL else 'LOSS' if d > TOL else 'TIE',
                improvement_ge_1um=bool(d <= -1e-6), improvement_ge_10um=bool(d <= -1e-5),
                deterioration_ge_1um=bool(d >= 1e-6), deterioration_ge_10um=bool(d >= 1e-5),
                absolute_delta_below_1um=bool(abs(d) < 1e-6), absolute_delta_below_10um=bool(abs(d) < 1e-5))
            for metric in pair_metrics:
                pr[f'delta_{metric}']=c[metric]-b[metric]
                pr[f'C3_{metric}']=c[metric]; pr[f'{base}_{metric}']=b[metric]
            paired.append(pr)
    losses=[r for r in paired if r['result']=='LOSS']
    write_csv(OUT/'ALL36_SUPPLEMENTAL_METRICS.csv', allrows)
    write_csv(OUT/'PAIRED_THRESHOLDS.csv', paired)
    write_csv(OUT/'LOSING_PAIRS.csv', losses)

    # Compare direct scorer primary outputs with parent-computed primary table.
    parent_rows=list(csv.DictReader((PARENT/'PARENT_ALL12_PAIRED.csv').open(encoding='utf-8-sig',newline='')))
    qcross=[]
    for p in parent_rows:
        sid=p['scene_id']
        for method,col in [('B','B_Q_m'),('C2','C2_Q_m'),('C3','C3_Q_m')]:
            got=methods[(sid,method)]['Q_0_20_m']; expected=float(p[col]); diff=got-expected
            assert abs(diff) < 1e-14, (sid,method,got,expected,diff)
            qcross.append(dict(scene_id=sid,method=method,primary_score_m=got,parent_score_m=expected,diff_m=diff,abs_diff_m=abs(diff)))
    write_csv(OUT/'PRIMARY_Q_CROSSCHECK.csv',qcross)

    # Preserve parent full axis/phase audit and recheck the two B-loss scenes.
    axisfile=PARENT/'PARENT_ALL36_AXES_PHASES.csv'
    parent_axes=list(csv.DictReader(axisfile.open(encoding='utf-8-sig',newline='')))
    axis_cross=[]
    for row in parent_axes:
        sid=row['scene_id']; method=row['method']; own=methods[(sid,method)]
        mappings={'all_Q_mm':'Q_0_20_m','early_Q_mm':'Q_0_5_m','late_Q_mm':'Q_5_20_m'}
        for field,src in mappings.items():
            own_mm=own[src]*1000; delta=own_mm-float(row[field]); assert abs(delta)<1e-9
            axis_cross.append(dict(scene_id=sid,method=method,metric=field,own_mm=own_mm,parent_mm=float(row[field]),diff_mm=delta))
        for phase,scorerphase in [('all','0_20'),('early','0_5'),('late','5_20')]:
            for axis in 'xyz':
                field=f'{phase}_{axis}_mm'; own_mm=own[f'rmse_{axis}_{scorerphase}_m']*1000
                delta=own_mm-float(row[field]); assert abs(delta)<1e-9
                axis_cross.append(dict(scene_id=sid,method=method,metric=field,own_mm=own_mm,parent_mm=float(row[field]),diff_mm=delta))
    write_csv(OUT/'AXIS_PHASE_CROSSCHECK.csv',axis_cross)

    qsum=load(PARENT/'PARENT_ALL12_Q_SUMMARY.json')
    win_summary={}
    for comparator in ('B','C2'):
        arr=[r for r in paired if r['comparator']==comparator]
        win_summary[comparator]={k:sum(r['result']==k for r in arr) for k in ('WIN','LOSS','TIE')}
        win_summary[comparator].update(improvements_ge_1um=sum(r['improvement_ge_1um'] for r in arr),
                                       improvements_ge_10um=sum(r['improvement_ge_10um'] for r in arr),
                                       deteriorations_ge_1um=sum(r['deterioration_ge_1um'] for r in arr),
                                       deteriorations_ge_10um=sum(r['deterioration_ge_10um'] for r in arr),
                                       ties_at_1e_12=sum(r['result']=='TIE' for r in arr))
    supp={m:{'mean_peak_mm':float(np.mean([methods[(s['scene_id'],m)]['peak_m'] for s in scenes])*1000),
             'mean_p95_mm':float(np.mean([methods[(s['scene_id'],m)]['p95_m'] for s in scenes])*1000),
             'mean_motor_saturated_fraction':float(np.mean([methods[(s['scene_id'],m)]['motor_saturated_fraction'] for s in scenes])),
             'mean_generalized_clipped_fraction':float(np.mean([methods[(s['scene_id'],m)]['generalized_clipped_fraction'] for s in scenes])),
             'mean_controller_time_ms_nonformal':float(np.mean([methods[(s['scene_id'],m)]['controller_time_mean_ms_nonformal'] for s in scenes])),
             'p95_controller_time_ms_nonformal':float(np.mean([methods[(s['scene_id'],m)]['controller_time_p95_ms_nonformal'] for s in scenes]))}
           for m in ('B','C2','C3')}
    summary_json={'status':'PASS_READONLY_RAW_SCORE_CROSSCHECK', 'scope':'12-scene mechanism screen only; no new Plant/training/TEST',
        'scene_count':len(scenes),'raw_score_count':len(allrows),'paired_count':len(paired), 'loss_count':len(losses),
        'primary_win_counts':win_summary,'parent_primary_summary':qsum['groups']['ALL'],
        'parent_full_q_summary_sha256':sha(PARENT/'PARENT_ALL12_Q_SUMMARY.json'),
        'parent_all36_axes_phases_sha256':sha(axisfile),
        'supplemental_means':supp,'pair_tolerance_m':TOL,
        'threshold_sensitivity':{comp:win_summary[comp] for comp in ('B','C2')},
        'all_B_losses':[{'scene_id':r['scene_id'],'delta_Q_mm':r['delta_Q_0_20_m']*1000,
            'delta_early_x_mm':r['delta_rmse_x_0_5_m']*1000,'delta_early_y_mm':r['delta_rmse_y_0_5_m']*1000,
            'delta_early_z_mm':r['delta_rmse_z_0_5_m']*1000,'delta_late_x_mm':r['delta_rmse_x_5_20_m']*1000,
            'delta_late_y_mm':r['delta_rmse_y_5_20_m']*1000,'delta_late_z_mm':r['delta_rmse_z_5_20_m']*1000,
            'delta_peak_mm':r['delta_peak_m']*1000,'delta_p95_mm':r['delta_p95_m']*1000} for r in losses if r['comparator']=='B'],
        'C2_scene2_collection_status_preserved':c2rows[RECOVERY_SID]['status'],
        'C2_scene2_raw_sha256':c2rows[RECOVERY_SID]['raw_sha256'],
        'C2_scene2_recovery_review_sha256':sha(C2_RECOVERY),
        'formal_timing_qualified':False,
        'timing_note':'controller_call_time_s is raw recorded timing; no qualification or wall-clock claim.',
        'interpretation':'12-scene screen only. 10/12 B wins = 83.3%, below 85%; no expansion to DEV72/TEST is supported by this screen.'}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary_json,indent=2,allow_nan=False)+'\n',encoding='utf-8')

    # Cross-check the existing 2-host fit replay on 3 representative scenes, not all 12.
    helperpath=PARENT/'common_input_residual.py'
    spec=importlib.util.spec_from_file_location('common_input_residual',helperpath); helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    common_parent=load(PARENT/'PARENT_ALL12_COMMON_INPUT.json'); common_map={(x['scene_id'],x['host'],x['method_weights'],x['phase']):x for x in common_parent['rows']}
    cross=[]
    selected=[lock['probe_scene_id'],'DL1018_VAL_T3_C00_W13','DL1018_VAL_T2_C05_W15']
    for sid in selected:
        status=load(Path(next(s['C3_status_path'] for s in scenes if s['scene_id']==sid)))
        fresh=helper.compare(status)
        for r in fresh['rows']:
            old=common_map[(sid,r['host'],r['method_weights'],r['phase'])]
            diff=np.asarray(r['axis_rmse_mps2'])-np.asarray(old['axis_rmse_mps2'])
            assert np.max(np.abs(diff))<1e-12,(sid,r,diff)
            cross.append(dict(scene_id=sid,host=r['host'],method_weights=r['method_weights'],phase=r['phase'],n=r['n'],
                x_rmse_mps2=r['axis_rmse_mps2'][0],y_rmse_mps2=r['axis_rmse_mps2'][1],z_rmse_mps2=r['axis_rmse_mps2'][2],
                max_abs_diff_vs_parent_mps2=float(np.max(np.abs(diff)))))
    write_csv(OUT/'COMMON_INPUT_KEY_SCENE_CROSSCHECK.csv',cross)
    manifest={'created_local':'2026-10-23','analysis_script_sha256':sha(Path(__file__)),
        'frozen_inputs':{'c3_source_lock':{'path':str(C3_LOCK),'sha256':sha(C3_LOCK)},
            'c3_continue_summary':{'path':str(C3_SUMMARY),'sha256':sha(C3_SUMMARY)},
            'c1_source_lock':{'path':str(c1path),'sha256':sha(c1path)},
            'c2_execution_ledger':{'path':str(c2ledgerpath),'sha256':sha(c2ledgerpath)},
            'primary_scorer':{'path':str(SCORER),'sha256':scorer_sha,'adapter_note':adapter_note},
            'parent_q_summary':{'path':str(PARENT/'PARENT_ALL12_Q_SUMMARY.json'),'sha256':sha(PARENT/'PARENT_ALL12_Q_SUMMARY.json')},
            'parent_axes_phase':{'path':str(axisfile),'sha256':sha(axisfile)},
            'parent_common_input':{'path':str(PARENT/'PARENT_ALL12_COMMON_INPUT.json'),'sha256':sha(PARENT/'PARENT_ALL12_COMMON_INPUT.json')},
            'common_input_helper':{'path':str(helperpath),'sha256':sha(helperpath)},
            'c2_recovery_review':{'path':str(C2_RECOVERY),'sha256':sha(C2_RECOVERY)}},
        'scored_files':scenes,'counts':{'runs':36,'pairs':24,'common_input_crosscheck_scenes':selected},
        'c2_scene2_status':'FAILED_NO_RETRY preserved; approved recovered raw scored by frozen ledger SHA.'}
    (OUT/'BINDING_MANIFEST.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':summary_json['status'],'runs':36,'pairs':24,'losses':len(losses),'win_counts':win_summary,'supplemental_means':supp,'output_dir':str(OUT)},indent=2))

if __name__=='__main__': main()




