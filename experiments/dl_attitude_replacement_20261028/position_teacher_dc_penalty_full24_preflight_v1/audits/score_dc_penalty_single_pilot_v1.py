#!/usr/bin/env python3
"""Frozen-score one DC diagnostic and summarize logged residual-action bias."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import h5py
import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = HERE.parents[3]
SCENE = "DL1018_VAL_T3_C01_W14"
ATTEMPT = STUDY / "runs" / SCENE / "attempt_001"
OFFICIAL = ROOT / "experiments/dl_attitude_replacement_20261028/gru_prediction_tau01_v1/audits/GRU_PREDICTION_TAU01_SCORE_final12.json"
SCORER = ROOT / "experiments/dl_attitude_replacement_20261026/gru_stream_cosine_tracking_head_full72_v1/audits/score_full72_candidate_v1.py"
PREVIOUS_SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/position_teacher_position_balanced_full24_pilot_v1/audits/SINGLE_PILOT_SCORE_v1.json"
OUT = HERE / "DC_PENALTY_SINGLE_PILOT_SCORE_v1.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_status(raw_path: Path, status_path: Path, scene_id: str) -> dict:
    status = readj(status_path)
    if (not raw_path.is_file() or not status_path.is_file() or
            sha(raw_path).lower() != status.get("raw_sha256", "").lower() or
            status.get("scene_id") != scene_id or status.get("state") not in (None, "COMPLETED") or
            status.get("status_value") not in (None, "STABLE") or status.get("log_status") not in (None, "STABLE") or
            status.get("transitions") != 20000 or status.get("state_samples") != 20001 or
            status.get("TEST_accessed") is True or status.get("test_data_read") is True):
        raise RuntimeError(f"Invalid or incomplete source status: {status_path}")
    return status


def scalar(log, name: str) -> float:
    return float(np.asarray(log[name][()]).reshape(-1)[0])


def vec(log, name: str) -> np.ndarray:
    return np.asarray(log[name][()]).reshape(-1)


def mat(log, name: str) -> np.ndarray:
    return np.asarray(log[name][()]).T


class ResidualGRU(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=14, hidden_size=32, num_layers=1, batch_first=True)
        self.head = nn.Linear(32, 3)

    def forward(self, x):
        h, _ = self.gru(x)
        return self.head(h)


def action_diagnostics(raw_path: Path, model_path: Path) -> dict:
    with h5py.File(raw_path, "r") as f:
        log = f["log"]
        t = vec(log, "time")[:-1]
        events = vec(log, "stage1_position_event").astype(bool)
        residual_events = vec(log, "stage1_position_residual_gru_event").astype(bool)
        ready = vec(log, "stage1_position_residual_gru_ready").astype(bool)
        raw_delta = mat(log, "stage1_position_residual_gru_raw_delta_mps2")
        clipped = mat(log, "stage1_position_residual_gru_clipped_delta_mps2")
        beta = vec(log, "stage1_position_residual_gru_beta")
        base = mat(log, "stage1_position_residual_gru_base_action_mps2")
        action = mat(log, "stage1_position_residual_gru_action_mps2")
        correction = mat(log, "stage1_position_residual_gru_applied_correction_mps2")
        x14 = mat(log, "stage1_position_feature_14")
        total_clip = vec(log, "stage1_position_residual_gru_total_clip_active")
        event_count = int(round(scalar(log, "stage1_position_residual_gru_event_count")))
        enabled = bool(round(scalar(log, "stage1_position_residual_gru_enabled")))
    idx = np.flatnonzero(events)
    ready_idx = idx[ready[idx]]
    if (not enabled or not np.array_equal(events, residual_events) or len(idx) != 1999 or
            len(ready_idx) != 1968 or event_count != 1999 or
            not np.allclose(t[idx[:4]], [.01, .02, .03, .04], atol=1e-12, rtol=0) or
            abs(t[ready_idx[0]]-.32) > 1e-12):
        raise RuntimeError("Candidate event clock/readiness contract mismatch")
    delta_ref = np.clip(raw_delta[idx], -.5, .5)
    delta_ref[~ready[idx]] = 0
    action_ref = np.clip(base[idx] + np.clip(t[idx]/1.8,0,1)[:,None]*delta_ref, -3, 3)
    action_ref[~ready[idx]] = 0
    delta_error = float(np.max(np.abs(clipped[idx]-delta_ref)))
    action_error = float(np.max(np.abs(action[idx]-action_ref)))
    correction_error = float(np.max(np.abs(correction[idx]-(action_ref-base[idx]))))
    if max(delta_error, action_error, correction_error) > 1e-12 or np.any(total_clip != 0):
        raise RuntimeError("Logged output action differs from fixed deployed formula or clips")
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model = ResidualGRU().cpu().eval();model.load_state_dict(checkpoint["state_dict"])
    feature = x14[idx].astype(np.float32)
    mean = np.asarray(checkpoint["normalizer_mean"], np.float32)
    std = np.asarray(checkpoint["normalizer_std"], np.float32)
    with torch.no_grad():
        pred = model(torch.from_numpy(((feature-mean)/std).astype(np.float32)[None])).numpy()[0]
    checkpoint_error = float(np.max(np.abs(pred.astype(np.float64)-raw_delta[idx])))
    if checkpoint_error > 2e-5:
        raise RuntimeError("Actual logged X14 does not replay the released checkpoint")
    corr = correction[ready_idx]
    return {
        "event_count": int(len(idx)), "ready_event_count": int(len(ready_idx)),
        "first_event_time_s": float(t[idx[0]]), "first_ready_event_index_zero_based": 31,
        "first_ready_time_s": float(t[ready_idx[0]]),
        "checkpoint_replay_max_abs_raw_delta_error_mps2": checkpoint_error,
        "delta_formula_max_abs_error_mps2": delta_error,
        "action_formula_max_abs_error_mps2": action_error,
        "applied_correction_formula_max_abs_error_mps2": correction_error,
        "total_action_clip_event_count": int(np.count_nonzero(total_clip)),
        "ready_raw_delta_mean_mps2_by_axis": raw_delta[ready_idx].mean(axis=0).tolist(),
        "ready_applied_correction_mean_mps2_by_axis": corr.mean(axis=0).tolist(),
        "ready_applied_correction_rms_mps2_by_axis": np.sqrt(np.mean(corr**2,axis=0)).tolist(),
        "ready_C5_base_action_mean_mps2_by_axis": base[ready_idx].mean(axis=0).tolist(),
        "ready_final_action_mean_mps2_by_axis": action[ready_idx].mean(axis=0).tolist(),
        "raw_delta_axis_clip_fraction": np.mean(np.abs(raw_delta[ready_idx]) >= .5, axis=0).tolist(),
        "interpretation": "Descriptive mean applied residual correction over ready events; not causal attribution.",
    }


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    official=readj(OFFICIAL);previous=readj(PREVIOUS_SCORE)
    if official.get("status") != "COMPLETE_12_SCREEN" or official.get("TEST_read") is not False:
        raise RuntimeError("Final12 frozen comparator record is invalid")
    if sha(SCORER).lower() != official["metric_source_sha256"].lower():
        raise RuntimeError("Frozen scorer hash differs from final12 record")
    if previous.get("scene_id") != SCENE or previous.get("TEST_read") is not False:
        raise RuntimeError("Prior position-balanced comparison record is invalid")
    spec=importlib.util.spec_from_file_location("frozen_tau_score",SCORER)
    if spec is None or spec.loader is None: raise RuntimeError("Cannot load frozen scorer")
    scorer=importlib.util.module_from_spec(spec);spec.loader.exec_module(scorer)

    release_path=STUDY/"RELEASE.json";lock_path=STUDY/"SOURCE_LOCK_v1.json"
    release=readj(release_path);lock=readj(lock_path)
    if (release.get("study_id") != "position_teacher_dc_penalty_full24_preflight_v1" or
            release.get("status") != "RELEASED" or release.get("authorized_Plant_calls") != 1 or
            release.get("Plant_calls") != 1 or release.get("TEST_read") is not False or
            sha(lock_path).lower() != release.get("source_lock_sha256", "").lower()):
        raise RuntimeError("Candidate single-call release/lock invalid")
    for rec in lock["files"]:
        path=STUDY/rec["relative_path"]
        if not path.is_file() or sha(path).lower() != rec["sha256"].lower():
            raise RuntimeError(f"Locked study source changed: {rec['relative_path']}")
    for rec in lock["external_inputs"]:
        path=Path(rec["path"])
        if not path.is_file() or sha(path).lower() != rec["sha256"].lower():
            raise RuntimeError(f"Locked external input changed: {rec['name']}")
    candidate_raw=ATTEMPT/"raw_run.mat";candidate_status_path=ATTEMPT/"run_status.json"
    status=check_status(candidate_raw,candidate_status_path,SCENE)
    run_start=readj(ATTEMPT/"run_start.json")
    no_plant=readj(STUDY/"NO_PLANT_PREPARE_RESULT_v1.json")
    no_plant_release=STUDY/"RELEASE_NO_PLANT_v1.json"
    if (sha(candidate_raw)!=status.get("raw_sha256") or sha(release_path)!=status.get("release_sha256") or
            run_start.get("release_sha256")!=sha(release_path) or
            status.get("source_lock_sha256")!=release["source_lock_sha256"] or
            status.get("release_no_plant_sha256")!=no_plant.get("release_sha256") or
            sha(no_plant_release)!=no_plant.get("release_sha256") or
            (ATTEMPT/"first_plant_step.marker").is_file() is False or status.get("plant_calls")!=1):
        raise RuntimeError("Candidate run/raw/preflight budget binding is invalid")

    scene=next((r for r in official["scene_results"] if r["scene_id"]==SCENE),None)
    if scene is None: raise RuntimeError("Fixed scene is absent from final12 scoring")
    constants=official["metric_constants"]
    metrics=("Q_m","task_SO3_rad","inner_SO3_rad")
    candidate_score=scorer.score_raw(candidate_raw,float(constants["gravity_mps2"]),float(constants["max_tilt_rad"]))
    scores={"DCPenaltyFull24":candidate_score};bindings={"DCPenaltyFull24":{
        "raw_path":str(candidate_raw.resolve()),"raw_sha256":sha(candidate_raw),
        "status_path":str(candidate_status_path.resolve()),"status_sha256":sha(candidate_status_path),
        "release_sha256":sha(release_path),"source_lock_sha256":sha(lock_path),"status":status}}
    for method in ("B","C5","Parent_Cosine_GRU"):
        rec=scene["methods"][method];raw=Path(rec["raw_path"])
        status_key,status_sha_key=("run_status_path","run_status_sha256") if "run_status_path" in rec else ("status_path","status_sha256")
        status_path=Path(rec[status_key]);bound_status=check_status(raw,status_path,SCENE)
        result=scorer.score_raw(raw,float(constants["gravity_mps2"]),float(constants["max_tilt_rad"]))
        for metric in metrics:
            if not math.isclose(result[metric],float(rec[metric]),rel_tol=0,abs_tol=1e-12):
                raise RuntimeError(f"Frozen re-score differs from final12 {method}.{metric}")
        scores[method]=result;bindings[method]={"raw_path":str(raw.resolve()),"raw_sha256":sha(raw),
            "status_path":str(status_path.resolve()),"status_sha256":sha(status_path),
            "status":bound_status,"final12_score_reproduced":True}
    old_binding=previous["input_bindings"]["PositionBalancedFull24"]
    old_raw=Path(old_binding["raw_path"]);old_status=Path(old_binding["run_status_path"])
    old_run_status=check_status(old_raw,old_status,SCENE)
    if sha(old_raw).lower()!=old_binding["raw_sha256"].lower() or sha(old_status).lower()!=old_binding["run_status_sha256"].lower():
        raise RuntimeError("Prior balanced model raw/status binding changed")
    prior_score=scorer.score_raw(old_raw,float(constants["gravity_mps2"]),float(constants["max_tilt_rad"]))
    for metric in metrics:
        if not math.isclose(prior_score[metric],previous["scores"]["PositionBalancedFull24"][metric],rel_tol=0,abs_tol=1e-12):
            raise RuntimeError(f"Prior balanced score no longer reproduces: {metric}")
    scores["PositionBalancedFull24Previous"] = prior_score
    bindings["PositionBalancedFull24Previous"]={"raw_path":str(old_raw.resolve()),"raw_sha256":sha(old_raw),
        "status_path":str(old_status.resolve()),"status_sha256":sha(old_status),"status":old_run_status,
        "prior_score_record_path":str(PREVIOUS_SCORE.resolve()),"prior_score_record_sha256":sha(PREVIOUS_SCORE),
        "frozen_score_reproduced":True}
    comparisons={}
    for method in ("B","C5","Parent_Cosine_GRU","PositionBalancedFull24Previous"):
        comparisons[method]={}
        for metric in metrics:
            a=float(scores["DCPenaltyFull24"][metric]);b=float(scores[method][metric])
            comparisons[method][metric]={"candidate_minus_reference":a-b,
                "relative_change":(a-b)/b if b else None,"candidate_lower_is_better":a<b}
    action=action_diagnostics(candidate_raw,STUDY/"DEPLOYMENT_MODEL_v1.pt")
    prior_action=action_diagnostics(old_raw,ROOT/"experiments/dl_attitude_replacement_20261028/position_teacher_position_balanced_full24_pilot_v1/position_balanced_full24.pt")
    action["prior_position_balanced_ready_applied_correction_mean_mps2_by_axis"]=prior_action["ready_applied_correction_mean_mps2_by_axis"]
    action["DC_minus_previous_balanced_correction_mean_mps2_by_axis"]=(
        np.asarray(action["ready_applied_correction_mean_mps2_by_axis"])-
        np.asarray(prior_action["ready_applied_correction_mean_mps2_by_axis"])).tolist()
    report={
        "schema":"POSITION_TEACHER_DC_PENALTY_FULL24_SINGLE_PILOT_SCORE_V1",
        "status":"SCORED_ONE_FIXED_VAL_DIAGNOSTIC_SCENE","study_id":release["study_id"],
        "scene_id":SCENE,"attempt":"attempt_001",
        "scope":"One previously used VAL diagnostic scene; not independent validation; no retuning from this result.",
        "score_wrapper_path":str(Path(__file__).resolve()),"score_wrapper_sha256":sha(Path(__file__)),
        "score_wrapper_postrun_only":True,"frozen_scorer_path":str(SCORER.resolve()),
        "frozen_scorer_sha256":sha(SCORER),"official_final12_path":str(OFFICIAL.resolve()),
        "official_final12_sha256":sha(OFFICIAL),"previous_balanced_score_path":str(PREVIOUS_SCORE.resolve()),
        "previous_balanced_score_sha256":sha(PREVIOUS_SCORE),"metric_constants":constants,
        "release_sha256":sha(release_path),"source_lock_sha256":sha(lock_path),
        "source_lock_file_count":lock["file_count"],"plant_calls_actual":1,"authorized_Plant_calls":1,
        "TEST_read":False,"inertia_reconstruction_enabled":False,"independent_validation":False,
        "scores":scores,"comparisons":comparisons,"input_bindings":bindings,
        "action_bias_diagnostics":action,
        "safety":candidate_score["safety"],"run_safety_stop_reason":status.get("safety_stop_reason",""),
    }
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"done":True,"scores":scores,"comparisons":comparisons,
        "ready_correction_mean_mps2_by_axis":action["ready_applied_correction_mean_mps2_by_axis"],
        "report":str(OUT)},indent=2),flush=True)


if __name__=="__main__":
    main()
