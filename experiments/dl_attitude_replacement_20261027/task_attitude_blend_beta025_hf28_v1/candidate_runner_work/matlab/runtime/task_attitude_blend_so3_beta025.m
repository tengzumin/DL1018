function [targetMixed,taskEuler] = task_attitude_blend_so3_beta025(targetPosition,referenceAcceleration,referenceYaw,P)
% Fixed deployable beta=0.25 SO(3) interpolation toward the trajectory task attitude.
% Inputs use only the position-loop target and same-step external trajectory reference.
beta=0.25;
targetPosition=double(targetPosition(:));
referenceAcceleration=double(referenceAcceleration(:));
assert(numel(targetPosition)==3&&numel(referenceAcceleration)==3&& ...
    all(isfinite(targetPosition))&&all(isfinite(referenceAcceleration))&& ...
    isscalar(referenceYaw)&&isfinite(referenceYaw), ...
    'TaskBlend:Input','Invalid target or trajectory reference.');
[~,taskEuler]=baseline_force_to_attitude(referenceAcceleration,double(referenceYaw),P);
qPosition=euler_zyx_quaternion(targetPosition);
qTask=euler_zyx_quaternion(taskEuler);
if dot(qPosition,qTask)<0,qTask=-qTask;end
qRelative=quat_multiply(quat_conjugate(qPosition),qTask);
qRelative=qRelative/max(norm(qRelative),eps);
v=qRelative(2:4);vNorm=norm(v);
if vNorm<1e-12
    qStep=[1;0;0;0];
else
    theta=2*atan2(vNorm,max(qRelative(1),0));
    qStep=[cos(beta*theta/2);sin(beta*theta/2)*v/vNorm];
end
qMixed=quat_multiply(qPosition,qStep);
qMixed=qMixed/max(norm(qMixed),eps);
targetMixed=quaternion_zyx_euler(qMixed);
end

function q=euler_zyx_quaternion(euler)
roll=euler(1);pitch=euler(2);yaw=euler(3);
cr=cos(roll/2);sr=sin(roll/2);
cp=cos(pitch/2);sp=sin(pitch/2);
cy=cos(yaw/2);sy=sin(yaw/2);
q=[cr*cp*cy+sr*sp*sy; ...
   sr*cp*cy-cr*sp*sy; ...
   cr*sp*cy+sr*cp*sy; ...
   cr*cp*sy-sr*sp*cy];
q=q/max(norm(q),eps);
end

function q=quat_conjugate(p)
q=[p(1);-p(2:4)];
end

function q=quat_multiply(a,b)
q=[a(1)*b(1)-dot(a(2:4),b(2:4)); ...
   a(1)*b(2:4)+b(1)*a(2:4)+cross(a(2:4),b(2:4))];
end

function euler=quaternion_zyx_euler(q)
w=q(1);x=q(2);y=q(3);z=q(4);
roll=atan2(2*(w*x+y*z),1-2*(x*x+y*y));
pitch=asin(max(-1,min(1,2*(w*y-z*x))));
yaw=atan2(2*(w*z+x*y),1-2*(y*y+z*z));
euler=[roll;pitch;yaw];
end
