function [forceInertial,torqueBody,details] = morphology_aware_wind_load(state,Pplant,windVelocityInertial,windCfg)
    % FUNCTION:
    %   以 CAD 整机投影面积确定基准风力，并叠加当前变臂相对 CAD 基准姿态的气动变化。
    % PURPOSE:
    %   将惯性系风速与飞行速度之差变换到机体系；整机 CAD 面积负责基准合力，机臂模型负责变臂增量和分布力矩。
    % INPUT: state 为 [位置_I;速度_I;ZYX欧拉角;机体系角速度]；windVelocityInertial 为惯性系风速（m/s）。
    %   Pplant 为真实 distributed_v1 Plant 几何；windCfg 提供空气密度（kg/m^3）和阻力系数。
    % OUTPUT: forceInertial 为惯性系合力（N），torqueBody 为机体系合力矩（N*m），details 记录分量和坐标系。
    % NOTE: CAD 基准面积已包含机臂、电机、桨叶、电池和机身；机臂只叠加相对基准臂长的变化，避免重复计算。
    %MORPHOLOGY_AWARE_WIND_LOAD CAD 标定的整机阻力及变臂修正。
    state = double(state(:));
    windVelocityInertial = double(windVelocityInertial(:));
    assert(numel(state) == 12 && all(isfinite(state)) && numel(windVelocityInertial) == 3 && all(isfinite(windVelocityInertial)),'TCN0901:WindLoadInput','state and wind velocity must be finite 12x1 and 3x1 vectors.');
    assert(isstruct(Pplant) && isfield(Pplant,'role') && strcmp(Pplant.role,'plant') && isfield(Pplant,'mass_model') && strcmpi(char(string(Pplant.mass_model)),'distributed_v1'),'TCN0901:WindPlant','Pplant must be a distributed_v1 plant object.');
    assert(isstruct(windCfg) && all(isfield(windCfg,{'rho_air','CdBody','CdArm'})),'TCN0901:WindLoadConfig','windCfg requires rho_air, CdBody, and CdArm.');
    vals = [windCfg.rho_air,windCfg.CdBody,windCfg.CdArm];
    assert(all(isfinite(vals)) && all(vals > 0),'TCN0901:WindLoadConfig','air density and drag coefficients must be positive finite scalars.');
    [~,~,~,~,geometry] = arm_mass_properties(Pplant.arm_lengths,Pplant,Pplant.arm_rates);
    assert(isequal(geometry.arm_effective_lengths,Pplant.arm_lengths - Pplant.arm_root_radius) && isequal(geometry.positions.arm,geometry.directions .* (.5 * (Pplant.arm_root_radius + Pplant.arm_lengths)).'),'TCN0901:WindGeometry','Wind load must use distributed_v1 geometry details.');
    R = rotation_zyx_local(state(7:9));
    airRelativeInertial = windVelocityInertial - state(4:6);
    airRelativeBody = R.' * airRelativeInertial;
    d = Pplant.component_dimensions;
    projectedArea = double(Pplant.wind_projected_area_m2(:));
    referenceArmLengths = double(Pplant.wind_reference_arm_lengths(:));
    assert(numel(projectedArea)==3 && all(isfinite(projectedArea)) && all(projectedArea>0) && ...
        numel(referenceArmLengths)==4 && all(isfinite(referenceArmLengths)) && ...
        all(referenceArmLengths>Pplant.arm_root_radius), ...
        'RBFBS0:WindGeometry','CAD 风面积或基准臂长无效。');
    cadReferenceForce = area_drag(airRelativeBody,projectedArea,windCfg.rho_air,windCfg.CdBody);
    armReferenceForces = zeros(3,4);
    armForces = zeros(3,4);
    armMomentArms = zeros(3,4);
    bodyForce = cadReferenceForce;
    for i = 1:4
        Q = geometry.rotations(:,:,i);
        vLocal = Q.' * airRelativeBody;
        fLocal = axis_drag(vLocal,[geometry.arm_effective_lengths(i);d.arm.width;d.arm.height],windCfg.rho_air,windCfg.CdArm);
        referenceEffectiveLength = referenceArmLengths(i) - Pplant.arm_root_radius;
        fReferenceLocal = axis_drag(vLocal,[referenceEffectiveLength;d.arm.width;d.arm.height],windCfg.rho_air,windCfg.CdArm);
        armForces(:,i) = Q * fLocal;
        armReferenceForces(:,i) = Q * fReferenceLocal;
        bodyForce = bodyForce - armReferenceForces(:,i);
        armMomentArms(:,i) = geometry.positions.arm(:,i) - Pplant.cog;
    end
    forceBody = bodyForce + sum(armForces,2);
    torqueBody = cross(-Pplant.cog,bodyForce);
    for i = 1:4
        torqueBody = torqueBody + cross(armMomentArms(:,i),armForces(:,i));
    end
    forceInertial = R * forceBody;
    assert(isequal(size(forceInertial),[3,1]) && isequal(size(torqueBody),[3,1]) && all(isfinite([forceInertial;torqueBody])),'TCN0901:WindLoadOutput','Wind load must be finite 3x1 force/torque.');
    details = struct('force_unit','N','torque_unit','N*m','force_frame','inertial','torque_frame','body','air_relative_velocity_inertial',airRelativeInertial,'air_relative_velocity_body',airRelativeBody,'force_body',forceBody,'body_residual_force_body',bodyForce,'cad_reference_force_body',cadReferenceForce,'cad_projected_area_m2',projectedArea,'arm_reference_force_body',armReferenceForces,'arm_force_body',armForces,'body_moment_arm_body',-Pplant.cog,'arm_moment_arms_body',armMomentArms,'arm_effective_lengths',geometry.arm_effective_lengths,'wind_reference_arm_lengths',referenceArmLengths,'arm_positions_body',geometry.positions.arm,'directions_body',geometry.directions,'rotations_local_to_body',geometry.rotations,'geometry_source','CAD 全机投影面积 + distributed_v1 变臂增量');
end

function f = area_drag(v,areas,rho,Cd)
    % FUNCTION:
    %   根据整机 X/Y/Z 三轴正交投影面积计算基准阻力。
    % INPUT: v 为机体系相对气流速度（m/s）；areas(i) 为垂直于机体第 i 轴的投影面积（m^2）。
    % OUTPUT: f 为机体系三轴阻力（N）。
    f = .5 * rho * Cd * areas .* abs(v) .* v;
end

function f = axis_drag(v,dims,rho,Cd)
    % FUNCTION:
    %   按逐轴投影面积和二次阻力关系计算局部坐标系气动力。
    % INPUT: v 为相对气流速度（m/s），dims 为长宽高（m），rho 为空气密度，Cd 为阻力系数。
    % OUTPUT: f 为该分量在局部坐标轴上的准稳态气动力（N）。
    areas = [dims(2) * dims(3);dims(1) * dims(3);dims(1) * dims(2)];
    f = .5 * rho * Cd * areas .* abs(v) .* v;
end

function R = rotation_zyx_local(eta)
    % FUNCTION:
    %   构造 ZYX 欧拉角对应的机体系到惯性系旋转矩阵。
    % INPUT: eta=[roll;pitch;yaw]（rad）；OUTPUT: body-to-inertial 旋转矩阵。
    phi = eta(1);
    theta = eta(2);
    psi = eta(3);
    cphi = cos(phi);
    sphi = sin(phi);
    ctheta = cos(theta);
    stheta = sin(theta);
    cpsi = cos(psi);
    spsi = sin(psi);
    R = [cpsi * ctheta,cpsi * stheta * sphi - spsi * cphi,cpsi * stheta * cphi + spsi * sphi;spsi * ctheta,spsi * stheta * sphi + cpsi * cphi,spsi * stheta * cphi - cpsi * sphi;-stheta,ctheta * sphi,ctheta * cphi];
end
