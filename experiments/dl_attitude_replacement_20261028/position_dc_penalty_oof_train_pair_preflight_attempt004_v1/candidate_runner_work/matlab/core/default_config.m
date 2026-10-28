function cfg = default_config()
    % FUNCTION:
    %   返回 TCN0916 distributed_v1 Plant、BS 控制器和学习模块使用的默认配置。
    % PURPOSE:
    %   集中声明仿真步长、物理/几何契约、控制器参数和唯一活动 RBF 35/81 Gamma 5/19 配置。
    % OUTPUT: cfg 为嵌套结构体，供 Plant 与控制器参数构造函数读取。
    % NOTE: 下列质量为当前 RBF-BS0 飞行器的配置值；质量属性由 distributed_v1 按分量重算。
    %DEFAULT_CONFIG TCN0916 distributed_v1 contract and BS baseline.
    % Plant 的质量模型、CoG 参考和 morphology 几何契约。
    cfg.name = 'RBFBS0_PHYSICAL_4S_V1';
    cfg.plant.mass_model = 'distributed_v1';
    cfg.mass_model = cfg.plant.mass_model;
    cfg.plant.mass = .695;
    cfg.plant.g = 9.8;
    cfg.plant.gravity = cfg.plant.g;
    cfg.plant.dt = 1e-3;
    cfg.plant.kf = 1.70e-6; % N/(rad/s)^2; 4S + 5-inch six-blade engineering estimate
    cfg.plant.km = 3.20e-8; % N*m/(rad/s)^2; engineering estimate
    cfg.plant.lbody = .118;
    cfg.plant.arm_root_radius = cfg.plant.lbody / 2;
    cfg.plant.arm_length_min = .15;
    cfg.plant.arm_length_max = .25;
    cfg.plant.arm_initial = .15 * ones(4,1);
    cfg.plant.arm_angles = pi / 4 + (0:3) * pi / 2;
    cfg.plant.arm_length_definition = 'body_origin_to_rotor_center_radial_distance';
    cfg.plant.geometry_contract_version = 'RBFBS0.distributed_v1.x_layout.v2';
    % CAD 正交投影面积：机体 X/Y/Z 轴方向的整机投影，包含静止姿态桨叶和电池外形。
    % 机体 X 朝向 CAD +X 侧两电机中点；机体 Z 为竖直轴。单位 m^2。
    % 面积基准臂长来自 CAD 电机中心到机体中心的径向距离，臂长变化仍由风载模型单独计算。
    cfg.plant.wind_projected_area_m2 = [0.008240355616;0.007699184218;0.027129155540];
    cfg.plant.wind_reference_arm_lengths = 0.141623 * ones(4,1);
    cfg.plant.state_position_reference = 'instantaneous_total_cog';
    cfg.plant.internal_morphing_momentum_model = 'neglected_quasi_static';
    cfg.plant.servo_mount_mode = 'root_fixed';
    cfg.plant.vehicle_envelope = struct('rotor_physical_radius',0.0635, ...
        'rotor_physical_radius_status','5_INCH_PROP_GEOMETRY_ESTIMATE');
    % 机身与电池质量按集中分量处理；电池位置暂按机身中心，见质量属性模型说明。
    cfg.plant.component_masses = struct('body',.130,'battery',.145, ...
        'arm',.040,'motor',.035,'rotor',.005,'servo',.025);
    cfg.plant.component_dimensions = struct('body',struct('length',.118,'width',.118,'height',.075), ...
        'arm',struct('width',.025,'height',.015), ...
        'motor',struct('radius',.015,'height',.025), ...
        'rotor',struct('inertia_equivalent_radius',.045,'height',.04), ...
        'servo',struct('length',.03,'width',.015,'height',.02));
    cfg.plant.inertia = diag([.012 .012 .022]);
    cfg.plant.arm_tip_mass = .04;
    cfg.plant.limits.motor_min = 0;
    cfg.plant.limits.motor_max = 1900; % rad/s; 4S loaded work limit estimate
    omega2max = cfg.plant.limits.motor_max^2;
    F_one_max = cfg.plant.kf*omega2max;
    T_max = 4*F_one_max;
    Mx_bound = sqrt(2)*cfg.plant.arm_initial(1)*F_one_max;
    My_bound = Mx_bound;
    Mz_bound = 2*cfg.plant.km*omega2max;
    cfg.plant.limits.generalized_min = [0;-Mx_bound;-My_bound;-Mz_bound];
    cfg.plant.limits.generalized_max = [T_max;Mx_bound;My_bound;Mz_bound];
    cfg.control.morphology_mode = 'morph';
    % 控制器反步增益、姿态命令滤波和 learned-head 调用配置。
    cfg.controller_morphology_mode = 'morph';
    cfg.controller_inertia_derivative_mode = 'full';
    cfg.control.bs.position = struct('k1',[1;1;1],'k2',[4;4;4]);
    cfg.control.bs.attitude = struct('k1',[1.5;1.5;1.3],'k2',[22.5;22.5;12.7]);
    cfg.control.limits = struct('max_tilt',pi / 6, ...
        'generalized_min',cfg.plant.limits.generalized_min, ...
        'generalized_max',cfg.plant.limits.generalized_max);
    cfg.control.command_filter = struct('wn',[18;18;12],'damping',[1;1;1], ...
        'acceleration_limit',[8;8;6]);
    cfg.control.learned = struct('position_sample_time',.01,'attitude_sample_time',.005, ...
        'window_length',32,'active_architecture','simple_causal_tcn_v1', ...
        'position_limit',[4;4;4],'attitude_limit',[.3;.3;.12]);
    % Values below are copied from CODERBF-BS params.m without changing its update law.
    % 下列 RBF/TCN 字段定义网络维度、离散尺度和训练/验证接口。
    [a,b,c] = ndgrid([-1.5,-.75,0,.75,1.5],[-1.5,-.75,0,.75,1.5],[-1.5,-.75,0,.75,1.5]);
    fullPositionCenters=[a(:).';b(:).';c(:).'];
    cfg.rbf.position = struct('rbf_input_dim',3,'linear_dim',0,'input_scale',[6;8;10], ...
        'gamma',1.2,'sigma_w',.002,'wmax',60,'dmax',[3;3;3],'s_limit',[7;8;10], ...
        'sigma',.95,'beta_rise_time',1.8,'centers',[]);
    [positionIndices,cfg.rbf.position.centers]=symmetric_center_subset(fullPositionCenters,35);
    cfg.rbf.position.center_source_indices=positionIndices;
    cfg.rbf.position.gamma_scale=5;
    [a,b,c,d,e,f] = ndgrid([-1 0 1],[-1 0 1],[-1 0 1],[-1 0 1],[-1 0 1],[-1 0 1]);
    fullAttitudeCenters=[a(:).';b(:).';c(:).';d(:).';e(:).';f(:).'];
    cfg.rbf.attitude = struct('rbf_input_dim',6,'linear_dim',0,'input_scale',[.6;4;.6;4;.6;3], ...
        'gamma',[2.1;2.25;1.1],'sigma_w',[.11;.12;.20],'wmax',60, ...
        'dmax',[45;45;4.7124], ...
        's_limit',[2.3;2.3;1.4],'sigma',1.2,'beta_rise_time',2.2, ...
        'centers',[]);
    [attitudeIndices,cfg.rbf.attitude.centers]=symmetric_center_subset(fullAttitudeCenters,81);
    cfg.rbf.attitude.center_source_indices=attitudeIndices;
    cfg.rbf.attitude.gamma_scale=19;
    cfg.tcn = struct('window_length',32,'kernel_size',3,'dilations',[1 2 4 8], ...
        'position_input_dim',24,'attitude_input_dim',26,'output_dim',3,'loss','MSE only');
    cfg.response_tcn = struct('history_channels',16,'history_length',253, ...
        'current_dim',20,'command_dim',8,'latent_dim',8,'mapper_widths',[64 32], ...
        'learner_frequency_hz',50,'learner_period_s',.020, ...
        'history_span_s',5.04,'maturity_threshold',.60, ...
        'morphology_start_min_s',5.2,'command_speed_mps',.02, ...
        'label_dim',6,'loss','normalized_6d_mse');
    cfg.reference.target = [3;4;5];
    cfg.reference.yaw = pi / 3;
    cfg.validation.duration = 0.50;
    cfg.validation.seed = 20260902;
end

function [indices,selectedCenters]=symmetric_center_subset(centers,targetCount)
count=size(centers,2);
assert(targetCount<=count&&mod(targetCount,2)==1, ...
    'RBFBS0:CompactCenterCount','Symmetric center selection requires an odd target count.');
[~,centerIndex]=min(sum(centers.^2,1));
[found,mirror]=ismember((-centers).',centers.','rows');
assert(all(found),'RBFBS0:CenterSymmetry','Full RBF centers must contain exact symmetric pairs.');
roots=find(((1:count).'<mirror)&((1:count).'~=centerIndex));
roots=roots(:).';selected=centerIndex;selectedPairs=false(count,1);
for pairNumber=1:(targetCount-1)/2
    bestIndex=NaN;bestDistance=-Inf;
    for candidate=roots
        if selectedPairs(candidate),continue;end
        pair=[candidate,mirror(candidate)];nearest=inf;
        for chosen=selected
            nearest=min(nearest,min(sum((centers(:,pair)-centers(:,chosen)).^2,1)));
        end
        if nearest>bestDistance+1e-12
            bestDistance=nearest;bestIndex=candidate;
        end
    end
    assert(isfinite(bestIndex),'RBFBS0:CenterSelection','Could not select the requested symmetric center count.');
    selectedPairs(bestIndex)=true;selected=[selected,bestIndex,mirror(bestIndex)]; %#ok<AGROW>
end
indices=selected;selectedCenters=centers(:,indices);
end
