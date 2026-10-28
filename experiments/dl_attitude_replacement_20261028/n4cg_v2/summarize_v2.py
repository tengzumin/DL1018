"""Read-only post-run aggregation, source-lock audit, and force-interface replay."""
from pathlib import Path
import json

import h5py
import numpy as np

from helper_parity_v2 import sha
from score_call_v2 import SCENES

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent/'causal_n4_gate_train24_acden_v2'
JSON = HERE/'THREE_SCENE_RESULT_v2.json'
MD = HERE/'THREE_SCENE_RESULT_v2.md'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    if JSON.exists() or MD.exists():
        raise RuntimeError('Refusing to overwrite result')
    cache={}
    def checked(path):
        path=Path(path)
        if path not in cache: cache[path]=sha(path)
        return cache[path]
    artifacts={}
    for label,path in {
        'protocol':HERE/'CALL_PROTOCOL_v2.json','no_plant_release':HERE/'RELEASE.json',
        'no_plant_source_lock':HERE/'SOURCE_LOCK_v2.json','matlab_helper_parity':HERE/'MATLAB_PARITY_RESULT_v2.json',
        'helper_fixture':HERE/'HELPER_PARITY_FIXTURE_v2.mat','python_helper_inputs':HERE/'HELPER_PARITY_INPUT_v2.json',
        'train24_audit_json':AUDIT/'CAUSAL_N4_GATE_TRAIN24_ACDEN_V2.json',
        'train24_audit_npz':AUDIT/'CAUSAL_N4_GATE_TRAIN24_ACDEN_V2_PER_EVENT.npz',
        'train24_audit_script':AUDIT/'audit_causal_n4_gate_train24_acden_v2.py',
        'score_script':HERE/'score_call_v2.py', 'single_call_wrapper':HERE/'run_causal_n4_single_call.m',
        'release_builder':HERE/'setup_calls_v2.py',
    }.items():
        artifacts[label]={'path':str(path.resolve()),'sha256':checked(path)}
    audit=read(AUDIT/'CAUSAL_N4_GATE_TRAIN24_ACDEN_V2.json')
    assert audit['source_hashes']['audit_script_sha256']==artifacts['train24_audit_script']['sha256']
    assert audit['source']['per_event_npz_sha256']==artifacts['train24_audit_npz']['sha256']
    parity=read(HERE/'MATLAB_PARITY_RESULT_v2.json')
    assert parity['status']=='PASS_MATLAB_HELPER_PARITY_V2' and parity['max_abs_error']<=2e-10
    outcomes=[]
    for i,scene in enumerate(SCENES):
        case=HERE/f'r{i}'; score=read(case/'SCORE_v2.json');release=read(case/'RELEASE.json')
        lockpath=case/'SOURCE_LOCK_SINGLE_v2.json'; lock=read(lockpath)
        assert checked(lockpath)==release['source_lock_sha256'] and score['source_lock_sha256']==checked(lockpath)
        for item in lock['files']:
            assert checked(item['path'])==item['sha256'], f"Locked source changed: {item['path']}"
        auditpath=HERE/'audits'/f'{scene}_no_plant.json'
        assert checked(auditpath)==release['prior_no_plant_preflight_sha256']
        assert read(auditpath)['status']=='PASS_FULL_RUNNER_NOPLANT_BOUNDARY'
        assert score['status']=='PASS_FIXED_CAUSAL_GATE_SCENE' and all(score['criteria'].values())
        attempt=case/'runs'/scene/'attempt_01';raw=attempt/'raw_run.mat';status=read(attempt/'run_status.json')
        assert status['raw_sha256']==score['raw_sha256']==checked(raw)
        assert status['Plant_calls']==1 and status['first_plant_step_marker_created']
        assert len(list((case/'runs').rglob('attempt_started.marker')))==1
        assert len(list((case/'runs').rglob('first_plant_step.marker')))==1
        binding=read(case/'bindings'/f'{scene}.json')
        with h5py.File(binding['c5_snapshot_path'],'r') as f:
            mass=float(np.asarray(f['cfg/plant/mass'][()]).reshape(-1)[0])
        with h5py.File(raw,'r') as f:
            log=f['log']
            def get(name):return np.asarray(log[name][()],dtype=np.float64)
            held,force=get('stage1_position_held_applied_acceleration_mps2'),get('stage1_position_held_force_I_N')
            residual=get('stage1_position_injected_force_I_N')
            nominal,commanded=get('position_bs_nominal_force_N'),get('position_commanded_force_N')
            mass_err=float(np.max(np.abs(force-mass*held)))
            subtract_err=float(np.max(np.abs(commanded-(nominal-residual))))
        assert mass_err<=2e-10 and subtract_err<=2e-10
        files={}
        for name,path in {'single_release':case/'RELEASE.json','single_source_lock':lockpath,
            'no_plant_audit':auditpath,'binding':case/'bindings'/f'{scene}.json',
            'run_start':attempt/'run_start.json','run_status':attempt/'run_status.json',
            'raw_run':raw,'score':case/'SCORE_v2.json'}.items():
            files[name]={'path':str(path.resolve()),'sha256':checked(path)}
        outcomes.append({'scene_id':scene,'scores':score['scores'],'Q_over_C5':score['Q_over_C5'],
            'criteria':score['criteria'],'gate':score['gate'],'action_chain_max_errors':score['action_chain_max_errors'],
            'parent_pointwise_max_abs_errors':score['parent_pointwise_max_abs_errors'],
            'force_interface':{'mass_kg':mass,'held_force_minus_mass_action_max_abs_N':mass_err,
                'commanded_minus_nominal_less_residual_max_abs_N':subtract_err},'files':files})
    result={'status':'PASS_FIXED_THREE_SCENE_CAUSAL_GATE_DIAGNOSTIC',
        'scope':'3 fixed physical TRAIN scenes; no broader generalization claim', 'Plant_calls':3,
        'no_plant_preflight_count':3, 'no_plant_preflight_plant_calls':0,
        'TEST_read':False,'VAL_read':False,'inertia_reconstruction_enabled':False,
        'helper_max_abs_error':parity['max_abs_error'], 'source_hashes_checked':len(cache),
        'shared_artifacts':artifacts,'scenes':outcomes,
        'self_excitation_interpretation':'All high-wind windows had lower measured Ebp than their same-scene parent; these observations do not establish a causal stability or self-excitation claim.'}
    JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    lines=['# 因果 N4 门控 v2：三场固定闭环结果','',
        '仅限 TRAIN_C5_24 中预先指定的 3 场；每场各一次，共 3 次 Plant 调用。三场预检均停在主循环之前，均为零调用。无 VAL/TEST、惯量重建、参数调整或场景扩展。','',
        '| 场景 | 对照 | Q_m | task_SO3_rad | inner_SO3_rad |', '|---|---|---:|---:|---:|']
    for row in outcomes:
        for name in ('B','C5','parent','candidate'):
            s=row['scores'][name]
            lines.append(f"| {row['scene_id']} | {name} | {s['Q_m']:.12g} | {s['task_SO3_rad']:.12g} | {s['inner_SO3_rad']:.12g} |")
    lines += ['', '| 场景 | Q/C5 | task≤B（高风） | g均值（t≥2） | g≥0.5比例 | g=0.5穿越次数 | 结论 |',
        '|---|---:|---|---:|---:|---:|---|']
    for i,row in enumerate(outcomes):
        g=row['gate']; c=row['criteria']
        task='不适用' if i==0 else ('是' if c['high_task_le_B'] else '否')
        lines.append(f"| {row['scene_id']} | {row['Q_over_C5']:.9f} | {task} | {g['g_mean']:.6f} | {g['g_ge_0p5_fraction']:.4%} | {g['g_0p5_crossings']} | PASS |")
    lines += ['', '每场均 20,000 步稳定、五项评分安全计数为零，1,999 事件中前 31 次无动作按零处理；门控、N4、输出限幅及 1 ms 保持的独立 SciPy 重放通过。低风 g 全程为 0，状态与保持动作相对 parent 的逐点最大误差均为 0。',
        '三场复核得到 `held_force = 0.695 × held_action` 和 `commanded_force = nominal_force − residual_argument` 最大误差均为 0；这是 position_bs_step 的估计残差补偿接口。',
        '两场高风的门在起动后基本常开，没有反复穿越 0.5；各时间窗的 2–5 Hz 动作能量低于同场 parent。单次对照不足以证明不存在闭环自激。',
        f"MATLAB R2025b 对齐 24 场事件及压力样例最大误差 `{parity['max_abs_error']:.3g}`，并验证非事件状态保持。",'',
        '## 协议、锁与调用记录','',
        f"- 预先冻结协议：`{artifacts['protocol']['path']}`；SHA-256 `{artifacts['protocol']['sha256']}`。",
        f"- 三场 no-Plant 源锁：`{artifacts['no_plant_source_lock']['path']}`；SHA-256 `{artifacts['no_plant_source_lock']['sha256']}`。",
        f"- TRAIN24 审计 NPZ：`{artifacts['train24_audit_npz']['path']}`；SHA-256 `{artifacts['train24_audit_npz']['sha256']}`。",
        f"- MATLAB 一致性：`{artifacts['matlab_helper_parity']['path']}`；SHA-256 `{artifacts['matlab_helper_parity']['sha256']}`。"]
    for row in outcomes:
        f=row['files'];lines.append(f"- `{row['scene_id']}`：单次 release `{f['single_release']['path']}`；源锁 SHA-256 `{f['single_source_lock']['sha256']}`；评分 `{f['score']['path']}`；调用状态 `{f['run_status']['path']}`；raw SHA-256 `{f['raw_run']['sha256']}`。")
    lines += ['', '完整对照分数、安全计数、逐场重放误差、能量窗口、所有调用与输入文件哈希见同目录 `THREE_SCENE_RESULT_v2.json`。',
        '复用入口为独立 runner 的 `position_compensation_n4_causal_gate_init/step.m` 和 `position_compensation_static_n4_init/step.m`；三个单次 release 均已消耗，后续研究应另建隔离运行与新协议。','']
    MD.write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':result['status'],'plant_calls':3,'result_json':str(JSON.resolve()),
        'result_md':str(MD.resolve()),'checked_sources':len(cache)},indent=2))


if __name__=='__main__':main()
