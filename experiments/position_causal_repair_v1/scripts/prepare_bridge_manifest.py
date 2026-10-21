from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
BRIDGE = [
    "DL1018_TRAIN_T1_C02_W08", "DL1018_TRAIN_T1_C02_W15",
    "DL1018_TRAIN_T2_C01_W08", "DL1018_TRAIN_T2_C01_W15",
    "DL1018_TRAIN_T3_C03_W08", "DL1018_TRAIN_T3_C03_W15",
]


def load_csv(p: Path) -> list[dict[str, str]]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(2 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    attempts = load_csv(ROOT / "logs/attempt_index.csv")
    specs = {r["scene_id"]: r for r in load_csv(ROOT / "configs/scene_specs.csv")}
    chosen: dict[tuple[str, str], dict[str, str]] = {}
    for r in attempts:
        if r["status"] not in ("COMPLETE", "STABLE"):
            continue
        key = (r["scene_id"], r["collector_id"])
        if key not in chosen or int(r["attempt_no"]) > int(chosen[key]["attempt_no"]):
            chosen[key] = r

    bridge_rows = []
    for scene in BRIDGE:
        spec = specs.get(scene)
        if not spec:
            raise RuntimeError(f"Bridge scene absent from frozen scene_specs.csv: {scene}")
        for role in ("B", "POS_OFF", "P_INIT_STUDENT"):
            r = chosen.get((scene, role))
            if r is None:
                raise RuntimeError(f"Missing completed historical {role} for {scene}")
            p = ROOT / Path(r["raw_path"].replace("/", "\\"))
            if not p.is_file():
                raise FileNotFoundError(p)
            st = p.stat()
            bridge_rows.append({
                "scene_id": scene, "split": r["split"], "task": spec["task"],
                "class_id": spec["class_id"], "wind_cell": spec["w"], "wind_band": spec["wind_band"],
                "role": role, "run_id": r["run_id"], "model_id": r["model_id"],
                "raw_path": r["raw_path"], "size_bytes": st.st_size,
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                "sha256": hash_file(p),
            })

    out_path = OUT / "manifests/BRIDGE6.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bridge_rows[0]))
        w.writeheader(); w.writerows(bridge_rows)

    dev_scene_no_wind = "DL1018_DEV_T1_C04_W00"
    dev_scene_w08 = "DL1018_DEV_T1_C07_W08"
    dev_rows = []
    for scene in (dev_scene_no_wind, dev_scene_w08):
        if scene not in specs:
            raise RuntimeError(f"Predeclared G06 replay scene missing: {scene}")
        for role in ("B", "P_A"):
            r = chosen.get((scene, role))
            if r is None:
                raise RuntimeError(f"Missing completed G06 {role} for {scene}")
            if r["gate_id"] != "G06_P_DEV":
                raise RuntimeError(f"Expected G06 source for {scene}/{role}; found {r['gate_id']}")
            p = ROOT / Path(r["raw_path"].replace("/", "\\"))
            st = p.stat()
            dev_rows.append({
                "scene_id": scene, "task": specs[scene]["task"], "class_id": specs[scene]["class_id"],
                "wind_cell": specs[scene]["w"], "role": role, "run_id": r["run_id"],
                "model_id": r["model_id"], "raw_path": r["raw_path"], "size_bytes": st.st_size,
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                "sha256": hash_file(p),
            })
    dev_path = OUT / "manifests/G06_REPLAY2.csv"
    with dev_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dev_rows[0]))
        w.writeheader(); w.writerows(dev_rows)

    print(json.dumps({"bridge_rows": len(bridge_rows), "bridge_scenes": BRIDGE,
                      "g06_replay_rows": len(dev_rows), "bridge_manifest": str(out_path),
                      "g06_manifest": str(dev_path), "hashed_bytes": sum(int(r["size_bytes"]) for r in bridge_rows + dev_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
