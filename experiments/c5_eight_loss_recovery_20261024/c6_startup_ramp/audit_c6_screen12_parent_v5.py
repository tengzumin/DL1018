"""Parent-reviewable C6 screen12 audit v2; never launches MATLAB or retries."""
from __future__ import annotations
import csv, importlib.util, json, math, os, sys
from pathlib import Path

sys.dont_write_bytecode = True
for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[key] = "1"
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
REPORT = ROOT / "reports/paper_continuation_20261023/c5_eight_loss_recovery/c6_startup_ramp"
SCENES = ("DL1018_VAL_T1_C00_W07", "DL1018_VAL_T1_C02_W09", "DL1018_VAL_T1_C05_W12",
          "DL1018_VAL_T1_C08_W15", "DL1018_VAL_T2_C00_W10", "DL1018_VAL_T2_C02_W12",
          "DL1018_VAL_T2_C05_W15", "DL1018_VAL_T2_C06_W00", "DL1018_VAL_T3_C00_W13",
          "DL1018_VAL_T3_C02_W15", "DL1018_VAL_T3_C03_W00", "DL1018_VAL_T3_C12_W09")
TAIL = SCENES[1:]
C6, C5, B72, NOPRED = ("C6_STARTUP_PREDICTION_RAMP", "C5_AXIS_MIXED_COORDINATE_M110",
                        "B_TRACEABLE", "C5_NO_DELAYED_PREDICTION")
EPS = 1e-12
FIELDS = ["initial_state", "time", "environment_wind_I", "arms/command", "arms/rho_true",
          "arms/rhoDot_true", "arms/rho_hat", "arms/rhoDot_hat", "reference/acceleration",
          "reference/position", "reference/velocity", "reference/yaw", "reference/yaw_acceleration",
          "reference/yaw_rate"]
METRICS = ("Q_0_20_m", "Q_0_5_m", "Q_5_20_m", "rmse_x_0_20_m", "rmse_x_0_5_m", "rmse_x_5_20_m",
           "rmse_y_0_20_m", "rmse_y_0_5_m", "rmse_y_5_20_m", "rmse_z_0_20_m", "rmse_z_0_5_m",
           "rmse_z_5_20_m", "peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction",
           "controller_mean_s", "controller_p95_s")
REGRESSION_METRICS = tuple(k for k in METRICS if k.startswith(("Q_", "rmse_")) or k in
                           ("peak_m", "p95_m", "motor_saturated_fraction", "generalized_clipped_fraction"))
PIN = {
 "first_audit": (TASK/"audit_c6_first_scene_pair_v1.py", "5dda7f17e0381be47e34757961f6b021e3d4c5f6c7f5c59b618fdf23d40cff9b"),
 "taskbook": (ROOT/"reports/paper_continuation_20261023/c5_eight_loss_recovery/C6_SCREEN12_IMPLEMENTATION_TASKBOOK_v1_ZH.md", "d9360ccccfe942f2ae1ab06b600e3c2a29c9cbc3cb05bc9f64b0b55454d49df9"),
 "c6_lock": (TASK/"C6_STARTUP_RAMP_INPUT_LOCK_v1.json", "919de01ed9a111f24f4028b5436bdfa46d817f32c475bbf18e70b87d2eb37c06"),
 "c6_contract": (TASK/"C6_STARTUP_RAMP_RUN_CONTRACT_v1.json", "6b75d40ff257d38a8aa6c9d7e1384dacbaee5b89d9a218a19bbe3037b7d7a463"),
 "snapshot": (TASK/"C6_STARTUP_RAMP_PREPARED_CFG_OPTS_v1.mat", "f6ad61507b1d9027abb6bb2e4f5fc30d8558c0820fe663e0a2deb3a62b84255b"),
 "prepare": (TASK/"C6_STARTUP_RAMP_PREPARE_RESULT_v1.json", "01ed7e161429579ab3d669214975c1042a32d133b9389fd83b91b6685fdeac6a"),
 "first_release": (TASK/"C6_FIRST_PARENT_RELEASE_v1.json", "05857a88062e8b7cda74da047b5ace7b615750eb59d643e215a25ff99d470f09"),
 "first_binding": (TASK/"C6_SOURCE_BINDING_v1.json", "dd834d6c354cc27f0493ce715a0dfe677d9e0ba574ddf899ececf0c2661eb964"),
 "tail_contract": (TASK/"C6_TAIL11_RUN_CONTRACT_v1.json", "df833c66edc8e3c02f9e2cc58bd1e2acea9b7f1c21698e3a4ce3c177f4abaa8c"),
 "tail_binding": (TASK/"C6_TAIL11_SOURCE_BINDING_v5.json", "8137db2a69ae763d7e2a0d1179bbdb7715929ac34afa3764e2489137920020cd"),
 "tail_runner": (TASK/"run_c6_startup_ramp_tail11_v5.m", "4baabec54329e86ed359aa13f3b4d1f8f1a9fb4bc3fd042697d762b938bf1eb9"),
 "tail_launcher": (TASK/"RUN_C6_TAIL11_EXACT_v5.ps1", "e03381f47a7c3c59ca1b81877b86a7d0e426760d6320dace832d8b7eef5892af"),
 "tail_release_contract": (TASK/"C6_TAIL11_PARENT_RELEASE_CONTRACT_v5.json", "de2cb807f89307aa361fdb0437e36e433a7df7859bb4f801ae5cdcaec743c068"),
 "tail_release": (TASK/"C6_TAIL11_PARENT_RELEASE_v5.json", "30f2cea2c4f49fb902355242647cbfb5486dc9eb6a60e6664b6f270718089214"),
 "helper": (TASK/"delayed_prediction_step_candidate.m", "53e5c2fa8098769b84952c93469625eae9abedccb199a1c57d3746b8005bd067"),
 "kernel": (TASK/"delayed_prediction_kernel.py", "0ad47c691f5411e36d75ab5f1f78ecb0a945564371ecfb2fc18066b47ae2bcac"),
 "c5_lock": (ROOT/"experiments/position_axis_coordinate_c5_20261023/C5_AXIS_COORDINATE_INPUT_LOCK_v1.json", "10a7eea144e3574e05eea7b4f7b56112595eac0c81d27b5e8c7a5a41499f84b0"),
 "b_lock": (ROOT/"experiments/b_traceable_c3core_dev72_20261023/B_TRACEABLE_DEV72_INPUT_LOCK_v3.json", "8d738e5c70ba2fc8697550549d1a0537f08eadb49b99bc5684e5c26f6222f452"),
 "b_lock_legacy": (ROOT/"experiments/b_traceable_c3core_20261023/B_TRACEABLE_INPUT_LOCK_v2.json", "7c5e1c2979c147b220139a5dfd764394334b61d88b55b2d8abd6ef48edf129d8"),
 "manifest": (ROOT/"reports/paper_continuation_20261023/c5_axis_coordinate_parent_review/C5_B72_SCORING_MANIFEST_v1.json", "7c1c17c1168e918f3796bb78ba1a5acc8fcee19d9a0ee96d971d9ec0f4fd7355"),
 "paired_csv": (ROOT/"reports/paper_continuation_20261023/c5_matched_ablation_dev72_parent_review/MATCHED_ABLATION_DEV72_ALL_PAIRS_v1.csv", "9ad962499032826a31ee0f4c3b424ec45793272f411314ab6c35d3356e34e49b"),
 "scorer": (ROOT/"reports/delayed_prediction_c3_dev72_parent_20261023/parent_raw_metrics.py", "c64482d0adbc4358417648ec08351bd78f1d3dbdb38950435fa71b9cb0f531b1"),
 "decoder": (ROOT/"reports/paper14_v2/phase1/audit_w15_position_replay.py", "372d92cb17da99884e742d3fa0c877200c3bb2bc6fac7f10e7a1a046b97a76af"),
 "timing": (REPORT/"PARENT_FIRST_CAUSAL_DIVERGENCE_TIMING_v1.json", "949747aa4894878fc1e960328c2220567bb3cae85f641e6c9f5ebfa7f2d0d8c6"),
 "first_raw_review": (REPORT/"C6_FIRST_SCENE_RAW_REVIEW_v1.json", "e3faaac63ce4fdc021e11b1fb489fb64928f5b02d831b4fa65ff14977a09e5a8"),
 "first_meta_review": (REPORT/"C6_FIRST_SCENE_METADATA_OS_REVIEW_v2.json", "ed0a681e32a7d6e76ca7f05356bbde313ec1cf65998b883925c2fb05cd425c29"),
}


def need(ok, msg):
    if not ok: raise AssertionError(msg)


def sha(path):
    import hashlib
    with Path(path).open("rb") as f: return hashlib.file_digest(f, "sha256").hexdigest()


def jload(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def same(a, b): return os.path.normcase(os.path.abspath(os.fspath(a))) == os.path.normcase(os.path.abspath(os.fspath(b)))


def mtext(x): return str(x[2]) if isinstance(x, tuple) and len(x)==3 and x[0]=="__matlab_char__" else str(x)


def unique(rows, key, label):
    out = {r[key]: r for r in rows}
    need(len(out)==len(rows), f"duplicate {label} row")
    return out


def load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec is not None and spec.loader is not None, f"cannot load pinned module {path}")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def verify_run(status, scene, candidate, raw, digest):
    schema=status.get("schema")
    if candidate==B72:
        if schema=="B_TRACEABLE_C3CORE_DEV72_RUN_STATUS_V3":
            need(scene!="DL1018_VAL_T2_C00_W10","unexpected legacy B72 schema on historical scene")
        elif schema=="B_TRACEABLE_C3CORE_RUN_STATUS_V2" and scene=="DL1018_VAL_T2_C00_W10":
            pass
        else:
            need(False,f"unrecognized B72 run-status schema/scene: {schema}/{scene}")
        need("candidate" not in status and status["runtime_method"]=="B2-RBF-Full-SPLIT"
             and status["collector_tag"]=="B_TRACEABLE_C3CORE_V1",
             f"B72 writer identity mismatch: {scene}/{schema}")
    elif candidate==C5:
        if schema=="C5_TAIL11_RUN_STATUS_V2":
            need(scene!="DL1018_VAL_T2_C00_W10","unexpected legacy C5 schema on historical scene")
        elif schema=="C5_AXIS_COORDINATE_RUN_STATUS_V1" and scene=="DL1018_VAL_T2_C00_W10":
            pass
        else:
            need(False,f"unrecognized C5 run-status schema/scene: {schema}/{scene}")
        need(status["candidate"]==candidate,f"C5 run identity mismatch: {scene}/{candidate}")
    elif candidate==C6:
        if schema=="C6_STARTUP_RAMP_RUN_STATUS_V1" and scene==SCENES[0]:
            pass
        elif schema=="C6_TAIL11_RUN_STATUS_V1" and scene in TAIL:
            pass
        else:
            need(False,f"unrecognized C6 run-status schema/scene: {schema}/{scene}")
        need(status["candidate"]==candidate,f"C6 run identity mismatch: {scene}/{candidate}")
    else:
        need(False,f"unsupported run-status candidate: {candidate}")
    need(status["scene_id"]==scene, f"run scene identity mismatch: {scene}/{candidate}")
    need(status["status"]=="RUN_COMPLETE_RAW_PENDING_AUDIT" and status["log_status"]=="STABLE"
         and not status["safety_stop_reason"] and int(status["plant_calls"])==1
         and int(status["last_transition"])==20000 and int(status["transitions"])==20000
         and int(status["state_samples"])==20001, f"unsafe/incomplete run: {scene}/{candidate}")
    need(status.get("TEST_accessed") is False and int(status.get("training_steps",-1))==0
         and int(status.get("optimizer_steps",-1))==0, f"TEST/training metadata mismatch: {scene}/{candidate}")
    need(same(status["raw_path"],raw) and status["raw_sha256"].lower()==digest.lower()
         and sha(raw)==digest.lower(), f"raw path/SHA mismatch: {scene}/{candidate}")

def metric_dict(score): return {k:float(score[k]) for k in METRICS}


def csv_metrics(row, prefix): return {k:float(row[f"{prefix}_{k}"]) for k in METRICS}


def check_score(actual, expected, scene, label):
    for key in METRICS:
        need(math.isfinite(actual[key]) and abs(actual[key]-expected[key])<=EPS,
             f"pinned scorer/archive mismatch >1e-12: {scene}/{label}/{key}")


def main():
    hashes={}
    for name,(path,expected) in PIN.items():
        need(path.is_file(),f"missing pinned input {name}: {path}")
        hashes[name]=sha(path); need(hashes[name]==expected,f"SHA mismatch for {name}")
    audit=load_mod(PIN["first_audit"][0],"c6_screen12_frozen_audit")
    decoder=load_mod(PIN["decoder"][0],"c6_screen12_decoder")
    scorer=load_mod(PIN["scorer"][0],"c6_screen12_scorer")
    kernel=load_mod(PIN["kernel"][0],"c6_screen12_kernel")
    task=TASK; report=REPORT
    lock=jload(PIN["c6_lock"][0]); contract=jload(PIN["c6_contract"][0]); tailc=jload(PIN["tail_contract"][0])
    binding=jload(PIN["tail_binding"][0]); release=jload(PIN["tail_release"][0])
    c5lock=jload(PIN["c5_lock"][0]); block=jload(PIN["b_lock"][0]); legacy_block=jload(PIN["b_lock_legacy"][0]); manifest=jload(PIN["manifest"][0])
    need(lock["scene_ids_reuse_12"]==list(SCENES) and contract["scene_ids"]==list(SCENES)
         and tailc["original_scene_ids"]==list(SCENES) and tailc["tail_scene_ids"]==list(TAIL)
         and c5lock["scene_ids_reuse_12"]==list(SCENES),"fixed scene scope/order changed")
    need(release["schema"]=="C6_TAIL11_PARENT_RELEASE_V1" and release["state"]=="APPROVED_C6_TAIL11_V1"
         and release["tail_scene_ids"]==list(TAIL) and release["tail_runner_sha256"].lower()==hashes["tail_runner"]
         and release["launcher_sha256"].lower()==hashes["tail_launcher"]
         and release["tail_source_binding_sha256"].lower()==hashes["tail_binding"]
         and release["tail_run_contract_sha256"].lower()==hashes["tail_contract"]
         and release["parent_release_contract_sha256"].lower()==hashes["tail_release_contract"]
         and release["c6_input_lock_sha256"].lower()==hashes["c6_lock"]
         and release["b72_raw_manifest_sha256"].lower()==hashes["manifest"]
         and release["TEST_accessed"] is False and release["automatic_retry"] is False,
         "v5 release is not bound to frozen source/scope")
    need(binding["schema"]=="C6_TAIL11_SOURCE_BINDING_V5"
         and binding["tail_runner_sha256"].lower()==hashes["tail_runner"]
         and binding["tail_scene_ids"]==list(TAIL),"v5 top-level binding mismatch")
    roles={r["role"]:r for r in binding["source_files"]}
    need(roles["tail_runner"]["sha256"].lower()==hashes["tail_runner"]
         and roles["launcher"]["sha256"].lower()==hashes["tail_launcher"],"v5 nested source binding mismatch")
    need(manifest["schema"]=="C5_B72_SCORING_MANIFEST_V1" and manifest["state"]=="PASS_C5_B72_ALL72_PARENT_AUDIT"
         and len(manifest["records"])==72,"B72 manifest mismatch")
    c6rows=unique(lock["scenes"],"scene_id","C6 lock"); c5rows=unique(c5lock["scenes"],"scene_id","C5 lock")
    brows=unique(block["scenes"],"scene_id","B lock"); b72rows=unique(manifest["records"],"scene_id","B72 manifest")
    need(list(c6rows)==list(SCENES) and list(c5rows)==list(SCENES),"locked C6/C5 scene order changed")

    # Bind natural no-Plant preflight and natural formal OS-0 tail completion.
    prepath=report/"C6_TAIL11_NOPLANT_PREFLIGHT_v5.json"
    noexit=report/"C6_TAIL11_NOPLANT_MATLAB_OS_EXIT_v5.json"
    noreceipt=report/"C6_TAIL11_NOPLANT_EXECUTION_RECEIPT_v5.json"
    pre,ne,nr=map(jload,(prepath,noexit,noreceipt))
    need(pre["status"]=="PASS_C6_TAIL11_NOPLANT_PREFLIGHT" and pre["checked_tail_scenes"]==11
         and pre["plant_calls"]==0 and pre["TEST_accessed"] is False
         and pre["model_loaded_and_W0_verified"] and pre["options_reconstructed_from_snapshot"]
         and pre["prepared_cfg_opts_equal"]
         and pre["cfg_opts_source_match_leaves"]=={"cfg":120,"opts":43,"source_identity":6},"no-Plant preflight failed")
    pre_rows=unique(pre["scene_input_checks"],"scene_id","noPlant")
    need(list(pre_rows)==list(TAIL),"no-Plant preflight scene order mismatch")
    for s in TAIL:
        m=b72rows[s]; p=pre_rows[s]
        need(p["attempt_absent"] and p["scene_shape_valid"] and p["prepared_identity_match"]
             and p["opts_rebuilt_from_snapshot"] and p["physical_B_source_sha256"].lower()==c6rows[s]["B_source"]["sha256"].lower()
             and p["scoring_B72_raw_sha256"].lower()==m["raw_sha256"].lower()
             and p["scoring_B72_status_sha256"].lower()==m["run_status_sha256"].lower(),f"noPlant input mismatch {s}")
    need(ne["status"]=="PASS_C6_TAIL11_NOPLANT_PREFLIGHT_OS0" and ne["natural_process_return"]
         and ne["matlab_os_exit_code"]==0 and ne["plant_calls"]==0
         and nr["status"]=="PASS_C6_TAIL11_NOPLANT_PREFLIGHT_OS0" and nr["natural_process_return"]
         and nr["matlab_os_exit_code"]==0 and nr["shell_natural_exit_code"]==0 and nr["plant_calls"]==0
         and nr["tail_release_sha256"].lower()==hashes["tail_release"]
         and nr["source_binding_sha256"].lower()==hashes["tail_binding"]
         and nr["preflight_report_sha256"].lower()==sha(prepath),"noPlant natural OS-0 receipts mismatch")
    batchp=task/"C6_TAIL11_BATCH_STATUS_v5.json"; bodyp=task/"C6_TAIL11_BODY_COMPLETE_v5.json"
    exitp=report/"C6_TAIL11_MATLAB_OS_EXIT_v5.json"; receiptp=report/"C6_TAIL11_EXECUTION_RECEIPT_v5.json"
    batch,body,oe,rc=map(jload,(batchp,bodyp,exitp,receiptp))
    need(batch["status"]=="COMPLETE_RAW_PENDING_PARENT_AUDIT" and batch["completed_scenes"]==11
         and batch["plant_calls"]==11 and [r["scene_id"] for r in batch["records"]]==list(TAIL)
         and body["status"]=="COMPLETE_RAW_PENDING_PARENT_AUDIT" and body["matlab_process_count"]==1
         and body["plant_calls"]==11 and [r["scene_id"] for r in body["per_scene_exit_records"]]==list(TAIL)
         and oe["status"]=="COMPLETE_RAW_PENDING_PARENT_AUDIT" and oe["matlab_os_exit_code"]==0
         and oe["natural_process_return"] and oe["plant_calls"]==11 and not oe["finalization_error"]
         and rc["status"]=="COMPLETE_RAW_PENDING_PARENT_AUDIT" and rc["natural_process_return"]
         and rc["matlab_os_exit_code"]==0 and rc["shell_natural_exit_code"]==0 and rc["completed_scenes"]==11
         and rc["plant_calls"]==11 and rc["TEST_accessed"] is False and not rc["finalization_error"]
         and rc["batch_status_sha256"].lower()==sha(batchp) and rc["body_sha256"].lower()==sha(bodyp),
         "formal v5 batch/body/OS receipts are not natural complete 11/11")
    tailrec=unique(batch["records"],"scene_id","tail batch")
    bodyrec=unique(body["per_scene_exit_records"],"scene_id","tail body")
    need(all(tailrec[s]==bodyrec[s] for s in TAIL),"tail body and batch records differ")
    # Read the archived fixed VAL screen rows; NO_PRED is reused, never rerun.
    with PIN["paired_csv"][0].open("r",encoding="utf-8-sig",newline="") as f: archived=list(csv.DictReader(f))
    selected=[r for r in archived if r["scene_id"] in SCENES]
    byscene={s:[r for r in selected if r["scene_id"]==s] for s in SCENES}
    need(all(len(byscene[s])==2 for s in SCENES),"paired screen table must have two frozen rows per scene")
    pairs={}
    for s,rs in byscene.items():
        variants={r["candidate_method"]:r for r in rs}
        need(set(variants)=={"C5_FREEZE_TRAINED_W0",NOPRED},f"unexpected archived pairing variants: {s}")
        pairs[s]=variants[NOPRED]
        need(pairs[s]["split"]=="VAL" and pairs[s]["origin"]=="SCREEN12_AUDIT_REUSE"
             and pairs[s]["candidate_method"]==NOPRED and "TEST" not in pairs[s]["candidate_path"].upper(),
             f"NO_PRED row is not the fixed preaudited VAL row: {s}")

    snap=PIN["snapshot"][0]; snapcfg=decoder.matlab_section(snap,"cfg"); snapopts=decoder.matlab_section(snap,"opts")
    c6audits={}; pair_scores={}; events={}; safeties={}; windpeaks={}; external={}; artifacts={}
    firstrefs=binding["pilot_refs"]
    expected_first={"first_raw":"11fc0a35f38efb5ac38d0d4f6a1da30be7c7eaada409baaa6d50521f0310eb38",
        "run_status":"918bc931d682b995e8581b2999714fb4723c2c1788be74eb0d22682aeac01ba6",
        "run_start":"bf5298af7bbf0b5c47d5c1dc38c3895eb6ca050b414465e9d23c90fe5952cf38",
        "first_plant_step_marker":"4be70a7d8354ec28a1906e1883ffe4cd84b134986a6b28729838902d87c72efb",
        "raw_review":PIN["first_raw_review"][1],"metadata_os_review":PIN["first_meta_review"][1]}
    for name,digest in expected_first.items():
        ref=firstrefs[name]; need(ref["sha256"].lower()==digest and sha(ref["path"])==digest,f"first pilot ref changed: {name}")
    first_raw=Path(firstrefs["first_raw"]["path"]); first_status_path=Path(firstrefs["run_status"]["path"])
    first_start_path=Path(firstrefs["run_start"]["path"])
    first_status=jload(first_status_path); verify_run(first_status,SCENES[0],C6,first_raw,expected_first["first_raw"])
    need(first_status["schema"]=="C6_STARTUP_RAMP_RUN_STATUS_V1"
         and first_status["actual_weight_update_enabled"] and first_status["actual_prediction_gradient_enabled"]
         and first_status["release_sha256"].lower()==hashes["first_release"],"first C6 status/release mismatch")
    first_meta=jload(firstrefs["metadata_os_review"]["path"]); first_review=jload(firstrefs["raw_review"]["path"])
    need(first_meta["status"]=="PASS_C6_FIRST_RAW_METADATA_NATURAL_OS0" and first_meta["natural_MATLAB_OS_exit_code"]==0
         and first_meta["event_count"]==1968 and first_meta["actual_candidate_Plant"]==1
         and first_meta["new_Plant_in_this_audit"]==0 and first_meta["TEST_accessed"] is False
         and first_meta["first_scene_review_is_tail_authorization"] is False
         and first_meta["cfg_opts_source_match_leaves"]=={"cfg":120,"opts":43,"source_identity":6}
         and first_review["status"]=="PASS_C6_FIRST_RAW_ALL_EVENTS" and first_review["event_count"]==1968,
         "first scene's reviewed metadata/raw proof mismatch")
    first_start=decoder.matlab_section(first_start_path,"runStart")
    first_identity=decoder.matlab_section(first_raw,"runIdentity")
    firstlock=c6rows[SCENES[0]]["B_source"]
    need(mtext(first_start["method"])==C6 and mtext(first_start["scene_id"])==SCENES[0]
         and mtext(first_start["scene_raw_sha256"]).lower()==firstlock["sha256"].lower()
         and mtext(first_identity["candidate"])==C6 and mtext(first_identity["scene_id"])==SCENES[0]
         and mtext(first_identity["scene_b_raw_sha256"]).lower()==firstlock["sha256"].lower(),
         "first runStart/raw does not bind the locked physical scene")
    for section,prepared in (("cfg",snapcfg),("opts",snapopts)):
        actual=first_start[section]
        if section=="opts": actual=dict(actual); actual.pop("r2e_first_plant_step_marker",None)
        need(audit.exact_tree(actual,prepared),f"first runStart {section} differs from prepared snapshot")
    need(same(first_status["run_start_path"],first_start_path)
         and first_status["run_start_sha256"].lower()==sha(first_start_path)
         and sha(firstrefs["first_plant_step_marker"]["path"])==expected_first["first_plant_step_marker"],
         "first C6 status/start/marker linkage mismatch")
    first_raw_review_path=Path(firstrefs["raw_review"]["path"])
    causal_path=PIN["timing"][0]; causal=jload(causal_path); tc=causal["checks"]
    need(causal["status"]=="PASS_PARENT_FIRST_EXPECTED_CAUSAL_DIVERGENCE_TIMING"
         and causal["raw_sha256_C6"].lower()==expected_first["first_raw"]
         and causal["raw_sha256_C5"].lower()=="27f3d6f19f20edeb3e45c77be25daf4746e41c800fbe6126b12c07fdc52caaa5"
         and tc["stage1_position_event_weight_after_33x3"]["corresponding_plant_step"]==330
         and tc["stage1_position_event_weight_before_33x3"]["corresponding_plant_step"]==340
         and tc["position_compensation_applied_acceleration_mps2"]["first_exact_difference_zero_based"]==340
         and tc["state"]["first_exact_difference_zero_based"]==341
         and tc["stage1_position_event_raw_acceleration_mps2"]["valid_events_only_for_max_abs"]==1968,
         "first-scene output-before-update timing proof mismatch")

    status_schema_counts={B72:{},C5:{},C6:{}}

    for scene in SCENES:
        physical=c6rows[scene]["B_source"]; c5physical=c5rows[scene]["B_source"]
        if scene=="DL1018_VAL_T2_C00_W10":
            need(scene not in brows,"legacy B scene unexpectedly in new-71 lock")
            bphysical={"path":legacy_block["scene_raw_path"],"sha256":legacy_block["scene_raw_sha256"]}
            blog={"path":legacy_block["scene_scored_log_path"],"sha256":legacy_block["scene_scored_log_sha256"],"matching_fields":legacy_block["scene_matching_fields"]}
        else:
            bphysical=brows[scene]["B_source"]; blog=brows[scene]["scored_log"]
        need(physical["sha256"].lower()==c5physical["sha256"].lower()==bphysical["sha256"].lower()
             and same(physical["path"],c5physical["path"]) and same(physical["path"],bphysical["path"])
             and same(physical["path"],blog["path"]) and blog["sha256"].lower()==physical["sha256"].lower()
             and blog["matching_fields"]==FIELDS and c6rows[scene]["b_scene_to_scored_log"]["matching_fields"]==FIELDS
             and c5rows[scene]["b_scene_to_scored_log"]["matching_fields"]==FIELDS
             and sha(physical["path"])==physical["sha256"].lower(),f"14-field physical source lock differs: {scene}")
        brow=b72rows[scene]
        # B72 score input is the manifest's run raw, never the input-lock's older physical B source.
        need(not same(brow["raw_path"],physical["path"]) and sha(brow["raw_path"])==brow["raw_sha256"].lower()
             and sha(brow["run_status_path"])==brow["run_status_sha256"].lower(),f"B72 manifest raw binding mismatch: {scene}")
        bstatus=jload(brow["run_status_path"]); verify_run(bstatus,scene,B72,Path(brow["raw_path"]),brow["raw_sha256"])
        schemas=status_schema_counts[B72]; schemas[bstatus["schema"]]=schemas.get(bstatus["schema"],0)+1
        if bstatus["schema"]=="B_TRACEABLE_C3CORE_DEV72_RUN_STATUS_V3":
            expected_b_lock_sha=hashes["b_lock"]
        elif bstatus["schema"]=="B_TRACEABLE_C3CORE_RUN_STATUS_V2" and scene=="DL1018_VAL_T2_C00_W10":
            need(legacy_block["schema"]=="B_TRACEABLE_C3CORE_INPUT_LOCK_V2"
                 and legacy_block["scene_id"]==scene and legacy_block["TEST_accessed"] is False
                 and legacy_block["scene_raw_sha256"].lower()==physical["sha256"].lower()
                 and same(legacy_block["scene_raw_path"],physical["path"])
                 and legacy_block["scene_matching_fields"]==FIELDS,
                 "legacy B input lock does not bind the physical scene")
            # This legacy scored_log is the physical source; B72 scoring comes only from the manifest row.
            need(legacy_block["scene_scored_log_sha256"].lower()==physical["sha256"].lower()
                 and same(legacy_block["scene_scored_log_path"],physical["path"]),
                 "legacy B lock scored_log physical-source binding mismatch")
            expected_b_lock_sha=hashes["b_lock_legacy"]
        else:
            need(False,f"unrecognized B72 status/input-lock schema/scene: {bstatus['schema']}/{scene}")
        need(bstatus["input_lock_sha256"].lower()==expected_b_lock_sha,
             f"B72 status input-lock mismatch: {scene}")
        c5status_path=ROOT/"experiments/position_axis_coordinate_c5_20261023/runs_c5_v1"/scene/"C5_AXIS_MASK_M110/attempt_01/run_status.json"
        c5status=jload(c5status_path); c5raw=Path(c5status["raw_path"])
        verify_run(c5status,scene,C5,c5raw,c5status["raw_sha256"])
        schemas=status_schema_counts[C5]; schemas[c5status["schema"]]=schemas.get(c5status["schema"],0)+1
        if c5status["schema"]=="C5_TAIL11_RUN_STATUS_V2":
            need(c5status["input_lock_sha256"].lower()==hashes["c5_lock"]
                 and c5status["physical_B_source_sha256"].lower()==physical["sha256"].lower()
                 and same(c5status["physical_B_source_path"],physical["path"])
                 and c5status["scoring_B72_raw_sha256"].lower()==brow["raw_sha256"].lower()
                 and same(c5status["scoring_B72_raw_path"],brow["raw_path"])
                 and c5status["scoring_B72_status_sha256"].lower()==brow["run_status_sha256"].lower()
                 and same(c5status["scoring_B72_status_path"],brow["run_status_path"]),
                 f"C5/B72 pair binding mismatch: {scene}")
        elif c5status["schema"]=="C5_AXIS_COORDINATE_RUN_STATUS_V1" and scene=="DL1018_VAL_T2_C00_W10":
            c5startpath=Path(c5status["run_start_path"])
            c5start=decoder.matlab_section(c5startpath,"runStart")
            need(c5status["run_start_sha256"].lower()==sha(c5startpath)
                 and c5status["input_lock_sha256"].lower()==hashes["c5_lock"]
                 and mtext(c5start["schema"])=="C5_AXIS_COORDINATE_RUN_START_V1"
                 and mtext(c5start["method"])==C5 and mtext(c5start["scene_id"])==scene
                 and mtext(c5start["input_lock_sha256"]).lower()==hashes["c5_lock"]
                 and mtext(c5start["scene_raw_sha256"]).lower()==physical["sha256"].lower()
                 and mtext(c5start["scoring_B72_raw_sha256"]).lower()==brow["raw_sha256"].lower()
                 and same(mtext(c5start["scoring_B72_raw_path"]),brow["raw_path"])
                 and mtext(c5start["scoring_B72_status_sha256"]).lower()==brow["run_status_sha256"].lower()
                 and same(mtext(c5start["scoring_B72_status_path"]),brow["run_status_path"]),
                 f"C5 legacy runStart/B72 binding mismatch: {scene}")
        else:
            need(False,f"unrecognized C5 status schema/scene: {c5status['schema']}/{scene}")
        pair=pairs[scene]
        need(pair["B_TRACEABLE_sha256"].lower()==brow["raw_sha256"].lower()
             and same(pair["B_TRACEABLE_path"],brow["raw_path"])
             and pair["C5_M110_sha256"].lower()==c5status["raw_sha256"].lower()
             and same(pair["C5_M110_path"],c5raw),f"archived C5/B72 pair raw mismatch: {scene}")

        if scene==SCENES[0]:
            c6raw=first_raw; c6status=first_status; c6start=first_start; c6identity=first_identity
            c6digest=expected_first["first_raw"]
        else:
            rec=tailrec[scene]; attempt=TASK/"runs_c6_startup_ramp_tail11_v5"/scene/"C6_STARTUP_PREDICTION_RAMP/attempt_01"
            c6raw=attempt/"raw_run.mat"; c6statuspath=attempt/"run_status.json"; c6startpath=attempt/"run_start.mat"
            marker=attempt/"first_plant_step.marker"; started=attempt/"attempt_started.marker"
            need(same(rec["raw_path"],c6raw) and same(rec["run_status_path"],c6statuspath)
                 and same(rec["run_start_path"],c6startpath) and sha(c6raw)==rec["raw_sha256"].lower()
                 and sha(c6statuspath)==rec["run_status_sha256"].lower() and sha(c6startpath)==rec["run_start_sha256"].lower()
                 and sha(marker)==rec["first_plant_step_marker_sha256"].lower()
                 and sha(started)==rec["attempt_started_marker_sha256"].lower()
                 and rec["status"]=="RUN_COMPLETE_RAW_PENDING_AUDIT" and rec["plant_calls"]==1
                 and rec["physical_B_source_sha256"].lower()==physical["sha256"].lower()
                 and rec["scoring_B72_raw_sha256"].lower()==brow["raw_sha256"].lower()
                 and bodyrec[scene]==rec,f"tail batch does not bind actual C6 artifacts: {scene}")
            c6status=jload(c6statuspath); c6digest=rec["raw_sha256"].lower()
            verify_run(c6status,scene,C6,c6raw,c6digest)
            need(c6status["schema"]=="C6_TAIL11_RUN_STATUS_V1"
                 and c6status["source_binding_sha256"].lower()==hashes["tail_binding"]
                 and c6status["tail_release_sha256"].lower()==hashes["tail_release"],f"tail C6 status not bound to v5: {scene}")
            c6start=decoder.matlab_section(c6startpath,"runStart")
            c6identity=decoder.matlab_section(c6raw,"runIdentity")
            need(c6status["run_start_sha256"].lower()==sha(c6startpath)
                 and c6status["first_plant_step_marker_sha256"].lower()==sha(marker)
                 and c6status["attempt_started_marker_sha256"].lower()==sha(started),f"tail status markers mismatch: {scene}")
            mi=c6start["model_identity"]
            need(mtext(mi["model_id"])==contract["model"]["id"] and mtext(mi["W0_sha256"]).lower()==contract["model"]["W0_sha256"].lower()
                 and mtext(mi["normalizer_arrays_sha256"]).lower()==contract["model"]["normalizer_arrays_sha256"].lower()
                 and int(audit.np.asarray(mi["selected_step"]).item())==int(contract["model"]["selected_step"])
                 and int(audit.np.asarray(mi["input_dim"]).item())==14 and int(audit.np.asarray(mi["window"]).item())==32
                 and (audit.np.asarray(c6start["initial_weight_reset_from_W0"]).item()==1) and (audit.np.asarray(c6start["controller_state_reset_for_scene"]).item()==1),
                 f"tail model/W0 identity mismatch: {scene}")
            need(audit.exact_tree(c6start["source_identity"],first_start["source_identity"])
                 and audit.exact_tree(c6identity["source_identity"],c6start["source_identity"])
                 and audit.exact_tree(c6identity["model_identity"],c6start["model_identity"])
                 and audit.exact_tree(c6identity["W0"],c6start["W0"]),f"tail run source/model identity changed: {scene}")
        verify_run(c6status,scene,C6,c6raw,c6digest)
        schemas=status_schema_counts[C6]; schemas[c6status["schema"]]=schemas.get(c6status["schema"],0)+1
        if c6status["schema"]=="C6_STARTUP_RAMP_RUN_STATUS_V1" and scene==SCENES[0]:
            c6_snapshot_sha=mtext(c6start["cfg_opts_snapshot_sha256"])
        elif c6status["schema"]=="C6_TAIL11_RUN_STATUS_V1" and scene in TAIL:
            c6_snapshot_sha=c6status["cfg_opts_snapshot_sha256"]
        else:
            need(False,f"unrecognized C6 snapshot-binding schema/scene: {c6status['schema']}/{scene}")
        need(c6status["actual_weight_update_enabled"] and c6status["actual_prediction_gradient_enabled"]
             and c6status["input_lock_sha256"].lower()==hashes["c6_lock"]
             and c6_snapshot_sha.lower()==hashes["snapshot"],f"C6 status flags/snapshot mismatch: {scene}")
        need(mtext(c6start["scene_id"])==scene
             and mtext(c6start.get("candidate",c6start.get("method")))==C6
             and mtext(c6start["scoring_B72_raw_sha256"]).lower()==brow["raw_sha256"].lower()
             and same(mtext(c6start["scoring_B72_raw_path"]),brow["raw_path"])
             and mtext(c6start["scoring_B72_status_sha256"]).lower()==brow["run_status_sha256"].lower()
             and same(mtext(c6start["scoring_B72_status_path"]),brow["run_status_path"]),f"C6 runStart/B72 mismatch: {scene}")
        opts=dict(c6start["opts"]); opts.pop("r2e_first_plant_step_marker",None)
        need(audit.exact_tree(c6start["cfg"],snapcfg) and audit.exact_tree(opts,snapopts),f"C6 cfg/opts mismatch: {scene}")
        if scene==SCENES[0]:
            scene_sha=mtext(c6identity["scene_b_raw_sha256"])
        else:
            scene_identity=c6start["scene_identity"]
            need(c6status["physical_B_source_sha256"].lower()==physical["sha256"].lower()
                 and same(c6status["physical_B_source_path"],physical["path"])
                 and mtext(c6start["physical_B_source_sha256"]).lower()==physical["sha256"].lower()
                 and same(mtext(c6start["physical_B_source_path"]),physical["path"])
                 and mtext(scene_identity["B_raw_sha256"]).lower()==physical["sha256"].lower()
                 and same(mtext(scene_identity["B_raw_path"]),physical["path"])
                 and mtext(c6identity["scene_identity"]["B_raw_sha256"]).lower()==physical["sha256"].lower(),
                 f"tail physical scene identity mismatch: {scene}")
            scene_sha=mtext(c6identity["scene_identity"]["B_raw_sha256"])
        need(scene_sha.lower()==physical["sha256"].lower(),f"C6 raw physical identity mismatch: {scene}")
        events[scene]=audit.event_audit(c6raw,c6start["cfg"],contract["model"]["W0_sha256"],kernel)
        need(events[scene]["event_count"]==1968,f"C6 event count mismatch: {scene}")
        c6audits[scene]={C6:audit.raw_shape_finite_audit(c6raw),C5:audit.raw_shape_finite_audit(c5raw),
                         B72:audit.raw_shape_finite_audit(Path(brow["raw_path"]))}
        with audit.h5py.File(physical["path"],"r") as hf:
            wind=audit.np.asarray(hf["log"]["environment_wind_I"])
        need(audit.np.isfinite(wind).all(),f"physical wind is non-finite: {scene}")
        windpeaks[scene]=float(audit.np.max(audit.np.abs(wind),initial=0.0))
        score={C6:scorer.score(dict(scene_id=scene,method=C6,path=str(c6raw),sha256=c6digest)),
               C5:scorer.score(dict(scene_id=scene,method="C5_M110",path=str(c5raw),sha256=c5status["raw_sha256"])),
               B72:scorer.score(dict(scene_id=scene,method=B72,path=brow["raw_path"],sha256=brow["raw_sha256"]))}
        ids={k:v["external_identity_sha256"] for k,v in score.items()}
        need(len(set(ids.values()))==1 and ids[C5]==pair["C5_M110_external_identity_sha256"].lower()
             and ids[B72]==pair["B_TRACEABLE_external_identity_sha256"].lower()
             and ids[C6]==pair["candidate_external_identity_sha256"].lower(),f"14-field external identity mismatch: {scene}")
        vals={k:metric_dict(v) for k,v in score.items()}; vals[NOPRED]=csv_metrics(pair,"candidate")
        check_score(vals[C5],csv_metrics(pair,"C5_M110"),scene,"C5_M110")
        check_score(vals[B72],csv_metrics(pair,"B_TRACEABLE"),scene,"B_TRACEABLE")
        pair_scores[scene]=vals; external[scene]=ids[C6]
        suffix=scene.rsplit("_",1)[-1]
        group="high_frequency_W09_W14" if suffix in {"W09","W10","W11","W12","W13","W14"} else "windless_W15" if suffix=="W15" else "other_fixed_scenes"
        need((group=="windless_W15")==(windpeaks[scene]==0.0),f"wind category vs physical wind differs: {scene}")
        safeties[scene]={"complete":True,"safe":True,"safety_stop_reason":"","plant_calls":1,
            "raw_shape_finite_audits":c6audits[scene],"transition_limit_flag_counts_C6":c6audits[scene][C6]["transition_limit_flag_counts"],
            "motor_saturated_fraction":{k:vals[k]["motor_saturated_fraction"] for k in vals},
            "generalized_clipped_fraction":{k:vals[k]["generalized_clipped_fraction"] for k in vals}}
        artifacts[scene]={"physical_B_source_path":physical["path"],"physical_B_source_sha256":physical["sha256"],
            "C6_raw_path":str(c6raw),"C6_raw_sha256":c6digest,"C5_raw_path":str(c5raw),"C5_raw_sha256":c5status["raw_sha256"],
            "B72_scoring_manifest_raw_path":brow["raw_path"],"B72_scoring_manifest_raw_sha256":brow["raw_sha256"],
            "B_input_lock_scored_log_is_physical_source":same(blog["path"],physical["path"]),
            "NO_PRED_archived_path":pair["candidate_path"],"NO_PRED_archived_raw_sha256":pair["candidate_sha256"]}

    def group_of(scene):
        w=scene.rsplit("_",1)[-1]
        return "high_frequency_W09_W14" if w in {"W09","W10","W11","W12","W13","W14"} else "windless_W15" if w=="W15" else "other_fixed_scenes"
    def mean(scenes,method,key): return sum(pair_scores[s][method][key] for s in scenes)/len(scenes)
    groups={"all_12":list(SCENES),
            "high_frequency_W09_W14":[s for s in SCENES if group_of(s)=="high_frequency_W09_W14"],
            "windless_W15":[s for s in SCENES if group_of(s)=="windless_W15"],
            "other_fixed_scenes":[s for s in SCENES if group_of(s)=="other_fixed_scenes"]}
    need([len(groups[k]) for k in ("all_12","high_frequency_W09_W14","windless_W15","other_fixed_scenes")] == [12,6,3,3],
         "preregistered screen groups must be 12/6-HF/3-W15-no-wind/3-other")
    means={}
    for name,ids in groups.items():
        means[name]={"scene_ids":ids,"count":len(ids),"metrics":{}}
        for method in (C6,C5,B72,NOPRED):
            means[name]["metrics"][method]={"mean_Q_0_20_m":mean(ids,method,"Q_0_20_m"),
                "mean_Q_0_5_m":mean(ids,method,"Q_0_5_m"),"mean_Q_5_20_m":mean(ids,method,"Q_5_20_m"),
                "mean_early_y_mse_m2":sum(pair_scores[s][method]["rmse_y_0_5_m"]**2 for s in ids)/len(ids)}
    rows=[]

    for scene in SCENES:
        vals=pair_scores[scene]; group=group_of(scene)
        rows.append({"scene_id":scene,"group":group,"max_abs_physical_wind":windpeaks[scene],
            "external_identity_sha256":external[scene],"metrics":vals,"safety_and_actuators":safeties[scene],
            "C6_event_formula_audit":events[scene],"artifacts":artifacts[scene],
            "delta_C6_minus_baseline":{base:{k:vals[C6][k]-vals[base][k] for k in METRICS} for base in (C5,B72,NOPRED)},
            "regressions_vs_baseline":{base:[k for k in REGRESSION_METRICS if vals[C6][k]-vals[base][k]>EPS]
                                        for base in (C5,B72,NOPRED)}})
    old_losses=("DL1018_VAL_T2_C00_W10","DL1018_VAL_T3_C00_W13")
    all_safe=all(r["safety_and_actuators"]["complete"] and r["safety_and_actuators"]["safe"]
                 and r["C6_event_formula_audit"]["event_count"]==1968 for r in rows)
    gates={
        "all_12_complete_safe_and_1968_events":all_safe,
        "mean_early_Q_C6_strictly_below_C5":means["all_12"]["metrics"][C6]["mean_Q_0_5_m"]<means["all_12"]["metrics"][C5]["mean_Q_0_5_m"],
        "HF_early_Y_MSE_C6_strictly_below_C5":means["high_frequency_W09_W14"]["metrics"][C6]["mean_early_y_mse_m2"]<means["high_frequency_W09_W14"]["metrics"][C5]["mean_early_y_mse_m2"],
        "both_original_C5_loss_scenes_main_Q_below_C5":all(pair_scores[s][C6]["Q_0_20_m"]<pair_scores[s][C5]["Q_0_20_m"] for s in old_losses),
        "overall_main_Q_C6_strictly_below_B72":means["all_12"]["metrics"][C6]["mean_Q_0_20_m"]<means["all_12"]["metrics"][B72]["mean_Q_0_20_m"],
        "HF_main_Q_C6_no_higher_than_B72":means["high_frequency_W09_W14"]["metrics"][C6]["mean_Q_0_20_m"]<=means["high_frequency_W09_W14"]["metrics"][B72]["mean_Q_0_20_m"],
        "W15_no_wind_main_Q_C6_no_higher_than_B72":means["windless_W15"]["metrics"][C6]["mean_Q_0_20_m"]<=means["windless_W15"]["metrics"][B72]["mean_Q_0_20_m"],
    }
    def wins(left,right):
        ds=[pair_scores[s][left]["Q_0_20_m"]-pair_scores[s][right]["Q_0_20_m"] for s in SCENES]
        return {"left":left,"right":right,"left_wins":sum(d < -EPS for d in ds),
                "right_wins":sum(d > EPS for d in ds),"ties_within_1e-12_m":sum(abs(d)<=EPS for d in ds),
                "left_minus_right_Q_m":ds}
    win_summary={"C6_vs_C5":wins(C6,C5),"C6_vs_B72":wins(C6,B72),"C6_vs_NO_PRED":wins(C6,NOPRED)}
    win_summary["C6_over_B72_at_least_original_10_of_12"]=win_summary["C6_vs_B72"]["left_wins"]>=10
    regressions={base:[{"scene_id":r["scene_id"],"metrics":r["regressions_vs_baseline"][base]}
                       for r in rows if r["regressions_vs_baseline"][base]] for base in (C5,B72,NOPRED)}
    need(all(sum(status_schema_counts[m].values())==len(SCENES) for m in (B72,C5,C6)),"status-schema counts do not cover all 12 runs")
    result={"schema":"C6_SCREEN12_RAW_AUDIT_V5",
        "status":"SCREEN12_AUDIT_COMPLETE_GATES_PASS" if all(gates.values()) else "SCREEN12_AUDIT_COMPLETE_GATES_FAIL",
        "integrity_status":"PASS_ALL_FIXED_ARTIFACTS_AND_RUNS","scope":"FIXED_12_VAL_SCENES_ONLY_NO_DEV72_EXPANSION_AUTHORIZED",
        "candidate":C6,"scene_ids":list(SCENES),"plant_calls_in_this_audit":0,"TEST_accessed":False,
        "source_hashes":hashes,
        "run_status_schema_counts":status_schema_counts,
        "run_status_schema_bindings":{
            "B72":{"missing_in_status_by_schema":{"B_TRACEABLE_C3CORE_DEV72_RUN_STATUS_V3":["candidate"],
                "B_TRACEABLE_C3CORE_RUN_STATUS_V2":["candidate"]},
                "legacy_scene":"DL1018_VAL_T2_C00_W10","legacy_schema":"B_TRACEABLE_C3CORE_RUN_STATUS_V2",
                "legacy_input_lock_path":str(PIN["b_lock_legacy"][0]),"legacy_input_lock_sha256":hashes["b_lock_legacy"],
                "legacy_scored_log_is_physical_source":True,
                "B72_scoring_raw_and_status_source":"pinned B72 manifest row"},
            "C5":{"missing_in_status_by_schema":{"C5_TAIL11_RUN_STATUS_V2":[],
                "C5_AXIS_COORDINATE_RUN_STATUS_V1":["physical_B_source_sha256","physical_B_source_path",
                    "scoring_B72_raw_sha256","scoring_B72_raw_path","scoring_B72_status_sha256","scoring_B72_status_path"]},
                "legacy_scene":"DL1018_VAL_T2_C00_W10","legacy_schema":"C5_AXIS_COORDINATE_RUN_STATUS_V1",
                "legacy_bindings":"pinned runStart V1: scene_raw_sha256 plus exact B72 raw/status paths and hashes; physical path is locked by C5/C6/B input locks"},
            "C6":{"missing_in_status_by_schema":{"C6_STARTUP_RAMP_RUN_STATUS_V1":["cfg_opts_snapshot_sha256"],
                "C6_TAIL11_RUN_STATUS_V1":[]},"pilot_scene":SCENES[0],
                "pilot_snapshot_binding":"first-scene runStart cfg_opts_snapshot_sha256, checked against the pinned prepared snapshot"}},
        "execution_proof":{"first_raw_sha256":expected_first["first_raw"],"first_metadata_review_sha256":expected_first["metadata_os_review"],
            "tail_release_sha256":hashes["tail_release"],"no_plant_OS_exit_sha256":sha(noexit),
            "no_plant_receipt_sha256":sha(noreceipt),"formal_tail_batch_sha256":sha(batchp),
            "formal_tail_body_sha256":sha(bodyp),"formal_tail_OS_exit_sha256":sha(exitp),"formal_tail_receipt_sha256":sha(receiptp),
            "natural_MATLAB_OS_exit_code":0,"tail_scenes_completed":11,"tail_Plant_calls":11,"first_Plant_calls":1},
        "causal_timing_proof":{"sha256":hashes["timing"],"status":causal["status"],
            "first_weight_after_difference_plant_step":330,"first_weight_before_difference_plant_step":340,
            "first_compensation_difference_plant_step":340,"first_physical_state_difference_index":341,
            "scope":"first scene timing evidence only; not a screen-wide performance claim"},
        "paired_NO_PRED_source":{"path":str(PIN["paired_csv"][0]),"sha256":hashes["paired_csv"],"rows":12,"origin":"SCREEN12_AUDIT_REUSE"},
        "B72_scoring_raw_rule":"Each B72 score uses its manifest raw_path/raw_sha256. Input-lock scored_log fields are physical-source bindings only.",
        "per_scene":rows,"group_means":means,"gate_results":gates,"pairwise_main_Q_wins":win_summary,
        "original_C5_loss_scenes":list(old_losses),"all_regressions":regressions,
        "interpretation":"A screen pass supports only a separate DEV72 decision; it does not establish eight-scene recovery or paper-level success."}
    out=REPORT/"C6_SCREEN12_RAW_AUDIT_v5.json"
    need(not out.exists(),f"refusing to overwrite {out}")
    with out.open("x",encoding="utf-8",newline="\n") as f: f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":result["status"],"scenes":len(rows),"report_path":str(out),"gates":gates},ensure_ascii=False))

if __name__=="__main__": main()
