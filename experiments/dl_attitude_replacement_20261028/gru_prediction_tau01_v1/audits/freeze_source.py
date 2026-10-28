import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[2]
MODEL = PROJECT / "experiments" / "dl_attitude_replacement_20261026" / "gru_stream_cosine_c5_teacher_v1" / "runs" / "GRU32_STREAM72_COSINE_S2026102001" / "gru_stream_c5_teacher_weights_v1.mat"
MODEL_SHA = "b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567"

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
sources = sorted(
    list((ROOT / "candidate_runner_work").rglob("*.m"))
    + list(ROOT.glob("run_*.m"))
    + [ROOT / "audits" / "check_prediction_tau01_step.m"]
)
records = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sources]
source_manifest = {
    "schema": "DL1018_GRU_PREDICTION_TAU01_SOURCE_HASH_MANIFEST_V1",
    "status": "FROZEN",
    "source_file_count": len(records),
    "files": records,
}
manifest_path = ROOT / "SOURCE_HASH_MANIFEST_v1.json"
write(manifest_path, source_manifest)

artifacts = [ROOT / n for n in [
    "LOCKED_CFG.json", "SCENE_INPUT_MANIFEST_v1.json",
    "MLP15_DEV72_PAYLOAD_MANIFEST_v2.json", "SOURCE_HASH_MANIFEST_v1.json",
]]
source_lock = {
    "schema": "DL1018_GRU_PREDICTION_TAU01_SOURCE_LOCK_V1",
    "status": "FROZEN",
    "root": str(ROOT / "candidate_runner_work"),
    "files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sources],
    "model_path": str(MODEL),
    "model_sha256": MODEL_SHA,
    "source_hash_manifest_sha256": sha(manifest_path),
    "study_artifacts": [
        {"relative_path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in artifacts
    ],
}
lock_path = ROOT / "SOURCE_LOCK_v1.json"
write(lock_path, source_lock)

release_path = ROOT / "RELEASE.json"
release = read(release_path)
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
write(release_path, release)
print(json.dumps({
    "source_file_count": len(records),
    "source_hash_manifest_sha256": sha(manifest_path),
    "source_lock_sha256": sha(lock_path),
    "release_sha256": sha(release_path),
    "model_sha256": sha(MODEL),
}, indent=2))
