function spec=gate_attitude_arm_spec(arm)
% Locked method mapping used by the holdout option builder and runner.
arm=upper(char(arm));
switch arm
    case 'C5_RBF'
        spec=struct('arm',arm,'paired_arm','baseline','rbf_enabled',true, ...
            'physics_helper_enabled',false,'feedforward_enabled',false,'observer_enabled',false);
    case 'DL_TCN'
        spec=struct('arm',arm,'paired_arm','candidate','rbf_enabled',false, ...
            'physics_helper_enabled',false,'feedforward_enabled',false,'observer_enabled',false);
    case 'DL_MLP15'
        spec=struct('arm',arm,'paired_arm','candidate','rbf_enabled',false, ...
            'physics_helper_enabled',false,'feedforward_enabled',false,'observer_enabled',false);
    case 'GRU_STREAM'
        spec=struct('arm',arm,'paired_arm','candidate','rbf_enabled',false, ...
            'physics_helper_enabled',false,'feedforward_enabled',false,'observer_enabled',false);
    otherwise
        error('GATE:AttitudeArm','Unknown C5 attitude arm %s.',arm);
end
end
