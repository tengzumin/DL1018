#!/usr/bin/env python3
"""Final all-24 causal student fit from locked offline teacher labels; no validation or Plant."""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
from scipy.io import savemat
from torch.nn import functional as F

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "position_cosine_gru_train24_causal_v1" / "task_aware_cv_v1"))
import fit_task_aware_fourfold_v1 as fit
from task_aware_common import DATA_PATH, DATA_MANIFEST_PATH, SOURCE_LOCK_PATH, sha256


OUT = Path(__file__).resolve().parent
TEACHER_DIR = OUT.parent / "position_cosine_gru_train24_causal_v1" / "task_aware_cv_v1"
TEACHER_NPZ = TEACHER_DIR / "TRAIN24_FEASIBILITY_TEACHER_DELTAS_v1.npz"
TEACHER_META = TEACHER_DIR / "TRAIN24_FEASIBILITY_TEACHER_MANIFEST_v1.json"
TEACHER_SCRIPT = TEACHER_DIR / "fit_teacher_distillation_oof_v1.py"
TEACHER_SHA = "e0519bc87a977d1349da3fdb0f582273bffaa61eb24ea380fb44e4a56791634a"
OUT_PT = OUT / "position_teacher_distill_full24.pt"
OUT_MAT = OUT / "position_teacher_distill_full24.mat"
OUT_JSON = OUT / "FULL24_FIT_v1.json"
OUT_LOCK = OUT / "MODEL_MANIFEST_v1.json"
SEED = 20261032
STEPS = 300
LR = 1e-3


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    for p in (OUT_PT, OUT_MAT, OUT_JSON, OUT_LOCK):
        if p.exists():
            raise RuntimeError(f"Refusing to overwrite {p}")
    teacher_meta = json.loads(TEACHER_META.read_text(encoding="utf-8"))
    if (sha256(TEACHER_NPZ) != TEACHER_SHA or teacher_meta.get("teacher_delta_npz_sha256") != TEACHER_SHA or
            teacher_meta.get("teacher_script_sha256") != sha256(TEACHER_SCRIPT) or
            teacher_meta.get("dataset_sha256") != sha256(DATA_PATH) or
            teacher_meta.get("dataset_manifest_sha256") != sha256(DATA_MANIFEST_PATH) or
            teacher_meta.get("dataset_source_lock_sha256") != sha256(SOURCE_LOCK_PATH)):
        raise RuntimeError("Teacher/data/script lineage SHA mismatch")
    with np.load(DATA_PATH, allow_pickle=False) as z:
        ids = z["scene_ids"].astype(str).tolist()
        x = z["x14_model_input"].astype(np.float32)
        ready = z["ready_mask"].astype(bool)
        target = z["target_interval_clip_mps2"].astype(np.float32)
        base = z["applied_acceleration_event_mps2"].astype(np.float32)
        event_t = z["event_time_s"].astype(np.float32)
    with np.load(TEACHER_NPZ, allow_pickle=False) as z:
        if (z["scene_ids"].astype(str).tolist() != ids or not np.array_equal(z["ready_mask"], ready) or
                not np.array_equal(z["target_clip_mps2"], target)):
            raise RuntimeError("Teacher labels do not match exact TRAIN24 row ordering/targets")
        teacher = z["teacher_delta_mps2"].astype(np.float32)
    if len(ids) != 24 or x.shape != (24,1999,14) or teacher.shape != (24,1999,3) or not np.isfinite(teacher).all():
        raise RuntimeError("Unexpected TRAIN24/X14/teacher shapes or nonfinite labels")
    if not np.array_equal(ready, np.broadcast_to(np.arange(1999) >= 31, (24,1999))) or np.any(teacher[:,:31] != 0):
        raise RuntimeError("Warmup contract or teacher warmup labels changed")

    torch.set_num_threads(1)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    mu = x.reshape(-1,14).mean(axis=0)
    sd = x.reshape(-1,14).std(axis=0)
    sd[sd < 1e-6] = 1.0
    xn = ((x - mu[None,None,:]) / sd[None,None,:]).astype(np.float32)
    torch.manual_seed(SEED)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(SEED)
    model = fit.ResidualGRU().to(device)
    tx = torch.as_tensor(xn, device=device)
    ty = torch.as_tensor(teacher, device=device)
    mask = torch.as_tensor(ready, device=device, dtype=torch.bool)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    loss_log=[]; started=time.perf_counter()
    for step in range(STEPS):
        optimizer.zero_grad(set_to_none=True)
        _, delta = model(tx)
        loss = F.smooth_l1_loss(delta[mask], ty[mask], reduction="mean")
        if not torch.isfinite(loss): raise RuntimeError(f"nonfinite full24 teacher loss at step {step+1}")
        loss.backward(); optimizer.step()
        if step==0 or (step+1)%50==0:
            loss_log.append({"step":step+1,"teacher_delta_smooth_l1":float(loss.detach().cpu())})
        if (step+1)%100==0: print(f"full24 student {step+1}/{STEPS} loss={loss.item():.6g}",flush=True)
    model.eval()
    with torch.no_grad():
        raw, delta = model(tx)
        delta = torch.where(mask[:,:,None],delta,torch.zeros_like(delta))
        beta = torch.as_tensor(np.clip(event_t/fit.BETA_RISE_S,0,1)[...,None],device=device)
        base_t = torch.as_tensor(base,device=device)
        action = torch.clamp(base_t+beta*delta,-fit.ACTION_LIMIT,fit.ACTION_LIMIT)
    raw_np,delta_np,action_np = (v.detach().cpu().numpy() for v in (raw,delta,action))
    e = delta_np[ready].astype(np.float64)-teacher[ready].astype(np.float64)
    action_err = action_np[ready].astype(np.float64)-target[ready].astype(np.float64)
    state = {k:v.detach().cpu() for k,v in model.state_dict().items()}
    payload={"state_dict":state,"input_mean":mu.astype(np.float32),"input_std":sd.astype(np.float32),
             "input_size":14,"hidden_size":32,"output_size":3,"seed":SEED,"optimizer_steps":STEPS,
             "learning_rate":LR,"teacher_npz_sha256":TEACHER_SHA,"teacher_manifest_sha256":sha256(TEACHER_META),
             "dataset_sha256":sha256(DATA_PATH),"train_scene_ids":ids,
             "beta_rise_time_s":1.8,"delta_limit_mps2":.5,"action_limit_mps2":3.0,
             "scope":"All 24 TRAIN_C5 teacher labels; parent seen-scene development fit, not independent validation or closed-loop evidence."}
    torch.save(payload,OUT_PT)
    w=model.state_dict()
    savemat(OUT_MAT,{"gru_weight_ih_l0":w["gru.weight_ih_l0"].detach().cpu().numpy(),
                     "gru_weight_hh_l0":w["gru.weight_hh_l0"].detach().cpu().numpy(),
                     "gru_bias_ih_l0":w["gru.bias_ih_l0"].detach().cpu().numpy(),
                     "gru_bias_hh_l0":w["gru.bias_hh_l0"].detach().cpu().numpy(),
                     "head_weight":w["head.weight"].detach().cpu().numpy(),
                     "head_bias":w["head.bias"].detach().cpu().numpy(),
                     "input_mean":mu.astype(np.float32),"input_std":sd.astype(np.float32),
                     "seed":np.int64(SEED),"optimizer_steps":np.int32(STEPS),
                     "beta_rise_time_s":np.float64(1.8),"delta_limit_mps2":np.float64(.5),
                     "action_limit_mps2":np.float64(3.0),"pytorch_gru_gate_order":"reset,update,new",
                     "teacher_npz_sha256":TEACHER_SHA},do_compression=True)
    fit_report={"training_scene_count":24,"ready_events":int(ready.sum()),"optimizer_steps":STEPS,
                "seed":SEED,"device":str(device),"normalizer_scope":"all 24 TRAIN scenes, all 1999 causal X14 events",
                "loss_log":loss_log,"in_sample_teacher_delta_rmse_mps2":float(np.sqrt(np.mean(e**2))),
                "in_sample_teacher_delta_mae_mps2":float(np.mean(np.abs(e))),
                "in_sample_position_residual_rmse_mps2":float(np.sqrt(np.mean(action_err**2))),
                "raw_delta_clip_fraction_ready":float(np.mean(np.abs(raw_np[ready])>=.5)),
                "teacher_delta_abs_ge_0_5_fraction_ready":float(np.mean(np.abs(teacher[ready])>=.5)),
                "action_abs_ge_3_fraction_ready":float(np.mean(np.abs(action_np[ready])>=3)),
                "runtime_seconds":time.perf_counter()-started}
    write_json(OUT_JSON,{"schema":"POSITION_C5_TEACHER_DISTILL_FULL24_FIT_V1",
                         "scope":"TRAIN_C5_24 only; no VAL/TEST raw, Plant, wind fields, or inertia reconstruction/use.",
                         "teacher_npz_sha256":TEACHER_SHA,"teacher_manifest_sha256":sha256(TEACHER_META),
                         "fit":fit_report,"note":"All-24 fit is for pilot preparation. Metrics are in-sample teacher/residual diagnostics, not independent validation, physical Q, or closed-loop evidence."})
    manifest={"schema":"POSITION_C5_TEACHER_DISTILL_FULL24_MODEL_MANIFEST_V1",
              "weights_mat_sha256":sha256(OUT_MAT),"checkpoint_sha256":sha256(OUT_PT),
              "fit_report_sha256":sha256(OUT_JSON),"fit_script_sha256":sha256(Path(__file__)),
              "dataset_sha256":sha256(DATA_PATH),"dataset_manifest_sha256":sha256(DATA_MANIFEST_PATH),
              "dataset_source_lock_sha256":sha256(SOURCE_LOCK_PATH),
              "teacher_npz_sha256":TEACHER_SHA,"teacher_manifest_sha256":sha256(TEACHER_META),
              "teacher_generator_script_sha256":sha256(TEACHER_SCRIPT),
              "scene_count":24,"train_scene_ids":ids,"seed":SEED,"optimizer_steps":STEPS,
              "normalizer":"all 24 TRAIN scenes only","architecture":"GRU(14,32)->Linear(32,3)",
              "training_target":"offline teacher delta; future scene trajectory used only to create labels, never model input",
              "loss":"SmoothL1(student clipped delta, teacher delta) on ready events",
              "beta_rise_time_s":1.8,"delta_limit_mps2":.5,"action_limit_mps2":3.0}
    write_json(OUT_LOCK,manifest)
    print(json.dumps({"done":True,"fit":fit_report,"mat_sha256":manifest["weights_mat_sha256"],
                      "pt_sha256":manifest["checkpoint_sha256"]},indent=2),flush=True)


if __name__=="__main__": main()

