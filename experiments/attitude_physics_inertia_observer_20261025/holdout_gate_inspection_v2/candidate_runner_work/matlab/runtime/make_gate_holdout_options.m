function opts=make_gate_holdout_options(cfg,positionModel,attitudeArm,geometryArm,identityLock)
% Bind a C5 method arm and a geometry-specific lock to the frozen C5 option builder.
if nargin<5,identityLock=struct;end
attitudeArm=upper(char(attitudeArm));
geometryArm=upper(char(geometryArm));
spec=gate_attitude_arm_spec(attitudeArm);
assert(ismember(geometryArm,{'ACTIVE','FIXED_MIN','FIXED_BOUND15'}), ...
    'GATE:GeometryArm','Unknown gate geometry arm.');
[baseline,candidate]=make_paired_c5_options(cfg,positionModel);
if strcmp(spec.paired_arm,'baseline')
    opts=baseline;
else
    opts=candidate;
end
opts.gate_attitude_arm=attitudeArm;
opts.gate_geometry_arm=geometryArm;
opts.gate_identity_lock=identityLock;
end