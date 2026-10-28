function nextState = rk4_vehicle_step(state, generalizedInput, force, torque, P)
    % FUNCTION:
    %   使用经典四阶 Runge-Kutta 方法执行一次固定步长 Plant 积分。
    % PURPOSE:
    %   在一个 P.dt 时间步内多次评估 vehicle_derivative，降低显式积分的截断误差。
    % INPUT:
    %   state: 当前 12 维 Plant 状态；generalizedInput: 推力与机体系控制力矩。
    %   force: 惯性系外力（N）；torque: 机体系外力矩（N*m）；P: Plant 参数。
    % OUTPUT: nextState 为积分后的 12 维状态，并将偏航角折回主值区间。
    %RK4_VEHICLE_STEP One deterministic fixed-step RK4 plant update.

    h = P.dt;
    k1 = vehicle_derivative(state,generalizedInput,force,torque,P);
    k2 = vehicle_derivative(state + 0.5 * h * k1,generalizedInput,force,torque,P);
    k3 = vehicle_derivative(state + 0.5 * h * k2,generalizedInput,force,torque,P);
    k4 = vehicle_derivative(state + h * k3,generalizedInput,force,torque,P);
    nextState = state + h * (k1 + 2 * k2 + 2 * k3 + k4) / 6;
    nextState(9) = atan2(sin(nextState(9)),cos(nextState(9)));
end
