from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
sys.path.insert(0, str(ROOT / "training"))
sys.path.insert(0, str(OUT / "scripts"))

from common import score as fixed_score, seed_all  # noqa: E402
from d4_kan import PositionKAN, from_initial  # noqa: E402
from d4_sequence_data import SeqEpisode, load_split  # noqa: E402

MASS = {"B": 0.25, "POS_OFF": 0.25, "P_INIT_STUDENT": 0.50}
SEEDS = (2026101901, 2026101902)
MAX_EPOCHS = 60
PATIENCE = 8
BATCH_SIZE = 256
STRIDE = 5
DT = 0.01
LAMBDA = 1.0 - 0.002 * DT


@dataclass
class EventSet:
    x: np.ndarray
    y: np.ndarray
    raw: np.ndarray
    weights: np.ndarray
    role: np.ndarray
    task: np.ndarray
    class_index: np.ndarray
    wind_cell: np.ndarray
    scene_id: np.ndarray
    phase: np.ndarray
    run_id: np.ndarray
    end_index: np.ndarray


def endpoint_ids(ep: SeqEpisode) -> np.ndarray:
    ids = np.arange(31, len(ep.ready), STRIDE, dtype=np.int64)
    if not ep.ready[ids].all():
        raise ValueError(f"stride endpoints include not-ready event {ep.run_id}")
    return ids


def assign_episode_weights(episodes: list[SeqEpisode]) -> int:
    scene_counts: Counter = Counter()
    for ep in episodes:
        scene_counts[(ep.role, ep.task, ep.class_index)] += 1
    phase_n: dict[str, int] = {}
    phase_count: dict[str, Counter] = {}
    endpoint_by_run: dict[str, np.ndarray] = {}
    for ep in episodes:
        ids = endpoint_ids(ep)
        counts = Counter(ep.phase[ids].astype(int).tolist())
        endpoint_by_run[ep.run_id] = ids
        phase_n[ep.run_id] = len(counts)
        phase_count[ep.run_id] = counts
    n_total = sum(len(x) for x in endpoint_by_run.values())
    for ep in episodes:
        ids = endpoint_by_run[ep.run_id]
        w = np.zeros(len(ep.ready), dtype=np.float64)
        n_scene = scene_counts[(ep.role, ep.task, ep.class_index)]
        for q in ids:
            ph = int(ep.phase[q])
            w[q] = MASS[ep.role] / (3 * 16 * n_scene * phase_n[ep.run_id] * phase_count[ep.run_id][ph])
        ep.event_weights = w
    total = sum(float(ep.event_weights.sum()) for ep in episodes)
    if not np.isclose(total, 1.0, atol=1e-9):
        raise AssertionError(f"D4 endpoint weights sum to {total}")
    for role, mass in MASS.items():
        got = sum(float(ep.event_weights.sum()) for ep in episodes if ep.role == role)
        if not np.isclose(got, mass, atol=1e-9):
            raise AssertionError(f"D4 source mass {role}: {got} != {mass}")
        for task in ("HELIX", "FIG8_3D", "SQUARE"):
            got = sum(float(ep.event_weights.sum()) for ep in episodes if ep.role == role and ep.task == task)
            if not np.isclose(got, mass / 3, atol=1e-9):
                raise AssertionError(f"D4 task weight {role}/{task}: {got}")
    return n_total


def make_event_set(episodes: list[SeqEpisode], dim: int) -> EventSet:
    xs=[]; ys=[]; raws=[]; ws=[]; roles=[]; tasks=[]; classes=[]; winds=[]; scenes=[]; phases=[]; runs=[]; ends=[]
    for ep in episodes:
        ids = endpoint_ids(ep)
        xs.append((ep.x20 if dim == 20 else ep.x14)[ids])
        ys.append(ep.y[ids]); raws.append(ep.raw[ids]); ws.append(ep.event_weights[ids])
        roles.extend([ep.role] * len(ids)); tasks.extend([ep.task] * len(ids))
        classes.extend([ep.class_index] * len(ids)); winds.extend([ep.wind_cell] * len(ids))
        scenes.extend([ep.scene_id] * len(ids)); phases.extend(ep.phase[ids].tolist())
        runs.extend([ep.run_id] * len(ids)); ends.extend(ids.tolist())
    return EventSet(np.concatenate(xs).astype(np.float32), np.concatenate(ys).astype(np.float32),
        np.concatenate(raws).astype(np.float32), np.concatenate(ws).astype(np.float64),
        np.asarray(roles, dtype=object), np.asarray(tasks, dtype=object), np.asarray(classes, dtype=np.int64),
        np.asarray(winds, dtype=np.int64), np.asarray(scenes, dtype=object), np.asarray(phases, dtype=np.int64),
        np.asarray(runs, dtype=object), np.asarray(ends, dtype=np.int64))


def normalizer_x20(train_eps: list[SeqEpisode], initial_norm: Path) -> tuple[np.ndarray, np.ndarray]:
    norm = np.load(initial_norm)
    mu, sigma = norm["mu"].astype(np.float64).copy(), norm["sigma"].astype(np.float64).copy()
    sum_x = np.zeros(6, dtype=np.float64); sum_x2 = np.zeros(6, dtype=np.float64); count = 0
    for ep in train_eps:
        z = ep.x20[:, 14:20].astype(np.float64)
        sum_x += z.sum(axis=0); sum_x2 += np.square(z).sum(axis=0); count += len(z)
    mu20 = sum_x / count
    sigma20 = np.maximum(np.sqrt(np.maximum(sum_x2 / count - mu20 ** 2, 0.0)), 1e-4)
    mu = np.concatenate((mu, mu20)); sigma = np.concatenate((sigma, sigma20))
    return mu, sigma


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_ledger(identity: str, status: str, note: str = "") -> None:
    path = OUT / "RESOURCE_LEDGER.csv"
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    hit = False
    for r in rows:
        if r["phase"] == "D4" and r["resource_type"] == "fit" and r["identity"] == identity:
            r["status"] = status; r["notes"] = note or r["notes"]; hit = True
    if not hit:
        active = [r for r in rows if r["phase"] == "D4" and r["resource_type"] == "fit"]
        if len(active) >= 6:
            raise RuntimeError("D4 six-fit budget exhausted")
        rows.append({"timestamp_utc": now_utc(), "phase": "D4", "resource_type": "fit",
                     "identity": identity, "count": "1", "status": status,
                     "notes": note or "New isolated D4 training fit; no Plant."})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=("timestamp_utc", "phase", "resource_type", "identity", "count", "status", "notes"))
        writer.writeheader(); writer.writerows(rows)


def update_d4_state(*, active_fit: str | None, completed_fit: str | None = None) -> None:
    path = OUT / "state/state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    ledger = pd.read_csv(OUT / "RESOURCE_LEDGER.csv", keep_default_na=False)
    fits = ledger.loc[(ledger.phase == "D4") & (ledger.resource_type == "fit")]
    started_ids = set(fits.identity.astype(str))
    if active_fit:
        started_ids.add(active_fit)
    state.update({"phase": "D4_TRAINING", "next": "D4_OFFLINE_REVIEW_AND_D5_GATE",
                  "status": "IN_PROGRESS", "fits_new": len(started_ids),
                  "d4_fits_new": len(started_ids),
                  "d4_completed_fits": int((fits.status == "COMPLETED").sum()),
                  "active_fit_id": active_fit, "active_process": ([{"kind": "python_fit", "fit_id": active_fit}]
                                                                    if active_fit else []),
                  "d4_plant_starts_new": 0,
                  "updated_at_utc": now_utc()})
    completed = []
    for report_path in (OUT / "models").glob("*/seed*/fit_report.json"):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") == "COMPLETE":
            completed.append(f"{report['family']}_SEED{report['seed']}")
    if completed_fit and completed_fit not in completed:
        completed.append(completed_fit)
    state["completed_fit_ids"] = completed
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def initial_model(device: torch.device) -> PositionKAN:
    model = from_initial(ROOT / "models/position/initial/best_model.pt",
                         ROOT / "models/position/initial/normalizer.npz", 14)
    model.eval()
    # Independent replica parity against the existing frozen training class.
    from models import KANModel
    norm = np.load(ROOT / "models/position/initial/normalizer.npz")
    ref = KANModel(14, norm["mu"], norm["sigma"], position_unclipped_silu=True)
    ref.load_state_dict(torch.load(ROOT / "models/position/initial/best_model.pt", map_location="cpu", weights_only=False)["state_dict"])
    rng = np.random.default_rng(43881)
    x = torch.as_tensor(rng.normal(size=(64, 14)).astype(np.float32))
    with torch.no_grad():
        phi_err = float(torch.max(torch.abs(model.encode(x) - ref.encode(x))))
        y_err = float(torch.max(torch.abs(model(x) - ref(x))))
    if max(phi_err, y_err) > 1e-7:
        raise RuntimeError(f"D4 X14 reimplementation parity failed: phi={phi_err}, output={y_err}")
    model.to(device)
    return model


def x20_initial_model(train_eps: list[SeqEpisode], device: torch.device) -> tuple[PositionKAN, float, float]:
    mu, sigma = normalizer_x20(train_eps, ROOT / "models/position/initial/normalizer.npz")
    model = from_initial(ROOT / "models/position/initial/best_model.pt",
                         ROOT / "models/position/initial/normalizer.npz", 20, mu, sigma)
    base = initial_model(torch.device("cpu"))
    sample = torch.as_tensor(np.concatenate([e.x20[endpoint_ids(e)[:10]] for e in train_eps[:8]], axis=0), dtype=torch.float32)
    with torch.no_grad():
        phi_err = float(torch.max(torch.abs(model.encode(sample) - base.encode(sample[:, :14]))))
        out_err = float(torch.max(torch.abs(model(sample) - base(sample[:, :14]))))
    if max(phi_err, out_err) > 1e-7:
        raise RuntimeError(f"D4 X20 zero-feature initialization mismatch: phi={phi_err}, output={out_err}")
    model.to(device)
    return model, phi_err, out_err


def clone_state(model: torch.nn.Module) -> dict:
    return {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}


def save_resume(path: Path, model, optimizer, *, identity, seed, epoch, best, best_epoch, best_state, stale,
                history, rng, elapsed_seconds, fallback_count):
    torch.save({"identity": identity, "seed": seed, "epoch": epoch, "model": clone_state(model),
                "optimizer": optimizer.state_dict(), "best": best, "best_epoch": best_epoch,
                "best_state": best_state, "stale": stale, "history": history,
                "numpy_rng": rng.bit_generator.state, "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
                "elapsed_seconds": elapsed_seconds, "fallback_count": fallback_count}, path)


def report_score(model: PositionKAN, data: EventSet, device: torch.device) -> tuple[float, dict]:
    return fixed_score(model, data, "position", device)


def append_comparison(fit_report: dict) -> None:
    path = OUT / "reports/D4_TRAINING_COMPARISON.csv"
    old = pd.read_csv(path) if path.is_file() else pd.DataFrame()
    row = {k: fit_report.get(k) for k in ("family", "seed", "status", "input_dim", "best_epoch",
        "train_windows", "val_windows", "optimizer_steps_total", "loss_endpoint_exposures",
        "recurrent_event_exposures", "val_fixed_score", "val_adaptive_score", "val_selected_score",
        "best_val_detail_json", "training_seconds", "model_path", "normalizer_path")}
    old = old.loc[~((old.get("family", pd.Series(dtype=object)) == row["family"])
                    & (old.get("seed", pd.Series(dtype=float)) == row["seed"]))] if not old.empty else old
    pd.concat([old, pd.DataFrame([row])], ignore_index=True).to_csv(path, index=False)


def component_fit_data(train_eps: list[SeqEpisode], val_eps: list[SeqEpisode], dim: int):
    assign_episode_weights(train_eps); train = make_event_set(train_eps, dim)
    assign_episode_weights(val_eps); val = make_event_set(val_eps, dim)
    if len(train.x) != 756480 or len(val.x) != 56736:
        raise AssertionError(f"Unexpected D4 event windows: {len(train.x)} train, {len(val.x)} val")
    return train, val


def fit_fixed(family: str, seed: int, train_eps: list[SeqEpisode], val_eps: list[SeqEpisode], device: torch.device) -> dict:
    dim = 20 if family == "C1_X20_FIXED_INFORMATION" else 14
    identity = f"{family}_SEED{seed}"
    folder = OUT / "models" / family / f"seed{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    fit_path = folder / "fit_report.json"
    if fit_path.is_file() and json.loads(fit_path.read_text(encoding="utf-8")).get("status") == "COMPLETE":
        return json.loads(fit_path.read_text(encoding="utf-8"))
    train, val = component_fit_data(train_eps, val_eps, dim)
    seed_all(seed); rng = np.random.default_rng(seed)
    if dim == 20:
        model, init_phi_err, init_out_err = x20_initial_model(train_eps, device)
        initial_norm = ROOT / "models/position/initial/normalizer.npz"
        mu, sigma = normalizer_x20(train_eps, initial_norm)
        np.savez(folder / "normalizer.npz", mu=mu, sigma=sigma)
    else:
        model = initial_model(device); init_phi_err = init_out_err = 0.0
        norm = np.load(ROOT / "models/position/initial/normalizer.npz")
        np.savez(folder / "normalizer.npz", mu=norm["mu"], sigma=norm["sigma"])
    model_identity = {"family": family, "seed": seed, "input_dim": dim,
        "train_run_ids": sorted(e.run_id for e in train_eps), "val_run_ids": sorted(e.run_id for e in val_eps),
        "train_windows": len(train.x), "val_windows": len(val.x), "optimizer": {"Adam_lr": 1e-3,
        "weight_decay": 1e-5, "batch": 256, "max_epochs": MAX_EPOCHS, "patience": PATIENCE}}
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    init_score, init_detail = report_score(model, val, device)
    x = torch.from_numpy(train.x); y = torch.from_numpy(train.y); w = torch.from_numpy(train.weights.astype(np.float32))
    history=[]; best=init_score; best_epoch=0; stale=0; best_state=clone_state(model); start_epoch=1
    resume=folder / "resume.pt"; elapsed=0.0
    if resume.is_file():
        q=torch.load(resume,map_location="cpu",weights_only=False)
        if q.get("identity") != model_identity: raise ValueError(f"D4 resume identity mismatch: {identity}")
        model.load_state_dict(q["model"]); optimizer.load_state_dict(q["optimizer"])
        best=q["best"]; best_epoch=q["best_epoch"]; best_state=q["best_state"]; stale=q["stale"]
        history=q["history"]; start_epoch=int(q["epoch"])+1; elapsed=float(q.get("elapsed_seconds",0))
        rng.bit_generator.state=q["numpy_rng"]; torch.set_rng_state(q["torch_rng"])
        if torch.cuda.is_available() and q.get("cuda_rng") is not None: torch.cuda.set_rng_state_all(q["cuda_rng"])
    else:
        save_resume(resume,model,optimizer,identity=model_identity,seed=seed,epoch=0,best=best,best_epoch=0,
                    best_state=best_state,stale=stale,history=history,rng=rng,elapsed_seconds=0,fallback_count=0)
    update_ledger(identity,"IN_PROGRESS",f"{len(train_eps)} TRAIN episodes; 0 Plant; seed={seed}")
    started=time.perf_counter(); fallback_count=0; n=len(x)
    for epoch in range(start_epoch,MAX_EPOCHS+1):
        model.train(); order=rng.permutation(n); train_loss=0.0
        for start in range(0,n,BATCH_SIZE):
            ids=order[start:start+BATCH_SIZE]; xb=x[ids].to(device); yb=y[ids].to(device); wb=w[ids].to(device)
            pred=model(xb); per=F.smooth_l1_loss(pred/3.0,yb/3.0,reduction="none").mean(dim=1)
            loss=(n/len(ids))*torch.sum(wb*per)
            optimizer.zero_grad(set_to_none=True); loss.backward(); optimizer.step()
            train_loss += float(torch.sum(wb*per).detach().cpu())
        val_score, val_detail = report_score(model,val,device)
        improved=val_score<best-1e-10
        if improved: best=val_score; best_epoch=epoch; stale=0; best_state=clone_state(model)
        else: stale += 1
        history.append({"epoch":epoch,"train_weighted_smooth_l1":train_loss,"val_score":val_score,
                        "val_detail":val_detail,"improved":bool(improved),"stale_epochs":stale})
        elapsed += time.perf_counter()-started; started=time.perf_counter()
        save_resume(resume,model,optimizer,identity=model_identity,seed=seed,epoch=epoch,best=best,best_epoch=best_epoch,
                    best_state=best_state,stale=stale,history=history,rng=rng,elapsed_seconds=elapsed,fallback_count=fallback_count)
        print(f"[{identity}] epoch={epoch:02d} val={val_score:.9g} best={best:.9g} stale={stale}",flush=True)
        if stale>=PATIENCE: break
    model.load_state_dict(best_state)
    with torch.no_grad():
        final_score, final_detail=report_score(model,val,device)
    ckpt={"input_dim":dim,"state_dict":best_state,"epoch":best_epoch,"seed":seed,
          "modality":"position","position_unclipped_silu":True,"family":family}
    torch.save(ckpt,folder/"best_model.pt")
    (folder/"model.json").write_text(json.dumps({"model_id":identity,"input_dim":dim,"architecture":"X_KAN",
        "parameters":sum(p.numel() for p in model.parameters()),"seed":seed,"selected_epoch":best_epoch,
        "normalizer_source":"Initial X14 preserved; added X20 columns from actual TRAIN only" if dim==20 else "Initial TRAIN frozen"},indent=2),encoding="utf-8")
    pd.DataFrame(history).drop(columns=["val_detail"]).to_csv(folder/"training_history.csv",index=False)
    report={"family":family,"seed":seed,"status":"COMPLETE","input_dim":dim,"best_epoch":best_epoch,
        "train_windows":len(train.x),"val_windows":len(val.x),"train_episodes":len(train_eps),"val_episodes":len(val_eps),
        "optimizer_steps_total":sum(int(np.ceil(len(train.x)/BATCH_SIZE)) for _ in history),
        "loss_endpoint_exposures":len(train.x)*len(history),"recurrent_event_exposures":0,
        "val_fixed_score":final_score,"val_adaptive_score":None,"val_selected_score":final_score,
        "best_val_detail_json":json.dumps(final_detail,separators=(",",":")),"initial_w0_val_score":init_score,
        "initial_w0_val_detail":init_detail,"x20_initial_phi_max_abs":init_phi_err,"x20_initial_output_max_abs":init_out_err,
        "training_seconds":elapsed,"model_path":str((folder/"best_model.pt").relative_to(ROOT)).replace("\\","/"),
        "normalizer_path":str((folder/"normalizer.npz").relative_to(ROOT)).replace("\\","/"),
        "early_stopping_patience":PATIENCE,"epochs_complete":len(history),"new_plant_starts":0,"new_fits":1}
    fit_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    update_ledger(identity,"COMPLETED",f"epochs={len(history)}; best_epoch={best_epoch}; 0 Plant")
    append_comparison(report)
    return report


def recurrent_outputs(phi: torch.Tensor, surface: torch.Tensor, eta: torch.Tensor,
                      beta: torch.Tensor, W0: torch.Tensor) -> tuple[torch.Tensor,int]:
    s_eff=torch.clamp(surface-eta,min=torch.tensor([-7.,-8.,-10.],device=surface.device),
                       max=torch.tensor([7.,8.,10.],device=surface.device))
    t=phi.shape[0]; dtype=phi.dtype; device=phi.device
    lam=torch.as_tensor(LAMBDA,dtype=dtype,device=device)
    steps=torch.arange(t,dtype=dtype,device=device)
    update=beta[:,None,None]*phi[:,:,None]*s_eff[:,None,:]
    scaled=update/(lam**(steps+1)).reshape(t,1,1)
    prefix=torch.cumsum(scaled,dim=0)
    exclusive=torch.cat((torch.zeros_like(prefix[:1]),prefix[:-1]),dim=0)
    before=(lam**steps).reshape(t,1,1)*(W0.unsqueeze(0)-DT*exclusive)
    after=lam*before-DT*update
    high=max(float(before.detach().abs().max().cpu()),float(after.detach().abs().max().cpu()))
    if high <= 60.0:
        raw=torch.einsum("tij,ti->tj",before,phi)
        return beta[:,None]*torch.clamp(raw,-3.0,3.0),0
    # Preserve the exact per-event projection when a learned trajectory reaches the bound.
    w=W0; outputs=[]
    for j in range(t):
        raw=phi[j]@w
        outputs.append(beta[j]*torch.clamp(raw,-3.0,3.0))
        w=torch.clamp(w+DT*(-beta[j]*torch.outer(phi[j],s_eff[j])-0.002*w),-60.0,60.0)
    return torch.stack(outputs),1


def c2_episode_predictions(model: PositionKAN, ep: SeqEpisode, device: torch.device,
                           fixed_only: bool=False) -> tuple[np.ndarray,np.ndarray,int]:
    ids=np.flatnonzero(ep.ready)
    x=torch.as_tensor(ep.x14[ids],dtype=torch.float32,device=device)
    y=ep.y[ids].astype(np.float64); beta=torch.as_tensor(ep.beta[ids],dtype=torch.float32,device=device)
    surface=torch.as_tensor(ep.x14[ids,3:6],dtype=torch.float32,device=device)
    eta=torch.as_tensor(ep.eta[ids],dtype=torch.float32,device=device)
    with torch.set_grad_enabled(model.training and not fixed_only):
        phi=model.encode(x); W0=model.readout.weight.T
        fixed_raw=phi@W0
        fixed=beta[:,None]*torch.clamp(fixed_raw,-3.,3.)
        if fixed_only:
            pred=fixed; fallback=0
        else:
            pred,fallback=recurrent_outputs(phi,surface,eta,beta,W0)
    return pred, fixed, fallback


def c2_validation(model: PositionKAN, episodes: list[SeqEpisode], device: torch.device) -> tuple[float,float,dict,int]:
    model.eval(); preds=[]; fixed=[]; targets=[]; weights=[]; roles=[]; tasks=[]; fallback=0
    with torch.no_grad():
        for ep in episodes:
            ids=endpoint_ids(ep); local=ids-31
            pred,fix,nfb=c2_episode_predictions(model,ep,device); fallback+=nfb
            preds.append(pred[local].detach().cpu().numpy()); fixed.append(fix[local].detach().cpu().numpy())
            targets.append(ep.y[ids]); weights.append(ep.event_weights[ids]); roles.extend([ep.role]*len(ids)); tasks.extend([ep.task]*len(ids))
    y=np.concatenate(targets).astype(np.float64); w=np.concatenate(weights).astype(np.float64)
    ap=np.concatenate(preds).astype(np.float64); fp=np.concatenate(fixed).astype(np.float64)
    adapt=float(np.sqrt(np.sum(w*np.mean((ap-y)**2,axis=1))))
    fixed_score_beta=float(np.sqrt(np.sum(w*np.mean((fp-y)**2,axis=1))))
    detail={}
    role_a=np.asarray(roles,dtype=object);task_a=np.asarray(tasks,dtype=object)
    for r in sorted(set(roles)):
        m=role_a==r;detail[f"adaptive/{r}"]=float(np.sqrt(np.sum(w[m]*np.mean((ap[m]-y[m])**2,axis=1))/w[m].sum()))
        detail[f"fixed_beta/{r}"]=float(np.sqrt(np.sum(w[m]*np.mean((fp[m]-y[m])**2,axis=1))/w[m].sum()))
    for task in ("HELIX","FIG8_3D","SQUARE"):
        m=task_a==task;detail[f"adaptive/{task}"]=float(np.sqrt(np.sum(w[m]*np.mean((ap[m]-y[m])**2,axis=1))/w[m].sum()))
        detail[f"fixed_beta/{task}"]=float(np.sqrt(np.sum(w[m]*np.mean((fp[m]-y[m])**2,axis=1))/w[m].sum()))
    return adapt,fixed_score_beta,detail,fallback


def fit_c2(seed: int, train_eps: list[SeqEpisode], val_eps: list[SeqEpisode], device: torch.device) -> dict:
    family="C2_X14_ADAPTATION_AWARE"; identity=f"{family}_SEED{seed}"
    folder=OUT/"models"/family/f"seed{seed}";folder.mkdir(parents=True,exist_ok=True)
    report_path=folder/"fit_report.json"
    if report_path.is_file() and json.loads(report_path.read_text(encoding="utf-8")).get("status")=="COMPLETE":
        return json.loads(report_path.read_text(encoding="utf-8"))
    n_windows=assign_episode_weights(train_eps);assign_episode_weights(val_eps)
    if n_windows!=756480: raise AssertionError(n_windows)
    seed_all(seed);rng=np.random.default_rng(seed);model=initial_model(device)
    norm=np.load(ROOT/"models/position/initial/normalizer.npz");np.savez(folder/"normalizer.npz",mu=norm["mu"],sigma=norm["sigma"])
    optimizer=torch.optim.Adam(model.parameters(),lr=1e-3,weight_decay=1e-5)
    init_adapt,init_fixed,init_detail,init_fallback=c2_validation(model,val_eps,device)
    identity_json={"family":family,"seed":seed,"train_run_ids":sorted(e.run_id for e in train_eps),
        "val_run_ids":sorted(e.run_id for e in val_eps),"train_windows":n_windows,
        "episodes_per_epoch":len(train_eps),"ready_updates_per_epoch":len(train_eps)*1968,
        "endpoint_stride":STRIDE,"batching":"one complete episode per optimizer step",
        "loss_reduction":"train_windows / episode_endpoint_count * sum(global_event_weight * SmoothL1)"}
    resume=folder/"resume.pt";history=[];best=init_adapt;best_epoch=0;stale=0;best_state=clone_state(model)
    start_epoch=1;elapsed=0.0;fallback_total=init_fallback
    if resume.is_file():
        q=torch.load(resume,map_location="cpu",weights_only=False)
        if q.get("identity")!=identity_json:raise ValueError(f"D4 resume identity mismatch: {identity}")
        model.load_state_dict(q["model"]);optimizer.load_state_dict(q["optimizer"])
        best=q["best"];best_epoch=q["best_epoch"];best_state=q["best_state"];stale=q["stale"]
        history=q["history"];start_epoch=int(q["epoch"])+1;elapsed=float(q.get("elapsed_seconds",0))
        fallback_total=int(q.get("fallback_count",0));rng.bit_generator.state=q["numpy_rng"]
        torch.set_rng_state(q["torch_rng"])
        if torch.cuda.is_available() and q.get("cuda_rng") is not None:torch.cuda.set_rng_state_all(q["cuda_rng"])
    else:
        save_resume(resume,model,optimizer,identity=identity_json,seed=seed,epoch=0,best=best,best_epoch=0,
            best_state=best_state,stale=stale,history=history,rng=rng,elapsed_seconds=0,fallback_count=fallback_total)
    update_ledger(identity,"IN_PROGRESS",f"{len(train_eps)} full TRAIN sequences; 0 Plant; seed={seed}")
    epoch_start=time.perf_counter()
    event_ids_cache={ep.run_id:endpoint_ids(ep) for ep in train_eps}
    local_cache={ep.run_id:event_ids_cache[ep.run_id]-31 for ep in train_eps}
    for epoch in range(start_epoch,MAX_EPOCHS+1):
        model.train();order=rng.permutation(len(train_eps));epoch_loss=0.0;epoch_fb=0
        for seq_number,ep_index in enumerate(order,start=1):
            ep=train_eps[int(ep_index)];ids=event_ids_cache[ep.run_id];local=local_cache[ep.run_id]
            ready=np.flatnonzero(ep.ready)
            x=torch.as_tensor(ep.x14[ready],dtype=torch.float32,device=device)
            phi=model.encode(x)
            beta=torch.as_tensor(ep.beta[ready],dtype=torch.float32,device=device)
            surf=torch.as_tensor(ep.x14[ready,3:6],dtype=torch.float32,device=device)
            eta=torch.as_tensor(ep.eta[ready],dtype=torch.float32,device=device)
            pred,fb=recurrent_outputs(phi,surf,eta,beta,model.readout.weight.T);epoch_fb+=fb
            pred_sel=pred[local];target=torch.as_tensor(ep.y[ids],dtype=torch.float32,device=device)
            per=F.smooth_l1_loss(pred_sel/3.0,target/3.0,reduction="none").mean(dim=1)
            wseq=torch.as_tensor(ep.event_weights[ids],dtype=torch.float32,device=device)
            # Match the weighted-mean scale used by random-window minibatches:
            # N/B * sum(w_i * loss_i), where this sequence is the batch.
            loss=(n_windows/len(ids))*torch.sum(wseq*per)
            optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step()
            epoch_loss+=float(torch.sum(wseq*per).detach().cpu())
            if seq_number%240==0:
                print(f"[{identity}] epoch={epoch:02d} sequences={seq_number}/{len(train_eps)}",flush=True)
        model.eval();val_adapt,val_fixed,val_detail,val_fb=c2_validation(model,val_eps,device)
        improved=val_adapt<best-1e-10
        if improved:best=val_adapt;best_epoch=epoch;stale=0;best_state=clone_state(model)
        else:stale+=1
        history.append({"epoch":epoch,"train_weighted_smooth_l1":epoch_loss,"val_adaptive_beta_score":val_adapt,
            "val_fixed_W0_beta_score":val_fixed,"val_detail":val_detail,"improved":bool(improved),
            "stale_epochs":stale,"projection_fallback_sequences":epoch_fb,"val_projection_fallback_sequences":val_fb})
        fallback_total+=epoch_fb+val_fb
        elapsed+=time.perf_counter()-epoch_start;epoch_start=time.perf_counter()
        save_resume(resume,model,optimizer,identity=identity_json,seed=seed,epoch=epoch,best=best,best_epoch=best_epoch,
            best_state=best_state,stale=stale,history=history,rng=rng,elapsed_seconds=elapsed,fallback_count=fallback_total)
        print(f"[{identity}] epoch={epoch:02d} adaptive_val={val_adapt:.9g} fixed_beta_val={val_fixed:.9g} best={best:.9g} stale={stale} projected_fallbacks={epoch_fb}",flush=True)
        if stale>=PATIENCE:break
    model.load_state_dict(best_state);model.eval();best_adapt,best_fixed,best_detail,best_fb=c2_validation(model,val_eps,device)
    checkpoint={"input_dim":14,"state_dict":best_state,"epoch":best_epoch,"seed":seed,"modality":"position",
        "position_unclipped_silu":True,"family":family,"head_semantics":"W0 shared outer parameter; episode-reset online recurrence"}
    torch.save(checkpoint,folder/"best_model.pt")
    pd.DataFrame(history).drop(columns=["val_detail"]).to_csv(folder/"training_history.csv",index=False)
    report={"family":family,"seed":seed,"status":"COMPLETE","input_dim":14,"best_epoch":best_epoch,
        "train_windows":n_windows,"val_windows":56736,"train_episodes":len(train_eps),"val_episodes":len(val_eps),
        "optimizer_steps_total":len(train_eps)*len(history),"optimizer_steps_per_epoch":len(train_eps),
        "loss_endpoint_exposures":n_windows*len(history),"recurrent_event_exposures":len(train_eps)*1968*len(history),
        "val_fixed_score":best_fixed,"val_adaptive_score":best_adapt,"val_selected_score":best_adapt,
        "best_val_detail_json":json.dumps(best_detail,separators=(",",":")),"initial_w0_fixed_beta_score":init_fixed,
        "initial_w0_adaptive_score":init_adapt,"initial_w0_val_detail":init_detail,
        "training_seconds":elapsed,"projection_fallback_sequences_total":fallback_total,
        "model_path":str((folder/"best_model.pt").relative_to(ROOT)).replace("\\","/"),
        "normalizer_path":str((folder/"normalizer.npz").relative_to(ROOT)).replace("\\","/"),
        "epochs_complete":len(history),"new_plant_starts":0,"new_fits":1,
        "limit":"Recorded-state recurrent adaptation objective; not a differentiable closed-loop model."}
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    update_ledger(identity,"COMPLETED",f"epochs={len(history)}; best_epoch={best_epoch}; full recurrence; 0 Plant")
    append_comparison(report)
    return report


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--family",choices=("C1_X20_FIXED_INFORMATION","C2_X14_ADAPTATION_AWARE"),required=True)
    parser.add_argument("--seed",type=int,choices=SEEDS,required=True)
    args=parser.parse_args()
    train_eps=load_split("train");val_eps=load_split("val")
    if len(train_eps)!=1920 or len(val_eps)!=144:
        raise SystemExit(f"Unexpected role pool: train={len(train_eps)}, val={len(val_eps)}")
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    identity=f"{args.family}_SEED{args.seed}"
    folder=OUT/"models"/args.family/f"seed{args.seed}"
    existing=folder/"fit_report.json"
    is_complete=existing.is_file() and json.loads(existing.read_text(encoding="utf-8")).get("status")=="COMPLETE"
    if not is_complete:
        update_d4_state(active_fit=identity)
    print(f"D4 start {args.family} seed={args.seed}; device={device}; train={len(train_eps)}; val={len(val_eps)}",flush=True)
    result=fit_fixed(args.family,args.seed,train_eps,val_eps,device) if args.family.startswith("C1") else fit_c2(args.seed,train_eps,val_eps,device)
    update_d4_state(active_fit=None,completed_fit=identity)
    print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)


if __name__=="__main__":main()
