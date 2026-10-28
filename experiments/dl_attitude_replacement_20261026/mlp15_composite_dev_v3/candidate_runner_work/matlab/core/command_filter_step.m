function [reference, nextState, requestedAcceleration] = command_filter_step(targetEuler, state, P)
    % FUNCTION:
    %   对目标欧拉角执行共享的二阶姿态命令滤波。
    % PURPOSE:
    %   依据角度误差、自然频率和阻尼计算受限角加速度，并离散推进滤波器状态。
    % INPUT: targetEuler 为目标 ZYX 欧拉角（rad）；state 保存当前角度/角速度；P 提供 dt、wn、阻尼和加速度限值。
    % OUTPUT: reference 含滤波角度、角速度及期望角加速度；nextState 为下一采样时刻滤波器状态。
    %COMMAND_FILTER_STEP Causal second-order filter shared by every controller.

    targetEuler = targetEuler(:);
    error = atan2(sin(targetEuler - state.euler),cos(targetEuler - state.euler));
    wn = P.command_filter.wn(:);
    zeta = P.command_filter.damping(:);
    requestedAcceleration = wn .^ 2 .* error - 2 * zeta .* wn .* state.rate;
    limit = P.command_filter.acceleration_limit(:);
    acceleration = min(max(requestedAcceleration,-limit),limit);

    reference.euler = state.euler;
    reference.euler_rate = state.rate;
    reference.euler_acceleration = acceleration;

    nextState.rate = state.rate + P.dt * acceleration;
    nextState.euler = state.euler + P.dt * nextState.rate;
    nextState.euler = atan2(sin(nextState.euler),cos(nextState.euler));
end
