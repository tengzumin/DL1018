function state = command_filter_init(initialEuler)
    % FUNCTION:
    %   初始化共享的二阶姿态命令滤波器状态。
    % INPUT: initialEuler 为初始 ZYX 欧拉角（rad）。
    % OUTPUT: state 包含初始欧拉角和置零的欧拉角速度（rad/s）。
    %COMMAND_FILTER_INIT Initial state for the shared second-order command filter.
    state.euler = initialEuler(:);
    state.rate = zeros(3,1);
end
