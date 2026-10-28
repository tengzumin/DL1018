import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[2]
PARENT = PROJECT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_tracking_head_full72_v1"
PARENT_MANIFEST = PARENT / "MANIFEST.json"
MODEL = PROJECT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_c5_teacher_v1" / "runs" / "GRU32_STREAM72_COSINE_S2026102001" / "gru_stream_c5_teacher_weights_v1.mat"
MODEL_SHA = "b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567"
STUDY_ID = "gru_prediction_tau01_v1"
CANDIDATE = "GRU32_STREAM72_COSINE_PREDICTION_TAU01_S2026102001"
VARIANT = "DL1018_GRU_PREDICTION_TAU01_RELEASE_V1"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

assert sha(MODEL) == MODEL_SHA, "Cosine GRU model SHA mismatch."
parent_sha = sha(PARENT_MANIFEST)

# This is the only active runtime edit.
helper_path = ROOT / "candidate_runner_work" / "matlab" / "runtime" / "delayed_prediction_step_candidate.m"
source = helper_path.read_text(encoding="utf-8-sig")
assert source.count("tau=1; rho=h/tau;") == 1
helper_path.write_text(source.replace("tau=1; rho=h/tau;", "tau=0.1; rho=h/tau;"), encoding="utf-8")

# Reuse the previously passing scene bindings and retag this study.
manifest = read(ROOT / "SCENE_INPUT_MANIFEST_v1.json")
manifest.update({
    "schema": "DL1018_GRU_PREDICTION_TAU01_INPUT_MANIFEST_V1",
    "study_id": STUDY_ID,
    "parent_study_id": "gru_stream_cosine_tracking_head_full72_v1",
    "parent_manifest_path": str(PARENT_MANIFEST),
    "parent_manifest_sha256": parent_sha,
})
write(ROOT / "SCENE_INPUT_MANIFEST_v1.json", manifest)

locked = read(ROOT / "LOCKED_CFG.json")
locked.update({
    "candidate_attitude_model_path": str(MODEL),
    "candidate_attitude_model_sha256": MODEL_SHA,
    "candidate_attitude_model_id": "GRU32_STREAM72_COSINE_S2026102001",
    "candidate_target_rms_source": "cosine model target_rms; loaded from the SHA-locked cosine MAT",
    "parent_study_id": "gru_stream_cosine_tracking_head_full72_v1",
    "parent_manifest_sha256": parent_sha,
    "position_method_id": "C5_AXIS_MIXED_COORDINATE_M110",
    "position_nn_compensation_scale": 1,
    "position_path_changed": True,
    "position_delayed_prediction_h_s": 0.01,
    "position_delayed_prediction_tau_s": 0.1,
    "position_delayed_prediction_rho": 0.1,
    "position_delayed_prediction_gamma": 12,
    "position_delayed_prediction_lambda": 0.002,
    "position_delayed_prediction_target": "C5 M110 filtered-PCF delayed velocity increment; normalizer/model unchanged",
})
write(ROOT / "LOCKED_CFG.json", locked)

helper = ROOT / "candidate_runner_work" / "matlab" / "runtime" / "prepare_gru_prediction_tau01_no_plant.m"
text = helper.read_text(encoding="utf-8-sig")
replacements = {
    "prepare_gru_ncmd_tracking_no_plant": "prepare_gru_prediction_tau01_no_plant",
    "GRUNCMD": "GRUTAU01",
    "DL1018_GRU_NCMD_TRACKING": "DL1018_GRU_PREDICTION_TAU01",
    "gru_ncmd_tracking_v1": STUDY_ID,
    "gru_stream_ncmd_v1": "gru_stream_cosine_c5_teacher_v1",
    "GRU32_STREAM72_NCMD_S2026102001": "GRU32_STREAM72_COSINE_S2026102001",
    "cd5870a48deac9eb3540c3662c59ec4212965c333669b730cdd4f6519d364de6": MODEL_SHA,
    "NCMD_target_rms": "cosine_target_rms",
    "NCMD release, model path, or model SHA is invalid.": "cosine release, model path, or model SHA is invalid.",
    "NCMD model": "cosine model",
    "NCMD input or target normalizers": "cosine input or target normalizers",
    "NCMD GRU": "cosine GRU",
    "NCMD binding": "prediction-tau binding",
}
for a, b in replacements.items():
    text = text.replace(a, b)
text = text.replace("gru_ncmd_tracking", STUDY_ID).replace("NCMD-GRU", "cosine-GRU")
text = text.replace("'gru_model_sha256',char(release.model_sha256),'target_rms'", "'gru_model_sha256',char(release.model_sha256),'target_rms'")
helper.write_text(text, encoding="utf-8")

# Unit check: exact parent-vs-candidate delayed-update scale for one causal event.
unit = ROOT / "audits" / "check_prediction_tau01_step.m"
ut = unit.read_text(encoding="utf-8-sig")
# Keep fixture and assertions; its function path names are study-relative.
unit.write_text(ut, encoding="utf-8")

entry_path = ROOT / "run_gru_prediction_tau01_attempt.m"
entry = entry_path.read_text(encoding="utf-8-sig")
for a, b in {
    "GRUNCMD": "GRUTAU01",
    "gru_ncmd_tracking_v1": STUDY_ID,
    "GRU_NCMD_TRACKING": "GRU_PREDICTION_TAU01",
    "GRU32_STREAM72_NCMD_TRACKING_S2026102001": CANDIDATE,
    "NCMD_target_rms": "cosine_target_rms",
    "log.gru_ncmd_tracking_release_sha256": "log.gru_prediction_tau01_release_sha256",
}.items():
    entry = entry.replace(a, b)
entry = entry.replace("DL1018_GRU_PREDICTION_TAU01_RELEASE_V1", VARIANT)
entry = entry.replace("prepared=prepare_gru_ncmd_tracking_no_plant(sceneId,false);", "prepared=prepare_gru_prediction_tau01_no_plant(sceneId,false);")
entry = entry.replace("studyRoot=fileparts(mfilename('fullpath'));cd(studyRoot);addpath(studyRoot,'-begin');", "studyRoot=fileparts(mfilename('fullpath'));cd(studyRoot);addpath(fullfile(studyRoot,'candidate_runner_work','matlab','runtime'),'-begin');addpath(studyRoot,'-begin');")
entry = entry.replace("attemptDir=fullfile(runsRoot,sceneId);", "if ~isfolder(runsRoot),mkdir(runsRoot);end;attemptDir=fullfile(runsRoot,sceneId);")
entry = entry.replace("assert(java.io.File(attemptDir).mkdir(),", "assert(java.io.File(attemptDir).mkdirs(),")
entry = entry.replace("'position_nn_compensation_scale',1,'command_filter_wn_rad_s',[18;18;12], ...", "'position_nn_compensation_scale',1,'command_filter_wn_rad_s',[18;18;12], ...\n    'position_path_changed',true,'position_delayed_prediction_h_s',0.01, ...\n    'position_delayed_prediction_tau_s',0.1,'position_delayed_prediction_rho',0.1, ...\n    'position_delayed_prediction_gamma',12,'position_delayed_prediction_lambda',0.002, ...\n    'position_model_normalizer_changed',false, ...")
entry = entry.replace("'gru_model_sha256',prepared.gru_model_sha256,'cosine_target_rms',prepared.target_rms, ...", "'gru_model_sha256',prepared.gru_model_sha256,'cosine_target_rms',prepared.target_rms, ...")
entry = entry.replace("'source_lock_sha256',prepared.source_lock_sha256, ...\n        'gru_model_sha256'", "'source_lock_sha256',prepared.source_lock_sha256, ...\n        'position_delayed_prediction_tau_s',0.1,'position_delayed_prediction_rho',0.1, ...\n        'position_path_changed',true,'gru_model_sha256'")
entry_path.write_text(entry, encoding="utf-8")

screen_path = ROOT / "run_gru_prediction_tau01_screen.m"
screen = screen_path.read_text(encoding="utf-8-sig")
for a, b in {
    "GRUNCMD": "GRUTAU01",
    "gru_ncmd_tracking_v1": STUDY_ID,
    "GRU_NCMD_TRACKING": "GRU_PREDICTION_TAU01",
    "GRU32_STREAM72_NCMD_TRACKING_S2026102001": CANDIDATE,
}.items():
    screen = screen.replace(a, b)
screen = screen.replace("DL1018_GRU_PREDICTION_TAU01_RELEASE_V1", VARIANT)
screen = screen.replace("run_gru_ncmd_tracking_attempt", "run_gru_prediction_tau01_attempt")
screen = screen.replace("strcmpi(char(status.gru_model_sha256),char(release.model_sha256))&& ...", "strcmpi(char(status.gru_model_sha256),char(release.model_sha256))&& ...\n            abs(double(status.position_delayed_prediction_tau_s)-.1)<1e-12&& ...\n            abs(double(status.position_delayed_prediction_rho)-.1)<1e-12&& ...\n            logical(status.position_path_changed), ...")
screen_path.write_text(screen, encoding="utf-8")

scenes = [r["scene_id"] for r in manifest["records"]]
release = {
    "schema": "DL1018_GRU_STREAM_DEV_RELEASE_V1", "variant_schema": VARIANT,
    "study_id": STUDY_ID, "candidate_arm_id": CANDIDATE, "candidate": CANDIDATE,
    "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT", "authorization_phase": "12_SCENE_PREDICTION_TAU01_FIXED",
    "authorized_Plant_calls": 12, "Plant_calls": 0, "authorized_scenes": scenes,
    "model_path": str(MODEL), "model_sha256": MODEL_SHA,
    "parent_candidate": "GRU32_STREAM72_COSINE_TRACKING_HEAD_S2026102001",
    "parent_study_id": "gru_stream_cosine_tracking_head_full72_v1",
    "parent_manifest_path": str(PARENT_MANIFEST), "parent_manifest_sha256": parent_sha,
    "parent_model_scope": "DEV24+VAL48 development evidence; not independent validation; this trial adds no training.",
    "scene_input_manifest_path": "SCENE_INPUT_MANIFEST_v1.json",
    "position_method_id": "C5_AXIS_MIXED_COORDINATE_M110", "position_nn_compensation_scale": 1,
    "position_path_changed": True, "position_delayed_prediction_h_s": 0.01,
    "position_delayed_prediction_tau_s": 0.1, "position_delayed_prediction_rho": 0.1,
    "position_delayed_prediction_gamma": 12, "position_delayed_prediction_lambda": 0.002,
    "target_rms_source": "unchanged cosine model target_rms", "command_filter_wn_rad_s": [18,18,12],
    "tracking_delta_head": "33x3", "base_weights_fixed": True, "training_runs": 0,
    "Plant_calls_completed": 0, "Plant_truth_deployment_input": False,
    "inertia_reconstruction_enabled": False, "TEST_read": False, "test_data_read": False,
    "expected_no_plant_scene": "DL1018_VAL_T3_C01_W14",
    "release_notes": "Only active change from the cosine tracking FULL72 parent: delayed prediction tau=0.1 s (h=0.01 s, rho=0.1); C5 M110 filtered-PCF, GRU/model normalizers, beta/limits/gains, WN18, and fixed J0 are inherited.",
}
write(ROOT / "RELEASE.json", release)
print(f"prepared {STUDY_ID}: {len(scenes)} scenes, model {sha(MODEL)}, parent {parent_sha}")
