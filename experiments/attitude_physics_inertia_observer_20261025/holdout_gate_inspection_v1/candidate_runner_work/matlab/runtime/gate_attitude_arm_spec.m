function spec=gate_attitude_arm_spec(arm)
% Locked method mapping used by the holdout option builder and runner.
arm=upper(char(arm));
switch arm
    case 'C5_RBF'
        spec=struct('arm',arm,'paired_arm','baseline','rbf_enabled',true, ...
            'physics_helper_enabled',false,'feedforward_enabled',false,'observer_enabled',false);
    case 'C5_RBF_F'
        spec=struct('arm',arm,'paired_arm','baseline','rbf_enabled',true, ...
            'physics_helper_enabled',true,'feedforward_enabled',true,'observer_enabled',false);
    case 'C5_00'
        spec=struct('arm',arm,'paired_arm','candidate','rbf_enabled',false, ...
            'physics_helper_enabled',true,'feedforward_enabled',false,'observer_enabled',false);
    case 'C5_10'
        spec=struct('arm',arm,'paired_arm','candidate','rbf_enabled',false, ...
            'physics_helper_enabled',true,'feedforward_enabled',true,'observer_enabled',false);
    case 'C5_01'
        spec=struct('arm',arm,'paired_arm','candidate','rbf_enabled',false, ...
            'physics_helper_enabled',true,'feedforward_enabled',false,'observer_enabled',true);
    case 'C5_11'
        spec=struct('arm',arm,'paired_arm','candidate','rbf_enabled',false, ...
            'physics_helper_enabled',true,'feedforward_enabled',true,'observer_enabled',true);
    otherwise
        error('GATE:AttitudeArm','Unknown C5 attitude arm %s.',arm);
end
end