#!/usr/bin/env python3
"""One frozen TRAIN_C5_24-only MLP15 fit for fixed-J0 physical residuals."""
from __future__ import annotations
import argparse, hashlib, json, os, random, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
import numpy as np
import torch
from scipy.io import savemat
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
WINDOW, INPUT_DIM = 15, 13
EXPECTED_MEMBERS = {
    "x_train.npy", "y_train.npy", "scene_ids.npy", "event_indices.npy",
    "event_time_s.npy", "label_start_state_indices.npy",
    "label_endpoint_state_indices.npy", "issued_torque_last_transition_indices.npy",
    "fixed_J0_kg_m2.npy",
}
FIT_MEMBERS = {"x_train.npy", "y_train.npy"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalizer_sha256(mean: np.ndarray, std: np.ndarray, rms: np.ndarray) -> str:
    payload = np.concatenate([mean.astype("<f8"), std.astype("<f8"), rms.astype("<f8")]).tobytes()
    return sha256_bytes(payload)


def write_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


class MLP15(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(WINDOW * INPUT_DIM, 64), nn.SiLU(),
            nn.Linear(64, 32), nn.SiLU(), nn.Linear(32, 3),
        )
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x.flatten(start_dim=1))


def make_windows(padded: torch.Tensor, scenes: torch.Tensor, steps: torch.Tensor) -> torch.Tensor:
    offsets = torch.arange(WINDOW, device=padded.device, dtype=torch.long)
    indices = steps[:, None] + offsets[None, :]
    gathered = torch.gather(padded[scenes], 2, indices[:, None, :].expand(-1, INPUT_DIM, -1))
    return gathered.transpose(1, 2).contiguous()


def load_and_validate(config_path: Path, freeze_path: Path):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if config.get("schema") != "DL1018_MLP15_PHYSICAL_RESIDUAL_TRAIN_CONFIG_V1" or config.get("status") != "FROZEN":
        raise ValueError("training config is not frozen")
    if freeze.get("schema") != "DL1018_MLP15_PHYSICAL_RESIDUAL_TRAIN_FREEZE_V1" or freeze.get("status") != "FROZEN_PRETRAIN":
        raise ValueError("training freeze manifest is not frozen")
    if sha256_file(config_path) != freeze.get("training_config_sha256"):
        raise ValueError("config SHA differs from the pretraining freeze manifest")
    if sha256_file(Path(__file__).resolve()) != freeze.get("trainer_sha256"):
        raise ValueError("trainer SHA differs from the pretraining freeze manifest")
    dataset = (ROOT / config["dataset_path"]).resolve()
    data_manifest = (ROOT / config["dataset_manifest_path"]).resolve()
    if sha256_file(dataset) != config["dataset_sha256"] or sha256_file(data_manifest) != config["dataset_manifest_sha256"]:
        raise ValueError("dataset or source manifest SHA mismatch")
    if sha256_file(dataset) != freeze.get("dataset_sha256"):
        raise ValueError("dataset SHA differs from the pretraining freeze manifest")
    if "TEST" in str(dataset).upper() or "TEST" in str(data_manifest).upper():
        raise ValueError("TEST path is prohibited")
    for relative, expected_hash in config["source_code_hashes"].items():
        if sha256_file(ROOT / relative) != expected_hash:
            raise ValueError(f"source code SHA mismatch: {relative}")
    for record in config["source_raw_identities"]:
        for path_key, hash_key in (("raw_path", "raw_sha256"), ("status_path", "status_sha256"), ("run_start_path", "run_start_sha256")):
            if sha256_file(ROOT / record[path_key]) != record[hash_key]:
                raise ValueError(f"source identity SHA mismatch: {record['scene_id']} {path_key}")
    with zipfile.ZipFile(dataset, "r") as zip_archive:
        observed = {}
        for info in zip_archive.infolist():
            raw = zip_archive.read(info.filename)
            observed[info.filename] = {"sha256": sha256_bytes(raw), "bytes": len(raw)}
        if set(observed) != EXPECTED_MEMBERS:
            raise ValueError(f"NPZ member names mismatch: {sorted(observed)}")
        if observed != config["dataset_members"]:
            raise ValueError("TRAIN NPZ member hashes/sizes differ from frozen config")
    with np.load(dataset, allow_pickle=False) as archive:
        if set(archive.files) != {name[:-4] for name in EXPECTED_MEMBERS}:
            raise ValueError(f"unexpected NPZ members: {archive.files}")
        arrays = {name[:-4]: np.asarray(archive[name[:-4]]) for name in EXPECTED_MEMBERS}
    ids = arrays["scene_ids"].astype(str).tolist()
    if ids != config["train_scene_ids"] or len(ids) != 24 or len(set(ids)) != 24:
        raise ValueError("ordered TRAIN scene IDs mismatch")
    if any("TEST" in s.upper() or "VAL" in s.upper() for s in ids):
        raise ValueError("non-TRAIN scene identity in fit package")
    x, y = arrays["x_train"], arrays["y_train"]
    if x.shape != (24, 1999, 13) or y.shape != (24, 1999, 3):
        raise ValueError(f"fit array shapes invalid: {x.shape}, {y.shape}")
    if x.dtype != np.float32 or y.dtype != np.float32 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("fit arrays have invalid dtype or non-finite values")
    if config.get("fit_arrays") != ["x_train", "y_train"] or config.get("fit_split") != "TRAIN_C5_24":
        raise ValueError("only TRAIN_C5_24 x_train/y_train may be fit")
    if config.get("dataset_members") != freeze.get("dataset_members"):
        raise ValueError("NPZ member identity differs between config and freeze manifest")
    if (config.get("seed"), config.get("batch_size"), config.get("optimizer_steps"), config.get("learning_rate"), config.get("weight_decay"), config.get("smooth_l1_beta"), config.get("device")) != (2026102001,512,60000,0.001,1e-5,1.0,"cuda:0"):
        raise ValueError("frozen training recipe differs from ADDENDUM02")
    output = (ROOT / config["output_dir"]).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite run output: {output}")
    if not np.allclose(arrays["fixed_J0_kg_m2"], np.diag(config["fixed_J0_diagonal_kg_m2"]), rtol=0, atol=1e-14):
        raise ValueError("fixed J0 does not match frozen config")
    return config, freeze, dataset, data_manifest, output, arrays


def preflight(config_path: Path, freeze_path: Path) -> None:
    config, freeze, dataset, data_manifest, output, arrays = load_and_validate(config_path, freeze_path)
    mean = arrays["x_train"].mean(axis=(0, 1), dtype=np.float64)
    std = np.maximum(arrays["x_train"].std(axis=(0, 1), dtype=np.float64), 1e-6)
    rms = np.sqrt(np.mean(arrays["y_train"].astype(np.float64) ** 2, axis=(0, 1)))
    if not np.isfinite(np.r_[mean, std, rms]).all() or np.any(rms <= 1e-8):
        raise ValueError("invalid TRAIN-only normalization")
    if config.get("device") != "cuda:0" or not torch.cuda.is_available():
        raise RuntimeError("ADDENDUM02 requires cuda:0; no device fallback is allowed")
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    probe = torch.ones((64, 64), device="cuda:0")
    if not torch.isfinite(probe @ probe).all().item():
        raise RuntimeError("deterministic CUDA operation failed")
    model = MLP15()
    synthetic = torch.zeros((2, WINDOW, INPUT_DIM))
    if tuple(model(synthetic).shape) != (2, 3):
        raise AssertionError("MLP15 shape check failed")
    print(json.dumps({"status":"PREFLIGHT_PASS", "train_scenes":len(arrays["scene_ids"]),
      "train_events":int(arrays["x_train"].shape[0]*arrays["x_train"].shape[1]),
      "fit_members":sorted(FIT_MEMBERS), "dataset_sha256":sha256_file(dataset),
      "config_sha256":sha256_file(config_path), "freeze_manifest_sha256":sha256_file(freeze_path),
      "trainer_sha256":sha256_file(Path(__file__).resolve()), "output_exists":output.exists(),
      "val_loaded":False, "test_read":False, "plant_called":False}, ensure_ascii=False))


def scene_metrics(err: np.ndarray, ids: list[str]) -> dict[str, Any]:
    # err shape: scenes x events x axes, in rad/s^2.
    axes = ["roll_x", "pitch_y", "yaw_z"]
    by_wind: dict[str, Any] = {}
    groups = sorted({s.rsplit("_", 1)[-1] for s in ids})
    for wind in groups:
        ix = [i for i, sid in enumerate(ids) if sid.rsplit("_", 1)[-1] == wind]
        subset = err[ix]
        by_wind[wind] = {
            "scene_count": len(ix),
            "axis_pooled_rmse_rad_s2": dict(zip(axes, np.sqrt(np.mean(subset**2, axis=(0,1))).tolist())),
            "axis_scene_macro_rmse_rad_s2": dict(zip(axes, np.mean(np.sqrt(np.mean(subset**2, axis=1)), axis=0).tolist())),
            "scene_macro_rmse_rad_s2": float(np.mean(np.sqrt(np.mean(subset**2, axis=(1,2))))),
        }
    return {
        "axis_pooled_rmse_rad_s2": dict(zip(axes, np.sqrt(np.mean(err**2, axis=(0,1))).tolist())),
        "axis_scene_macro_rmse_rad_s2": dict(zip(axes, np.mean(np.sqrt(np.mean(err**2, axis=1)), axis=0).tolist())),
        "scene_macro_rmse_rad_s2": float(np.mean(np.sqrt(np.mean(err**2, axis=(1,2))))),
        "by_wind_group": by_wind,
    }


def train(config_path: Path, freeze_path: Path) -> None:
    config, freeze, dataset, data_manifest, output, arrays = load_and_validate(config_path, freeze_path)
    x, y = arrays["x_train"], arrays["y_train"]
    mean = x.mean(axis=(0,1), dtype=np.float64)
    std = np.maximum(x.std(axis=(0,1), dtype=np.float64), 1e-6)
    target_rms = np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=(0,1)))
    if not np.allclose(target_rms, config["target_rms_from_train_only_rad_s2"], rtol=0, atol=1e-12):
        raise ValueError("TRAIN-only target RMS differs from frozen configuration")
    if normalizer_sha256(mean, std, target_rms) != config["normalizer_arrays_sha256"]:
        raise ValueError("TRAIN-only normalizer arrays SHA differs from frozen configuration")
    normalized = ((x.astype(np.float64) - mean) / std).astype(np.float32)
    targets = (y.astype(np.float64) / target_rms).astype(np.float32)
    device_name = config["device"]
    if device_name == "cuda:0" and not torch.cuda.is_available():
        raise RuntimeError("frozen config requires CUDA but cuda:0 is unavailable")
    device = torch.device(device_name)
    seed = config["seed"]
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    train_pad = F.pad(torch.as_tensor(normalized, device=device).permute(0,2,1), (WINDOW-1,0))
    target_tensor = torch.as_tensor(targets, device=device)
    model = MLP15().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    rng = np.random.default_rng(seed)
    output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    log_every = int(config.get("log_every_steps", 1000))
    if log_every < 1:
        raise ValueError("log_every_steps must be positive")
    log_path = output / "training_log.jsonl"
    with log_path.open("w", encoding="utf-8") as log:
        for step in range(1, config["optimizer_steps"] + 1):
            scenes = torch.as_tensor(rng.integers(0,24,config["batch_size"],dtype=np.int64), device=device)
            steps = torch.as_tensor(rng.integers(0,1999,config["batch_size"],dtype=np.int64), device=device)
            windows = make_windows(train_pad, scenes, steps)
            target = target_tensor[scenes,steps]
            model.train(); optimizer.zero_grad(set_to_none=True)
            loss = F.smooth_l1_loss(model(windows), target, beta=config["smooth_l1_beta"])
            if not torch.isfinite(loss): raise FloatingPointError(f"nonfinite loss at step {step}")
            loss.backward(); optimizer.step()
            if step % log_every == 0 or step == config["optimizer_steps"]:
                row = {"step":step,"train_batch_smooth_l1_normalized":float(loss.item()),
                       "elapsed_seconds":time.perf_counter()-start,"validation_evaluated":False}
                log.write(json.dumps(row)+"\n"); log.flush()
                print(json.dumps(row), flush=True)
    # The only checkpoint is the fixed final step; no VAL metrics or selection are used.
    model.eval()
    flat_count = x.shape[0]*x.shape[1]
    prediction = np.empty(y.shape, dtype=np.float32)
    with torch.inference_mode():
        for first in range(0, flat_count, 4096):
            last = min(first+4096,flat_count)
            flat = torch.arange(first,last,device=device)
            scenes = torch.div(flat,1999,rounding_mode="floor")
            steps = torch.remainder(flat,1999)
            prediction.reshape(-1,3)[first:last] = model(make_windows(train_pad,scenes,steps)).cpu().numpy()
    prediction_phys = prediction.astype(np.float64)*target_rms
    dmax = np.asarray(config["runtime_output_clip_rad_s2"], dtype=np.float64)
    clipped = np.clip(prediction_phys,-dmax,dmax)
    metrics = scene_metrics(clipped-y.astype(np.float64), arrays["scene_ids"].astype(str).tolist())
    metrics.update({"split":"TRAIN_C5_24","event_count":int(flat_count),
                    "fit_loss_normalized_smooth_l1_final_batch":float(loss.item()),
                    "prediction_clip_rad_s2":dmax.tolist(),"prediction_was_clipped_fraction_by_axis":
                    (np.mean(np.abs(prediction_phys)>dmax,axis=(0,1))).tolist()})
    config_hash = sha256_file(config_path)
    freeze_hash = sha256_file(freeze_path)
    checkpoint = {
        "schema":"DL1018_MLP15_PHYSICAL_RESIDUAL_CHECKPOINT_V1", "step":config["optimizer_steps"],
        "seed":seed,"state_dict":model.cpu().state_dict(),
        "input_mean":torch.as_tensor(mean),"input_std":torch.as_tensor(std),
        "target_rms":torch.as_tensor(target_rms),"config_sha256":config_hash,
        "freeze_manifest_sha256":freeze_hash,"train_split":"TRAIN_C5_24",
    }
    checkpoint_path = output/"model_final.pt"
    torch.save(checkpoint,checkpoint_path)
    state=model.state_dict()
    weights_path=output/"mlp15_attitude_weights_v1.mat"
    savemat(weights_path,{
      "input_mean":mean.reshape(1,-1),"input_std":std.reshape(1,-1),"target_rms":target_rms.reshape(1,-1),
      "fc1_weight":state["net.0.weight"].numpy().astype(np.float64),"fc1_bias":state["net.0.bias"].numpy().astype(np.float64),
      "fc2_weight":state["net.2.weight"].numpy().astype(np.float64),"fc2_bias":state["net.2.bias"].numpy().astype(np.float64),
      "head_weight":state["net.4.weight"].numpy().astype(np.float64),"head_bias":state["net.4.bias"].numpy().astype(np.float64),
      "head_weight_online":np.zeros((32,3)),"head_covariance_online":10*np.eye(33),
      "seed":np.asarray([[seed]],dtype=np.int64),"training_step":np.asarray([[config["optimizer_steps"]]],dtype=np.int64),
    },do_compression=True,oned_as="row")
    sample_window = make_windows(train_pad,torch.tensor([0],device=device),torch.tensor([100],device=device))
    with torch.inference_mode(): expected=(model(sample_window).cpu().numpy()[0]*target_rms)
    parity_path=output/"parity_vector_v1.mat"
    savemat(parity_path,{"input_normalized_window":sample_window.cpu().numpy()[0].astype(np.float64).T,
       "expected_residual_rad_s2":expected.astype(np.float64),"scene_index_zero_based":np.asarray([[0]],dtype=np.int32),
       "event_index_zero_based":np.asarray([[100]],dtype=np.int32)},do_compression=True,oned_as="row")
    write_json(output/"training_metrics_train.json",metrics)
    receipt={"schema":"DL1018_MLP15_PHYSICAL_RESIDUAL_TRAIN_RECEIPT_V1","status":"PASS",
      "train_split":"TRAIN_C5_24","fit_members":["x_train","y_train"],"seed":seed,
      "optimizer_steps":config["optimizer_steps"],"config_sha256":config_hash,
      "freeze_manifest_sha256":freeze_hash,"trainer_sha256":sha256_file(Path(__file__).resolve()),
      "dataset_sha256":sha256_file(dataset),"dataset_manifest_sha256":sha256_file(data_manifest),
      "input_mean_fit_split":"TRAIN_C5_24","input_std_fit_split":"TRAIN_C5_24",
      "target_rms_fit_split":"TRAIN_C5_24","validation_during_training":False,
      "val_used_for_fit":False,"test_read":False,"plant_called":False,
      "device":str(device),"torch_version":torch.__version__,
      "cuda_name":torch.cuda.get_device_name(0) if device.type=="cuda" else None,
      "elapsed_seconds":time.perf_counter()-start,
      "output_sha256":{p.name:sha256_file(p) for p in (checkpoint_path,weights_path,parity_path,output/"training_log.jsonl",output/"training_metrics_train.json")}}
    write_json(output/"training_receipt.json",receipt)
    print(json.dumps({"status":"TRAINING_PASS","output_dir":str(output),"metrics":metrics,
      "elapsed_seconds":receipt["elapsed_seconds"],"plant_called":False,"val_used_for_fit":False,"test_read":False},ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--freeze-manifest",type=Path,required=True)
    parser.add_argument("--preflight",action="store_true")
    args=parser.parse_args()
    if args.preflight: preflight(args.config,args.freeze_manifest)
    else: train(args.config,args.freeze_manifest)

if __name__=="__main__": main()

