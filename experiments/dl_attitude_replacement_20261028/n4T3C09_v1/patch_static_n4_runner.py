from pathlib import Path

runner = Path(__file__).parent / "candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m"
s = runner.read_text(encoding="utf-8")
for old, new in (
    ("dualNotch", "staticN4"),
    ("DualNotch", "StaticN4"),
    ("dual_notch", "static_n4"),
    ("[2.2;3.2]", "[2.2;3.2;3.7;4.8]"),
    ("[2.2,3.2]", "[2.2,3.2,3.7,4.8]"),
    ("[4;4]", "[4;4;4;4]"),
    ("[4,4]", "[4,4,4,4]"),
    ("[2,3]", "[4,3]"),
    ("DL1018_POSITION_C5_DUAL_NOTCH_NO_POSITION_GRU_NOPLANT_V1",
     "DL1018_POSITION_C5_STATIC_N4_NO_POSITION_GRU_NOPLANT_V1"),
    ("DL1018_POSITION_C5_DUAL_NOTCH_NO_POSITION_GRU_SINGLE_CALL_V1",
     "DL1018_POSITION_C5_STATIC_N4_NO_POSITION_GRU_SINGLE_CALL_V1"),
):
    if old not in s:
        raise SystemExit(f"missing runner anchor: {old}")
    s = s.replace(old, new)
old = "position_compensation_static_n4_init"
if old not in s:
    raise SystemExit("missing init-call anchor")
old_id = "position_compensation_static_n4_no_residual_gru_ablation_T3_single_call_v1"
if s.count(old_id) != 3:
    raise SystemExit(f"expected 3 transformed study-id anchors, got {s.count(old_id)}")
s = s.replace(old_id, "static_n4_T3C09_no_position_gru_v1", 1)
runner.write_text(s, encoding="utf-8", newline="\n")
if any(x in s for x in ("dualNotch", "DualNotch", "dual_notch", "position_compensation_dual_notch")):
    raise SystemExit("dual-notch symbols remain in patched runner")
print(runner)
