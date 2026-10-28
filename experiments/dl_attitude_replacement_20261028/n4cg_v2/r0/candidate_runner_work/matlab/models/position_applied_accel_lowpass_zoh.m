function [y,alpha] = position_applied_accel_lowpass_zoh(x,u,dt,tau)
% Exact first-order low-pass update for a zero-order-held event input.
x=double(x(:));u=double(u(:));dt=double(dt);tau=double(tau);
assert(numel(x)==3&&numel(u)==3&&all(isfinite([x;u]))&&isscalar(dt)&& ...
    isfinite(dt)&&dt>0&&isscalar(tau)&&isfinite(tau)&&tau>0, ...
    'PositionLPF:Input','State/input must be finite 3-vectors and dt/tau positive seconds.');
alpha=-expm1(-dt/tau);
y=x+alpha*(u-x);
assert(isscalar(alpha)&&alpha>0&&alpha<1&&all(isfinite(y)), ...
    'PositionLPF:Output','Exact ZOH low-pass update is invalid.');
end
