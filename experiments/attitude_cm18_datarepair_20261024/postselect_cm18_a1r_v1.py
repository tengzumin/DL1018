"""Post-selection raw-unit comparison for frozen A1 and completed A1R."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, os, re, sys
from pathlib import Path
from typing import Any

RELEASE = "reports/attitude_cm18_datarepair_20261024/ROOT_A1R_TRAINING_RELEASE_v2.json"
RELEASE_SHA = "6a71c3d2f4275edea9ea62694083cedd5afb6602bc8ae209a1f091fcfd709737"
RUN = "experiments/attitude_cm18_datarepair_20261024/training_a1r_v1"
DATA = "reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json"
DATA_SHA = "3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0"
C5 = "reports/attitude_cm18_datarepair_20261024/c5_val48_c5_teacher_v3/C5_VAL48_EVENT_CACHE_MANIFEST_v3.json"
C5_SHA = "3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501"
AUDIT = "reports/attitude_cm18_datarepair_20261024/ROOT_A1R_TERMINAL_SELECTION_AUDIT_v1.json"
AUDIT_SHA = "f8cbafcd1bbba5ff739da71cfb6a39e4f5185a40d587cec72de63cb10ca1ebce"
A1_DEPLOY = "experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json"
A1_DEPLOY_SHA = "ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae"
NORMALIZER_SHA = "faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c"
BEST_SHA = "5fa4308b6220e530e6c2e7a6f45c4b6e22ddddef80d1bc5cafdcf58564bc5ef3"
TRAINER = "experiments/attitude_cm18_datarepair_20261024/train_cm18_a1r_v1.py"
READER = "experiments/attitude_cm18_datarepair_20261024/cache_reader_cm18_b_ref_repaired_v1.py"
NUMPY_MODEL = "experiments/attitude_cm18_a1_20261024/model_cm18_v1.py"
TORCH_MODEL = "experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py"
SOURCE_SHA = {
    TRAINER: "792fa211ed66a618fc5fd9159dfb39838ead2911a79017ca0febd54268db12e7",
    READER: "e62ccca443088e4ffbb5e82c7b70ea6fce02a1897d1aa37f99f730052773d148",
    NUMPY_MODEL: "ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6",
    TORCH_MODEL: "bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0",
}
OUTPUT = "experiments/attitude_cm18_datarepair_20261024/postselection_a1r_v1"
NAMES = ("x", "y", "z")
PARAMS = {"W1": ("fc1.weight", (32,18)), "b1": ("fc1.bias", (32,)),
          "W2": ("fc2.weight", (32,32)), "b2": ("fc2.bias", (32,)),
          "W3": ("fc3.weight", (24,32)), "b3": ("fc3.bias", (24,))}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def file(root: Path, rel: str) -> Path:
    p = (root / rel).resolve(strict=True); p.relative_to(root.resolve(strict=True))
    if not p.is_file(): raise ValueError(f"expected file: {rel}")
    return p

def read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict): raise ValueError(f"expected JSON object: {path}")
    return obj

def module(root: Path, rel: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, file(root, rel))
    if not spec or not spec.loader: raise ImportError(rel)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
    return mod

def params_from_checkpoint(state: dict[str, Any], mean: Any, std: Any, rms: Any, np: Any) -> dict[str, Any]:
    p = {}
    for key, (tensor, shape) in PARAMS.items():
        value = state[tensor].detach().cpu().numpy()
        if value.shape != shape or value.dtype != np.float32 or not np.isfinite(value).all():
            raise ValueError(f"invalid best parameter {tensor}")
        p[key] = value.astype(np.float64)
    p.update(input_mean=mean, input_std=std, train_axis_rms_rad_s2=rms)
    return p

def gate_completed(root: Path, release_sha: str, np: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if release_sha.lower() != RELEASE_SHA: raise ValueError("A1R release SHA mismatch")
    release_path = file(root, RELEASE)
    if sha(release_path) != RELEASE_SHA: raise ValueError("A1R release file changed")
    release = read_json(release_path)
    if (release.get("schema") != "CM18_A1R_TRAINING_RELEASE_V1" or
        release.get("decision") != "APPROVE_ONE_FORMAL_TRAINING" or
        release.get("optimizer_steps") != 60000 or release.get("seed") != 2026102001 or
        release.get("device") != "cuda:0" or release.get("output_directory") != RUN):
        raise ValueError("unexpected A1R release identity")
    for rel, expected in SOURCE_SHA.items():
        if sha(file(root, rel)) != expected: raise ValueError(f"frozen source changed: {rel}")
    ds_pin=release.get("dataset_manifest", {})
    if ds_pin.get("path") != DATA or ds_pin.get("sha256") != DATA_SHA:
        raise ValueError("release repaired dataset pin differs")
    src = release.get("source_files", [])
    pins = {x.get("path"): x.get("sha256") for x in src if isinstance(x, dict)}
    if pins.get(TRAINER) != SOURCE_SHA[TRAINER] or pins.get(READER) != SOURCE_SHA[READER]:
        raise ValueError("release source pins differ")
    audit_path = file(root, AUDIT)
    audit = read_json(audit_path)
    if (sha(audit_path) != AUDIT_SHA or audit.get("status") != "PASS" or
        audit.get("training_terminal") != "COMPLETED" or audit.get("steps") != 60000 or
        audit.get("best_step") != 40000 or audit.get("checkpoint_sha256") != BEST_SHA or
        audit.get("C5_not_used_for_selection") is not True):
        raise ValueError("ROOT terminal selection audit is not the frozen A1R PASS")
    run = root / RUN
    receipt = read_json(file(root, f"{RUN}/run_receipt.json"))
    if (receipt.get("schema") != "CM18_A1R_TRAINING_RECEIPT_V1" or
        receipt.get("status") != "COMPLETED" or receipt.get("optimizer_steps_completed") != 60000 or
        receipt.get("best_step") != 40000 or receipt.get("best_checkpoint_sha256") != BEST_SHA or
        receipt.get("C5_VAL48_used_for_training_or_selection") is not False or
        receipt.get("TEST_accessed") is not False):
        raise ValueError("run receipt is not terminal and frozen")
    config = read_json(file(root, f"{RUN}/training_config.json"))
    if (config.get("schema") != "CM18_A1R_TRAINING_CONFIG_V1" or config.get("optimizer_steps") != 60000 or
        config.get("seed") != 2026102001 or config.get("batch_size") != 512 or
        config.get("c5_val48_used_for_selection") is not False):
        raise ValueError("unexpected A1R training config")
    norm = read_json(file(root, f"{RUN}/normalizer.json"))
    if norm.get("schema") != "CM18_A1R_NORMALIZER_V1" or norm.get("canonical_float64_sha256") != NORMALIZER_SHA:
        raise ValueError("canonical TRAIN normalizer pin mismatch")
    canonical = {"input_mean": np.asarray(norm["input_mean_float64"], dtype=np.float64),
                 "input_std": np.asarray(norm["input_std_float64"], dtype=np.float64),
                 "train_axis_rms_rad_s2": np.asarray(norm["train_axis_rms_rad_s2_float64"], dtype=np.float64)}
    if (canonical["input_mean"].shape != (18,) or canonical["input_std"].shape != (18,) or
        canonical["train_axis_rms_rad_s2"].shape != (3,) or
        any(not np.isfinite(v).all() for v in canonical.values()) or np.any(canonical["input_std"] < 1e-6)):
        raise ValueError("canonical normalizer arrays invalid")
    h = hashlib.sha256(b"".join(np.ascontiguousarray(canonical[k], dtype=np.float64).tobytes()
                                for k in ("input_mean", "input_std", "train_axis_rms_rad_s2"))).hexdigest()
    if h != NORMALIZER_SHA: raise ValueError("normalizer canonical bytes differ")
    history = []
    with file(root, f"{RUN}/val_metrics.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): raise ValueError("blank validation metric row")
            history.append(json.loads(line))
    if len(history) != 61 or [r.get("optimizer_step") for r in history] != list(range(0,60001,1000)):
        raise ValueError("validation history is incomplete")
    best_score, best_step = float("inf"), None
    for row in history:
        score = float(row["b_val_scene_weighted_normalized_score"])
        if not np.isfinite(score): raise ValueError("nonfinite B VAL score")
        if score < best_score: best_score, best_step = score, row["optimizer_step"]
    if best_step != 40000 or abs(best_score - float(receipt["best_score"])) > 1e-12:
        raise ValueError("best selection differs from complete B VAL history")
    ckpt_path = file(root, f"{RUN}/best.pt")
    if sha(ckpt_path) != BEST_SHA: raise ValueError("best checkpoint SHA mismatch")
    import torch
    if torch.cuda.is_initialized(): raise RuntimeError("postselection must remain CPU-only")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    if (ckpt.get("schema") != "CM18_A1R_CHECKPOINT_V1" or ckpt.get("kind") != "best" or
        ckpt.get("optimizer_step") != 40000): raise ValueError("unexpected best checkpoint")
    state = ckpt.get("state_dict")
    if not isinstance(state, dict): raise ValueError("best checkpoint state_dict missing")
    for key in ("input_mean", "input_std", "train_axis_rms_rad_s2"):
        expected = canonical[key].astype(np.float32)
        actual = state[key].detach().cpu().numpy()
        if actual.dtype != np.float32 or not np.array_equal(actual, expected):
            raise ValueError(f"checkpoint float32 buffer mismatch: {key}")
    return release, {"receipt": receipt, "config": config, "audit": audit,
                     "normalizer": norm, "canonical": canonical, "checkpoint": ckpt,
                     "checkpoint_sha256": BEST_SHA, "best_score": best_score}, read_json(file(root, DATA))

def load_b_val(root: Path, dataset_manifest: dict[str, Any], np: Any) -> list[dict[str, Any]]:
    trainer = module(root, TRAINER, "a1r_postselect_trainer")
    reader = module(root, READER, "a1r_postselect_reader")
    rows = trainer._validate_dataset_manifest(root, dataset_manifest)
    scenes = reader.load_qualified_split(root, DATA, "VAL", DATA_SHA)
    return trainer._validate_scenes(scenes, rows, "VAL", np)

def load_c5_val(root: Path, np: Any) -> list[dict[str, Any]]:
    from scipy.io import loadmat
    manifest_path = file(root, C5)
    if sha(manifest_path) != C5_SHA: raise ValueError("C5 VAL48 manifest SHA mismatch")
    manifest = read_json(manifest_path)
    rows = manifest.get("scenes")
    if (manifest.get("schema") != "C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V3" or
        manifest.get("status") != "PASS" or manifest.get("training_eligible") is not False or
        not isinstance(rows, list) or len(rows) != 48):
        raise ValueError("C5 VAL48 manifest is not diagnostic-only PASS")
    result = []
    for row in rows:
        if row.get("status") != "PASS" or row.get("cache_available") is not True:
            raise ValueError("C5 cache row unavailable or failed")
        rel = row.get("cache_path_relative")
        path = file(root, str(rel).replace("\\", "/"))
        if sha(path) != row.get("cache_sha256") or path.stat().st_size != row.get("cache_bytes"):
            raise ValueError(f"C5 cache identity mismatch: {row.get('scene_id')}")
        mat = loadmat(path, simplify_cells=True)
        cache = mat.get("cache")
        if not isinstance(cache, dict) or cache.get("schema") != "CM18_VAL_C5_EVENT_CACHE_V2":
            raise ValueError("unexpected C5 cache schema")
        ident, ev = cache.get("identity", {}), cache.get("events", {})
        sid = row["scene_id"]
        if ident.get("scene_id") != sid or ident.get("training_eligible") not in (False, 0):
            raise ValueError(f"C5 cache scene/purpose mismatch: {sid}")
        x = np.asarray(ev["X18"], dtype=np.float64); y = np.asarray(ev["target_raw"], dtype=np.float64)
        phase = np.asarray(ev["phase_code"], dtype=np.int64).reshape(-1)
        if x.shape != (1999,18) or y.shape != (1999,3) or phase.shape != (1999,) or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError(f"invalid C5 event arrays: {sid}")
        result.append({"scene_id": sid, "split": "VAL", "X18": x, "target_raw": y, "phase_code": phase})
    return result

def metric(error: Any, np: Any) -> dict[str, Any]:
    if error.ndim != 2 or error.shape[1] != 3 or not np.isfinite(error).all(): raise ValueError("invalid error matrix")
    axis = np.sqrt(np.mean(np.square(error), axis=0, dtype=np.float64))
    return {"events": int(error.shape[0]), "axis_rmse_rad_s2": {k: float(axis[i]) for i,k in enumerate(NAMES)},
            "vector_rmse_rad_s2": float(np.sqrt(np.mean(np.sum(np.square(error),axis=1),dtype=np.float64)))}

def scene_tags(sid: str) -> tuple[str,str,str]:
    m = re.search(r"_T(\d+)_C(\d+)_W(\d{2})(?:_|$)", sid)
    if not m: raise ValueError(f"cannot parse task/condition/wind from scene id {sid}")
    return "T"+m.group(1), "C"+m.group(2), "W"+m.group(3)

def pair_metric(a: Any, b: Any, y: Any, np: Any) -> dict[str, Any]:
    ma, mb = metric(a-y,np), metric(b-y,np)
    return {"A1": ma, "A1R": mb,
            "A1R_minus_A1_axis_rmse_rad_s2": {k: mb["axis_rmse_rad_s2"][k]-ma["axis_rmse_rad_s2"][k] for k in NAMES},
            "A1R_minus_A1_vector_rmse_rad_s2": mb["vector_rmse_rad_s2"]-ma["vector_rmse_rad_s2"]}

def evaluate_domain(name: str, scenes: list[dict[str, Any]], pred_a1: list[Any], pred_a1r: list[Any], np: Any):
    all_err_a1=[]; all_err_a1r=[]; details=[]; groups={"task":{},"wind":{}}
    group_rows={"task":{},"wind":{}}
    for s, pa, pr in zip(scenes,pred_a1,pred_a1r,strict=True):
        y=np.asarray(s["target_raw"],dtype=np.float64); pa=np.asarray(pa,dtype=np.float64); pr=np.asarray(pr,dtype=np.float64)
        if y.shape!=(1999,3) or pa.shape!=y.shape or pr.shape!=y.shape: raise ValueError("prediction/target shape mismatch")
        tags=scene_tags(s["scene_id"]); all_err_a1.append(pa-y); all_err_a1r.append(pr-y)
        details.append({"domain":name,"scene_id":s["scene_id"],"task":tags[0],"condition":tags[1],"wind":tags[2],**pair_metric(pa,pr,y,np)})
        for axis,tag in (("task",tags[0]),("wind",tags[2])):
            group_rows[axis].setdefault(tag,[[],[]]); group_rows[axis][tag][0].append(pa-y); group_rows[axis][tag][1].append(pr-y)
    for axis, mapping in group_rows.items():
        for tag,(ea,er) in mapping.items():
            a=np.concatenate(ea); b=np.concatenate(er); groups[axis][tag]=pair_metric(a,b,np.zeros_like(a),np)
    ea=np.concatenate(all_err_a1); er=np.concatenate(all_err_a1r)
    return {"domain":name,"scene_count":len(scenes),"event_count":int(ea.shape[0]),
            "pooled_raw_unit_rmse":pair_metric(ea,er,np.zeros_like(ea),np),"by_task":groups["task"],"by_wind":groups["wind"]}, details

def run(root: Path, release_sha: str) -> Path:
    root=root.resolve(strict=True)
    if (root/OUTPUT).exists(): raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    if os.environ.get("KMP_DUPLICATE_LIB_OK"): raise RuntimeError("KMP_DUPLICATE_LIB_OK is forbidden")
    os.environ.update(MKL_THREADING_LAYER="SEQUENTIAL",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
    import numpy as np
    import torch
    torch.set_num_threads(1)
    if torch.cuda.is_initialized(): raise RuntimeError("CUDA must not be initialized for this CPU-only evaluation")
    release, trained, data_manifest=gate_completed(root,release_sha,np)
    if sha(file(root,DATA))!=DATA_SHA: raise ValueError("repaired dataset manifest SHA mismatch")
    b_scenes=load_b_val(root,data_manifest,np)
    c5_scenes=load_c5_val(root,np)
    ids=[s["scene_id"] for s in b_scenes]
    if len(ids)!=48 or [s["scene_id"] for s in c5_scenes]!=ids: raise ValueError("B/C5 VAL48 scene order differs")
    # The A1 artifact is a fixed comparator; its own normalized score is not used.
    a1_path=file(root,A1_DEPLOY)
    if sha(a1_path)!=A1_DEPLOY_SHA: raise ValueError("frozen A1 deployment SHA mismatch")
    a1=read_json(a1_path)
    if a1.get("schema")!="CM18_A1_DEPLOYMENT_PARAMETERS_V1" or a1.get("identity",{}).get("selected_step")!=30000:
        raise ValueError("unexpected frozen A1 deployment")
    numpy_model=module(root,NUMPY_MODEL,"postselect_numpy_model")
    torch_model=module(root,TORCH_MODEL,"postselect_torch_model")
    pa1={k:np.asarray(v,dtype=np.float64) for k,v in a1["parameters"].items()}
    if set(pa1)!={"W1","b1","W2","b2","W3","b3","input_mean","input_std","train_axis_rms_rad_s2"}:
        raise ValueError("frozen A1 deployment parameter keys differ")
    state=trained["checkpoint"]["state_dict"]
    pr=params_from_checkpoint(state,trained["canonical"]["input_mean"],trained["canonical"]["input_std"],
                              trained["canonical"]["train_axis_rms_rad_s2"],np)
    # Verify canonical-double Torch inference against the pinned NumPy implementation on both domains.
    tm=torch_model.TorchCM18A1(pr["input_mean"],pr["input_std"],pr["train_axis_rms_rad_s2"])
    tm.load_numpy_parameters(pr); tm.eval()
    xs=[]
    for scenes in (b_scenes,c5_scenes):
        for s in scenes:
            xs.extend(s["X18"][ix] for ix in (0,500,1000,1500,1998))
    xcheck=np.asarray(xs,dtype=np.float64)
    ncheck=numpy_model.forward(xcheck,pr)["physical_output_rad_s2"]
    with torch.inference_mode(): tcheck=tm(torch.as_tensor(xcheck,dtype=torch.float64))["physical_output_rad_s2"].cpu().numpy()
    parity=float(np.max(np.abs(ncheck-tcheck)))
    if not np.isfinite(parity) or parity>2e-12: raise ValueError(f"A1R Torch/NumPy parity failed: {parity}")
    domains=[]
    for name,scenes in (("B_REF_REPAIRED_VAL48",b_scenes),("C5_VAL48_POST_SELECTION_DIAGNOSTIC",c5_scenes)):
        pa=[numpy_model.forward(s["X18"],pa1)["physical_output_rad_s2"] for s in scenes]
        prd=[numpy_model.forward(s["X18"],pr)["physical_output_rad_s2"] for s in scenes]
        domains.append(evaluate_domain(name,scenes,pa,prd,np))
    summary={"schema":"CM18_A1R_POSTSELECTION_RAW_UNIT_COMPARISON_V1","status":"PASS",
        "A1R_checkpoint_sha256":trained["checkpoint_sha256"],"A1R_selected_step":40000,
        "A1R_canonical_normalizer_sha256":NORMALIZER_SHA,"A1_deployment_sha256":A1_DEPLOY_SHA,
        "A1_selected_step":30000,"Torch_double_vs_NumPy_max_abs_rad_s2":parity,
        "Torch_parity_rows":int(len(xcheck)),"domains":[x[0] for x in domains],
        "selection_or_training_used_C5":False,"normalized_scores_compared_across_models":False,
        "TEST_accessed":False,"Plant_calls":0,"optimizer_steps":0}
    scene_rows=[r for _,rows in domains for r in rows]
    deploy={"schema":"CM18_A1R_DEPLOYMENT_PARAMETERS_V1","artifact_class":"DO_NOT_GIT_UPLOAD",
        "dtype":"float64 canonical normalizer; W/b promoted from frozen float32 best checkpoint",
        "parameters":{k:np.asarray(v,dtype=np.float64).tolist() for k,v in pr.items()},
        "identity":{"release_sha256":RELEASE_SHA,"checkpoint_sha256":BEST_SHA,"selected_step":40000,
          "normalizer_float64_sha256":NORMALIZER_SHA,"A1_deployment_sha256":A1_DEPLOY_SHA,
          "dataset_manifest_sha256":DATA_SHA,"C5_VAL48_manifest_sha256":C5_SHA,
          "postselect_source_sha256":sha(Path(__file__).resolve()),"Torch_NumPy_parity_max_abs_rad_s2":parity}}
    out=(root/OUTPUT).resolve()
    out.relative_to(root)
    out.mkdir(exist_ok=False)
    (out/".gitignore").write_text("*\n!.gitignore\n!DO_NOT_GIT_UPLOAD.txt\n",encoding="utf-8")
    (out/"DO_NOT_GIT_UPLOAD.txt").write_text("Model parameters and evaluation outputs; do not upload to Git.\n",encoding="utf-8")
    (out/"deployment_parameters_v1.json").write_text(json.dumps(deploy,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    (out/"comparison_metrics_v1.json").write_text(json.dumps({**summary,"domain_metrics":[x[0] for x in domains]},indent=2,allow_nan=False)+"\n",encoding="utf-8")
    with (out/"per_scene_metrics_v1.csv").open("x",newline="",encoding="utf-8") as f:
        fields=["domain","scene_id","task","condition","wind","events","A1_x_rmse","A1_y_rmse","A1_z_rmse","A1_vector_rmse","A1R_x_rmse","A1R_y_rmse","A1R_z_rmse","A1R_vector_rmse","delta_x","delta_y","delta_z","delta_vector"]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in scene_rows:
            a=row["A1"];b=row["A1R"];d=row["A1R_minus_A1_axis_rmse_rad_s2"]
            w.writerow({"domain":row["domain"],"scene_id":row["scene_id"],"task":row["task"],"condition":row["condition"],"wind":row["wind"],"events":a["events"],
              **{f"A1_{k}_rmse":a["axis_rmse_rad_s2"][k] for k in NAMES},"A1_vector_rmse":a["vector_rmse_rad_s2"],
              **{f"A1R_{k}_rmse":b["axis_rmse_rad_s2"][k] for k in NAMES},"A1R_vector_rmse":b["vector_rmse_rad_s2"],
              **{f"delta_{k}":d[k] for k in NAMES},"delta_vector":row["A1R_minus_A1_vector_rmse_rad_s2"]})
    return out

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root",type=Path,default=Path.cwd())
    ap.add_argument("--release-sha256",default=RELEASE_SHA)
    args=ap.parse_args()
    print(run(args.repo_root,args.release_sha256))

if __name__=="__main__": main()

