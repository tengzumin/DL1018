#!/usr/bin/env python3
"""CPU-only, read-only model postprocessing; never fits or accesses validation data."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
import numpy as np
import torch
from scipy.io import loadmat,savemat
from torch.nn import functional as F

ROOT=Path(__file__).resolve().parents[3]
AXES=("roll_x","pitch_y","yaw_z")
WINDOW,INPUT_DIM=15,13


def sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def normalizer_sha256(mean:np.ndarray,std:np.ndarray,rms:np.ndarray)->str:
    payload=np.concatenate([mean.astype("<f8"),std.astype("<f8"),rms.astype("<f8")]).tobytes()
    return hashlib.sha256(payload).hexdigest()


def make_windows(padded:torch.Tensor,scenes:torch.Tensor,steps:torch.Tensor)->torch.Tensor:
    offsets=torch.arange(WINDOW,dtype=torch.long,device="cpu")
    indices=steps[:,None]+offsets[None,:]
    gathered=torch.gather(padded[scenes],2,indices[:,None,:].expand(-1,INPUT_DIM,-1))
    return gathered.transpose(1,2).contiguous()


def forward_physical(window:torch.Tensor,state:dict[str,torch.Tensor],target_rms:torch.Tensor)->torch.Tensor:
    flat=window.flatten(start_dim=1)
    h=F.silu(F.linear(flat,state["net.0.weight"],state["net.0.bias"]))
    h=F.silu(F.linear(h,state["net.2.weight"],state["net.2.bias"]))
    return F.linear(h,state["net.4.weight"],state["net.4.bias"])*target_rms


def metric_summary(error:np.ndarray,scene_ids:list[str])->dict[str,Any]:
    by_wind={}
    winds=sorted({sid.rsplit("_",1)[-1] for sid in scene_ids})
    for wind in winds:
        indices=[i for i,sid in enumerate(scene_ids) if sid.rsplit("_",1)[-1]==wind]
        subset=error[indices]
        by_wind[wind]={
            "scene_count":len(indices),
            "axis_pooled_rmse_rad_s2":dict(zip(AXES,np.sqrt(np.mean(subset**2,axis=(0,1))).tolist())),
            "axis_scene_macro_rmse_rad_s2":dict(zip(AXES,np.mean(np.sqrt(np.mean(subset**2,axis=1)),axis=0).tolist())),
            "scene_macro_rmse_rad_s2":float(np.mean(np.sqrt(np.mean(subset**2,axis=(1,2))))),
        }
    return {
        "split":"TRAIN_C5_24","event_count":int(error.shape[0]*error.shape[1]),
        "axis_pooled_rmse_rad_s2":dict(zip(AXES,np.sqrt(np.mean(error**2,axis=(0,1))).tolist())),
        "axis_scene_macro_rmse_rad_s2":dict(zip(AXES,np.mean(np.sqrt(np.mean(error**2,axis=1)),axis=0).tolist())),
        "scene_macro_rmse_rad_s2":float(np.mean(np.sqrt(np.mean(error**2,axis=(1,2))))),
        "by_wind_group":by_wind,
    }


def run(config_path:Path,freeze_path:Path,expected_checkpoint_sha256:str)->None:
    # PyTorch is constrained to CPU: no CUDA query or CUDA tensor is used here.
    torch.set_grad_enabled(False)
    config=json.loads(config_path.read_text(encoding="utf-8"))
    freeze=json.loads(freeze_path.read_text(encoding="utf-8"))
    config_hash=sha256_file(config_path); freeze_hash=sha256_file(freeze_path)
    if config.get("status")!="FROZEN" or freeze.get("status")!="FROZEN_PRETRAIN":
        raise ValueError("repair config/freeze manifest is not frozen")
    if config_hash!=freeze.get("training_config_sha256") or config.get("trainer_sha256")!=freeze.get("trainer_sha256"):
        raise ValueError("config/trainer identity differs from frozen manifest")
    for ref in config.get("addenda",[]):
        if sha256_file(ROOT/ref["path"])!=ref["sha256"]:
            raise ValueError(f"bound addendum SHA mismatch: {ref['path']}")
    dataset=(ROOT/config["dataset_path"]).resolve()
    checkpoint_path=(ROOT/config["output_dir"])/"model_final.pt"
    weights_path=(ROOT/config["output_dir"])/"mlp15_attitude_weights_v1.mat"
    output_dir=checkpoint_path.parent
    training_log_path=output_dir/"training_log.jsonl"
    training_stderr_path=config_path.resolve().parent/"training_stderr_v1r1.log"
    metrics_path=output_dir/"training_metrics_train.json"
    parity_path=output_dir/"parity_vector_v1.mat"
    receipt_path=output_dir/"training_postprocess_receipt_v1.json"
    for path in (metrics_path,parity_path,receipt_path):
        if path.exists(): raise FileExistsError(f"refusing to overwrite postprocess artifact: {path}")
    dataset_hash=sha256_file(dataset)
    checkpoint_hash=sha256_file(checkpoint_path)
    if expected_checkpoint_sha256.lower()!=checkpoint_hash:
        raise ValueError("checkpoint SHA differs from explicitly reviewed input SHA")
    if dataset_hash!=config.get("dataset_sha256") or dataset_hash!=freeze.get("dataset_sha256"):
        raise ValueError("TRAIN NPZ SHA differs from frozen config/manifest")
    if not weights_path.is_file(): raise FileNotFoundError(weights_path)
    log_bytes=training_log_path.read_bytes()
    log_lines=log_bytes.splitlines(keepends=True)
    expected_steps=list(range(config["log_every_steps"],config["optimizer_steps"]+1,config["log_every_steps"]))
    if len(log_lines)!=len(expected_steps): raise ValueError("training log line count differs from frozen 1000-step cadence")
    log_rows=[json.loads(line.decode("utf-8")) for line in log_lines]
    if [row.get("step") for row in log_rows]!=expected_steps or expected_steps[-1]!=60000:
        raise ValueError("training log steps are missing, duplicated, or out of order")
    elapsed_values=[]
    for row in log_rows:
        if row.get("validation_evaluated") is not False:
            raise ValueError("training log indicates a validation evaluation")
        loss=row.get("train_batch_smooth_l1_normalized"); elapsed=row.get("elapsed_seconds")
        if not isinstance(loss,(int,float)) or not np.isfinite(loss): raise ValueError("non-finite training loss log entry")
        if not isinstance(elapsed,(int,float)) or not np.isfinite(elapsed): raise ValueError("non-finite elapsed time log entry")
        elapsed_values.append(float(elapsed))
    if any(b<=a for a,b in zip(elapsed_values,elapsed_values[1:])):
        raise ValueError("training elapsed-time log is not strictly increasing")
    training_log_hash=hashlib.sha256(log_bytes).hexdigest()
    final_log_row_hash=hashlib.sha256(log_lines[-1]).hexdigest()
    final_log_row={k:log_rows[-1][k] for k in ("step","train_batch_smooth_l1_normalized","elapsed_seconds","validation_evaluated")}
    stderr_bytes=training_stderr_path.read_bytes()
    stderr_text=stderr_bytes.decode("utf-8",errors="replace")
    device_error_marker="RuntimeError: Expected all tensors to be on the same device"
    if device_error_marker not in stderr_text or "cpu and cuda:0!" not in stderr_text:
        raise ValueError("training stderr lacks the recorded CPU/CUDA parity-export error")
    training_stderr_hash=hashlib.sha256(stderr_bytes).hexdigest()
    checkpoint=torch.load(checkpoint_path,map_location="cpu",weights_only=True)
    if int(checkpoint.get("step",-1))!=60000 or int(checkpoint.get("seed",-1))!=2026102001:
        raise ValueError("checkpoint is not the authorized final 60k step / seed")
    if checkpoint.get("train_split")!="TRAIN_C5_24": raise ValueError("checkpoint split mismatch")
    if checkpoint.get("config_sha256")!=config_hash or checkpoint.get("freeze_manifest_sha256")!=freeze_hash:
        raise ValueError("checkpoint config/freeze identity mismatch")
    if sha256_file(checkpoint_path)!=checkpoint_hash: raise ValueError("checkpoint changed while read")
    expected_shapes={"net.0.weight":(64,195),"net.0.bias":(64,),
      "net.2.weight":(32,64),"net.2.bias":(32,),"net.4.weight":(3,32),"net.4.bias":(3,)}
    checkpoint_state=checkpoint.get("state_dict",{})
    if set(checkpoint_state)!=set(expected_shapes): raise ValueError("checkpoint state_dict key mismatch")
    checkpoint_shape_report={}
    for key,shape in expected_shapes.items():
        actual=tuple(checkpoint_state[key].shape)
        if actual!=shape: raise ValueError(f"checkpoint parameter shape mismatch for {key}: {actual} != {shape}")
        checkpoint_shape_report[key]=list(actual)
    normalizer_shapes={"input_mean":(13,),"input_std":(13,),"target_rms":(3,)}
    for key,shape in normalizer_shapes.items():
        actual=tuple(checkpoint[key].shape)
        if actual!=shape: raise ValueError(f"checkpoint normalizer shape mismatch for {key}: {actual} != {shape}")
    weight_mat=loadmat(weights_path)
    mat_fields={"net.0.weight":"fc1_weight","net.0.bias":"fc1_bias",
      "net.2.weight":"fc2_weight","net.2.bias":"fc2_bias",
      "net.4.weight":"head_weight","net.4.bias":"head_bias"}
    parameter_parity={}
    for key,field in mat_fields.items():
        if field not in weight_mat: raise ValueError(f"MAT weight missing {field}")
        expected=checkpoint_state[key].detach().cpu().numpy().astype(np.float64).reshape(-1)
        observed=np.asarray(weight_mat[field],dtype=np.float64).reshape(-1)
        if expected.size!=observed.size or not np.array_equal(expected,observed):
            raise ValueError(f"checkpoint/MAT parameter mismatch: {key}/{field}")
        parameter_parity[field]={"element_count":int(expected.size),"max_abs_diff":0.0,"values_exact_after_flatten":True}
    for key in ("input_mean","input_std","target_rms"):
        if key not in weight_mat: raise ValueError(f"MAT normalizer missing {key}")
        expected=checkpoint[key].detach().cpu().numpy().astype(np.float64).reshape(-1)
        observed=np.asarray(weight_mat[key],dtype=np.float64).reshape(-1)
        if expected.size!=observed.size or not np.array_equal(expected,observed):
            raise ValueError(f"checkpoint/MAT normalizer mismatch: {key}")
        parameter_parity[key]={"element_count":int(expected.size),"max_abs_diff":0.0,"values_exact_after_flatten":True}

    # Only these two arrays are loaded from the NPZ; no scene/VAL/TEST member is touched.
    with np.load(dataset,allow_pickle=False) as archive:
        x=np.asarray(archive["x_train"])
        y=np.asarray(archive["y_train"])
    if x.shape!=(24,1999,13) or y.shape!=(24,1999,3) or x.dtype!=np.float32 or y.dtype!=np.float32:
        raise ValueError(f"unexpected TRAIN array shapes/dtypes: {x.shape}/{x.dtype}; {y.shape}/{y.dtype}")
    if not np.isfinite(x).all() or not np.isfinite(y).all(): raise ValueError("non-finite TRAIN array")
    scene_ids=config.get("train_scene_ids",[])
    if len(scene_ids)!=24 or len(set(scene_ids))!=24 or any("VAL" in s.upper() or "TEST" in s.upper() for s in scene_ids):
        raise ValueError("config does not contain the exact 24 TRAIN scene identities")
    mean=x.mean(axis=(0,1),dtype=np.float64)
    std=np.maximum(x.std(axis=(0,1),dtype=np.float64),1e-6)
    rms=np.sqrt(np.mean(y.astype(np.float64)**2,axis=(0,1)))
    ck_mean=checkpoint["input_mean"].numpy().reshape(-1)
    ck_std=checkpoint["input_std"].numpy().reshape(-1)
    ck_rms=checkpoint["target_rms"].numpy().reshape(-1)
    if not (np.allclose(mean,ck_mean,rtol=0,atol=1e-12) and np.allclose(std,ck_std,rtol=0,atol=1e-12) and np.allclose(rms,ck_rms,rtol=0,atol=1e-12)):
        raise ValueError("checkpoint normalizers differ from recomputed TRAIN-only statistics")
    if normalizer_sha256(mean,std,rms)!=config["normalizer_arrays_sha256"]:
        raise ValueError("recomputed TRAIN-only normalizer SHA mismatch")
    if [float(v) for v in rms]!=config["target_rms_from_train_only_rad_s2"]:
        if not np.allclose(rms,config["target_rms_from_train_only_rad_s2"],rtol=0,atol=1e-12):
            raise ValueError("target RMS differs from frozen config")

    normalized=((x.astype(np.float64)-mean)/std).astype(np.float32)
    padded=F.pad(torch.as_tensor(normalized,dtype=torch.float32,device="cpu").permute(0,2,1),(WINDOW-1,0))
    state=checkpoint_state
    state={k:v.detach().to(device="cpu",dtype=torch.float32) for k,v in state.items()}
    rms_tensor=torch.as_tensor(ck_rms,dtype=torch.float32,device="cpu")
    prediction=np.empty(y.shape,dtype=np.float32)
    total=24*1999
    with torch.inference_mode():
        for first in range(0,total,4096):
            stop=min(first+4096,total)
            flat=torch.arange(first,stop,dtype=torch.long,device="cpu")
            scenes=torch.div(flat,1999,rounding_mode="floor")
            steps=torch.remainder(flat,1999)
            prediction.reshape(-1,3)[first:stop]=forward_physical(make_windows(padded,scenes,steps),state,rms_tensor).numpy()
    dmax=np.asarray(config["runtime_output_clip_rad_s2"],dtype=np.float64)
    clipped=np.clip(prediction.astype(np.float64),-dmax,dmax)
    error=clipped-y.astype(np.float64)
    metrics=metric_summary(error,scene_ids)
    metrics.update({"prediction_clip_rad_s2":dmax.tolist(),
      "prediction_was_clipped_fraction_by_axis":np.mean(np.abs(prediction)>dmax,axis=(0,1)).tolist(),
      "input_mean_sha256":hashlib.sha256(mean.astype("<f8").tobytes()).hexdigest(),
      "input_std_sha256":hashlib.sha256(std.astype("<f8").tobytes()).hexdigest(),
      "target_rms_sha256":hashlib.sha256(rms.astype("<f8").tobytes()).hexdigest(),
      "metrics_source":"CPU-only inference from frozen final checkpoint over TRAIN_C5_24; no refit"})

    # MATLAB parity fixture is one TRAIN event window; output is the unclipped head prediction.
    scene_index,event_index=0,100
    window=make_windows(padded,torch.tensor([scene_index]),torch.tensor([event_index]))
    with torch.inference_mode(): expected=forward_physical(window,state,rms_tensor).numpy()[0].astype(np.float64)
    if not parity_path.exists():
        savemat(parity_path,{"input_normalized_window":window.numpy()[0].astype(np.float64).T,
          "expected_residual_rad_s2":expected,"scene_index_zero_based":np.asarray([[scene_index]],dtype=np.int32),
          "event_index_zero_based":np.asarray([[event_index]],dtype=np.int32)},do_compression=True,oned_as="row")
    metrics_path.write_text(json.dumps(metrics,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    receipt={"schema":"DL1018_MLP15_PHYSICAL_RESIDUAL_POSTPROCESS_RECEIPT_V1","status":"PASS_CPU_POSTPROCESS",
      "postprocessor_sha256":sha256_file(Path(__file__).resolve()),
      "checkpoint_sha256":checkpoint_hash,"matlab_weights_sha256":sha256_file(weights_path),
      "train_dataset_sha256":dataset_hash,"training_config_sha256":config_hash,"freeze_manifest_sha256":freeze_hash,
      "trainer_execution":{"completed_optimizer_updates":60000,"completed_training":True,
        "post_training_export_status":"trainer exited after checkpoint and MATLAB weights export while generating parity vector",
        "trainer_exit_nonzero":True,"trainer_exit_code":1,
        "post_training_error":"RuntimeError: Expected all tensors to be on the same device, but found at least two devices, cpu and cuda:0!",
        "training_log_sha256":training_log_hash,"training_log_line_count":len(log_rows),
        "training_log_steps_first_last":[log_rows[0]["step"],log_rows[-1]["step"]],
        "training_log_final_row_sha256":final_log_row_hash,"training_log_final_row_summary":final_log_row,
        "training_stderr_sha256":training_stderr_hash,"training_stderr_contains_known_device_error":True,
        "root_cause":"model.cpu() for checkpoint serialization moved the live model to CPU; the subsequent parity window remained on cuda:0"},
      "postprocess":{"device":"cpu","optimizer_step_called":False,"checkpoint_or_weights_modified":False,
        "checkpoint_state_dict_shapes":checkpoint_shape_report,"checkpoint_mat_value_comparison":parameter_parity,
        "metrics_recomputed_from":"x_train,y_train only","parity_fixture":"TRAIN scene index 0, event index 100",
        "val_arrays_loaded":False,"test_arrays_loaded":False,"plant_called":False},
      "outputs_sha256":{"training_metrics_train.json":sha256_file(metrics_path),
        "parity_vector_v1.mat":sha256_file(parity_path),"model_final.pt":checkpoint_hash,
        "mlp15_attitude_weights_v1.mat":sha256_file(weights_path),
        "training_log.jsonl":training_log_hash,"training_stderr_v1r1.log":training_stderr_hash}}
    receipt_path.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if sha256_file(checkpoint_path)!=checkpoint_hash: raise RuntimeError("checkpoint was modified by postprocessor")
    print(json.dumps({"status":"PASS_CPU_POSTPROCESS","checkpoint_sha256":checkpoint_hash,
      "metrics_sha256":sha256_file(metrics_path),"parity_sha256":sha256_file(parity_path),
      "receipt_sha256":sha256_file(receipt_path),"val_arrays_loaded":False,"test_arrays_loaded":False,"plant_called":False},ensure_ascii=False))


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--freeze-manifest",type=Path,required=True)
    parser.add_argument("--expected-checkpoint-sha256",required=True)
    args=parser.parse_args()
    run(args.config,args.freeze_manifest,args.expected_checkpoint_sha256)

if __name__=="__main__":main()
