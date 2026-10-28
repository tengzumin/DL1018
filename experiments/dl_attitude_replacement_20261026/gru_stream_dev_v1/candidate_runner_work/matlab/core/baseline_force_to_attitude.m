function [thrust,euler,limited]=baseline_force_to_attitude(acceleration,yaw,P)
    % FUNCTION:
    %   baseline_force_to_attitude
    % PURPOSE:
    %   将期望惯性系加速度与偏航角转换为推力和欧拉姿态命令，并报告倾角限制状态。
    % INPUT:
    %   acceleration: 期望惯性系加速度。
    %   yaw: 参考偏航角。
    %   P: Plant 参数结构。
    % OUTPUT:
    %   thrust: 期望总推力。
    %   euler: 期望欧拉姿态。
    %   limited: 是否触发姿态倾角限制。
    %BASELINE_FORCE_TO_ATTITUDE Strict ZYX force-direction adapter shared by baselines.
    specific=acceleration(:)+[0;0;P.g];
    A=cos(yaw)*specific(1)+sin(yaw)*specific(2);
    B=sin(yaw)*specific(1)-cos(yaw)*specific(2);
    euler=[atan2(B,hypot(specific(3),A));atan2(A,specific(3));yaw];
    tilt=hypot(euler(1),euler(2));
    limited=tilt>P.limits.max_tilt;
    if limited, euler(1:2)=euler(1:2)*P.limits.max_tilt/tilt;
    end
    thrust=P.mass*norm(specific);
end
