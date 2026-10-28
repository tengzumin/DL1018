import csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import h5py
import numpy as np
from scipy.spatial.transform import Rotation

HERE=Path(__file__).resolve().parent
STUDY=HERE.parent
BASE=STUDY.parent
PROJECT=HERE.parents[3]
SCENES=["DL1018_VAL_T1_C08_W15","DL1018_VAL_T2_C05_W15","DL1018_VAL_T3_C02_W15","DL1018_VAL_T1_C05_W12","DL1018_VAL_T2_C02_W12","DL1018_VAL_T3_C00_W13"]
METHODS=("cosine_GRU","constant_GRU","B","C5")
COMPARE=("B","C5","constant_GRU")
MAIN=("Q_m","SO3_rad","inner_tracking_rad")
OUTS=[HERE/n for n in ("COSINE_SIX_SCENE_SUMMARY_v1.json","COSINE_SIX_SCENE_PAIRED_v1.csv","COSINE_SIX_SCENE_AXIS_PHASE_v1.csv","COSINE_SIX_SCENE_SUMMARY_v1.md")]

def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(8*1024*1024),b""): h.update(b)
 return h.hexdigest()

def readj(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def a(g,k): return np.asarray(g[k][()],dtype=np.float64)
def wrap(x): return np.arctan2(np.sin(x),np.cos(x))
def so3(x,y): return (Rotation.from_euler("xyz",y).inv()*Rotation.from_euler("xyz",x)).magnitude()
def score(path,g,mt):
 with h5py.File(path,"r") as f:
  L=f["log"]; x=a(L,"state").T; t=a(L,"time").reshape(-1)
  rp=a(f["scene/reference"],"position").T; acc=a(f["scene/reference"],"acceleration").T.copy()
  yaw=a(f["scene/reference"],"yaw").reshape(-1); inner=a(L,"filtered_attitude_reference").T
  motor=np.asarray(L["motor_saturated"][()],dtype=bool).T
  clip=np.asarray(L["generalized_clipped"][()],dtype=bool).T
  tilt=np.asarray(L["tilt_limited"][()],dtype=bool).reshape(-1)
 assert x.shape==(20001,12) and rp.shape==acc.shape==(20001,3) and inner.shape==(20000,3)
 assert np.max(np.abs(np.diff(t)-.001))<1e-10
 acc[:,2]+=g; aa=np.cos(yaw)*acc[:,0]+np.sin(yaw)*acc[:,1]; bb=np.sin(yaw)*acc[:,0]-np.cos(yaw)*acc[:,1]
 r=np.arctan2(bb,np.hypot(acc[:,2],aa)); p=np.arctan2(aa,acc[:,2])
 scale=np.minimum(1.,mt/np.maximum(np.hypot(r,p),np.finfo(float).eps))
 task=np.column_stack((r*scale,p*scale,yaw))
 pe=x[:,:3]-rp; te=wrap(task-x[:,6:9]); ie=wrap(inner-x[:20000,6:9])
 ti=t[:20000]
 masks={"all":(np.ones(20001,dtype=bool),np.ones(20000,dtype=bool)),
        "0_5s":(t<5.,ti<5.),"15_20s":(t>=15.,ti>=15.)}
 axes={}
 for name,(sm,im) in masks.items():
  axes[name]={"state_samples":int(sm.sum()),"inner_samples":int(im.sum()),
   "position_xyz_rmse_m":np.sqrt(np.mean(pe[sm]**2,axis=0)).tolist(),
   "task_wrapped_euler_rmse_rad":np.sqrt(np.mean(te[sm]**2,axis=0)).tolist(),
   "inner_wrapped_euler_rmse_rad":np.sqrt(np.mean(ie[im]**2,axis=0)).tolist()}
 return {"Q_m":float(np.sqrt(np.mean(np.sum(pe**2,axis=1)))),
  "SO3_rad":float(np.sqrt(np.mean(so3(x[:,6:9],task)**2))),
  "inner_tracking_rad":float(np.sqrt(np.mean(so3(x[:20000,6:9],inner)**2))),
  "axis_phase":axes,"safety":{"motor_saturation_samples":int(np.any(motor,axis=1).sum()),
  "generalized_clip_samples":int(np.any(clip,axis=1).sum()),"tilt_limited_samples":int(tilt.sum()),
  "state_samples":20001,"transitions":20000}}

def main():
 for p in OUTS:
  if p.exists(): raise FileExistsError(p)
 old=BASE/"gru_stream_dev_v1"; oldm=readj(old/"MANIFEST.json")
 recs={r["scene_id"]:r for r in oldm["records"]}
 old_report=old/"ROOT_SIX_PYTHON_METRICS_v1.json"; oldj=readj(old_report)
 oldrows={r["scene_id"]:r["methods"] for r in oldj["rows"]}
 axis_report=readj(old/"audits"/"SIX_SCENE_METRICS_PYTHON_v1.json")
 consts_path=BASE/"mlp15_composite_dev_v3"/"RELEASE.json"; consts=readj(consts_path)
 consts_sha=sha(consts_path)
 assert consts_sha.lower()==axis_report["metric_constants_release_sha256"].lower()
 formula=BASE/"mlp15_composite_dev_v3"/"audits"/"audit_composite_dev_raw.m"
 formula_sha=sha(formula); g=float(consts["gravity_mps2"]); mt=float(consts["max_tilt_rad"])
 release_path=STUDY/"RELEASE.json"; release=readj(release_path); release_sha=sha(release_path)
 stage2_snapshot=STUDY/"ROOT_RELEASE_STAGE2_SNAPSHOT_v1.json"; stage2_release_sha=sha(stage2_snapshot)
 stage2_release=readj(stage2_snapshot)
 approval=readj(STUDY/"ROOT_FIRST_FLIGHT_APPROVAL_v1.json")
 first_release_sha=approval["release_sha256"]
 first_score=readj(STUDY/"ROOT_FIRST_SCENE_PYTHON_METRICS_v1.json")["methods"]["candidate"]
 rows=[]; input_sha={}; calls=0
 for sid in SCENES:
  rec=recs[sid]; exp=oldrows[sid]; ms={}
  cr=STUDY/"runs"/sid/"raw_run.mat"; cs=cr.with_name("run_status.json")
  ca=STUDY/"audits"/(sid+"_GRU_STREAM_RAW_AUDIT.json")
  cstat=readj(cs); caudit=readj(ca); csha=sha(cr); cssha=sha(cs); casha=sha(ca)
  expected_release=first_release_sha if sid==SCENES[0] else stage2_release_sha
  assert cstat["state"]=="COMPLETED" and cstat["status_value"]=="STABLE" and cstat["Plant_calls"]==1 and not cstat["TEST_read"]
  assert cstat["release_sha256"].lower()==expected_release.lower() and cstat["raw_sha256"].lower()==csha.lower()
  assert caudit["status"]=="PASS_INDEPENDENT_GRU_STREAM_RAW_REPLAY" and caudit["candidate_raw_sha256"].lower()==csha.lower()
  assert caudit["model_sha256"].lower()==release["model_sha256"].lower()
  ms["cosine_GRU"]=score(cr,g,mt); ms["cosine_GRU"].update(raw_path=str(cr),raw_sha256=csha,raw_audit_sha256=casha,run_status_sha256=cssha,release_sha256=cstat["release_sha256"],audit_status=caudit["status"])
  input_sha.update({str(cr):csha,str(cs):cssha,str(ca):casha}); calls+=int(cstat["Plant_calls"])
  nr=old/"runs"/sid/"raw_run.mat"; ns=nr.with_name("run_status.json"); na=old/"audits"/(sid+"_GRU_STREAM_RAW_AUDIT.json")
  nstat=readj(ns); naud=readj(na); nsha=sha(nr); nssha=sha(ns); nasha=sha(na)
  assert nstat["state"]=="COMPLETED" and nstat["raw_sha256"].lower()==nsha.lower()
  assert naud["status"]=="PASS_INDEPENDENT_GRU_STREAM_RAW_REPLAY" and naud["candidate_raw_sha256"].lower()==nsha.lower()
  ms["constant_GRU"]=score(nr,g,mt); ms["constant_GRU"].update(raw_path=str(nr),raw_sha256=nsha,raw_audit_sha256=nasha,run_status_sha256=nssha,audit_status=naud["status"])
  input_sha.update({str(nr):nsha,str(ns):nssha,str(na):nasha})
  for name,rkey,skey,expected_key,hashkey,statushashkey in (
   ("B","b_raw_path","b_status_path","b","b_raw_sha256","b_status_sha256"),
   ("C5","c5_raw_path","c5_status_path","c5","c5_raw_sha256","c5_status_sha256")):
   raw=Path(rec[rkey]); sp=Path(rec[skey]); st=readj(sp); rh=sha(raw); sh=sha(sp)
   assert rh.lower()==rec[hashkey].lower() and sh.lower()==rec[statushashkey].lower() and st["raw_sha256"].lower()==rh.lower()
   ms[name]=score(raw,g,mt); ms[name].update(raw_path=str(raw),raw_sha256=rh,raw_audit_sha256=None,run_status_sha256=sh,metric_source_report_sha256=sha(old_report))
   input_sha.update({str(raw):rh,str(sp):sh})
  for name,key in (("B","b"),("C5","c5"),("constant_GRU","candidate")):
   for metric in MAIN: assert abs(ms[name][metric]-exp[key][metric])<=2e-10,(sid,name,metric,ms[name][metric],exp[key][metric])
  if sid==SCENES[0]:
   for metric in MAIN: assert abs(ms["cosine_GRU"][metric]-first_score[metric])<=2e-10,(metric,ms["cosine_GRU"][metric],first_score[metric])
  comp={}
  for other in COMPARE:
   comp[other]={}
   for metric in MAIN:
    d=ms["cosine_GRU"][metric]-ms[other][metric]
    comp[other][metric]={"delta":float(d),"relative_change_pct":float(100*d/ms[other][metric]),"win":bool(d < -1e-12),"loss":bool(d > 1e-12),"tie":bool(abs(d)<=1e-12)}
  rows.append({"scene_id":sid,"stratum":"W15" if sid.endswith("W15") else "HF","methods":ms,"cosine_vs":comp})

 groups={}
 for group,selected in (("ALL6",rows),("W15",[r for r in rows if r["stratum"]=="W15"]),("HF",[r for r in rows if r["stratum"]=="HF"])):
  groups[group]={"scene_count":len(selected),"macro_mean":{m:{k:float(np.mean([r["methods"][m][k] for r in selected])) for k in MAIN} for m in METHODS},
   "cosine_relative_change_pct":{o:{k:float(100*(np.mean([r["methods"]["cosine_GRU"][k] for r in selected])-np.mean([r["methods"][o][k] for r in selected]))/np.mean([r["methods"][o][k] for r in selected])) for k in MAIN} for o in COMPARE},
   "wins":{o:{k:sum(r["cosine_vs"][o][k]["win"] for r in selected) for k in MAIN} for o in COMPARE},
   "losses":{o:{k:sum(r["cosine_vs"][o][k]["loss"] for r in selected) for k in MAIN} for o in COMPARE}}
 wins={o:{k:[r["scene_id"] for r in rows if r["cosine_vs"][o][k]["win"]] for k in MAIN} for o in COMPARE}
 losses={o:{k:[r["scene_id"] for r in rows if r["cosine_vs"][o][k]["loss"]] for k in MAIN} for o in COMPARE}
 safety={m:{k:int(sum(r["methods"][m]["safety"][k] for r in rows)) for k in ("motor_saturation_samples","generalized_clip_samples","tilt_limited_samples")} for m in METHODS}
 assert len(rows)==6 and calls==6 and all(v==0 for v in safety["cosine_GRU"].values())

 paired=[]; axes=[]
 for r in rows:
  row={"scene_id":r["scene_id"],"stratum":r["stratum"]}
  for m in METHODS:
   d=r["methods"][m]
   for k in MAIN: row[m+"_"+k]=d[k]
   for k in ("motor_saturation_samples","generalized_clip_samples","tilt_limited_samples"): row[m+"_"+k]=d["safety"][k]
   for phase,p in d["axis_phase"].items():
    pos,task,inner=p["position_xyz_rmse_m"],p["task_wrapped_euler_rmse_rad"],p["inner_wrapped_euler_rmse_rad"]
    axes.append({"scene_id":r["scene_id"],"stratum":r["stratum"],"method":m,"phase":phase,"state_samples":p["state_samples"],"inner_samples":p["inner_samples"],
     "position_x_rmse_m":pos[0],"position_y_rmse_m":pos[1],"position_z_rmse_m":pos[2],
     "task_roll_wrapped_euler_rmse_rad":task[0],"task_pitch_wrapped_euler_rmse_rad":task[1],"task_yaw_wrapped_euler_rmse_rad":task[2],
     "inner_roll_wrapped_euler_rmse_rad":inner[0],"inner_pitch_wrapped_euler_rmse_rad":inner[1],"inner_yaw_wrapped_euler_rmse_rad":inner[2]})
  for o in COMPARE:
   for k in MAIN:
    row["cosine_win_vs_"+o+"_"+k]=r["cosine_vs"][o][k]["win"]
    row["cosine_loss_vs_"+o+"_"+k]=r["cosine_vs"][o][k]["loss"]
  for m in METHODS:
   row[m+"_raw_sha256"]=r["methods"][m]["raw_sha256"]; row[m+"_raw_audit_sha256"]=r["methods"][m]["raw_audit_sha256"]
  paired.append(row)
 resource={"authorized_calls":int(release["authorized_Plant_calls"]),"completed_candidate_calls_from_status":calls,
  "completed_scenes":len(rows),"first_session":26858,"first_exit":0,"remaining_five_session":91284,"remaining_five_exit":0,
  "first_release_sha256":first_release_sha,"remaining_five_release_sha256":stage2_release_sha,
  "stage2_release_Plant_calls_at_signing":int(stage2_release.get("Plant_calls",0)),
  "current_final_RELEASE_sha256":release_sha,"current_final_RELEASE_Plant_calls":int(release.get("Plant_calls",0)),
  "candidate_raw_bytes":sum(Path(r["methods"]["cosine_GRU"]["raw_path"]).stat().st_size for r in rows),
  "new_training_jobs_in_deployment_study":0,"training_steps_for_frozen_model":int(release.get("training_steps",0)),
  "baseline_reruns":0,"TEST_read":False,
  "note":"每个raw按其原始stage release SHA绑定；current RELEASE为root航次后快照。实际调用数来自六个COMPLETED run_status。"}
 constant_report_sha=sha(old_report)
 metrics_formula=BASE/"mlp15_composite_dev_v3"/"audits"/"audit_composite_dev_raw.m"
 summary={"schema":"GRU_STREAM_COSINE_SIX_SCENE_METRICS_V1","created_utc":datetime.now(timezone.utc).isoformat(),
  "status":"PASS_READ_ONLY_SIX_SCENE_SCORE_AND_AXIS_PHASE_SUMMARY","candidate":release["candidate"],"model_sha256":release["model_sha256"],
  "scene_order":SCENES,"groups":groups,"candidate_wins_by_comparator":wins,"candidate_losses_by_comparator":losses,
  "safety_totals":safety,"resource_ledger":resource,
  "metric_definitions":{"SO3_rad":"四元数测地角RMSE，不是Euler轴分量。",
   "axis_note":"wrapped Euler roll/pitch/yaw RMSE是坐标逐轴分解，不是SO3分量且不替代SO3。",
   "task_euler":"用参考加速度、yaw、9.8m/s^2重力和0.523598775598299rad tilt上限构造外环姿态目标。",
   "inner_euler":"filtered_attitude_reference与状态Euler比较；时间范围为前20000 transition。",
   "windows":"0_5s: 0<=t<5；15_20s: 状态0<=t<=20且t>=15，inner 15<=t<20；组均值按场宏平均。"},
  "metric_constants":{"source_path":str(consts_path),"sha256":consts_sha,"gravity_mps2":g,"max_tilt_rad":mt,
   "formula_source_path":str(metrics_formula),"formula_source_sha256":formula_sha},
  "provenance_sha256":{"cosine_release":release_sha,"first_flight_approval":sha(STUDY/"ROOT_FIRST_FLIGHT_APPROVAL_v1.json"),
   "constant_manifest":sha(old/"MANIFEST.json"),"constant_metrics":constant_report_sha,
   "constant_audit_metrics":sha(old/"audits"/"SIX_SCENE_METRICS_PYTHON_v1.json"),
   "metric_constants":consts_sha,"metric_formula":formula_sha},
  "input_file_sha256":input_sha,"rows":rows,
  "interpretation_limit":"六场配对离线总结，不是稳定性证明，也不授权扩展。"}
 with OUTS[0].open("x",encoding="utf-8") as f: json.dump(summary,f,ensure_ascii=False,indent=2); f.write("\n")
 with OUTS[1].open("x",newline="",encoding="utf-8-sig") as f:
  w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
 with OUTS[2].open("x",newline="",encoding="utf-8-sig") as f:
  w=csv.DictWriter(f,fieldnames=list(axes[0]));w.writeheader();w.writerows(axes)
 lines=["# GRU cosine 六场配对结果","","六场均 COMPLETED 且 raw audit PASS。本报告只读 raw；未启动 MATLAB、训练、重跑 baseline 或读取 TEST。","","SO(3) 是四元数测地角 RMSE。wrapped Euler roll/pitch/yaw 数值是逐轴分解，不是 SO(3) 分量，也不替代 SO(3) 指标。","","## 主指标宏平均","","| Group | Method | Q (mm) | Task SO(3) (mrad) | Inner (mrad) |","|---|---|---:|---:|---:|"]
 for group in ("ALL6","W15","HF"):
  for m in METHODS:
   v=groups[group]["macro_mean"][m]; lines.append(f"| {group} | {m} | {1000*v['Q_m']:.4f} | {1000*v['SO3_rad']:.4f} | {1000*v['inner_tracking_rad']:.4f} |")
 lines += ["","## cosine逐场输赢",""]
 for o in COMPARE:
  lines.append(o+": wins "+", ".join(f"{k} {len(wins[o][k])}/6" for k in MAIN)+"; losses "+", ".join(f"{k}={','.join(losses[o][k]) or 'none'}" for k in MAIN))
 lines += ["","逐场分数与raw/audit SHA见 COSINE_SIX_SCENE_PAIRED_v1.csv；全部方法的xyz和task/inner wrapped Euler轴误差，按full、0–5s、15–20s分段见 COSINE_SIX_SCENE_AXIS_PHASE_v1.csv。","",
  f"cosine六场安全计数：motor saturation {safety['cosine_GRU']['motor_saturation_samples']}, generalized clip {safety['cosine_GRU']['generalized_clip_samples']}, tilt limited {safety['cosine_GRU']['tilt_limited_samples']}.",
  f"账本：授权{resource['authorized_calls']}次、实际完成{calls}次，新增raw {resource['candidate_raw_bytes']} bytes；部署研究训练0、baseline重跑0、TEST未读。实际Plant计数由六份status汇总；原Stage release与航后final RELEASE SHA分别记录。",""]
 OUTS[3].write_text("\n".join(lines),encoding="utf-8")
 print(json.dumps({"status":summary["status"],"outputs":[str(p) for p in OUTS],"groups":groups,"wins":wins,"losses":losses,"safety":safety,"resources":resource},ensure_ascii=False,indent=2))

if __name__=="__main__": main()




