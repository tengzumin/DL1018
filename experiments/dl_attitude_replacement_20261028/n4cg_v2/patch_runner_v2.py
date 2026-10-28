"""Patch the isolated T3 N4 runner at its final applied-compensation hook."""
from pathlib import Path

p = Path(__file__).parent / 'candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m'
s = p.read_text(encoding='utf-8')

def replace(old, new, count=1):
    global s
    if s.count(old) != count:
        raise RuntimeError(f'Expected {count} anchor(s), got {s.count(old)}: {old[:100]}')
    s = s.replace(old, new)

replace("staticN4IdentityOk=any(strcmp(releaseSchema,{'DL1018_POSITION_C5_RESIDUAL_GRU_NOPLANT_V1','DL1018_POSITION_C5_STATIC_N4_NO_POSITION_GRU_NOPLANT_V1','DL1018_POSITION_C5_STATIC_N4_NO_POSITION_GRU_SINGLE_CALL_V1'}))&& ...\n        strcmp(char(field_or(release,'study_id','')),'static_n4_T3C09_no_position_gru_v1')&& ...",
        "staticN4IdentityOk=any(strcmp(releaseSchema,{'DL1018_CAUSAL_N4_GATE_NOPLANT_V2','DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2'}))&& ...\n        strcmp(char(field_or(release,'study_id','')),'causal_n4_gate_v2')&& ...")
replace("        max(abs(staticN4RuntimeA(:)-staticN4ReleaseA(:)))<1e-12;",
        "        max(abs(staticN4RuntimeA(:)-staticN4ReleaseA(:)))<1e-12&& ...\n        isequaln(staticN4Runtime,staticN4Release);")
replace("    staticN4NoPlantReleaseOk=staticN4IdentityOk&& ...\n        strcmp(char(field_or(release,'status','')),'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT')&& ...",
        "    staticN4NoPlantReleaseOk=staticN4IdentityOk&&strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_NOPLANT_V2')&& ...\n        strcmp(char(field_or(release,'status','')),'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT')&& ...")
replace("    staticN4SinglePlantReleaseOk=staticN4IdentityOk&& ...\n        strcmp(char(field_or(release,'status','')),'RELEASED')&& ...",
        "    staticN4SinglePlantReleaseOk=staticN4IdentityOk&&strcmp(releaseSchema,'DL1018_CAUSAL_N4_GATE_SINGLE_CALL_V2')&& ...\n        numel(authorizedScenes)==1&&strcmp(char(field_or(release,'fixed_scene_id','')),sceneId)&& ...\n        strcmp(char(field_or(release,'status','')),'RELEASED')&& ...")
replace("    assert(parentReleaseOk||notchCandidateReleaseOk||residualCandidateReleaseOk||staticN4CandidateReleaseOk, ...",
        "    assert(staticN4CandidateReleaseOk, ...")
replace("'static_n4_T3C09_no_position_gru_v1'", "'causal_n4_gate_v2'", count=1)
replace("trainBinding=jsondecode(fileread(fullfile(studyRoot,'TRAIN_SCENE_BINDING_v1.json')));",
        "trainBinding=jsondecode(fileread(fullfile(studyRoot,'bindings',[sceneId '.json'])));")
replace("        helperPath=which('position_compensation_static_n4_init');\n        assert(strcmpi(helperPath,fullfile(isolatedRoot,'matlab','runtime', ...\n            'position_compensation_static_n4_init.m')), ...",
        "        helperPath=which('position_compensation_n4_causal_gate_init');\n        assert(strcmpi(helperPath,fullfile(isolatedRoot,'matlab','runtime', ...\n            'position_compensation_n4_causal_gate_init.m')), ...")
replace("    stage1PositionStaticN4State=position_compensation_static_n4_init();\n    assert(max(abs(stage1PositionStaticN4State.b(:)-staticN4ReleaseB(:)))<1e-12&& ...\n        max(abs(stage1PositionStaticN4State.a(:)-staticN4ReleaseA(:)))<1e-12, ...\n        'StaticN4:CoefficientContract','Runtime helper coefficients differ from the frozen release.');",
        "    stage1PositionStaticN4State=position_compensation_n4_causal_gate_init();\n    assert(max(abs(stage1PositionStaticN4State.n4.b(:)-staticN4ReleaseB(:)))<1e-12&& ...\n        max(abs(stage1PositionStaticN4State.n4.a(:)-staticN4ReleaseA(:)))<1e-12&& ...\n        isequal(stage1PositionStaticN4State.bp_sos,double(staticN4Release.gate_bp_sos))&& ...\n        isequal(stage1PositionStaticN4State.lo_sos,double(staticN4Release.gate_lo_sos)), ...\n        'StaticN4:CoefficientContract','Runtime N4/gate coefficients differ from the frozen release.');")
replace("    stage1PositionStaticN4EventApplied=nan(n,3);stage1PositionStaticN4EventClip=false(n,3);",
        "    stage1PositionStaticN4EventApplied=nan(n,3);stage1PositionStaticN4EventClip=false(n,3);\n    stage1PositionGateDiagnostics=nan(n,5); % Ebp, Elo, ratio, target, g at events")
replace("                                [stage1PositionStaticN4State,notchApplied,notchRaw,notchClip]= ...\n                                    position_compensation_static_n4_step( ...\n                                    stage1PositionStaticN4State,notchInput,true);",
        "                                [stage1PositionStaticN4State,notchApplied,notchRaw,gateDiag]= ...\n                                    position_compensation_n4_causal_gate_step( ...\n                                    stage1PositionStaticN4State,notchInput,true,t(k));\n                                notchClip=gateDiag.clip;\n                                stage1PositionGateDiagnostics(k,:)=[gateDiag.Ebp,gateDiag.Elo, ...\n                                    gateDiag.ratio,gateDiag.gtarget,gateDiag.g];")
replace("            'stage1_position_applied_static_n4_event_clip_active',stage1PositionStaticN4EventClip(q,:), ...",
        "            'stage1_position_applied_static_n4_event_clip_active',stage1PositionStaticN4EventClip(q,:), ...\n            'stage1_position_causal_n4_gate_diagnostics',stage1PositionGateDiagnostics(q,:), ...")
p.write_text(s, encoding='utf-8', newline='\n')
