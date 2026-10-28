function P = simulation_parameters(cfg,armLengths,armRates,previousInertia) %#ok<INUSD>
    % FUNCTION:
    %   根据仿真配置构造带真实质量属性和控制分配矩阵的 Plant 参数对象。
    % PURPOSE:
    %   将给定形态、物理常数、执行器限制和模型契约集中提供给 Plant 动力学及其配套模块。
    % INPUT: cfg 为工程配置；armLengths/rates 为四臂长度（m）及变化率（m/s），缺省时采用初始长度和零变化率。
    % OUTPUT: P.role 为 plant，包含按当前几何重算的 CoG、惯量、惯量导数和 Plant allocation。
    % NOTE: P 的形态真值或估计值由调用方输入决定；控制器路径应传入 command-side 估计量，而非 rho_true。
    %SIMULATION_PARAMETERS Build the strict distributed_v1 Plant parameter object.
    if nargin < 2 || isempty(armLengths),armLengths = cfg.plant.arm_initial;
    end
    if nargin < 3 || isempty(armRates),armRates = zeros(4,1);
    end
    assert(isstruct(cfg) && isfield(cfg,'plant') && isfield(cfg.plant,'mass_model') && strcmpi(char(string(cfg.plant.mass_model)),'distributed_v1'),'TCN0901:MassModel','cfg.plant.mass_model must be distributed_v1.');
    P = struct('role','plant','dt',cfg.plant.dt,'mass',cfg.plant.mass,'g',cfg.plant.g,'kf',cfg.plant.kf,'km',cfg.plant.km,'mass_model','distributed_v1','arm_lengths',armLengths(:),'arm_rates',armRates(:),'nominal_arm_lengths',cfg.plant.arm_initial(:),'base_inertia',cfg.plant.inertia,'arm_tip_mass',cfg.plant.arm_tip_mass,'component_masses',cfg.plant.component_masses,'component_dimensions',cfg.plant.component_dimensions,'arm_length_definition',cfg.plant.arm_length_definition,'arm_root_radius',cfg.plant.arm_root_radius,'arm_length_min',cfg.plant.arm_length_min,'arm_length_max',cfg.plant.arm_length_max,'servo_mount_mode',cfg.plant.servo_mount_mode,'geometry_contract_version',cfg.plant.geometry_contract_version,'arm_angles',cfg.plant.arm_angles,'state_position_reference',cfg.plant.state_position_reference,'internal_morphing_momentum_model',cfg.plant.internal_morphing_momentum_model,'vehicle_envelope',cfg.plant.vehicle_envelope);
    P.wind_projected_area_m2 = cfg.plant.wind_projected_area_m2(:);
    P.wind_reference_arm_lengths = cfg.plant.wind_reference_arm_lengths(:);
    assert(numel(P.wind_projected_area_m2)==3 && all(isfinite(P.wind_projected_area_m2)) && ...
        all(P.wind_projected_area_m2>0) && numel(P.wind_reference_arm_lengths)==4 && ...
        all(isfinite(P.wind_reference_arm_lengths)) && ...
        all(P.wind_reference_arm_lengths>P.arm_root_radius), ...
        'RBFBS0:WindGeometry','CAD 风面积或基准臂长配置无效。');
    [P.inertia,P.cog,P.inertia_dot,P.cog_rate] = arm_mass_properties(P.arm_lengths,P,P.arm_rates);
    P.allocation.C = allocation_matrix(P.arm_lengths,P);
    P.allocation.model = 'true_plant_forward';
    P.limits = cfg.plant.limits;
    P.limits.max_tilt = cfg.control.limits.max_tilt;
    P.limits.generalized_min = P.limits.generalized_min(:);
    P.limits.generalized_max = P.limits.generalized_max(:);
    P.actuator.model = 'ideal_instantaneous';
    P.arm_actuator_model = 'ideal_prescribed_motion';
    P.bs = cfg.control.bs;
    P.pd = struct('position',struct('kp',[5;5;5],'kd',[5;5;5]),'attitude',struct('kp',[15;15;15],'kd',[15;15;15]));
    P.command_filter = cfg.control.command_filter;
    P.learned = cfg.control.learned;
    P.rbf = struct('position',default_rbf('position'),'attitude',default_rbf('attitude'));
    if isfield(cfg,'rbf'),if isfield(cfg.rbf,'position'),P.rbf.position = merge_fields(P.rbf.position,cfg.rbf.position);
    end;
    if isfield(cfg.rbf,'attitude'),P.rbf.attitude = merge_fields(P.rbf.attitude,cfg.rbf.attitude);
    end;
end
end
function q = default_rbf(name)
    % FUNCTION:
    %   为 position 或 attitude 通道生成对应的 RBF 基函数和自适应参数默认结构。
    % INPUT: name 指定 position 或 attitude；OUTPUT: 含中心、输入尺度、增益、泄漏和限幅的配置结构体。
    if strcmp(name,'position'),[a,b,c] = ndgrid(-1:1,-1:1,-1:1);
        q = struct('centers',[a(:).';b(:).';c(:).'],'input_scale',[6;8;10],'sigma',.95,'gamma',[1.2;1.2;1.2],'leakage',[.002;.002;.002],'output_limit',[3;3;3],'surface_limit',[7;8;10],'weight_limit',60);
    else,[a,b,c,d,e,f] = ndgrid(-1:1,-1:1,-1:1,-1:1,-1:1,-1:1);
        q = struct('centers',[a(:).';b(:).';c(:).';d(:).';e(:).';f(:).'],'input_scale',[.6;4;.6;4;.6;3],'sigma',1.2,'gamma',[.003;.003;.001],'leakage',[.11;.12;.20],'output_limit',[.3;.3;.12],'surface_limit',[2.3;2.3;1.4],'weight_limit',60);
    end
end
% FUNCTION:
%   用 extra 中同名字段覆盖默认 RBF 结构体中的字段。
% INPUT: out 为默认配置，extra 为用户覆盖项；OUTPUT: 合并后的配置结构体。
function out = merge_fields(out,extra),n = fieldnames(extra);
    for i = 1:numel(n),out.(n{i}) = extra.(n{i});
    end,end
