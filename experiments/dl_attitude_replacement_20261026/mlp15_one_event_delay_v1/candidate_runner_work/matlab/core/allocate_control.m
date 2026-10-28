function [motorSpeed,actualGeneralized,info] = allocate_control(command,Pcontroller,Pplant,previousMotor)
    % FUNCTION:
    %   将控制器请求的广义推力/力矩转换为四个电机转速命令。
    % PURPOSE:
    %   先按 controller 限制裁剪请求，再使用 controller allocation 求解平方转速，并按 Plant 电机界限饱和。
    % INPUT: command 为 [推力; 机体系三轴力矩]；Pcontroller/Pplant 分别提供名义控制分配与真实 Plant 执行器约束。
    % OUTPUT: motorSpeed 为电机转速；actualGeneralized 为按 Plant 分配矩阵得到的实际广义输入；info 记录限幅和模型不匹配。
    % NOTE: previousMotor 当前仅为接口兼容输入，函数本身不使用它。
    %ALLOCATE_CONTROL Formal four-argument allocation interface.
    if nargin < 4,previousMotor = [];
    end %#ok<NASGU>
    assert(isstruct(Pcontroller) && isfield(Pcontroller,'allocation') && isfield(Pcontroller.allocation,'C'), ...
        'TCN0901:ControllerContract','Pcontroller.allocation.C is required.');
    assert(isstruct(Pplant) && isfield(Pplant,'allocation') && isfield(Pplant.allocation,'C'), ...
        'TCN0901:PlantContract','Pplant.allocation.C is required.');
    requested = command(:);
    applied = min(max(requested,Pcontroller.limits.generalized_min),Pcontroller.limits.generalized_max);
    motorSquared = Pcontroller.allocation.C \ applied;
    motor = sqrt(max(motorSquared,0));
    motor = min(max(motor,Pplant.limits.motor_min),Pplant.limits.motor_max);
    tol = 1e-9;
    motorLimited = motor <= Pplant.limits.motor_min + tol | motor >= Pplant.limits.motor_max - tol | motorSquared < 0;
    motorSpeed = motor;
    actualGeneralized = Pplant.allocation.C * motor .^ 2;
    info.motor_saturated = motorLimited;
    info.generalized_command_clipped = abs(requested - applied) > tol;
    info.generalized_saturated = info.generalized_command_clipped;
    info.requested_generalized = requested;
    info.clipped_generalized = applied;
    info.motor_squared_requested = motorSquared;
    info.motor_squared_negative = motorSquared < -tol;
    info.motor_squared_above_max = motorSquared > Pplant.limits.motor_max^2 + tol;
    info.motor_squared_physically_infeasible = ...
        info.motor_squared_negative | info.motor_squared_above_max;
    info.motor_squared_applied = motor .^ 2;
    info.motor_command = motor;
    info.motor_amplitude_limited = motorLimited;
    info.actuator_tracking_error = zeros(size(motor));
    info.wrench_tracking_error = actualGeneralized - command(:);
    info.thrust_tracking_error = info.wrench_tracking_error(1);
    info.moment_tracking_error = info.wrench_tracking_error(2:4);
    info.allocation_model_mismatch = Pplant.allocation.C - Pcontroller.allocation.C;
    info.C_controller = Pcontroller.allocation.C;
    info.C_plant = Pplant.allocation.C;
    info.controller_morphology_mode = Pcontroller.morphology_mode;
end
