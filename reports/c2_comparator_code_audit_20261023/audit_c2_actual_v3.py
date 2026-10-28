from __future__ import annotations
import argparse, hashlib, json, math, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import h5py
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
C2 = ROOT / "experiments" / "position_beta_clock_c2_20261023"
REVIEW = Path(__file__).resolve().parent
C2_LOCK = C2 / "C2_SOURCE_LOCK.json"
CONTRACT = C2 / "C2_RUN_CONTRACT.json"
R1 = C2 / "C2_RELEASE_v1.json"
R2 = C2 / "C2_RELEASE_v2.json"
R3 = C2 / "C2_RELEASE_v3.json"
C1_LOCK = ROOT / "experiments" / "position_prior_calibration_c1_20261022_v9" / "C1_SOURCE_LOCK_v2.json"
C1_RELEASE = ROOT / "experiments" / "position_prior_calibration_c1_20261022_v9" / "C1_RELEASE_v9.json"
C1_PROBE = ROOT / "experiments" / "position_prior_calibration_c1_20261022_v9" / "reports" / "probe_c1_v9.json"
C1_CONT = ROOT / "experiments" / "position_prior_calibration_c1_20261022_v9" / "reports" / "continue_c1_v9.json"
P_SUM = C2 / "reports" / "C2_PROBE_SUMMARY.json"
C_SUM_V3 = C2 / "reports" / "C2_CONTINUE_SUMMARY_v3.json"
RECOVERY = REVIEW / "C2_SCENE2_RECOVERY_REVIEW.json"
PIN = {
 "c2_lock":"390888537a0138f36a0d9b3a1e1fc607ecdc57939a38dabb66db79c0887aca87",
 "contract":"9c42275d3214a9ac85a98b66518234fce16e8b5d7ad6826dcbf4fd8488a88be3",
 "r1":"9f50b902fb5eaee390a0c5eae017603ae1bcfd0382cb27f73289145993e963b3",
 "r2":"996e2f852de324613a313b4bdd922e442ec44f59fa5204784dac390dc705e541",
 "r3":"e075d00b0aad54b96587e7652378cee124e47ab3715186d80530197ec111b50e",
 "c1_lock":"02668f6268944715e65e6d2cffa52b395417506132212b00e7d273d88df164e5",
 "c1_release":"7aa072835b0e633f9e40d0e471a17870735d32ddf079eafc61ac6790ea7974d0",
 "c1_probe_summary":"065414e7e7022db943c528c70fd13eab5bd82473bd827620a6a171179f6a8916",
 "c1_continue_summary":"0dd4da87930528be8c7733f1f82698d510db756cb05edf1858d7cd0a1f925ab1",
 "c2_probe_summary":"daa74f2f0fd3a60196142a545161a8c16ff7ab6e6b252d31d374de869041ebf9",
 "c2_recovery":"2105f1eb4b6ce0ee29dab04066e06c3fde47f3ec8e298293f6b945f3495a4ec4",
 "c2_continue_v3_summary":"d6dff5a777caf454dc1448da86eab87937e6a3e8f9535b1ab70c62c5cdd39969",
}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()
def jread(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def h5tree(n):
 if isinstance(n,h5py.Group): return {k:h5tree(v) for k,v in n.items()}
 v=n[()]; cl=n.attrs.get("MATLAB_class",b"")
 if isinstance(cl,bytes): cl=cl.decode(errors="ignore")
 if cl=="char":
  a=np.transpose(np.asarray(v))
  return ("__char__",tuple(a.shape),"".join(chr(int(x)) for x in a.flatten(order="F") if int(x)))
 if isinstance(v,np.ndarray) and v.dtype.kind=="O":
  a=np.transpose(v); items=[h5tree(n.file[r]) if r else None for r in a.flatten(order="F")]
  # Keep each referenced MATLAB cell as one object; assigning tuples through
  # ndarray.flat can unpack their elements and corrupt the cell structure.
  return ("__cell__",tuple(a.shape),tuple(items))
 if isinstance(v,np.ndarray): return np.transpose(v).tolist()
 if isinstance(v,np.generic): return v.item()
 return v
def mat5tree(v):
 if hasattr(v,"_fieldnames"): return {k:mat5tree(getattr(v,k)) for k in v._fieldnames}
 if isinstance(v,np.ndarray):
  if v.dtype.kind in "US":
   text="".join(str(x) for x in v.flatten(order="F"))
   w=max((len(str(x)) for x in v.flat),default=0)
   return ("__char__",tuple(v.shape)+(w,),text)
  if v.dtype.kind=="O":
   if v.size==1 and hasattr(v.item(),"_fieldnames"):
    return mat5tree(v.item())
   if all(hasattr(x,"_fieldnames") for x in v.flat):
    items=[mat5tree(x) for x in v.flatten(order="F")]
    out=np.empty(v.shape,dtype=object)
    for i,item in enumerate(items): out.flat[i]=item
    return out.tolist()
   items=tuple(mat5tree(x) for x in v.flatten(order="F"))
   return ("__cell__",tuple(v.shape),items)
  return v.tolist()
 if isinstance(v,np.generic): return v.item()
 return v
def matsection(p,key):
 if h5py.is_hdf5(p):
  with h5py.File(p,"r") as f: return h5tree(f[key])
 d=loadmat(p,simplify_cells=False,struct_as_record=False,squeeze_me=False)
 return mat5tree(d[key].item())
def simple(v):
 if isinstance(v,tuple) and len(v)==3 and v[0]=="__char__": return v[2]
 if isinstance(v,tuple) and len(v)==3 and v[0]=="__cell__": return [simple(x) for x in v[2]]
 if isinstance(v,dict): return {k:simple(x) for k,x in v.items()}
 if isinstance(v,list): return [simple(x) for x in v]
 return v
def text(v):
 v=simple(v)
 if not isinstance(v,str): raise TypeError(f"expected text, got {type(v).__name__}")
 return v
def flatcell(v):
 if isinstance(v,tuple) and len(v)==3 and v[0]=="__char__": return [v[2]]
 if isinstance(v,tuple) and len(v)==3 and v[0]=="__cell__": return sum((flatcell(x) for x in v[2]),[])
 if isinstance(v,list): return sum((flatcell(x) for x in v),[])
 if isinstance(v,str): return [v]
 raise TypeError(f"unexpected cell type {type(v).__name__}")
def scalar(v):
 v=simple(v)
 while isinstance(v,list) and len(v)==1: v=v[0]
 if isinstance(v,(int,float,bool,str)): return v
 raise TypeError(f"expected scalar, got {type(v).__name__}")
def equal(a,b):
 if isinstance(a,dict) and isinstance(b,dict): return set(a)==set(b) and all(equal(a[k],b[k]) for k in a)
 if isinstance(a,(list,tuple)) and isinstance(b,type(a)): return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
 if isinstance(a,(int,float,np.number)) and isinstance(b,(int,float,np.number)):
  return (math.isnan(float(a)) and math.isnan(float(b))) or float(a)==float(b)
 return a==b
def diffs(a,b,p=""):
 if isinstance(a,dict) and isinstance(b,dict):
  out=[]
  for k in sorted(set(a)|set(b)):
   q=f"{p}/{k}"
   if k not in a or k not in b: out.append(q+" [missing]")
   else: out.extend(diffs(a[k],b[k],q))
  return out
 if isinstance(a,(list,tuple)) and isinstance(b,type(a)):
  if len(a)!=len(b): return [p+" [length]"]
  return sum((diffs(x,y,f"{p}/{i}") for i,(x,y) in enumerate(zip(a,b))),[])
 return [] if equal(a,b) else [p]
def normpath(p): return os.path.normcase(os.path.abspath(str(p)))
def stat(p):
 s=Path(p).stat(); return {"path":str(Path(p).resolve()),"size":s.st_size,"mtime_ns":s.st_mtime_ns}
def rows(v): return v if isinstance(v,list) else [v]
def scene(c1lock,sid):
 x=[r for r in c1lock["shared_scenes"] if r["scene_id"]==sid]
 if len(x)!=1: raise ValueError(f"scene identity not unique: {sid}")
 return x[0]
def c1_comparator(c1probe,c1cont,c1release,sid,condition):
 matches=[r for r in c1probe["run_rows"]+c1cont["run_rows"]
          if r["scene_id"]==sid and r["condition"]==condition]
 if len(matches)!=1: raise ValueError(f"C1 comparator row not unique: {sid} {condition}")
 row=matches[0]
 if row["status"]!="STABLE": raise ValueError(f"C1 comparator not stable: {sid} {condition}")
 if row.get("reused_prior_run",False):
  if condition!="B" or sid!=c1release["probe_scene"] or \
     row["actual_run_release"].lower()!=c1release["prior_release_sha256"].lower():
   raise ValueError(f"unexpected C1 prior-run reuse: {sid} {condition}")
  runroot=Path(c1release["reused_b_runs_root"])
 else:
  if row["actual_run_release"].lower()!=sha(C1_RELEASE).lower():
   raise ValueError(f"C1 new comparator release mismatch: {sid} {condition}")
  runroot=Path(c1release["runner_path"]).parent/"runs_v9"
 rawpath=runroot/sid/condition/"attempt_01"/"raw_run.mat"
 if not rawpath.is_file(): raise FileNotFoundError(f"C1 comparator path missing: {rawpath}")
 return {"path":str(rawpath.resolve()),"sha256":row["raw_sha256"].lower(),
         "reused_prior_run":bool(row.get("reused_prior_run",False)),
         "actual_run_release":row["actual_run_release"],"summary_row":row}
def sources(c2lock,c1lock):
 ch=c2lock["runtime_change"]
 repl={
  normpath(ch["original_core_path"]):{"path":ch["candidate_core_path"],"sha256":ch["candidate_core_sha256"].lower()},
  normpath(ch["wrapper_original_path"]):{"path":ch["wrapper_candidate_path"],"sha256":ch["wrapper_sha256"].lower()},
 }
 out=[]
 for group in ("frozen_runtime_files","frozen_plant_files"):
  for r in c1lock[group]: out.append(repl.get(normpath(r["path"]),{"path":r["path"],"sha256":r["sha256"].lower()}))
 return out
def opts_check(opts,start):
 p=opts["stage1_position_runtime"]; h=p["position_only_search_head"]; m=p["model"]
 w=np.asarray(m["output_W"],dtype=np.float64); pw=np.asarray(p["weight"],dtype=np.float64); hw=np.asarray(h["W0"],dtype=np.float64)
 wsha=hashlib.sha256(np.asfortranarray(w).tobytes(order="F")).hexdigest()
 checks={
  "formal_rbf_baseline":scalar(opts["formal_rbf_baseline"])==1,
  "position_rbf_replacement_disabled":scalar(opts["rbf_position_output_enabled"])==0 and scalar(opts["rbf_position_update_enabled"])==0,
  "attitude_rbf_kept":scalar(opts["rbf_attitude_output_enabled"])==1 and scalar(opts["rbf_attitude_update_enabled"])==1,
  "pcf_full_enabled":scalar(p["enabled"])==1 and scalar(p["update_enabled"])==1 and scalar(p["command_filter_coordination_v3_5"]["enabled"])==1,
  "FEATURE_gamma12_kappa1_beta1":text(h["head_type"]).upper()=="FEATURE" and scalar(h["gamma"])==12 and scalar(h["kappa"])==1 and scalar(p["beta_scale"])==1,
  "frozen_encoder_reset":scalar(h["encoder_frozen"])==1 and scalar(h["state_reset_each_episode"])==1,
  "DSSM14_model":text(m["model_id"])=="DSSM14" and text(m["architecture"])=="DSSM",
  "all_W0_copies_equal":w.shape==(33,3) and w.shape==pw.shape==hw.shape and np.array_equal(w,pw) and np.array_equal(w,hw),
  "W0_sha_pinned":wsha==start["model_W0_sha256"],
  "candidate_marker_matches":text(opts["r2e_first_plant_step_marker"])==text(start["r2e_first_plant_step_marker_path"]),
 }
 return {"pass":all(checks.values()),"checks":checks,"actual":{"model_id":text(m["model_id"]),"architecture":text(m["architecture"]),"W0_shape":list(w.shape),"W0_sha256":wsha,"head_type":text(h["head_type"]),"gamma":scalar(h["gamma"]),"kappa":scalar(h["kappa"]),"beta_scale":scalar(p["beta_scale"]),"pcf_enabled":scalar(p["enabled"]),"pcf_update_enabled":scalar(p["update_enabled"]),"formal_rbf_baseline":scalar(opts["formal_rbf_baseline"]),"position_rbf_output_enabled":scalar(opts["rbf_position_output_enabled"]),"position_rbf_update_enabled":scalar(opts["rbf_position_update_enabled"])}}
def audit(row,stage,relsha,c2lock,c1lock,contract,release,preflight_path,approval_path,expected_sources,cfg_eff,source_cache,c1compmap,expected_status="STABLE"):
 startp=Path(row["run_start_path"]); rawp=Path(row["raw_path"]); statp=Path(row["run_status_path"]); markerp=Path(row["r2e_first_plant_step_marker_path"]); attempt= startp.parent
 startsha,rawsha,statussha,marksha=(sha(p) for p in (startp,rawp,statp,markerp))
 if (startsha.lower()!=row["run_start_sha256"].lower() or rawsha.lower()!=row["raw_sha256"].lower() or statussha.lower()!=row["run_status_sha256"].lower() or marksha.lower()!=row["r2e_first_plant_step_marker_sha256"].lower()): raise ValueError("summary artifact SHA mismatch")
 start=matsection(startp,"runStart"); s=simple(start)
 with h5py.File(rawp,"r") as f:
  names=sorted(k for k in f.keys() if k!="#refs#")
  ident=simple(h5tree(f["runIdentity"]))
 status=json.loads(statp.read_text(encoding="utf-8-sig")); pf=json.loads(Path(preflight_path).read_text(encoding="utf-8-sig")); approval=json.loads(Path(approval_path).read_text(encoding="utf-8-sig"))
 sh=scene(c1lock,s["scene_id"]); model=c2lock["shared_c1_inputs"]
 cfgdiff=diffs(start["cfg"],cfg_eff,"cfg")
 actualsrc=flatcell(start["source_paths"]); actualsha=flatcell(start["source_sha256"]); srcdiff=[]
 if len(actualsrc)!=31 or len(actualsha)!=31 or len(expected_sources)!=31: srcdiff.append("count")
 for i,(p,h,e) in enumerate(zip(actualsrc,actualsha,expected_sources)):
  if normpath(p)!=normpath(e["path"]) or h.lower()!=e["sha256"].lower(): srcdiff.append(f"lock[{i}]")
  if normpath(p) not in source_cache:
   current=sha(p); source_cache[normpath(p)]={"path":str(Path(p).resolve()),"sha256":current,"size":Path(p).stat().st_size,"mtime_ns":Path(p).stat().st_mtime_ns}
  if source_cache[normpath(p)]["sha256"].lower()!=h.lower(): srcdiff.append(f"disk[{i}]")
 flags={}
 imap=("scene_id","condition","method","source_lock_sha256","release_sha256","user_budget_authorization_sha256","preflight_sha256","scene_source_raw_sha256","c1_b_comparator_raw_sha256","c1_on1_comparator_raw_sha256","model_mat_sha256","normalizer_npz_sha256","optimizer_steps","gpu_jobs","TEST_accessed")
 iddiff=[]
 for k in imap:
  a=ident.get(k); b=s.get(k)
  if isinstance(a,str) and isinstance(b,str): ok=a.lower()==b.lower() if "sha256" in k else a==b
  else: ok=equal(a,b)
  if not ok: iddiff.append(k)
 if ident.get("first_plant_marker_path")!=s.get("r2e_first_plant_step_marker_path"): iddiff.append("first_plant_marker_path")
 id_sources={
  "scene_source_raw_path":sh["b_raw_path"],"scene_source_raw_sha256":sh["b_raw_sha256"],"scene_payload_sha256":sh["payload_sha256"],
  "c1_b_comparator_raw_path":c1compmap[(s["scene_id"],"B")]["path"],"c1_b_comparator_raw_sha256":c1compmap[(s["scene_id"],"B")]["sha256"],
  "c1_on1_comparator_raw_path":c1compmap[(s["scene_id"],"ON1")]["path"],"c1_on1_comparator_raw_sha256":c1compmap[(s["scene_id"],"ON1")]["sha256"],
  "model_mat_path":model["model_mat_path"],"model_mat_sha256":model["model_mat_sha256"],"model_W0_sha256":model["w0_output_W_double_f_order_sha256"],
  "normalizer_npz_path":model["normalizer_npz_path"],"normalizer_npz_sha256":model["normalizer_npz_sha256"],"normalizer_arrays_sha256":model["normalizer_arrays_sha256"],
  "effective_config_path":model["effective_config_path"],"effective_config_sha256":model["effective_config_sha256"]}
 sourcediff=[]
 for k,v in id_sources.items():
  got=s.get(k); ok=normpath(got)==normpath(v) if k.endswith("_path") else str(got).lower()==str(v).lower()
  if not ok: sourcediff.append(k)
 cfgclk={"dt":scalar(s["cfg"]["plant"]["dt"]),"beta_rise_time":scalar(s["cfg"]["rbf"]["position"]["beta_rise_time"]),"position_hz":scalar(s["cfg"]["rbf"]["runtime"]["position_update_hz"])}
 c1b=c1compmap[(s["scene_id"],"B")]; c1on=c1compmap[(s["scene_id"],"ON1")]
 compok=s["c1_b_comparator_raw_sha256"].lower()==c1b["sha256"] and s["c1_on1_comparator_raw_sha256"].lower()==c1on["sha256"]
 if expected_status=="STABLE":
  status_expect={"status":"STABLE","scene_id":s["scene_id"],"condition":contract["candidate_condition_id"],"method":contract["candidate_condition_id"],"completed_transition":20000,"raw_sha256":rawsha,"run_start_sha256":startsha,"source_lock_sha256":PIN["c2_lock"],"release_sha256":relsha,"plant_start_confirmed":True,"optimizer_steps":0,"gpu_jobs":0,"TEST_accessed":False}
 else:
  status_expect={"status":"FAILED_NO_RETRY","scene_id":s["scene_id"],"condition":contract["candidate_condition_id"],"plant_invocation_entered":True,"plant_start_confirmed":True,"partial_raw_preserved":True,"partial_raw_sha256":rawsha,"run_start_sha256":startsha,"source_lock_sha256":PIN["c2_lock"],"release_sha256":relsha,"optimizer_steps":0,"gpu_jobs":0,"TEST_accessed":False}
 statusdiff=[k for k,v in status_expect.items() if status.get(k)!=v]
 if expected_status=="STABLE" and (status.get("timing_isolated") is not False or status.get("formal_timing_qualified") is not False): statusdiff.append("timing_flags")
 opt=opts_check(simple(start["opts"]),s)
 preok=pf.get("status")=="PASS" and pf.get("mode")==stage and pf.get("source_lock_sha256","").lower()==PIN["c2_lock"] and pf.get("release_sha256","").lower()==relsha and pf.get("approval_sha256","").lower()==sha(approval_path) and pf.get("plant_started") is False and pf.get("optimizer_steps")==0 and pf.get("gpu_jobs")==0 and pf.get("TEST_accessed") is False and pf.get("formal_timing_qualified") is False and s["preflight_sha256"].lower()==sha(preflight_path).lower()
 appok=approval.get("status")=="APPROVED_"+stage and approval.get("mode")==stage and approval.get("candidate_condition_id")==contract["candidate_condition_id"] and approval.get("source_lock_sha256","").lower()==PIN["c2_lock"] and approval.get("release_sha256","").lower()==relsha
 startok=s.get("scene_id")==row["scene_id"] and s.get("condition")==contract["candidate_condition_id"] and s.get("method")==contract["candidate_condition_id"] and s.get("source_lock_sha256","").lower()==PIN["c2_lock"] and s.get("release_sha256","").lower()==relsha and s.get("optimizer_steps")==[[0.0]] and s.get("gpu_jobs")==[[0.0]] and s.get("TEST_accessed")==[[0]] and s.get("timing_isolated")==[[0]] and s.get("formal_timing_qualified")==[[0]]
 timing_ok=(status.get("timing_isolated") is False and status.get("formal_timing_qualified") is False) if expected_status=="STABLE" else (scalar(s["timing_isolated"])==0 and scalar(s["formal_timing_qualified"])==0)
 flags={"cfg_full_equals_effective_config":not cfgdiff,"cfg_clock":cfgclk=={"dt":.001,"beta_rise_time":1.8,"position_hz":100},"source_paths_sha_31_matches_lock_and_disk":not srcdiff,"runIdentity_matches_runStart":not iddiff,"runStatus_scope_and_identity":not statusdiff,"locked_model_scene_comparator_identity":not sourcediff and compok,"actual_opts_W0_gamma_PCF_contract":opt["pass"],"approval_preflight_release_binding":appok and preok,"timing_unqualified_recorded":timing_ok,"marker_and_attempt_files":marksha.lower()==row["r2e_first_plant_step_marker_sha256"].lower() and (attempt/"attempt_started.marker").is_file()}
 return {"scene_id":row["scene_id"],"stage":stage,"expected_collection_status":expected_status,"raw_sha256":rawsha,"run_start_sha256":startsha,"status_sha256":statussha,"raw_top_names_without_log_decode":names,"runIdentity_fields":sorted(ident),"cfg_equal":not cfgdiff,"cfg_mismatch_paths":cfgdiff[:20],"cfg_top_fields":len(start["cfg"]),"cfg_clock":cfgclk,"source_count":len(actualsrc),"source_diffs":srcdiff,"runIdentity_diffs":iddiff,"status_diffs":statusdiff,"locked_identity_diffs":sourcediff,"C1_comparator_hashes_match_summary_and_path_rule":compok,"C1_comparator_actual_paths":{"B":c1b,"ON1":c1on},"actual_opts":opt,"preflight_ok":preok,"approval_ok":appok,"timing_isolated":status.get("timing_isolated"),"formal_timing_qualified":status.get("formal_timing_qualified"),"pass_flags":flags,"pass":all(flags.values())}
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--mode",choices=("probe","full"),default="probe")
 args=ap.parse_args()
 c2lock=jread(C2_LOCK); contract=jread(CONTRACT); c1lock=jread(C1_LOCK); c1release=jread(C1_RELEASE)
 for p,pin in ((C2_LOCK,PIN["c2_lock"]),(CONTRACT,PIN["contract"]),(C1_LOCK,PIN["c1_lock"]),(C1_RELEASE,PIN["c1_release"])):
  if sha(p).lower()!=pin: raise ValueError(f"pinned SHA mismatch {p}")
 if c1release["source_lock_sha256"].lower()!=PIN["c1_lock"]: raise ValueError("C1 release/source lock binding mismatch")
 rel1=jread(R1); rel2=jread(R2); rel3=jread(R3)
 for p,pin,rel in ((R1,PIN["r1"],rel1),(R2,PIN["r2"],rel2),(R3,PIN["r3"],rel3)):
  if sha(p).lower()!=pin or rel["source_lock_sha256"].lower()!=PIN["c2_lock"]:
   raise ValueError(f"C2 release/source-lock binding mismatch: {p}")
 for rel in (rel1,rel2,rel3):
  if rel["c1_source_lock_sha256"].lower()!=PIN["c1_lock"] or rel["c1_release_sha256"].lower()!=PIN["c1_release"] or \
     rel["c1_probe_summary_sha256"].lower()!=PIN["c1_probe_summary"] or rel["c1_continue_summary_sha256"].lower()!=PIN["c1_continue_summary"]:
   raise ValueError("C2 release does not pin the current C1 source/release/summaries")
 c1probe=jread(C1_PROBE); c1cont=jread(C1_CONT)
 if sha(C1_PROBE).lower()!=PIN["c1_probe_summary"] or sha(C1_CONT).lower()!=PIN["c1_continue_summary"]:
  raise ValueError("C1 comparator summary SHA mismatch")
 c1compmap={}
 for sidrow in c1lock["shared_scenes"]:
  sid=sidrow["scene_id"]
  for condition in ("B","ON1"):
   c1compmap[(sid,condition)]=c1_comparator(c1probe,c1cont,c1release,sid,condition)
 probe=jread(P_SUM); probe_sha=sha(P_SUM)
 if probe_sha.lower()!=PIN["c2_probe_summary"] or probe["release_sha256"].lower()!=PIN["r1"] or probe["status"]!="PROBE_COMPLETE":
  raise ValueError("v1 C2 probe summary/release binding mismatch")
 pairs=[("PROBE",r,PIN["r1"],"STABLE") for r in rows(probe["run_rows"])]
 release=rel1
 if args.mode=="full":
  recovery=jread(RECOVERY); recsha=sha(RECOVERY)
  cont=jread(C_SUM_V3); contsha=sha(C_SUM_V3)
  if recsha.lower()!=PIN["c2_recovery"] or recovery["scene_id"]!=c1lock["shared_scenes"][1]["scene_id"] or \
     recovery["collection_success"] is not False or recovery["raw_usable_for_scoring"] is not True:
   raise ValueError("scene2 failed-but-scoreable recovery binding mismatch")
  repair=rel3["repair"]
  if repair["parent_release_sha256"].lower()!=PIN["r2"] or repair["probe_summary_sha256"].lower()!=probe_sha or \
     repair["recovery_review_sha256"].lower()!=recsha:
   raise ValueError("v3 parent/probe/recovery binding mismatch")
  if contsha.lower()!=PIN["c2_continue_v3_summary"] or cont["status"]!="CONTINUE_COMPLETE" or \
     cont["release_sha256"].lower()!=PIN["r3"] or cont["source_lock_sha256"].lower()!=PIN["c2_lock"] or \
     cont["probe_summary_sha256"].lower()!=probe_sha or len(cont["run_rows"])!=10:
   raise ValueError("v3 continuation summary/release binding mismatch")
  fi=recovery["five_file_identity"]
  recrow={"scene_id":recovery["scene_id"],"condition":recovery["condition"],
   "raw_path":fi["raw"]["path"],"raw_sha256":fi["raw"]["sha256"],
   "run_start_path":fi["run_start"]["path"],"run_start_sha256":fi["run_start"]["sha256"],
   "run_status_path":fi["run_status"]["path"],"run_status_sha256":fi["run_status"]["sha256"],
   "r2e_first_plant_step_marker_path":fi["first_plant_marker"]["path"],
   "r2e_first_plant_step_marker_sha256":fi["first_plant_marker"]["sha256"]}
  pairs += [("CONTINUE",recrow,PIN["r2"],"FAILED_NO_RETRY")]
  pairs += [("CONTINUE",r,PIN["r3"],"STABLE") for r in rows(cont["run_rows"])]
  scenes=[x["scene_id"] for x in c1lock["shared_scenes"]]
  expected=[scenes[0],scenes[1]]+scenes[2:]
  if [r["scene_id"] for _,r,_,_ in pairs]!=expected: raise ValueError("C2 v1 probe + recovered scene2 + v3 ten scenes order/count differs from locked C1 scenes")
  release=rel3
 else:
  scenes=[x["scene_id"] for x in c1lock["shared_scenes"]]
  if [r["scene_id"] for _,r,_,_ in pairs]!=scenes[:1]: raise ValueError("C2 probe scene order/count differs from locked C1 scenes")
 sources_expected=sources(c2lock,c1lock)
 if len(sources_expected)!=31: raise ValueError("lock source count is not 31")
 cfg_eff=matsection(Path(c2lock["shared_c1_inputs"]["effective_config_path"]),"cfg")
 cache={}
 all_sources=[]
 for x in sources_expected:
  h=sha(x["path"]); st=stat(x["path"])
  if h.lower()!=x["sha256"].lower(): raise ValueError(f"current source SHA changed: {x['path']}")
  cache[normpath(x["path"]) ]={**st,"sha256":h}; all_sources.append({"path":str(Path(x["path"]).resolve()),"sha256":h,"size":st["size"],"mtime_ns":st["mtime_ns"]})
 reports=C2/"reports"
 p_appr=reports/"C2_PROBE_APPROVAL.json"; p_pf=reports/"preflight_c2_probe.json"
 audits=[]
 for stage,row,relsha,expected_status in pairs:
  if stage=="PROBE":
   ap=p_appr; pf=p_pf
  elif relsha==PIN["r2"]:
   ap=reports/"C2_CONTINUE_APPROVAL_v2.json"; pf=reports/"preflight_c2_continue_v2.json"
  else:
   ap=reports/"C2_CONTINUE_APPROVAL_v3.json"; pf=reports/"preflight_c2_continue_v3.json"
  audits.append(audit(row,stage,relsha,c2lock,c1lock,contract,release,pf,ap,sources_expected,cfg_eff,cache,c1compmap,expected_status))
 for x in all_sources:
  p=Path(x["path"]); now=stat(p); h=sha(p)
  if h.lower()!=x["sha256"].lower() or now["size"]!=x["size"] or now["mtime_ns"]!=x["mtime_ns"]: raise ValueError(f"locked source changed during audit: {p}")
 out=REVIEW/("C2_ACTUAL_PROBE_AUDIT_V3.json" if args.mode=="probe" else "C2_ACTUAL_FULL_AUDIT_V3.json")
 if out.exists(): raise FileExistsError(f"refusing overwrite {out}")
 result={"schema":"C2_ACTUAL_RUN_METADATA_AUDIT_V3","mode":args.mode.upper(),"created_utc":datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z"),"scope":"Read-only run_start cfg/opts/source paths and raw top-level runIdentity; raw log arrays are not decoded. No Plant/training/GPU/TEST.","source_lock_sha256":sha(C2_LOCK),"contract_sha256":sha(CONTRACT),"release_chain_sha256":{"v1":sha(R1),"v2":sha(R2),"v3":sha(R3)},"probe_summary_sha256":probe_sha,"v3_continue_summary_sha256":sha(C_SUM_V3) if args.mode=="full" else None,"scene2_recovery_review_sha256":sha(RECOVERY) if args.mode=="full" else None,"C1_comparator_source_rule":"Use C1 probe/continue summary raw SHA and run_c1_screen.m path rule: reused first-scene B under C1_RELEASE_v9.reused_b_runs_root; all other C1 B/ON1 under C1 release runner directory/runs_v9/<scene>/<condition>/attempt_01/raw_run.mat. Do not use shared_scenes scene-source raw as the C1 B comparator.","locked_source_count":len(all_sources),"locked_sources":all_sources,"scene_count":len(audits),"runs":audits,"all_pass":all(x["pass"] for x in audits),"C1_full_opts_archived":False,"C1_opts_limit":"C1 run_start stores options_audit rather than complete cfg/opts; audit checks C2 actual opts against the locked DSSM/PCF contract and does not invent a C1 opts snapshot.","script_sha256":sha(Path(__file__))}
 with out.open("x",encoding="utf-8",newline="\n") as f: json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False); f.write("\n")
 print(json.dumps({"output":str(out.resolve()),"sha256":sha(out),"all_pass":result["all_pass"],"scenes":len(audits)}))
if __name__=="__main__": main()

