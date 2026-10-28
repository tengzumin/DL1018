#!/usr/bin/env python3
"""Independent NumPy model and fixed-J0 residual references; no Plant or VAL access."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any
import numpy as np
import torch
from scipy.io import loadmat,savemat

ROOT=Path(__file__).resolve().parents[3]


def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
    return h.hexdigest()


def silu(x:np.ndarray)->np.ndarray:
    z=np.exp(-np.clip(x,-700.0,700.0))
    return x/(1.0+z)


def numpy_mlp(window_13x15:np.ndarray,state:dict[str,torch.Tensor],target_rms:np.ndarray)->np.ndarray:
    # MATLAB column-major window(:) is event-major then feature-minor.
    x=window_13x15.T.reshape(-1).astype(np.float64)
    w=lambda key:state[key].detach().cpu().numpy().astype(np.float64)
    b=lambda key:state[key].detach().cpu().numpy().astype(np.float64)
    h=silu(w("net.0.weight")@x+b("net.0.bias"))
    h=silu(w("net.2.weight")@h+b("net.2.bias"))
    return (w("net.4.weight")@h+b("net.4.bias"))*target_rms.astype(np.float64)


def fixed_j0_residual(omega:np.ndarray,times:np.ndarray,torque:np.ndarray,J0:np.ndarray)->np.ndarray:
    span=float(times[-1]-times[0])
    alpha=(omega[-1]-omega[0])/span
    gyro=np.cross(omega[:-1],omega[:-1]@J0.T)
    torque_acc=(np.linalg.solve(J0,(gyro-torque).T)).T
    return alpha+np.mean(torque_acc,axis=0)


def run(config_path:Path,freeze_path:Path,checkpoint_sha:str)->None:
    cfg=json.loads(config_path.read_text(encoding="utf-8")); fr=json.loads(freeze_path.read_text(encoding="utf-8"))
    if sha(config_path)!=fr["training_config_sha256"] or sha(Path(__file__).with_name("TRAINING_FREEZE_MANIFEST_v1r1.json"))!=fr["freeze_manifest_sha256"]:
        raise ValueError("training freeze identity mismatch")
    run_dir=(ROOT/cfg["output_dir"]).resolve()
    checkpoint_path=run_dir/"model_final.pt"
    parity_path=run_dir/"parity_vector_v1.mat"
    mat_model_path=run_dir/"mlp15_attitude_weights_v1.mat"
    fixture_path=run_dir/"no_plant_causal_fixture_v1.mat"
    report_path=run_dir/"python_no_plant_reference_v1.json"
    for p in (fixture_path,report_path):
        if p.exists():raise FileExistsError(f"refusing to overwrite {p}")
    checkpoint_hash=sha(checkpoint_path)
    if checkpoint_hash.lower()!=checkpoint_sha.lower():raise ValueError("checkpoint SHA mismatch")
    checkpoint=torch.load(checkpoint_path,map_location="cpu",weights_only=True)
    weights_hash=sha(mat_model_path)
    mat=loadmat(mat_model_path)
    if int(checkpoint["step"])!=60000 or int(checkpoint["seed"])!=2026102001:raise ValueError("unauthorized checkpoint")
    parity=loadmat(parity_path)
    window=np.asarray(parity["input_normalized_window"],dtype=np.float64)
    expected_torch=np.asarray(parity["expected_residual_rad_s2"],dtype=np.float64).reshape(-1)
    if window.shape!=(13,15) or expected_torch.shape!=(3,):raise ValueError("training parity vector shape mismatch")
    target_rms=checkpoint["target_rms"].detach().cpu().numpy().astype(np.float64).reshape(-1)
    predicted=numpy_mlp(window,checkpoint["state_dict"],target_rms)
    err=float(np.max(np.abs(predicted-expected_torch)))
    if err>2e-6:raise AssertionError(f"NumPy vs saved PyTorch output mismatch: {err}")
    mat_output_model={
      "target_rms":np.asarray(mat["target_rms"],dtype=np.float64).reshape(-1),
      "fc1_weight":np.asarray(mat["fc1_weight"],dtype=np.float64),
      "fc1_bias":np.asarray(mat["fc1_bias"],dtype=np.float64).reshape(-1),
      "fc2_weight":np.asarray(mat["fc2_weight"],dtype=np.float64),
      "fc2_bias":np.asarray(mat["fc2_bias"],dtype=np.float64).reshape(-1),
      "head_weight":np.asarray(mat["head_weight"],dtype=np.float64),
      "head_bias":np.asarray(mat["head_bias"],dtype=np.float64).reshape(-1)}
    J0=np.diag(np.asarray(cfg["fixed_J0_diagonal_kg_m2"],dtype=np.float64))
    d=np.asarray([0.7,-0.4,0.2],dtype=np.float64)
    delta=np.asarray([0.3,-0.15,0.05],dtype=np.float64)
    alpha=np.asarray([0.4,-0.2,0.1],dtype=np.float64)
    omega_start=np.asarray([0.12,-0.07,0.2],dtype=np.float64)
    dt=0.001
    times2=0.01+np.arange(11,dtype=np.float64)*dt
    omega2=omega_start+np.arange(11,dtype=np.float64)[:,None]*dt*alpha
    gyro2=np.cross(omega2[:-1],omega2[:-1]@J0.T)
    torque2=(J0@alpha)[None,:]+gyro2-(J0@d)[None,:]
    torque2_alt=torque2+(J0@delta)[None,:]
    obs=fixed_j0_residual(omega2,times2,torque2,J0)
    obs_alt=fixed_j0_residual(omega2,times2,torque2_alt,J0)
    if np.max(np.abs(obs-d))>1e-12:raise AssertionError(f"synthetic sign/unit contract failed: {obs} vs {d}")
    if np.max(np.abs(obs_alt-(d-delta)))>1e-12:raise AssertionError("altered issued torque did not shift residual by inverse J0")
    times3=0.02+np.arange(11,dtype=np.float64)*dt
    omega3=omega2[-1]+np.arange(11,dtype=np.float64)[:,None]*dt*alpha
    gyro3=np.cross(omega3[:-1],omega3[:-1]@J0.T)
    torque3=(J0@alpha)[None,:]+gyro3-(J0@d)[None,:]
    def feature(rate):
        f=np.zeros(13,dtype=np.float64);f[3:6]=rate;return f.reshape(13,1)
    variables={
      "J0":J0,"dmax":np.asarray(cfg["runtime_output_clip_rad_s2"],dtype=np.float64).reshape(3,1),
      "parity_window_normalized":window,"parity_python_expected_rad_s2":predicted.reshape(3,1),
      "parity_scene_index_zero_based":np.asarray([[0]],dtype=np.int32),"parity_event_index_zero_based":np.asarray([[100]],dtype=np.int32),
      "feature1":feature(omega2[0]),"feature2":feature(omega2[-1]),"feature3":feature(omega3[-1]),
      "sample_index1":np.asarray([[10]],dtype=np.int32),"sample_index2":np.asarray([[20]],dtype=np.int32),"sample_index3":np.asarray([[30]],dtype=np.int32),
      "time_s1":np.asarray([[times2[0]]]),"time_s2":np.asarray([[times2[-1]]]),"time_s3":np.asarray([[times3[-1]]]),
      "omega_history2":omega2,"torque_history2":torque2,"torque_history2_alt":torque2_alt,
      "history_time2":times2.reshape(1,-1),"history_sample_indices2":np.arange(10,21,dtype=np.int64).reshape(1,-1),
      "omega_history3":omega3,"torque_history3":torque3,
      "history_time3":times3.reshape(1,-1),"history_sample_indices3":np.arange(20,31,dtype=np.int64).reshape(1,-1),
      "expected_observation2":d.reshape(3,1),"expected_observation2_alt":(d-delta).reshape(3,1),
      "expected_disturbance_accel":d.reshape(3,1),"torque_perturbation_accel":delta.reshape(3,1)}
    savemat(fixture_path,variables,do_compression=True,oned_as="row")
    report={"schema":"DL1018_MLP15_NO_PLANT_PYTHON_REFERENCE_V1","status":"PASS_PYTHON_REFERENCE",
      "checkpoint_sha256":checkpoint_hash,"mat_weights_sha256":weights_hash,
      "train_parity_fixture_source":"postprocessor TRAIN scene index 0/event index 100; no VAL data",
      "numpy_vs_torch_output_max_abs_diff_rad_s2":err,"numpy_python_expected_rad_s2":predicted.tolist(),
      "fixed_J0_residual_python_rad_s2":obs.tolist(),"expected_known_disturbance_rad_s2":d.tolist(),
      "altered_issued_torque_residual_python_rad_s2":obs_alt.tolist(),"expected_after_torque_shift_rad_s2":(d-delta).tolist(),
      "sign_and_units_fixture_max_abs_error_rad_s2":float(np.max(np.abs(obs-d))),
      "altered_torque_fixture_max_abs_error_rad_s2":float(np.max(np.abs(obs_alt-(d-delta)))),
      "fixture_path":str(fixture_path.relative_to(ROOT)).replace("\\","/"),"fixture_sha256":sha(fixture_path),
      "validation_accessed":False,"test_accessed":False,"plant_called":False}
    report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS_PYTHON_REFERENCE","numpy_torch_max_abs_diff":err,
      "synthetic_label_error":report["sign_and_units_fixture_max_abs_error_rad_s2"],
      "fixture_sha256":sha(fixture_path),"report_sha256":sha(report_path),
      "validation_accessed":False,"test_accessed":False,"plant_called":False},ensure_ascii=False))


def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--config",type=Path,required=True);p.add_argument("--freeze-manifest",type=Path,required=True);p.add_argument("--expected-checkpoint-sha256",required=True)
    a=p.parse_args();run(a.config,a.freeze_manifest,a.expected_checkpoint_sha256)
if __name__=="__main__":main()
