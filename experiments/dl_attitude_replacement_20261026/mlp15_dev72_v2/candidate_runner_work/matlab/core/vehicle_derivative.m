function derivative = vehicle_derivative(state, generalizedInput, force, torque, P)
    % FUNCTION:
    %   计算四旋翼刚体六自由度动力学的状态导数。
    % PURPOSE:
    %   将推力、力矩、外部风载和时变惯量代入平动与转动方程，供积分器推进 Plant 状态。
    % INPUT:
    %   state: [位置_I; 速度_I; ZYX欧拉角; 机体系角速度]，长度和速度单位为 m、m/s，角量为 rad、rad/s。
    %   generalizedInput: [总推力; 机体系滚转/俯仰/偏航力矩]，单位为 N、N*m。
    %   force: 惯性系外力，单位为 N；torque: 机体系外力矩，单位为 N*m。
    %   P: 角色为 plant 的模型参数，包含该动力学模型的质量、惯量、重力和惯量变化率。
    % OUTPUT:
    %   derivative: 与 state 同序的状态导数；位置导数为惯性系速度。
    % NOTE:
    %   state 的位置参考点由 Plant 契约定义；真实 Plant 与名义动力学评估均可复用此方程，控制器输入另由数据契约限制。
    %VEHICLE_DERIVATIVE Rigid-body 6-DOF model with ZYX Euler coordinates.

    assert(isstruct(P) && isfield(P,'role') && strcmp(P.role,'plant'), ...
        'TCNNEW:PlantContract', 'vehicle_derivative requires P_plant.');
    if isfield(P,'mass_model') && strcmpi(char(string(P.mass_model)),'distributed_v1')
        assert(isfield(P,'state_position_reference') && ...
            strcmp(char(string(P.state_position_reference)), ...
            'instantaneous_total_cog'), 'TCNNEW:StateReferenceContract', ...
            'distributed_v1 state must be referenced to instantaneous total CoG.');
    end

    velocity = state(4:6);
    eta = state(7:9);
    omega = state(10:12);
    R = rotation_zyx(eta);

    acceleration = R * [0;0;generalizedInput(1)] / P.mass - ...
        [0;0;P.g] + force(:) / P.mass;
    etaRate = euler_rate(eta, omega);
    moment = generalizedInput(2:4) + torque(:);
    omegaDot = P.inertia \ (moment - cross(omega,P.inertia * omega) - ...
        P.inertia_dot * omega);

    derivative = [velocity;acceleration;etaRate;omegaDot];
end

function R = rotation_zyx(eta)
    % FUNCTION:
    %   构造 ZYX 欧拉角对应的机体系到惯性系旋转矩阵。
    % INPUT: eta 为 [roll; pitch; yaw]，单位 rad。
    % OUTPUT: R 将机体系向量变换到惯性系。
    phi = eta(1);
    theta = eta(2);
    psi = eta(3);
    cphi = cos(phi);
    sphi = sin(phi);
    ctheta = cos(theta);
    stheta = sin(theta);
    cpsi = cos(psi);
    spsi = sin(psi);
    R = [cpsi * ctheta, cpsi * stheta * sphi - spsi * cphi, cpsi * stheta * cphi + spsi * sphi; ...
        spsi * ctheta, spsi * stheta * sphi + cpsi * cphi, spsi * stheta * cphi - cpsi * sphi; ...
        -stheta,      ctheta * sphi,                   ctheta * cphi];
end

function rate = euler_rate(eta,omega)
    % FUNCTION:
    %   将机体系角速度映射为 ZYX 欧拉角速度。
    % INPUT: eta 为 ZYX 欧拉角（rad），omega 为机体系角速度（rad/s）。
    % OUTPUT: rate 为 [roll_dot; pitch_dot; yaw_dot]（rad/s）。
    % NOTE: pitch 在奇异点附近限幅，以避免欧拉运动学矩阵发散。
    phi = eta(1);
    theta = max(min(eta(2),pi / 2 - 1e-4),-pi / 2 + 1e-4);
    T = [1,sin(phi) * tan(theta),cos(phi) * tan(theta); ...
        0,cos(phi),-sin(phi); ...
        0,sin(phi) / cos(theta),cos(phi) / cos(theta)];
    rate = T * omega;
end
