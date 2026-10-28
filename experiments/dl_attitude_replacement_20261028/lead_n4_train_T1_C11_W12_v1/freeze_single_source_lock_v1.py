"""Freeze the authorized-call source list after the no-Plant audit exists."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
SCENE = "DL1018_DEV_T1_C11_W12"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    base = json.loads((HERE / "SOURCE_LOCK_v2.json").read_text(encoding="utf-8"))
    audit_path = HERE / "audits" / f"{SCENE}_no_plant.json"
    marker_path = HERE / "audits" / f"{SCENE}_marker.json"
    for path in (audit_path, marker_path, HERE / "RELEASE_NOPLANT_v1.json", HERE / "SOURCE_LOCK_v2.json"):
        if not path.is_file():
            raise RuntimeError(f"Required no-Plant evidence missing: {path}")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    noplant_release = json.loads((HERE / "RELEASE_NOPLANT_v1.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS_FULL_RUNNER_NOPLANT_BOUNDARY"
    assert audit["scene_id"] == SCENE and audit["Plant_calls"] == 0
    assert audit["attempt_markers"] == 0 and audit["first_plant_step_markers"] == 0
    assert audit["release_sha256"] == sha(HERE / "RELEASE_NOPLANT_v1.json")
    assert audit["source_lock_sha256"] == sha(HERE / "SOURCE_LOCK_v2.json")
    files = {x["path"]: x["sha256"] for x in base["files"]}
    for path in (audit_path, marker_path, HERE / "RELEASE_NOPLANT_v1.json", HERE / "SOURCE_LOCK_v2.json"):
        files[str(path.resolve())] = sha(path)
    rows = [{"path": p, "sha256": h} for p, h in sorted(files.items(), key=lambda row: row[0].lower())]
    out = HERE / "SOURCE_LOCK_SINGLE_v2.json"
    if out.exists():
        raise RuntimeError(f"Refusing to overwrite {out}")
    out.write_text(json.dumps({"study_id": "causal_n4_gate_v2", "scene_id": SCENE, "files": rows},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"source_lock_single_sha256": sha(out), "locked_files": len(rows),
                      "scene": SCENE, "prior_no_plant_sha256": sha(audit_path)}, indent=2))


if __name__ == "__main__":
    main()
