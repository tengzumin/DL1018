function cfg=bind_paired_fixed_j0(cfg)
% Freeze the controller's fixed C0/J0 model into the paired helper config.
Pplant=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
Pfixed=controller_parameters(cfg,Pplant,'fixed');
J0=double(Pfixed.inertia);
assert(isequal(size(J0),[3,3])&&all(eig(J0)>0), ...
    'PAIRED:J0','Fixed controller inertia must be 3-by-3 SPD.');
identity=struct( ...
    'J0_controller_fixed_kgm2',J0, ...
    'J0_controller_fixed_sha256',paired_sha256_double(J0));
if isfield(cfg,'attitude_replacement')
    assert(isequaln(cfg.attitude_replacement,identity), ...
        'PAIRED:J0','Existing frozen J0 identity differs from the fixed controller.');
else
    cfg.attitude_replacement=identity;
end
end
