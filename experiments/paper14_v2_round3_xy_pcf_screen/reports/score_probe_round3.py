from __future__ import annotations
import csv, hashlib, importlib.util, json, sys
from pathlib import Path
import h5py
import numpy as np

HERE = Path(__file__).resolve().parents[1]
REPORTS = HERE / "reports"
LOCK_PATH = HERE / "frozen_inputs.json"
OUT = REPORTS / "probe_score_round3.json"
TOL = 1e-12

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_module(name: str, path: Path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load {path}")
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def direct_metrics(raw_path: Path) -> dict[str, object]:
    with h5py.File(raw_path,"r") as f:
        log=f["log"]
        def arr(key):
            a=np.asarray(log[key]);return a.transpose(tuple(reversed(range(a.ndim)))) if a.ndim>=2 else a
        t=arr("transition_time").reshape(-1);state=arr("state");ref=arr("reference/position")
        keep=(t>=0.0)&(t<20.0)
        e=ref[:t.size,:3][keep]-state[:t.size,:3][keep]
        return {"Q_0_20":float(np.sqrt(np.mean(np.sum(e*e,axis=1)))),
                **{f"RMSE_{a.upper()}_0_20":float(np.sqrt(np.mean(e[:,j]**2))) for j,a in enumerate("xyz")}}

def main() -> int:
    result={"schema":"ROUND3_PROBE_SCORE_CROSSCHECK_V1","status":"BLOCKED","mode":"PROBE_ONLY",
            "decision":"NO_CONTINUE_AUTHORIZATION","full_12_scene_pass":False,"test_accessed":False,"errors":[]}
    try:
        lock_sha=sha(LOCK_PATH);L=json.loads(LOCK_PATH.read_text(encoding="utf-8-sig"));sid=L["scenes"][0]["scene_id"]
        require=lambda ok,msg: (_ for _ in ()).throw(RuntimeError(msg)) if not ok else None
        require(sid=="DL1018_VAL_T2_C00_W10","unexpected PROBE scene")
        raw_scan_path=Path(L["scoring_helper"]["path"])
        require(sha(raw_scan_path)==L["scoring_helper"]["sha256"],"locked raw scanner changed")
        compat_path=REPORTS/"rescore_round3_compat.py";verifier_path=REPORTS/"verify_round3_identity_compat.py"
        scorer=load_module("r3_probe_compat_scorer",compat_path);scanner=scorer.load_scanner()
        verifier=load_module("r3_probe_compat_verifier",verifier_path)
        manifest=list(csv.DictReader(Path(L["reuse_manifest"]["path"]).open(encoding="utf-8-sig",newline="")))
        on=next(x for x in manifest if x["scene_id"]==sid and x["role"]=="ON_CANDIDATE")
        b=next(x for x in manifest if x["scene_id"]==sid and x["role"]=="B_BASELINE")
        off=next(x for x in L["round2_off_raws"] if x["scene_id"]==sid)
        candidate=HERE/"runs"/sid/"attempt_01"/"raw_run.mat"
        paths={"R3_XY":candidate,"B":Path(b["raw_path"]),"PCF_ON":Path(on["raw_path"]),"PCF_OFF":Path(off["raw_path"])}
        expected={"R3_XY":sha(candidate),"B":b["raw_sha256"],"PCF_ON":on["raw_sha256"],"PCF_OFF":off["raw_sha256"]}
        for role,path in paths.items():
            require(path.is_file(),f"missing {role} raw")
            if "TEST" in str(path).upper(): raise RuntimeError(f"sealed TEST path refused: {path}")
        event_audit=verifier.verify_candidate(L,sid)
        metrics={}
        direct={}
        for role,path in paths.items():
            metrics[role]=scorer.score_raw(scanner,path,expected[role],role)[0]
            direct[role]=direct_metrics(path)
            for key,val in direct[role].items():
                err=abs(float(metrics[role][key])-val)
                require(err<=TOL,f"{role} {key} raw_scan/manual mismatch: {err}")
        r2rows=list(csv.DictReader(Path(L["upstream_round2"]["results_path"]).open(encoding="utf-8-sig",newline="")))
        r2=next(x for x in r2rows if x["scene_id"]==sid)
        for role,prefix in (("B","b"),("PCF_ON","on"),("PCF_OFF","off")):
            require(abs(float(metrics[role]["Q_0_20"])-float(r2[f"{prefix}_q_0_20_m"]))<=TOL,f"{role} Q differs from frozen R2 results")
            for axis in "XYZ":
                k=f"RMSE_{axis}_0_20";col=f"rmse_{axis.lower()}_{prefix}_0_20_m"
                require(abs(float(metrics[role][k])-float(r2[col]))<=TOL,f"{role} {k} differs from frozen R2 results")
        delta={role:float(metrics["R3_XY"]["Q_0_20"])-float(metrics[role]["Q_0_20"]) for role in ("B","PCF_ON","PCF_OFF")}
        z_delta=float(metrics["R3_XY"]["RMSE_Z_0_20"])-float(metrics["PCF_ON"]["RMSE_Z_0_20"])
        audit=json.loads((REPORTS/"probe_review_round3.json").read_text(encoding="utf-8-sig"))
        require(audit.get("status")=="PASS" and audit.get("scene_id")==sid and audit.get("frozen_inputs_sha256")==lock_sha,"independent raw audit missing/stale")
        input_hashes={role:sha(path) for role,path in paths.items()}
        require(input_hashes==expected,"a score input changed during scoring")
        result.update({"status":"PROBE_PASS","scene_id":sid,"frozen_inputs_sha256":lock_sha,
            "compat_scorer_sha256":sha(compat_path),"compat_verifier_sha256":sha(verifier_path),
            "locked_rescore_sha256":sha(HERE/"rescore_round3.py"),"locked_raw_scan_sha256":sha(raw_scan_path),
            "probe_audit_report_sha256":sha(REPORTS/"probe_review_round3.json"),
            "raw_sha256":input_hashes,"event_audit":event_audit,
            "metrics":{role:{k:float(v) for k,v in m.items() if k in ("Q_0_20","RMSE_X_0_20","RMSE_Y_0_20","RMSE_Z_0_20","RMSE_X_0_5","RMSE_Y_0_5","RMSE_Z_0_5","RMSE_X_5_20","RMSE_Y_5_20","RMSE_Z_5_20","peak","p95","controller_call_time_mean_s","motor_saturated_fraction","generalized_clipped_fraction")} for role,m in metrics.items()},
            "raw_scan_vs_direct_max_abs_error":{role:max(abs(float(metrics[role][k])-v) for k,v in direct[role].items()) for role in metrics},
            "delta_q_xy_minus_b_on_off_m":delta,"delta_rmse_z_xy_minus_on_m":z_delta,
            "probe_direction":{"beats_B":delta["B"] < -TOL,"beats_PCF_ON":delta["PCF_ON"] < -TOL,"beats_PCF_OFF":delta["PCF_OFF"] < -TOL,"Z_beats_PCF_ON":z_delta < -TOL},
            "test_accessed":False,"continue_authorized":False})
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        print(f"PROBE_SCORE_BLOCKED: {result['errors'][-1]}",file=sys.stderr)
    result["script_sha256"]=sha(Path(__file__).resolve())
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,allow_nan=False))
    return 0 if result["status"]=="PROBE_PASS" and result["full_12_scene_pass"] is False else 1

if __name__=="__main__": raise SystemExit(main())

