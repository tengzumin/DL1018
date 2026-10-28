function s=composite_metrics(L,scene,release)
X=double(L.state);t=double(L.time(:));
assert(size(X,1)==20001&&L.last_transition==20000&&all(isfinite(X(:))));
positionError=X(:,1:3)-double(scene.reference.position);acc=double(scene.reference.acceleration);
acc(:,3)=acc(:,3)+double(release.gravity_mps2);yaw=double(scene.reference.yaw(:));
A=cos(yaw).*acc(:,1)+sin(yaw).*acc(:,2);B=sin(yaw).*acc(:,1)-cos(yaw).*acc(:,2);
roll=atan2(B,hypot(acc(:,3),A));pitch=atan2(A,acc(:,3));
tilt=min(1,double(release.max_tilt_rad)./max(hypot(roll,pitch),eps));
outer=angle_error(X(:,7:9),[roll.*tilt,pitch.*tilt,yaw]);
inner=angle_error(X(1:20000,7:9),double(L.filtered_attitude_reference));
s=struct('Q_m',sqrt(mean(sum(positionError.^2,2))),'SO3_rad',sqrt(mean(outer.^2)), ...
    'inner_tracking_rad',sqrt(mean(inner.^2)),'RMSE_xyz_m',sqrt(mean(positionError.^2,1)), ...
    'motor_saturation_samples',nnz(any(L.motor_saturated,2)), ...
    'generalized_clip_samples',nnz(any(L.generalized_clipped,2)), ...
    'peak_position_error_m',max(vecnorm(positionError,2,2)),'peak_SO3_rad',max(outer), ...
    'Q_0_5_m',sqrt(mean(sum(positionError(t<5,:).^2,2))), ...
    'Q_15_20_m',sqrt(mean(sum(positionError(t>=15,:).^2,2))));
end

function theta=angle_error(a,b)
qa=quat(double(a));qb=quat(double(b));theta=2*acos(min(1,abs(sum(qa.*qb,2))));
end

function q=quat(e)
c=cos(e/2);s=sin(e/2);
q=[c(:,1).*c(:,2).*c(:,3)+s(:,1).*s(:,2).*s(:,3), ...
    s(:,1).*c(:,2).*c(:,3)-c(:,1).*s(:,2).*s(:,3), ...
    c(:,1).*s(:,2).*c(:,3)+s(:,1).*c(:,2).*s(:,3), ...
    c(:,1).*c(:,2).*s(:,3)-s(:,1).*s(:,2).*c(:,3)];
end
