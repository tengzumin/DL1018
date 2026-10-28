"""Fixed-trajectory event-stream replay: keep XY straight-through, notch Z only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.transform import Rotation


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCORE = ROOT / "experiments/dl_attitude_replacement_20261028/gru_cosine_c5_applied_notch_35hz_q1_v1/audits/NOTCH_HF6_FROZEN_SCORE_v2.json"
OUT_JSON = HERE / "Z_ONLY_NOTCH_FIXED_TRAJECTORY_HF6_v2.json"
OUT_MD = HERE / "Z_ONLY_NOTCH_FIXED_TRAJECTORY_HF6_v2.md"
SCENES = (
    "DL1018_VAL_T3_C01_W14", "DL1018_DEV_T1_C10_W09", "DL1018_DEV_T2_C09_W10",
    "DL1018_DEV_T3_C09_W09", "DL1018_VAL_T1_C07_W14", "DL1018_VAL_T2_C04_W14",
)
DT, EVENT_DT, MASS, G = 0.001, 0.01, 0.695, 9.8
MAX_TILT = np.pi / 6
WN = np.array([18.0, 18.0, 12.0])
ZETA = np.ones(3)
YAW_ACCEL_LIMIT = 6.0
BANDS = ((2.0, 5.0),)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def arr3(g: h5py.Group, name: str, n: int) -> np.ndarray:
    x = np.asarray(g[name][()], dtype=float)
    if x.shape == (3, n):
        x = x.T
    if x.shape != (n, 3):
        raise RuntimeError(f"{name}: expected {(n, 3)}, got {x.shape}")
    return x


def wrap(a: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(a), np.cos(a))


def target_euler(accel: np.ndarray, yaw_state: np.ndarray, yaw_ref: np.ndarray) -> np.ndarray:
    specific = accel.copy()
    specific[:, 2] += G
    aa = np.cos(yaw_state)*specific[:, 0] + np.sin(yaw_state)*specific[:, 1]
    bb = np.sin(yaw_state)*specific[:, 0] - np.cos(yaw_state)*specific[:, 1]
    roll = np.arctan2(bb, np.hypot(specific[:, 2], aa))
    pitch = np.arctan2(aa, specific[:, 2])
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, MAX_TILT/np.maximum(tilt, np.finfo(float).eps))
    return np.column_stack((roll*scale, pitch*scale, yaw_ref))


def task_euler(ref_acc: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    return target_euler(ref_acc, yaw, yaw)


def replay_command_filter(target: np.ndarray, initial: np.ndarray) -> np.ndarray:
    state_euler = initial.copy()
    rate = np.zeros(3)
    out = np.empty_like(target)
    for k, cmd in enumerate(target):
        out[k] = state_euler
        err = wrap(cmd-state_euler)
        requested = WN**2*err - 2*ZETA*WN*rate
        alpha = np.clip(requested, [-np.inf, -np.inf, -YAW_ACCEL_LIMIT],
                        [np.inf, np.inf, YAW_ACCEL_LIMIT])
        rate += DT*alpha
        state_euler = wrap(state_euler+DT*rate)
    return out


def geodesic_rmse(a: np.ndarray, b: np.ndarray) -> float:
    d = (Rotation.from_euler("xyz", a).inv()*Rotation.from_euler("xyz", b)).magnitude()
    return float(np.sqrt(np.mean(d**2)))


def band_power(x: np.ndarray, low: float, high: float) -> float:
    n = len(x)
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(n, DT)
    w = np.full(len(f), 2.0); w[0] = 1.0
    if n % 2 == 0: w[-1] = 1.0
    use = (f >= low) & (f < high)
    return float(np.sum(np.abs(X[use])**2*w[use, None])/n**2)


def band_rms(x: np.ndarray, low: float, high: float) -> float:
    return float(np.sqrt(max(0.0, band_power(x, low, high))))


def signed_cross_power(a: np.ndarray, b: np.ndarray, low: float, high: float) -> float:
    n = len(a); A = np.fft.rfft(a, axis=0); B = np.fft.rfft(b, axis=0)
    f = np.fft.rfftfreq(n, DT)
    w = np.full(len(f), 2.0); w[0] = 1.0
    if n % 2 == 0: w[-1] = 1.0
    use = (f >= low) & (f < high)
    return float(2*np.sum(np.real(A[use]*np.conj(B[use]))*w[use, None])/n**2)


def zoh(event_output: np.ndarray, event_idx: np.ndarray, n: int) -> np.ndarray:
    result = np.zeros((n, 3)); held = np.zeros(3); event_set = set(map(int, event_idx))
    for k in range(n):
        if k in event_set: held = event_output[k].copy()
        result[k] = held
    return result


def replay_scene(row: dict) -> dict:
    sid = row["scene_id"]
    bindings = row["bindings"]
    cand = bindings["Applied_Notch_3p5Hz_Q1"]
    parent = bindings["Parent_Cosine_GRU"]
    raw_path, parent_path = Path(cand["raw_path"]), Path(parent["raw_path"])
    if sha(raw_path).lower() != cand["raw_sha256"].lower():
        raise RuntimeError(f"notch raw SHA mismatch: {sid}")
    if sha(parent_path).lower() != parent["raw_sha256"].lower():
        raise RuntimeError(f"parent raw SHA mismatch: {sid}")
    for info, method in ((cand,"notch"),(parent,"parent")):
        status_path = Path(info["run_status_path"])
        if sha(status_path).lower() != info["run_status_sha256"].lower():
            raise RuntimeError(f"{method} run-status SHA mismatch: {sid}")
        status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        if status.get("scene_id") != sid or status.get("safety_stop_reason", "") != "" or \
           status.get("test_data_read", status.get("TEST_read", status.get("TEST_accessed", False))) is not False:
            raise RuntimeError(f"{method} status scope/identity mismatch: {sid}")

    with h5py.File(raw_path, "r") as f:
        log = f["log"]; ident = f["runIdentity"]
        time = np.asarray(log["transition_time"][()], float).reshape(-1); n = len(time)
        state = np.asarray(log["state"][()], float).T[:n]
        events = np.asarray(log["stage1_position_event"][()], bool).reshape(-1)
        inference_valid = np.asarray(log["stage1_position_event_inference_valid"][()], bool).reshape(-1)
        idx = np.flatnonzero(events)
        notch_input = arr3(log,"stage1_position_applied_notch_event_input_mps2",n)
        logged_raw = arr3(log,"stage1_position_applied_notch_event_output_raw_mps2",n)
        logged_applied = arr3(log,"stage1_position_applied_notch_event_output_applied_mps2",n)
        limits = arr3(log,"stage1_position_applied_notch_event_output_limit_mps2",n)
        logged_clip = arr3(log,"stage1_position_applied_notch_event_clip_active",n).astype(bool)
        head_event = arr3(log,"stage1_position_event_applied_acceleration_mps2",n)
        actual_comp = arr3(log,"position_compensation_applied_acceleration_mps2",n)
        nominal = arr3(log,"position_nominal_acceleration_mps2",n)
        actual_command_force = arr3(log,"position_commanded_force_N",n)
        target_logged = arr3(log,"command_filter_target_euler",n)
        filtered_logged = arr3(log,"filtered_attitude_reference",n)
        ref_acc = arr3(f["scene/reference"],"acceleration",n+1)[:n]
        ref_yaw = np.asarray(f["scene/reference/yaw"][()],float).reshape(-1)[:n]
        b = np.asarray(ident["notch_b"][()],float).reshape(-1)
        a = np.asarray(ident["notch_a"][()],float).reshape(-1)
        tau = float(np.asarray(ident["position_delayed_prediction_tau_s"][()]).squeeze())
        rho = float(np.asarray(ident["position_delayed_prediction_rho"][()]).squeeze())

    if n != 20000 or len(idx)!=1999 or not np.array_equal(np.diff(idx),np.full(1998,10)):
        raise RuntimeError(f"notch event alignment mismatch: {sid}")
    if np.max(np.abs(np.diff(time)-DT))>1e-12 or abs(time[idx[0]]-EVENT_DT)>1e-12:
        raise RuntimeError(f"transition/event time mismatch: {sid}")
    valid, invalid = idx[inference_valid[idx]], idx[~inference_valid[idx]]
    if not np.allclose(notch_input[valid],head_event[valid],atol=1e-12,rtol=0) or \
       np.max(np.abs(notch_input[invalid]))>1e-12:
        raise RuntimeError(f"notch input does not bind to actual head output: {sid}")

    # Validate actual full XYZ notch recurrence, then replay fixed coefficients on Z only.
    s_full=np.zeros((3,4)); s_z=np.zeros((1,4))
    full_raw=np.zeros((n,3)); z_raw=np.zeros((n,3)); z_applied=np.zeros((n,3))
    full_rec_max=0.0
    for k in idx:
        x=notch_input[k]
        y=b[0]*x+b[1]*s_full[:,0]+b[2]*s_full[:,1]-a[1]*s_full[:,2]-a[2]*s_full[:,3]
        full_rec_max=max(full_rec_max,float(np.max(np.abs(y-logged_raw[k]))))
        s_full=np.column_stack((x,s_full[:,0],y,s_full[:,2]))
        zy=b[0]*x[2]+b[1]*s_z[0,0]+b[2]*s_z[0,1]-a[1]*s_z[0,2]-a[2]*s_z[0,3]
        s_z=np.array([[x[2],s_z[0,0],zy,s_z[0,2]]])
        z_raw[k]=[x[0],x[1],zy]
        z_applied[k]=np.minimum(np.maximum(z_raw[k],-limits[k]),limits[k])
    full_comp=zoh(logged_applied,idx,n)
    z_comp=zoh(z_applied,idx,n)
    full_hold_error=float(np.max(np.abs(full_comp-actual_comp)))
    # Reconstruct adapter target and frozen command-filter output from the fixed raw state trajectory.
    yaw_state=state[:,8]
    actual_accel=actual_command_force/MASS
    task=task_euler(ref_acc,ref_yaw)
    full_target=target_euler(nominal-full_comp,yaw_state,ref_yaw)
    full_target_err=float(np.max(np.abs(wrap(full_target-target_logged))))
    replay_full=replay_command_filter(full_target,state[0,6:9])
    full_filter_err=float(np.max(np.abs(wrap(replay_full-filtered_logged))))
    z_target=target_euler(nominal-z_comp,yaw_state,ref_yaw)
    z_filtered=replay_command_filter(z_target,state[0,6:9])
    if max(full_target_err,full_filter_err,full_rec_max,full_hold_error)>1e-9:
        raise RuntimeError(f"full-notch replay parity failed {sid}: {full_target_err}, {full_filter_err}, {full_rec_max}")
    if np.max(np.abs(actual_accel-(nominal-full_comp)))>2e-10:
        raise RuntimeError(f"logged full-notch force identity mismatch: {sid}")

    with h5py.File(parent_path,"r") as f:
        parent_filter=arr3(f["log"],"filtered_attitude_reference",n)
        parent_acc=arr3(f["scene/reference"],"acceleration",n+1)[:n]
        parent_yaw=np.asarray(f["scene/reference/yaw"][()],float).reshape(-1)[:n]
    ref_difference=max(float(np.max(np.abs(parent_acc-ref_acc))),float(np.max(np.abs(wrap(parent_yaw-ref_yaw)))))
    if ref_difference>1e-12: raise RuntimeError(f"parent/task reference mismatch {sid}")

    delta_target=z_target[:,:2]-full_target[:,:2]
    delta_filtered=z_filtered[:,:2]-replay_full[:,:2]
    comp_band={}
    for low,high in BANDS:
        key=f"{low:g}_{high:g}Hz"
        p_full=band_power(full_target[:,:2],low,high)
        p_delta=band_power(delta_target,low,high)
        p_z=band_power(z_target[:,:2],low,high)
        cross=signed_cross_power(full_target[:,:2],delta_target,low,high)
        filtered_cross=signed_cross_power(replay_full[:,:2],delta_filtered,low,high)
        comp_band[key]={
            "full_notch_compensation_rms_mps2":band_rms(full_comp,low,high),
            "z_only_notch_compensation_rms_mps2":band_rms(z_comp,low,high),
            "signed_compensation_delta_rms_mps2":band_rms(z_comp-full_comp,low,high),
            "full_notch_target_RP_rms_mrad":1000*band_rms(full_target[:,:2],low,high),
            "z_only_target_RP_rms_mrad":1000*band_rms(z_target[:,:2],low,high),
            "signed_target_RP_delta_rms_mrad":1000*band_rms(delta_target,low,high),
            "target_RP_cross_term_mrad2":1e6*cross,
            "target_power_identity_residual_mrad2":1e6*(p_z-p_full-p_delta-cross),
            "full_notch_filtered_reference_RP_rms_mrad":1000*band_rms(replay_full[:,:2],low,high),
            "z_only_filtered_reference_RP_rms_mrad":1000*band_rms(z_filtered[:,:2],low,high),
            "signed_filtered_reference_RP_delta_rms_mrad":1000*band_rms(delta_filtered,low,high),
            "filtered_reference_RP_cross_term_mrad2":1e6*filtered_cross,
            "filtered_reference_power_identity_residual_mrad2":1e6*(
                band_power(z_filtered[:,:2],low,high)-band_power(replay_full[:,:2],low,high)-
                band_power(delta_filtered,low,high)-filtered_cross),
            "parent_filtered_reference_RP_rms_mrad":1000*band_rms(parent_filter[:,:2],low,high),
        }
    return {
        "scene_id":sid,"split":row["bindings"]["Applied_Notch_3p5Hz_Q1"]["release_kind"],
        "notch_raw_path":str(raw_path),"notch_raw_sha256":cand["raw_sha256"],
        "parent_raw_path":str(parent_path),"parent_raw_sha256":parent["raw_sha256"],
        "tau_s":tau,"rho":rho,"notch_events":int(len(idx)),"valid_head_events":int(len(valid)),
        "notch_full_XYZ_recurrence_max_abs_mps2":full_rec_max,
        "full_target_rebuild_max_abs_rad":full_target_err,"full_filter_replay_max_abs_rad":full_filter_err,
        "full_event_output_to_logged_compensation_max_abs_mps2":full_hold_error,
        "actual_command_identity_max_abs_mps2":float(np.max(np.abs(actual_accel-(nominal-full_comp)))),
        "parent_reference_match_max_abs":ref_difference,
        "task_to_filtered_reference_SO3_mrad":{
            "full_notch_logged":1000*geodesic_rmse(task,filtered_logged),
            "full_notch_replayed":1000*geodesic_rmse(task,replay_full),
            "z_only_notch_replayed":1000*geodesic_rmse(task,z_filtered),
            "parent_no_notch_logged":1000*geodesic_rmse(task,parent_filter),
        },
        "2_5Hz":comp_band["2_5Hz"],
    }


def main() -> None:
    if OUT_JSON.exists() or OUT_MD.exists(): raise RuntimeError("refusing to overwrite Z-only replay outputs")
    score=json.loads(SCORE.read_text(encoding="utf-8-sig"))
    if score.get("TEST_read_by_scorer") is not False or score.get("inertia_reconstruction_by_scorer") is not False:
        raise RuntimeError("frozen notch score scope is not permitted")
    if [r["scene_id"] for r in score["scene_results"]] != list(SCENES):
        raise RuntimeError("six-scene order/set differs from locked screen")
    rows=[replay_scene(r) for r in score["scene_results"]]
    names=rows[0]["task_to_filtered_reference_SO3_mrad"].keys()
    means={name:float(np.mean([r["task_to_filtered_reference_SO3_mrad"][name] for r in rows])) for name in names}
    hfmeans={}
    for hf in sorted({r["scene_id"].rsplit("_",1)[-1] for r in rows}):
        group=[r for r in rows if r["scene_id"].rsplit("_",1)[-1]==hf]
        hfmeans[hf]={name:float(np.mean([r["task_to_filtered_reference_SO3_mrad"][name] for r in group])) for name in names}
    macro_25={k:float(np.mean([r["2_5Hz"][k] for r in rows])) for k in rows[0]["2_5Hz"]}
    frozen_parent=float(score["macro_mean"]["Parent_Cosine_GRU"]["task_SO3_mrad"])
    frozen_notch=float(score["macro_mean"]["Applied_Notch_3p5Hz_Q1"]["task_SO3_mrad"])
    result={"schema":"DL1018_Z_ONLY_NOTCH_FIXED_TRAJECTORY_HF6_V1",
        "status":"COMPLETE_OFFLINE_FIXED_TRAJECTORY_REPLAY_NOT_CLOSED_LOOP",
        "scope":"Six existing applied-notch HF6 raws. Z-only 3.5Hz/Q1 causal event filter, XY direct; replayed on fixed recorded notch trajectories. No Plant, TEST, training, or inertia reconstruction.",
        "Plant_calls_by_replay":0,"TEST_read":False,"training_runs":0,"inertia_reconstruction":False,
        "input_notch_score_path":str(SCORE),"input_notch_score_sha256":sha(SCORE),
        "filter_definition":{"type":"causal second-order notch at 100-Hz Stage1 events; Z only; XY straight-through; event ZOH; zero state",
            "center_hz":3.5,"Q":1.0,"sample_rate_hz":100,
            "b":[0.9005755352793756,-1.757773520542205,0.9005755352793756],
            "a":[1.0,-1.757773520542205,0.8011510705587512],
            "parameters_swept":False},
        "summary_equal_scene_mean_task_to_filtered_reference_mrad":means,
        "summary_by_HF_group_task_to_filtered_reference_mrad":hfmeans,
        "summary_equal_scene_mean_2_5Hz":macro_25,
        "frozen_closed_loop_task_SO3_context_from_notch_score":{"parent_no_notch_mrad":frozen_parent,"full_notch_mrad":frozen_notch},
        "scene_results":rows,
        "interpretation":[
            "The Z-only condition uses only the actual notch-run Stage1 input event stream and fixed recorded states. XY compensation is passed through; Z is filtered causally; both use the original event timing and logged output limit.",
            "Task-to-filtered-reference values are same-trajectory command/reference diagnostics, not closed-loop task scores. They cannot be compared as if Z-only had produced those states.",
            "Parent and full-notch closed-loop task scores are included only as context. No Z-only closed-loop run was executed.",
            "Frequency metrics are signed target deltas plus cross terms; target power is nonlinear in compensation and the spectra are not additive.",
        ]}
    OUT_JSON.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    write_md(result)
    print(json.dumps({"status":result["status"],"json":str(OUT_JSON),"markdown":str(OUT_MD)},indent=2))


def write_md(r:dict)->None:
    names=("full_notch_logged","z_only_notch_replayed","parent_no_notch_logged")
    lines=["# Z-only notch fixed-trajectory replay on HF6","",
        "Offline event-stream replay only. The Z-only filter uses each completed notch raw's logged Stage1 input events; XY compensation passes straight through and Z uses the fixed 3.5-Hz/Q=1 causal filter. The replay holds each output between existing 100-Hz events on the recorded state trajectory. No Plant, TEST, training, or inertia reconstruction.","",
        "## Task to filtered-reference orientation","",
        "| Reference condition | Equal-scene mean SO(3) (mrad) |","|---|---:|"]
    for name in names: lines.append(f"| {name} | {r['summary_equal_scene_mean_task_to_filtered_reference_mrad'][name]:.3f} |")
    lines.extend(["",f"Frozen closed-loop task SO(3) context: Parent no-notch GRU {r['frozen_closed_loop_task_SO3_context_from_notch_score']['parent_no_notch_mrad']:.3f} mrad; full notch {r['frozen_closed_loop_task_SO3_context_from_notch_score']['full_notch_mrad']:.3f} mrad. These are score_raw closed-loop results; Z-only has no closed-loop score.","",
        "## 2–5 Hz signals","",
        "| Quantity | Full notch mean | Z-only mean | Signed delta / cross term |","|---|---:|---:|---:|"])
    m=r["summary_equal_scene_mean_2_5Hz"]
    for label,a,b,c in [
        ("Compensation RMS (m/s²)","full_notch_compensation_rms_mps2","z_only_notch_compensation_rms_mps2","signed_compensation_delta_rms_mps2"),
        ("Target RP RMS (mrad)","full_notch_target_RP_rms_mrad","z_only_target_RP_rms_mrad","signed_target_RP_delta_rms_mrad"),
        ("Filtered reference RP RMS (mrad)","full_notch_filtered_reference_RP_rms_mrad","z_only_filtered_reference_RP_rms_mrad","signed_filtered_reference_RP_delta_rms_mrad")]:
        lines.append(f"| {label} | {m[a]:.4f} | {m[b]:.4f} | {m[c]:.4f} |")
    lines.extend([
        f"| Target RP power cross term (mrad²) | — | — | {m['target_RP_cross_term_mrad2']:+.3f} |",
        f"| Filtered-reference RP power cross term (mrad²) | — | — | {m['filtered_reference_RP_cross_term_mrad2']:+.3f} |",
    ])
    lines.extend(["", "Per-scene values, HF-group means, raw hashes, event counts, full-notch parity, and target-power identity checks are in the JSON.","",
        "The task→filtered values come from fixed recorded states, so they are diagnostic replays, not closed-loop Z-only performance. A lower 2–5 Hz target RMS alone does not establish task improvement; the signed target delta and cross term are reported.","",
        "Reproduce from repository root: `python experiments/dl_attitude_replacement_20261028/method_alternatives_review_v1/z_only_notch_replay_hf6_v1.py`.",""])
    OUT_MD.write_text("\n".join(lines),encoding="utf-8")


if __name__=="__main__": main()
