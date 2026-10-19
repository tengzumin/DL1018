function m=measure_pcf_dl1018(log,scene,W0)
% Metrics mirror the frozen V3 evaluator, adding full controller-call timing.
n=min(numel(log.transition_time),size(log.state,1)-1);
t=double(log.transition_time(1:n));x=double(log.state(1:n,:));
e=double(log.reference.position(1:n,:))-x(:,1:3);
att=wrap_local(double(log.filtered_attitude_reference(1:n,:))-x(:,7:9));
q=t>=5&t<20;full=t>=0&t<20;early=t>=0&t<5;
P=phase_local(scene,t);dynamic=(P.extend|P.retract)&q;
motor=double(log.motor_command(1:n,:));
sat=mean(any(log.motor_saturated(1:n,:),2),'omitnan');
clip=mean(any(log.generalized_clipped(1:n,:),2),'omitnan');
tv=sum(abs(diff(motor,1,1)),'all')/(4*1900*20);
axisAngle=acos(max(-1,min(1,sum(axis_z_local(x(:,7:9)).* ...
    axis_z_local(double(log.raw_outer_attitude(1:n,:))),2))));
controllerMs=1000*double(log.controller_call_time_s(1:n));
assert(isfield(log,'position_event_flag')&&isfield(log,'attitude_event_flag'), ...
    'DL1018:JointEventTiming','Position and attitude event flags are required for joint-event timing.');
jointEvent=logical(log.position_event_flag(1:n))|logical(log.attitude_event_flag(1:n));
validController=controllerMs(jointEvent&isfinite(controllerMs));
validLoop=controllerMs(isfinite(controllerMs));
if isempty(validController),controllerP99=NaN;controllerWorst=NaN;
else,controllerP99=prctile(validController,99);controllerWorst=max(validController);end
if isempty(validLoop),loopP99=NaN;loopWorst=NaN;
else,loopP99=prctile(validLoop,99);loopWorst=max(validLoop);end
validEvents=0;scheduled=0;reset=NaN;dtMedian=NaN;weightTV=NaN;
if isfield(log,'stage1_position_event_inference_valid')
    validEvents=sum(log.stage1_position_event_inference_valid(:));
    scheduled=sum(log.stage1_position_event(:));
    reset=norm(double(log.stage1_position_weight_initial)-double(W0),'fro');
    z=double(log.stage1_position_effective_update_dt_s(:));z=z(isfinite(z)&z>0);
    if ~isempty(z),dtMedian=median(z);end
    W=double(log.stage1_position_event_weight_after_33x3);
    if size(W,3)>1
        weightTV=sum(arrayfun(@(j)norm(W(:,:,j+1)-W(:,:,j),'fro'),1:size(W,3)-1))/20;
    end
end
rmse=@(z,mask) local_rmse(z,mask);
m=struct('status',string(log.status),'transitions',n, ...
    'complete',strcmpi(char(log.status),'STABLE')&&n==20000, ...
    'finite',all(isfinite([x(:);e(:);att(:);axisAngle(:);motor(:)])), ...
    'Q_5_20_m',rmse(e,q),'Q_0_20_m',rmse(e,full),'Q_0_5_m',rmse(e,early), ...
    'peak_5_20_m',local_peak(e,q),'end_error_m',norm(e(end,:)), ...
    'dynamic_Q_5_20_m',rmse(e,dynamic), ...
    'attitude_RMSE_0_20_rad',rmse(att,full),'attitude_RMSE_5_20_rad',rmse(att,q), ...
    'yaw_peak_abs_rad',max(abs(att(:,3)),[],'omitnan'), ...
    'thrust_axis_RMSE_rad',sqrt(mean(axisAngle.^2,'omitnan')), ...
    'motor_saturation_fraction',sat,'generalized_clip_fraction',clip, ...
    'motor_TV_normalized_per_s',tv,'controller_p99_ms',controllerP99, ...
    'controller_worst_ms',controllerWorst,'control_loop_p99_ms',loopP99, ...
    'control_loop_worst_ms',loopWorst,'joint_event_count',nnz(jointEvent),'scheduled_events',scheduled, ...
    'valid_inference_events',validEvents,'effective_update_dt_median_s',dtMedian, ...
    'weight_reset_fro_error',reset,'weight_matrix_TV_per_s',weightTV, ...
    'eta_abs_max_mps',max(abs(double(field_or(log,'stage1_position_pcf_eta_after_mps',nan(n,3)))),[],'all','omitnan'), ...
    'rf_abs_max_mps2',max(abs(double(field_or(log,'stage1_position_pcf_r_f_mps2',nan(n,3)))),[],'all','omitnan'));
end
function v=local_rmse(e,mask)
if any(mask),v=sqrt(mean(sum(e(mask,:).^2,2),'omitnan'));else,v=NaN;end
end
function v=local_peak(e,mask)
if any(mask),v=max(vecnorm(e(mask,:),2,2),[],'omitnan');else,v=NaN;end
end
function P=phase_local(s,t)
n=numel(t);P=struct('extend',false(n,1),'retract',false(n,1));
cmd=double(s.arms.command);rho=double(s.arms.rho_true);dt=median(diff(double(s.time(:))));
for i=1:n
    k=max(1,min(size(cmd,1),round(t(i)/dt)+1));
    P.extend(i)=any(cmd(k,:)>0);P.retract(i)=any(cmd(k,:)<0);
end
end
function x=wrap_local(x),x=atan2(sin(x),cos(x));end
function z=axis_z_local(e)
p=e(:,1);t=e(:,2);z=[cos(p).*sin(t),-sin(p),cos(p).*cos(t)];
z=z./max(vecnorm(z,2,2),eps);
end
function x=field_or(s,n,d)
if isfield(s,n),x=s.(n);else,x=d;end
end
