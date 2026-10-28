function [moments, info] = attitude_bs_step(state, reference, estimateTorque, P)
    % FUNCTION:
    %   根据 ZYX 欧拉角及其角速度误差计算机体系三轴控制力矩。
    % PURPOSE:
    %   构造反步虚拟角加速度，转换为机体系角加速度后补偿陀螺耦合、时变惯量和估计残差力矩。
    % INPUT: state 含 Euler_ZYX（rad）和 omega_B（rad/s）；reference 含期望欧拉角及其一、二阶导数。
    %   estimateTorque 为机体系残差力矩估计（N*m）；P 提供 BS 增益、惯量及惯量导数。
    % OUTPUT: moments 为机体系 [Mx;My;Mz]（N*m）；info 返回误差面、运动学映射和名义力矩。
    %ATTITUDE_BS_STEP Backstepping attitude loop with torque-level compensation.

    eta = state(7:9);
    omega = state(10:12);
    [T,Tdot] = euler_kinematics(eta,omega);
    etaRate = T * omega;

    etaDesired = reference.euler(:);
    etaRateDesired = reference.euler_rate(:);
    etaAccelerationDesired = reference.euler_acceleration(:);
    e = wrap_angles(etaDesired - eta);
    de = etaRateDesired - etaRate;
    k1 = P.bs.attitude.k1(:);
    k2 = P.bs.attitude.k2(:);
    alpha = etaRateDesired + k1 .* e;
    z2 = alpha - etaRate;
    alphaDot = etaAccelerationDesired + k1 .* de;
    nominalAngularAcceleration = alphaDot + e + k2 .* z2;

    % The BS virtual acceleration is eta_ddot.  Plant dynamics integrate body
    % omega, for which eta_ddot=T*omega_dot+Tdot*omega.  Convert exactly before
    % forming a body moment; treating eta_ddot as omega_dot is only a small-angle
    % approximation and biases high-frequency/large-tilt cases.
    % 该映射保留 ZYX 欧拉运动学项，避免把欧拉角二阶导数直接当作机体系角加速度。
    nominalBodyAngularAcceleration = T \ (nominalAngularAcceleration - Tdot * omega);
    gyro = cross(omega, P.inertia * omega);
    inertiaDotForBS = P.inertia_dot;
    if isfield(P,'inertia_dot_for_bs')
        inertiaDotForBS = P.inertia_dot_for_bs;
    end
    nominalMoment = P.inertia * nominalBodyAngularAcceleration + gyro + ...
        inertiaDotForBS * omega;
    rawMoment = nominalMoment - estimateTorque(:);
    moments = rawMoment;

    info.error = e;
    info.rate_error = de;
    info.surface = z2;
    info.nominal_angular_acceleration = nominalAngularAcceleration;
    info.nominal_body_angular_acceleration = nominalBodyAngularAcceleration;
    info.euler_rate_map = T;
    info.euler_rate_map_dot = Tdot;
    info.nominal_moment = nominalMoment;
    info.inertia_dot_for_bs = inertiaDotForBS;
    info.raw_moment = rawMoment;
    info.estimate_torque = estimateTorque(:);
    info.euler_rate = etaRate;
end

function [T,Tdot] = euler_kinematics(eta,omega)
    % FUNCTION:
    %   计算 ZYX 欧拉角速度映射矩阵及其沿当前姿态运动的时间导数。
    % INPUT: eta 为欧拉角（rad），omega 为机体系角速度（rad/s）。
    % OUTPUT: T 满足 etaDot=T*omega；Tdot 用于 etaDDot=T*omegaDot+Tdot*omega。
    phi = eta(1);
    theta = max(min(eta(2), pi / 2 - 1e-4), -pi / 2 + 1e-4);
    T = [1, sin(phi) * tan(theta), cos(phi) * tan(theta); ...
        0, cos(phi),           -sin(phi); ...
        0, sin(phi) / cos(theta), cos(phi) / cos(theta)];
    etaRate = T * omega;
    phiDot = etaRate(1);
    thetaDot = etaRate(2);
    sphi = sin(phi);
    cphi = cos(phi);
    ttheta = tan(theta);
    sectheta = 1 / cos(theta);
    Tphi = [0,cphi * ttheta,-sphi * ttheta; ...
        0,-sphi,-cphi; ...
        0,cphi * sectheta,-sphi * sectheta];
    Ttheta = [0,sphi * sectheta ^ 2,cphi * sectheta ^ 2; ...
        0,0,0; ...
        0,sphi * sectheta * ttheta,cphi * sectheta * ttheta];
    Tdot = Tphi * phiDot + Ttheta * thetaDot;
end

function value = wrap_angles(value)
    % FUNCTION:
    %   将角度差映射到主值区间，避免跨越 ±pi 时产生虚假的大误差。
    % INPUT/OUTPUT: value 为以 rad 表示的角度或角度差数组。
    value = atan2(sin(value), cos(value));
end
