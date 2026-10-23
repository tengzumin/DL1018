"""Curate completed screen evidence only; no automatic Git staging or publication."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
OUT = BASE / "GIT_CLOSED_ABLATION_SCREEN_CURATED_MANIFEST_v1.json"
PATHS = BASE / "GIT_CLOSED_ABLATION_SCREEN_PATHS_v1.txt"
assert not OUT.exists() and not PATHS.exists()
closed = [ROOT / "experiments" / name for name in (
    "position_c5_matched_ablations_20261023", "position_c5_matched_ablations_v2_20261023",
    "position_c5_matched_ablations_v3_20261023", "position_c5_matched_ablations_v4_20261023")]
closed += [BASE / name for name in ("c5_matched_ablation_execution", "c5_matched_ablation_parent_raw_review",
    "c5_matched_ablation_peer_review", "physical_residual_tracking_lemma", "physical_residual_tracking_peer_review",
    "c5_all_method_dev_comparison")]
explicit = [ROOT / ".gitattributes"] + [BASE / name for name in ("README_RESUME_ZH.md", "STATE.json",
    "C5_ABLATION_SCREEN12_DECISION_ZH.md", "C5_MATCHED_ABLATION_FULL72_CONDITIONAL_TASKBOOK_DRAFT_ZH.md",
    "DEV72_METHOD_RESULTS_INCREMENT_ZH.md", Path(__file__).name)]
allowed = {".m", ".py", ".ps1", ".json", ".md", ".csv", ".patch", ".pdf", ".png", ".marker"}
selected = set(explicit)
excluded = []
for folder in closed:
    assert folder.is_dir(), folder
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if any("prefdir" in part.lower() or part == "__pycache__" or "fixture" in part.lower()
               for part in path.relative_to(ROOT).parts) or path.suffix.lower() not in allowed:
            excluded.append(relative)
            continue
        selected.add(path)
entries = []
for path in sorted(selected):
    content = path.read_bytes()
    assert path.suffix.lower() not in {".mat", ".pt", ".pth", ".ckpt", ".pem", ".key"}
    if path.suffix.lower() not in {".png", ".pdf"}:
        assert not re.search(rb"-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----", content), path
    entries.append({"path": path.relative_to(ROOT).as_posix(), "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest()})
manifest = {"scope": "Closed screen12 ablations, physical lemma reviewed scope, five-method dev summary; excludes active DEV72 implementation.",
            "file_count": len(entries), "bytes": sum(e["size"] for e in entries), "files": entries,
            "excluded_count": len(excluded), "excluded_mat_cache_checkpoint_fixture_prefdir": True,
            "Plant_started": False, "TEST_accessed": False}
with OUT.open("x", encoding="utf-8") as stream:
    json.dump(manifest, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
PATHS.write_text("\n".join([e["path"] for e in entries]+[OUT.relative_to(ROOT).as_posix()])+"\n", encoding="utf-8")
print(json.dumps({"files": len(entries)+1, "bytes": manifest["bytes"]+OUT.stat().st_size,
                  "excluded": len(excluded), "pathspec": str(PATHS)}))
