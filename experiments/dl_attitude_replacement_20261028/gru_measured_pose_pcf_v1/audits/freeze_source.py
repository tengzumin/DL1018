import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT.parents[1] / "dl_attitude_replacement_20261026" / "gru_stream_cosine_c5_teacher_v1" / "runs" / "GRU32_STREAM72_COSINE_S2026102001" / "gru_stream_c5_teacher_weights_v1.mat"
MODEL_SHA = "b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

assert sha(MODEL) == MODEL_SHA, "Cosine GRU model SHA mismatch."
source_paths = sorted(
    [p for p in (ROOT / "candidate_runner_work").rglob("*.m")]
    + [p for p in ROOT.glob("run_*.m")]
    + [ROOT / "audits" / "check_measured_pose_pcf_step.m"]
)
records = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in source_paths]
manifest = {
    "schema": "DL1018_GRU_MEASURED_POSE_PCF_SOURCE_HASH_MANIFEST_V1",
    "status": "FROZEN",
    "source_file_count": len(records),
    "files": records,
}
manifest_path = ROOT / "SOURCE_HASH_MANIFEST_v1.json"
dump(manifest_path, manifest)

artifact_paths = [
    ROOT / "LOCKED_CFG.json",
    ROOT / "SCENE_INPUT_MANIFEST_v1.json",
    ROOT / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json",
    manifest_path,
]
source_lock = {
    "schema": "DL1018_GRU_MEASURED_POSE_PCF_SOURCE_LOCK_V1",
    "status": "FROZEN",
    "root": str(ROOT / "candidate_runner_work"),
    "files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in source_paths],
    "model_path": str(MODEL),
    "model_sha256": MODEL_SHA,
    "source_hash_manifest_sha256": sha(manifest_path),
    "study_artifacts": [
        {"relative_path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in artifact_paths
    ],
}
lock_path = ROOT / "SOURCE_LOCK_v1.json"
dump(lock_path, source_lock)

release = load(ROOT / "RELEASE.json")
release.update({
    "scene_input_manifest_sha256": sha(ROOT / "SCENE_INPUT_MANIFEST_v1.json"),
    "source_hash_manifest_path": "SOURCE_HASH_MANIFEST_v1.json",
    "source_hash_manifest_sha256": sha(manifest_path),
    "source_lock_path": "SOURCE_LOCK_v1.json",
    "source_lock_sha256": sha(lock_path),
    "locked_cfg_path": "LOCKED_CFG.json",
    "locked_cfg_sha256": sha(ROOT / "LOCKED_CFG.json"),
    "validator_metadata_path": "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json",
    "validator_metadata_sha256": sha(ROOT / "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json"),
    "source_file_count": len(records),
    "Plant_calls_completed": 0,
    "status": "PREPARED_NO_PLANT_PENDING_ROOT_AUDIT",
})
dump(ROOT / "RELEASE.json", release)
print(json.dumps({
    "source_file_count": len(records),
    "source_hash_manifest_sha256": sha(manifest_path),
    "source_lock_sha256": sha(lock_path),
    "release_sha256": sha(ROOT / "RELEASE.json"),
    "model_sha256": sha(MODEL),
}, indent=2))
