function [command, info] = position_bs_step(state, reference, residualForce, P)
    % FUNCTION:
    %   根据位置与速度反步误差生成期望推力、滚转角和俯仰角命令。
    % PURPOSE:
    %   由惯性系误差构造期望加速度与名义力，扣除残差力估计后映射为 ZYX 姿态命令。
    % INPUT: state 顺序为 [position_I; velocity_I; Euler_ZYX; omega_B]；reference 含位置、速度和加速度。
    %   姿态转换使用当前偏航角 state(9)；residualForce 为惯性系估计残差力（N）。
    %   P 提供质量、重力、BS 增益和倾角限制。
    % OUTPUT: command=[thrust_N; roll_rad; pitch_rad]；info 返回误差面、加速度及力补偿中间量。
    %POSITION_BS_STEP Backstepping outer loop with a force-level residual.
    % State order is [position; velocity; Euler angles; body rates].

    position = state(1:3);
    velocity = state(4:6);
    yaw = state(9);

    e = reference.position(:) - position;
    de = reference.velocity(:) - velocity;
    k1 = P.bs.position.k1(:);
    k2 = P.bs.position.k2(:);
    alpha = reference.velocity(:) + k1 .* e;
    z2 = alpha - velocity;

    aNominal = reference.acceleration(:) + k1 .* de + e + k2 .* z2;
    nominalForce = P.mass * aNominal;
    commandedForce = nominalForce - residualForce(:);
    specificForce = commandedForce / P.mass + [0; 0; P.g];

    % ZYX attitude command whose body z-axis follows the requested force.
    % specificForce 为重力补偿后的期望惯性系比力；姿态由机体推力轴对准该方向得到。
    horizontal = hypot(specificForce(1), specificForce(2));
    if norm(specificForce) < 1e-9
        rollCommand = 0;
        pitchCommand = 0;
    else
        pitchCommand = atan2(cos(yaw) * specificForce(1) + ...
            sin(yaw) * specificForce(2), specificForce(3));
        rollCommand = atan2(sin(yaw) * specificForce(1) - ...
            cos(yaw) * specificForce(2), hypot(specificForce(3), horizontal));
    end

    tilt = hypot(rollCommand, pitchCommand);
    if tilt > P.limits.max_tilt
        scale = P.limits.max_tilt / tilt;
        rollCommand = scale * rollCommand;
        pitchCommand = scale * pitchCommand;
    end

    thrust = P.mass * norm(specificForce);
    command = [thrust; rollCommand; pitchCommand];

    info.error = e;
    info.rate_error = de;
    info.surface = z2;
    info.nominal_acceleration = aNominal;
    info.commanded_acceleration = commandedForce / P.mass;
    info.nominal_force = nominalForce;
    info.commanded_force = commandedForce;
    info.residual_force = residualForce(:);
    info.estimate = residualForce(:); % compatibility field; canonical unit is N.
    info.estimate_acceleration = residualForce(:) / P.mass;
end
