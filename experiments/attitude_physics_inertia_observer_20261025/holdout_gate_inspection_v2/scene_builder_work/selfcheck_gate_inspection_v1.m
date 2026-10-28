function report = selfcheck_gate_inspection_v1()
%SELFCHECK_GATE_INSPECTION_V1 Run deterministic no-Plant scene/geometry assertions.
    report=build_gate_inspection_scenes('SELF_CHECK');
    assert(report.plant_calls==0 && ~report.holdout_payloads_generated, ...
        'GateScene:SelfCheckBoundary','Self-check must remain no-Plant and ID/seed-only for holdout.');
end

