function P = controller_parameters(cfg, Pplant, varargin)
    % FUNCTION:
    %   根据形态模式建立供控制律和分配器使用的名义参数对象。
    % PURPOSE:
    %   选择固定或随形态变化的控制器几何/惯量，并显式记录是否在 BS 中保留惯量导数项。
    % INPUT: cfg 为控制配置，Pplant 为 Plant 角色的参数结构体；闭环控制路径应由 command-side morphology 估计构造该对象。
    %   可选 varargin{1} 覆盖形态模式。
    % OUTPUT: P.role 为 controller，包含所选名义参数及 controller_nominal allocation 矩阵。
    % NOTE: morphology_mode='fixed' 使用 nominal_arm_lengths；'morph' 使用传入结构体的形态属性。闭环调用不应将 rho_true 传给 controller。
    %CONTROLLER_PARAMETERS Build the nominal model visible to BS and allocator.

    mode = nested(cfg, {'controller_morphology_mode'}, 'morph');
    if nargin >= 3 && ~isempty(varargin{1}), mode = varargin{1};
    end
    mode = lower(char(string(mode)));
    assert(ismember(mode, {'fixed','morph'}), 'TCNNEW:MorphologyMode', ...
        'controller_morphology_mode must be fixed or morph.');
    inertiaDerivativeMode = nested(cfg, ...
        {'controller_inertia_derivative_mode'}, 'full');
    inertiaDerivativeMode = lower(char(string(inertiaDerivativeMode)));
    assert(ismember(inertiaDerivativeMode, {'full','omit_jdot'}), ...
        'TCNNEW:InertiaDerivativeMode', ...
        'controller_inertia_derivative_mode must be full or omit_jdot.');
    assert(isstruct(Pplant) && strcmp(Pplant.role,'plant'), ...
        'TCNNEW:PlantContract', 'Pplant must be a plant parameter object.');

    if strcmp(mode, 'morph')
        armLengths = Pplant.arm_lengths;
        armRates = Pplant.arm_rates;
        inertia = Pplant.inertia;
        cog = Pplant.cog;
        inertiaDot = Pplant.inertia_dot;
        cogRate = Pplant.cog_rate;
    else
        armLengths = Pplant.nominal_arm_lengths;
        armRates = zeros(size(armLengths));
        nominalMassModel = struct('mass',Pplant.mass, ...
            'inertia',Pplant.base_inertia, ...
            'arm_tip_mass',Pplant.arm_tip_mass, ...
            'mass_model',Pplant.mass_model, ...
            'component_masses',Pplant.component_masses, ...
            'component_dimensions',Pplant.component_dimensions, ...
            'arm_length_definition',Pplant.arm_length_definition, ...
            'arm_root_radius',Pplant.arm_root_radius, ...
            'arm_length_min',Pplant.arm_length_min, ...
            'arm_length_max',Pplant.arm_length_max, ...
            'servo_mount_mode',Pplant.servo_mount_mode, ...
            'geometry_contract_version',Pplant.geometry_contract_version, ...
            'arm_angles',Pplant.arm_angles, ...
            'state_position_reference',Pplant.state_position_reference, ...
            'internal_morphing_momentum_model',Pplant.internal_morphing_momentum_model, ...
            'vehicle_envelope',Pplant.vehicle_envelope);
        [inertia,cog,inertiaDot,cogRate] = arm_mass_properties( ...
            armLengths, nominalMassModel, armRates);
    end

    P = struct();
    P.role = 'controller';
    P.morphology_mode = mode;
    P.dt = Pplant.dt;
    P.mass = Pplant.mass;
    P.g = Pplant.g;
    P.kf = Pplant.kf;
    P.km = Pplant.km;
    P.mass_model = Pplant.mass_model;
    P.arm_lengths = armLengths;
    P.arm_rates = armRates;
    P.arm_angles = Pplant.arm_angles;
    P.nominal_arm_lengths = Pplant.nominal_arm_lengths;
    P.inertia = inertia;
    P.cog = cog;
    P.inertia_dot = inertiaDot;
    P.controller_inertia_derivative_mode = inertiaDerivativeMode;
    P.inertia_dot_for_bs = inertiaDot;
    if strcmp(inertiaDerivativeMode,'omit_jdot')
        P.inertia_dot_for_bs = zeros(size(inertiaDot));
    end
    P.cog_rate = cogRate;
    P.component_masses = Pplant.component_masses;
    P.component_dimensions = Pplant.component_dimensions;
    P.arm_length_definition = Pplant.arm_length_definition;
    P.arm_root_radius = Pplant.arm_root_radius;
    P.arm_length_min = Pplant.arm_length_min;
    P.arm_length_max = Pplant.arm_length_max;
    P.servo_mount_mode = Pplant.servo_mount_mode;
    P.geometry_contract_version = Pplant.geometry_contract_version;
    P.state_position_reference = Pplant.state_position_reference;
    P.internal_morphing_momentum_model = Pplant.internal_morphing_momentum_model;
    P.vehicle_envelope = Pplant.vehicle_envelope;
    P.limits = Pplant.limits;
    P.bs = Pplant.bs;
    P.pd = Pplant.pd;
    P.command_filter = Pplant.command_filter;
    P.learned = Pplant.learned;
    P.rbf = Pplant.rbf;
    P.allocation.C = allocation_matrix(P.arm_lengths, P);
    P.allocation.model = 'controller_nominal';
end

function value = nested(s, names, defaultValue)
    % FUNCTION:
    %   按 names 给出的字段路径读取嵌套配置值。
    % INPUT: s 为配置结构体，names 为字段名序列，defaultValue 为缺失时的缺省值。
    % OUTPUT: 路径末端字段值；任一层缺失或不是结构体时返回 defaultValue。
    value = s;
    for i = 1:numel(names)
        if ~isstruct(value) || ~isfield(value, names{i})
            value = defaultValue;
            return;
        end
        value = value.(names{i});
    end
end
