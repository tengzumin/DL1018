function [inertia, cog, inertiaDot, cogRate, details] = ...
        distributed_mass_properties(lengths, plant, rates)
    % FUNCTION:
    %   汇总机身、电池、机臂、电机、旋翼和舵机的质心与转动惯量。
    % PURPOSE:
    %   按 distributed_v1 的刚性分量近似，计算随臂长变化的总惯量、总 CoG 及其时间导数。
    % INPUT: lengths/rates 分别为四个旋翼中心半径（m）及其变化率（m/s）；plant 提供分量质量、尺寸和安装几何。
    % OUTPUT: inertia（kg*m^2）、cog（机体系 m）、inertiaDot（kg*m^2/s）、cogRate（m/s）和中间几何 details。
    % NOTE: 状态位置参考瞬时总 CoG；内部 morphing 动量耦合项按 neglected_quasi_static 配置假设忽略。
    %DISTRIBUTED_MASS_PROPERTIES CODETCN-BS0825 distributed_v1 mass properties.
    %   Arm length is the body-origin to rotor-center radius.  The model is a
    %   simulation assumption, not a hardware measurement claim.

    lengths = double(lengths(:));
    assert(numel(lengths) == 4 && all(isfinite(lengths)) && all(lengths > 0), ...
        'TCNNEW:ArmLength', 'Arm lengths must be four finite positive values.');
    if nargin < 3 || isempty(rates), rates = zeros(4,1);
    end
    rates = double(rates(:));
    assert(numel(rates) == 4 && all(isfinite(rates)), ...
        'TCNNEW:ArmRate', 'Arm rates must be four finite values.');

    m = component_masses(plant);
    d = component_dimensions(plant);
    rootRadius = required(plant,'arm_root_radius');
    servoMode = char(string(required(plant,'servo_mount_mode')));

    totalMass = m.body + m.battery + 4 * (m.arm + m.motor + m.rotor + m.servo);
    massValue = required(plant,'mass');
    assert(abs(totalMass-massValue) <= 1e-12, ...
        'TCNNEW:MassBalance','cfg.plant.mass must equal the sum of component masses (%.9g kg).',totalMass);

    [directions, angles] = arm_directions(plant);
    z = zeros(3,1);
    positions.body = z;
    positionRates.body = z;
    % 电池安装坐标和尺寸未提供，暂按机身原点处的点质量建模。
    positions.battery = z;
    positionRates.battery = z;
    positions.arm = zeros(3,4);
    positionRates.arm = zeros(3,4);
    positions.motor = directions .* lengths.';
    positionRates.motor = directions .* rates.';
    positions.rotor = positions.motor;
    positionRates.rotor = positionRates.motor;
    servoScalar = rootRadius + 0.5 * d.servo.length;
    positions.servo = directions .* servoScalar;
    positionRates.servo = zeros(3,4);
    armEffectiveLengths = lengths - rootRadius;
    armScalar = 0.5 * (rootRadius + lengths);
    positions.arm = directions .* armScalar.';
    positionRates.arm = directions .* (0.5 * rates.');

    cogNumerator = m.body * positions.body + ...
        m.battery * positions.battery + ...
        m.arm * sum(positions.arm,2) + m.motor * sum(positions.motor,2) + ...
        m.rotor * sum(positions.rotor,2) + m.servo * sum(positions.servo,2);
    cog = cogNumerator / totalMass;
    cogRateNumerator = m.body * positionRates.body + ...
        m.battery * positionRates.battery + ...
        m.arm * sum(positionRates.arm,2) + m.motor * sum(positionRates.motor,2) + ...
        m.rotor * sum(positionRates.rotor,2) + m.servo * sum(positionRates.servo,2);
    cogRate = cogRateNumerator / totalMass;

    I3 = eye(3);
    inertia = zeros(3);
    inertiaDot = zeros(3);
    rotations = zeros(3,3,4);
    localInertia = zeros(3,3,4,4);
    localInertiaDot = zeros(3,3,4,4);
    Ibody = cuboid_inertia(m.body,d.body.length,d.body.width,d.body.height);
    [term, termDot] = component_term(Ibody,zeros(3),m.body, ...
        positions.body,positionRates.body,cog,cogRate,I3);
    inertia = inertia + term;
    inertiaDot = inertiaDot + termDot;
    [term, termDot] = component_term(zeros(3),zeros(3),m.battery, ...
        positions.battery,positionRates.battery,cog,cogRate,I3);
    inertia = inertia + term;
    inertiaDot = inertiaDot + termDot;
    for i = 1:4
        R = body_rotation(angles(i));
        rotations(:,:,i) = R;
        L = armEffectiveLengths(i);
        Ldot = rates(i);
        Iarm = cuboid_inertia(m.arm,L,d.arm.width,d.arm.height);
        IarmDot = m.arm / 6 * L * Ldot * diag([0,1,1]);
        Imotor = cylinder_inertia(m.motor,d.motor.radius,d.motor.height);
        Irotor = cylinder_inertia(m.rotor,d.rotor.inertia_equivalent_radius, ...
            d.rotor.height);
        Iservo = cuboid_inertia(m.servo,d.servo.length,d.servo.width,d.servo.height);
        localInertia(:,:,i,1) = R * Iarm * R.';
        localInertia(:,:,i,2) = Imotor;
        localInertia(:,:,i,3) = Irotor;
        localInertia(:,:,i,4) = R * Iservo * R.';
        localInertiaDot(:,:,i,1) = R * IarmDot * R.';

        [term, termDot] = component_term(localInertia(:,:,i,1), ...
            localInertiaDot(:,:,i,1),m.arm,positions.arm(:,i), ...
            positionRates.arm(:,i),cog,cogRate,I3);
        inertia = inertia + term;
        inertiaDot = inertiaDot + termDot;
        [term, termDot] = component_term(Imotor,zeros(3),m.motor, ...
            positions.motor(:,i),positionRates.motor(:,i),cog,cogRate,I3);
        inertia = inertia + term;
        inertiaDot = inertiaDot + termDot;
        [term, termDot] = component_term(Irotor,zeros(3),m.rotor, ...
            positions.rotor(:,i),positionRates.rotor(:,i),cog,cogRate,I3);
        inertia = inertia + term;
        inertiaDot = inertiaDot + termDot;
        [term, termDot] = component_term(localInertia(:,:,i,4), ...
            zeros(3),m.servo,positions.servo(:,i),positionRates.servo(:,i), ...
            cog,cogRate,I3);
        inertia = inertia + term;
        inertiaDot = inertiaDot + termDot;
    end

    inertia = 0.5 * (inertia + inertia.');
    inertiaDot = 0.5 * (inertiaDot + inertiaDot.');
    assert(all(isfinite(inertia),'all') && all(eig(inertia) > 0), ...
        'TCNNEW:InertiaNotPositiveDefinite', ...
        'distributed_v1 inertia must be finite and positive definite.');
    assert(all(isfinite(inertiaDot),'all') && all(isfinite(cogRate)), ...
        'TCNNEW:MassPropertyRate', 'distributed_v1 rates must be finite.');

    details = struct('mass_model','distributed_v1', ...
        'total_mass',totalMass,'component_masses',m, ...
        'component_dimensions',d,'arm_lengths',lengths, ...
        'arm_rates',rates,'arm_effective_lengths',armEffectiveLengths, ...
        'arm_root_radius',rootRadius,'servo_mount_mode',servoMode, ...
        'state_position_reference',plant.state_position_reference, ...
        'internal_morphing_momentum_model',plant.internal_morphing_momentum_model, ...
        'rotor_physical_radius',plant.vehicle_envelope.rotor_physical_radius, ...
        'angles',angles,'directions',directions,'rotations',rotations, ...
        'positions',positions,'position_rates',positionRates, ...
        'local_inertia',localInertia,'local_inertia_dot',localInertiaDot);
end

function [term, termDot] = component_term(localI, localIDot, mass, ...
        position, positionRate, cog, cogRate, I3)
    % FUNCTION:
    %   将单个刚性分量的局部惯量平移到总 CoG，并求平行轴项的时间导数。
    % INPUT: localI/localIDot 为分量局部惯量及其导数；position/positionRate 与 cog/cogRate 均在机体系中。
    % OUTPUT: term 为该分量对总惯量的贡献；termDot 为对应的时间导数。
    r = position - cog;
    rDot = positionRate - cogRate;
    shift = (r.' * r) * I3 - r * r.';
    shiftDot = 2 * (r.' * rDot) * I3 - rDot * r.' - r * rDot.';
    term = localI + mass * shift;
    termDot = localIDot + mass * shiftDot;
end

function I = cuboid_inertia(mass, length, width, height)
    % FUNCTION:
    %   按长方体主轴公式计算绕质心的对角转动惯量。
    % INPUT: mass（kg）及沿三个主轴的 length、width、height（m）。
    % OUTPUT: 以输入主轴顺序表示的 3x3 惯量矩阵（kg*m^2）。
    I = mass / 12 * diag([width ^ 2 + height ^ 2, length ^ 2 + height ^ 2, ...
        length ^ 2 + width ^ 2]);
end

function I = cylinder_inertia(mass, radius, height)
    % FUNCTION:
    %   按均匀实心圆柱公式计算绕质心主轴的对角转动惯量。
    % INPUT: mass（kg）、radius（m）和 height（m）。
    % OUTPUT: 圆柱轴向沿局部 z 轴的 3x3 惯量矩阵（kg*m^2）。
    I = diag([mass / 12 * (3 * radius ^ 2 + height ^ 2), ...
        mass / 12 * (3 * radius ^ 2 + height ^ 2), 0.5 * mass * radius ^ 2]);
end

function R = body_rotation(angle)
    % FUNCTION:
    %   构造绕机体系 z 轴的平面旋转矩阵。
    % INPUT: arm 安装角 angle（rad）；OUTPUT: 将臂局部平面向量旋转到机体系的矩阵。
    R = [cos(angle),-sin(angle),0; sin(angle),cos(angle),0; 0,0,1];
end

function value = component_masses(plant)
    % FUNCTION:
    %   读取并校验 distributed_v1 所需的分量质量。
    % INPUT: plant 参数结构体；OUTPUT: 含 body、battery、arm、motor、rotor、servo 的正有限质量结构体（kg）。
    value = required(plant,'component_masses');
    names = {'body','battery','arm','motor','rotor','servo'};
    for i = 1:numel(names)
        assert(isfield(value,names{i}), 'TCNNEW:ComponentMasses', ...
            'component_masses.%s is missing.', names{i});
        assert(isscalar(value.(names{i})) && isfinite(value.(names{i})) && ...
            value.(names{i}) > 0, 'TCNNEW:ComponentMasses', ...
            'component_masses.%s must be positive and finite.', names{i});
    end
end

function value = component_dimensions(plant)
    % FUNCTION:
    %   读取分量几何尺寸配置并检查各分量字段是否存在。
    % INPUT: plant 参数结构体；OUTPUT: body、arm、motor、rotor、servo 尺寸结构体（m）。
    value = required(plant,'component_dimensions');
    names = {'body','arm','motor','rotor','servo'};
    for i = 1:numel(names)
        assert(isfield(value,names{i}), 'TCNNEW:ComponentDimensions', ...
            'component_dimensions.%s is missing.', names{i});
    end
end

function value = required(s,name)
    % FUNCTION:
    %   从结构体中读取 mass-property 契约要求的字段。
    % INPUT: s 为配置结构体，name 为字段名；OUTPUT: 对应字段值，缺失时触发契约错误。
    assert(isstruct(s) && isfield(s,name), 'TCNNEW:DistributedContract', ...
        'distributed_v1 requires plant.%s.', name);
    value = s.(name);
end
