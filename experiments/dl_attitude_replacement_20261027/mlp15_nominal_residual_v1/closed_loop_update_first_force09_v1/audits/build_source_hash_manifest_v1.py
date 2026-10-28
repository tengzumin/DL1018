"""Hash the isolated MATLAB candidate sources without reading run raws."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STUDY = Path(__file__).resolve().parent.parent


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
manifest = {
    "schema": "DL1018_MLP15_FORCE09_SOURCE_HASH_MANIFEST_V1",
    "study_id": release["study_id"],
    "source_file_count": len(files),
    "model_sha256": release["model_sha256"],
    "position_nn_compensation_scale": release["position_nn_compensation_scale"],
    "files": files,
}
(STUDY / "SOURCE_HASH_MANIFEST_v1.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(json.dumps({"status": "PASS_SOURCE_HASH_MANIFEST", "source_file_count": len(files)}, indent=2))
