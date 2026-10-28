import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parents[1] / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_full72_v1"
PARENT_MANIFEST = PARENT / "MANIFEST.json"
MODEL = ROOT.parents[1] / "dl_attitude_replacement_20261026" / "gru_stream_cosine_c5_teacher_v1" / "runs" / "GRU32_STREAM72_COSINE_S2026102001" / "gru_stream_c5_teacher_weights_v1.mat"
MODEL_SHA = "b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567"
STUDY_ID = "gru_measured_pose_pcf_v1"
CANDIDATE = "GRU32_STREAM72_COSINE_MEASURED_POSE_PCF_S2026102001"
VARIANT = "DL1018_GRU_MEASURED_POSE_PCF_RELEASE_V1"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# Bind the fixed 12 scenes to the unchanged cosine tracking FULL72 parent.
input_manifest = read_json(ROOT / "SCENE_INPUT_MANIFEST_v1.json")
input_manifest["schema"] = "DL1018_GRU_MEASURED_POSE_PCF_INPUT_MANIFEST_V1"
input_manifest["study_id"] = STUDY_ID
input_manifest["parent_study_id"] = "gru_stream_cosine_tracking_head_full72_v1"
input_manifest["parent_manifest_path"] = str(PARENT_MANIFEST)
input_manifest["parent_manifest_sha256"] = sha(PARENT_MANIFEST)
write_json(ROOT / "SCENE_INPUT_MANIFEST_v1.json", input_manifest)

# Start from the parent's real locked C5/BS/GRU-tracking configuration.
locked = read_json(ROOT / "LOCKED_CFG.json")
locked.update({
    "candidate_attitude_model_path": str(MODEL),
    "candidate_attitude_model_sha256": MODEL_SHA,
    "candidate_attitude_model_id": "GRU32_STREAM72_COSINE_S2026102001",
    "candidate_target_rms_source": "cosine model target_rms; loaded from the SHA-locked cosine MAT",
    "position_nn_compensation_scale": 1,
    "position_nn_compensation_enabled": False,
    "parent_study_id": "gru_stream_cosine_tracking_head_full72_v1",
    "parent_manifest_sha256": sha(PARENT_MANIFEST),
    "position_filter_realization_attitude_source": "measured_euler_with_issued_thrust",
    "position_filter_realization_helper": "position_filter_realization_pcf_step_v3_5",
    "position_filter_realization_math_changed": False,
})
write_json(ROOT / "LOCKED_CFG.json", locked)

# Retarget the NCMD no-plant validator to the frozen cosine model and the new variant.
helper_path = ROOT / "candidate_runner_work" / "matlab" / "runtime" / "prepare_gru_measured_pose_pcf_no_plant.m"
helper = helper_path.read_text(encoding="utf-8-sig")
replacements = {
    "prepare_gru_ncmd_tracking_no_plant": "prepare_gru_measured_pose_pcf_no_plant",
    "unchanged C5 + the frozen NCMD GRU32 model": "unchanged C5 + the frozen cosine GRU32 model",
    "GRUNCMD": "GRUMPCF",
    "NCMD release, model path, or model SHA is invalid.": "cosine release, model path, or model SHA is invalid.",
    "DL1018_GRU_NCMD_TRACKING": "DL1018_GRU_MEASURED_POSE_PCF",
    "gru_ncmd_tracking_v1": STUDY_ID,
    "gru_stream_ncmd_v1": "gru_stream_cosine_c5_teacher_v1",
    "GRU32_STREAM72_NCMD_S2026102001": "GRU32_STREAM72_COSINE_S2026102001",
    "cd5870a48deac9eb3540c3662c59ec4212965c333669b730cdd4f6519d364de6": MODEL_SHA,
    "NCMD-GRU": "measured-pose PCF cosine-GRU",
    "NCMD_target_rms": "cosine_target_rms",
    "NCMD_target_rms": "cosine_target_rms",
}
for old, new in replacements.items():
    helper = helper.replace(old, new)
helper = helper.replace("NCMD_GRU", "COSINE_GRU").replace("NCMD model", "cosine model")
helper = helper.replace("NCMD-GRU", "cosine-GRU")
helper_path.write_text(helper, encoding="utf-8")

# The sole control/math edit: feed measured current Euler to the unchanged PCF helper.
loop_path = ROOT / "candidate_runner_work" / "matlab" / "runtime" / "run_mlp15_dev72_closed_loop.m"
loop = loop_path.read_text(encoding="utf-8-sig")
old_call = """[af,rf,etaNext]=position_filter_realization_pcf_step_v3_5( ...
                            thrust,ir.euler,positionInfo.commanded_acceleration,stage1PcfEta, ..."""
new_call = """[af,rf,etaNext]=position_filter_realization_pcf_step_v3_5( ...
                            thrust,x(k,7:9).',positionInfo.commanded_acceleration,stage1PcfEta, ..."""
assert loop.count(old_call) == 1, "Expected exactly one active PCF call in the closed-loop source."
loop = loop.replace(old_call, new_call)
old_log = """     log.safety_stop_reason=safetyStopReason;
     log.paired_arm=arm;"""
new_log = """     log.safety_stop_reason=safetyStopReason;
     log.stage1_position_pcf_euler_source='measured_euler_with_issued_thrust';
     log.stage1_position_pcf_euler_used_rad=x(q,7:9);
     log.paired_arm=arm;"""
assert loop.count(old_log) == 1, "Could not bind the PCF source audit fields."
loop_path.write_text(loop.replace(old_log, new_log), encoding="utf-8")

# Isolated root entry and resume screen, still gated on a later root-approved release.
entry_path = ROOT / "run_gru_measured_pose_pcf_attempt.m"
entry = entry_path.read_text(encoding="utf-8-sig")
entry_replacements = {
    "GRUNCMD": "GRUMPCF",
    "gru_ncmd_tracking_v1": STUDY_ID,
    "GRU_NCMD_TRACKING": "GRU_MEASURED_POSE_PCF",
    "GRU32_STREAM72_NCMD_TRACKING_S2026102001": CANDIDATE,
    "NCMD_target_rms": "cosine_target_rms",
    "log.gru_ncmd_tracking_release_sha256": "log.gru_measured_pose_pcf_release_sha256",
}
for old, new in entry_replacements.items():
    entry = entry.replace(old, new)
entry = entry.replace("DL1018_GRU_MEASURED_POSE_PCF_RELEASE_V1", VARIANT)
entry = entry.replace("'tracking_runtime','gru_stream_tracking_head_step_v1',", "'tracking_runtime','gru_stream_tracking_head_step_v1', ...\n    'position_filter_realization_attitude_source','measured_euler_with_issued_thrust',")
entry_path.write_text(entry, encoding="utf-8")

screen_path = ROOT / "run_gru_measured_pose_pcf_screen.m"
screen = screen_path.read_text(encoding="utf-8-sig")
for old, new in entry_replacements.items():
    screen = screen.replace(old, new)
screen = screen.replace("DL1018_GRU_MEASURED_POSE_PCF_RELEASE_V1", VARIANT)
screen_path.write_text(screen, encoding="utf-8")

# RELEASE is pending until the parent performs its independent pre-Plant QA.
scenes = [r["scene_id"] for r in input_manifest["records"]]
release = {
    "schema": "DL1018_GRU_STREAM_DEV_RELEASE_V1",
    "variant_schema": VARIANT,
    "study_id": STUDY_ID,
    "candidate_arm_id": CANDIDATE,
    "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
    "authorization_phase": "12_SCENE_MEASURED_POSE_PCF_FIXED",
    "authorized_Plant_calls": 12,
    "Plant_calls": 0,
    "authorized_scenes": scenes,
    "candidate": CANDIDATE,
    "model_path": str(MODEL),
    "model_sha256": MODEL_SHA,
    "parent_candidate": "GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001",
    "parent_study_id": "gru_stream_cosine_tracking_head_full72_v1",
    "parent_manifest_path": str(PARENT_MANIFEST),
    "parent_manifest_sha256": sha(PARENT_MANIFEST),
    "parent_model_scope": "DEV24+VAL48 development evidence; not independent validation; this trial adds no training.",
    "scene_input_manifest_path": "SCENE_INPUT_MANIFEST_v1.json",
    "position_method_id": "C5_AXIS_MIXED_COORDINATE_M110",
    "position_nn_compensation_scale": 1,
    "position_path_changed": False,
    "position_filter_realization_attitude_source": "measured_euler_with_issued_thrust",
    "position_filter_realization_helper": "position_filter_realization_pcf_step_v3_5",
    "command_filter_wn_rad_s": [18, 18, 12],
    "attitude_base_model": "GRU32_STREAM72_COSINE_S2026102001",
    "target_rms_source": "cosine model target_rms",
    "tracking_delta_head": "33x3",
    "base_weights_fixed": True,
    "training_runs": 0,
    "Plant_calls_completed": 0,
    "Plant_truth_deployment_input": False,
    "inertia_reconstruction_enabled": False,
    "TEST_read": False,
    "test_data_read": False,
    "expected_no_plant_scene": "DL1018_VAL_T3_C01_W14",
    "release_notes": "One active method change from parent: unchanged PCF math receives current measured x(k,7:9) with issued thrust; z acceleration remains the requested acceleration. No true realized thrust, inertia, inertia derivative, or wind is a controller input.",
}
write_json(ROOT / "RELEASE.json", release)

print(f"prepared {STUDY_ID}: {len(scenes)} scenes, model {sha(MODEL)}, parent {sha(PARENT_MANIFEST)}")
