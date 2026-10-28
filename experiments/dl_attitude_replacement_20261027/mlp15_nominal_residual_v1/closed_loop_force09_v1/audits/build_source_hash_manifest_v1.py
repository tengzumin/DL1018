"""Hash force09 MATLAB sources and bind unchanged MLP update-order sources."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STUDY = Path(__file__).resolve().parent.parent
PARENT = STUDY.parent / "closed_loop_candidate_v1"
BOUND = (
    "candidate_runner_work/matlab/runtime/mlp15_physical_residual_step_v1.m",
    "candidate_runner_work/matlab/runtime/mlp15_attitude_step_v1.m",
    "candidate_runner_work/matlab/runtime/mlp15_attitude_forward_v1.m",
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


release = json.loads((STUDY / "RELEASE.json").read_text(encoding="utf-8-sig"))
files = []
for path in sorted((STUDY / "candidate_runner_work" / "matlab").rglob("*.m")):
    files.append({"path": path.relative_to(STUDY).as_posix(), "sha256": digest(path)})
bindings = {}
for rel in BOUND:
    child, parent = STUDY / rel, PARENT / rel
    child_hash, parent_hash = digest(child), digest(parent)
    if child_hash != parent_hash:
        raise RuntimeError(f"MLP update-order source differs from original parent: {rel}")
    bindings[rel] = {"sha256": child_hash, "parent_sha256": parent_hash, "identical": True}

manifest = {
    "schema": "DL1018_MLP15_FORCE09_SOURCE_HASH_MANIFEST_V1",
    "study_id": release["study_id"],
    "parent_variant": "closed_loop_candidate_v1",
    "source_file_count": len(files),
    "model_sha256": release["model_sha256"],
    "position_nn_compensation_scale": release["position_nn_compensation_scale"],
    "parent_MLP_order_bindings": bindings,
    "files": files,
}
(STUDY / "SOURCE_HASH_MANIFEST_v1.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(json.dumps({"status": "PASS_SOURCE_HASH_MANIFEST",
                  "source_file_count": len(files),
                  "parent_MLP_sources_bound": len(bindings)}, indent=2))
