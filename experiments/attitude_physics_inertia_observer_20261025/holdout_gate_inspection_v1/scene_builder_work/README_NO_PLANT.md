# Gate scene builder work (pre-review draft)

All functions here are no-Plant. The builder reads the locked geometry configuration and calls only the locked `wind_velocity_profile` for W00-W14. W15 is explicitly an all-zero array. It does not call `make_scenes_dl1018`, load scene tables, or read any TEST evidence.

- `gate_scene_id_seed_manifest_v1_DRAFT.csv`: GH48 plus independent GHP6 IDs/seeds only; status remains unaudited and unfrozen.
- `build_gate_inspection_scenes('MANIFEST')`: returns the ID/seed manifest in memory.
- `build_gate_inspection_scenes('PILOT','ACTIVE')`: builds six pilot payloads in memory only.
- `build_gate_inspection_scenes('HOLDOUT','FIXED_MIN','ACTIVE')`: holdout generation requires an explicitly selected pilot comparator. Do not call until comparator selection/release.
- `R_task` is empty with status `PENDING_LOCKED_C5_BINDER` unless the locked C5 binder passes a finite 3x3x20001 array.
- `check_gate_inspection_geometry(time,stateHistory,rho,cfg)`: evaluates component proxy clearance and ordered forward/return CoG crossings. It does not model contact response.

Geometry uses configured body/arm/motor/servo boxes and motor/rotor cylinders, CoG offsets from the distributed_v1 mass layout, and the configured 0.0635 m rotor physical radius estimate. Battery is a point mass because the Plant config has no battery dimensions. The checker uses exact projected support extents and conservatively tests each whole component whenever its x support intersects the wall slab. Its result is a configured-component proxy, not hardware clearance.

Verified by the requested assertion path in MATLAB R2025b after adding this directory to the path:
`report=selfcheck_gate_inspection_v1();`
The self-check creates pilot payloads only in memory and never materializes holdout payloads or runs Plant.


