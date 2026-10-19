function metrics=final_metrics_v311(log,scene,spec,core,BQ,BA,BPeak,Bcomplete)
% Reduce one saved/returned Plant log to the preregistered V311 metrics.
n=min(numel(log.transition_time),size(log.state,1)-1);
t=double(log.transition_time(1:n));x=double(log.state(1:n,:));mask=t>=0&t<20;
e=double(log.reference.position(1:n,:))-x(:,1:3);
att=atan2(sin(double(log.filtered_attitude_reference(1:n,:))-x(:,7:9)), ...
    cos(double(log.filtered_attitude_reference(1:n,:))-x(:,7:9)));
motor=double(log.motor_command(1:n,:));em=vecnorm(e,2,2);
axisQ=sqrt(mean(e(mask,:).^2,1));axisA=sqrt(mean(att(mask,:).^2,1));
if isempty(motor)
    maxStep=NaN;stepTime=NaN;
else
    dm=abs(diff(motor,1,1));
    if isempty(dm)
        maxStep=0;stepTime=NaN;
    else
        [maxStep,ix]=max(dm(:));[ii,~]=ind2sub(size(dm),ix);stepTime=t(ii);
    end
end
phase=phase_labels(scene,t);phaseRows=struct([]);
for ph=unique(phase,'stable').'
    m=mask&phase==ph;
    if ~any(m),continue;end
    z=struct('phase',char(ph),'samples',nnz(m),'Q_rmse_m',sqrt(mean(sum(e(m,:).^2,2))), ...
        'position_peak_m',max(em(m)),'position_p95_m',prctile(em(m),95), ...
        'A_rmse_rad',sqrt(mean(sum(att(m,:).^2,2))),'yaw_peak_abs_rad',max(abs(att(m,3))));
    if isempty(phaseRows),phaseRows=z;else,phaseRows(end+1,1)=z;end %#ok<AGROW>
end
sceneDt=median(diff(double(scene.time(:))));
windIndex=max(1,min(size(scene.environment_wind_I,1),round(t/sceneDt)+1));
wind=double(scene.environment_wind_I(windIndex,:));
windSpeed=vecnorm(wind,2,2);wf=double(log.wind_force_I(1:n,:));wt=double(log.wind_torque_B(1:n,:));
ws=vecnorm(wf,2,2);ts=vecnorm(wt,2,2);
headFro=0;headProjection=0;headSaturated=0;headUpdates=0;
if isfield(log,'attitude_head_deltaW_norm')
    headFro=max(double(log.attitude_head_deltaW_norm(:)),[],'omitnan');
    if isempty(headFro)||~isfinite(headFro),headFro=0;end
end
if isfield(log,'attitude_head_event_audit')
    audit=log.attitude_head_event_audit;
    if isfield(audit,'projection'),headProjection=nnz(audit.projection);end
    if isfield(audit,'saturated'),headSaturated=nnz(audit.saturated);end
    if isfield(audit,'update_norm'),headUpdates=nnz(double(audit.update_norm)>0);end
end
positionHeadFro=0;positionHeadProjection=0;positionHeadSaturation=0;positionHeadUpdates=0;
if isfield(log,'stage1_position_event')
    positionEvent=logical(log.stage1_position_event(1:n));
    if isfield(log,'stage1_position_weight_norm')
        positionHeadFro=max(double(log.stage1_position_weight_norm(positionEvent)),[],'omitnan');
        if isempty(positionHeadFro)||~isfinite(positionHeadFro),positionHeadFro=0;end
    end
    if isfield(log,'stage1_position_event_projection')
        projectionPosition=double(log.stage1_position_event_projection(1:n));
        positionHeadProjection=nnz(positionEvent&isfinite(projectionPosition)&projectionPosition~=0);
    end
    if isfield(log,'stage1_position_event_raw_acceleration_mps2')
        rawPosition=double(log.stage1_position_event_raw_acceleration_mps2(1:n,:));
        positionHeadSaturation=nnz(any(abs(rawPosition(positionEvent,:))>3+1e-9,2));
    end
    if isfield(log,'stage1_position_event_weight_delta_fro')
        deltaPosition=double(log.stage1_position_event_weight_delta_fro(1:n));
        positionHeadUpdates=nnz(positionEvent&deltaPosition>0);
    end
end
metrics=struct('status',char(log.status),'complete',logical(core.complete),'finite',logical(core.finite), ...
    'transitions',double(core.transitions),'Q_0_20_m',sqrt(mean(sum(e(mask,:).^2,2))), ...
    'Q_5_20_m',double(core.Q_5_20_m),'position_peak_m',max(em(mask)), ...
    'position_p95_m',prctile(em(mask),95),'position_axis_rmse_m',axisQ, ...
    'A_0_20_rad',sqrt(mean(sum(att(mask,:).^2,2))),'attitude_axis_rmse_rad',axisA, ...
    'yaw_peak_abs_rad',max(abs(att(mask,3))),'motor_TV_normalized_per_s',double(core.motor_TV_normalized_per_s), ...
    'max_motor_step_rad_s',double(maxStep),'max_motor_step_time_s',double(stepTime), ...
    'motor_saturation_fraction',double(core.motor_saturation_fraction), ...
    'generalized_clip_fraction',double(core.generalized_clip_fraction), ...
    'motor_min_rad_s',min(motor,[],'all'),'motor_max_rad_s',max(motor,[],'all'), ...
    'controller_p99_ms',double(core.controller_p99_ms),'controller_worst_ms',double(core.controller_worst_ms), ...
    'head_max_fro',double(headFro),'head_projection_count',double(headProjection), ...
    'head_saturation_freeze_count',double(headSaturated),'head_update_count',double(headUpdates), ...
    'position_head_max_fro',double(positionHeadFro), ...
    'position_head_projection_count',double(positionHeadProjection), ...
    'position_head_output_saturation_count',double(positionHeadSaturation), ...
    'position_head_update_count',double(positionHeadUpdates), ...
    'wind_speed_rms_mps',sqrt(mean(windSpeed.^2)),'wind_speed_peak_mps',max(windSpeed), ...
    'wind_force_rms_N',sqrt(mean(ws.^2)),'wind_force_peak_N',max(ws), ...
    'wind_force_dominant_hz',dominant_frequency(ws,t(1:numel(ws))), ...
    'wind_torque_rms_Nm',sqrt(mean(ts.^2)),'wind_torque_peak_Nm',max(ts), ...
    'wind_torque_dominant_hz',dominant_frequency(ts,t(1:numel(ts))), ...
    'wind_input_f1_hz',double(spec.f1_hz),'wind_input_f2_hz',double(spec.f2_hz), ...
    'relative_Q_improvement_vs_B',NaN,'relative_A_improvement_vs_B',NaN, ...
    'paired_scene_valid',false,'phase_metrics_json',jsonencode(phaseRows), ...
    'safety_stop_reason',char(field_or(log,'safety_stop_reason','')));
if Bcomplete&&metrics.complete&&metrics.finite
    metrics.relative_Q_improvement_vs_B=safe_improvement(BQ,metrics.Q_0_20_m);
    metrics.relative_A_improvement_vs_B=safe_improvement(BA,metrics.A_0_20_rad);
    metrics.paired_scene_valid=true;
end
if isfinite(BPeak),metrics.position_peak_B_m=BPeak;else,metrics.position_peak_B_m=NaN;end
end

function labels=phase_labels(scene,t)
cmd=double(scene.arms.command);rho=double(scene.arms.rho_true);
dt=median(diff(double(scene.time(:))));labels=strings(numel(t),1);
for i=1:numel(t)
    k=max(1,min(size(cmd,1),round(t(i)/dt)+1));
    if any(cmd(k,:)>0)
        labels(i)="EXTEND";
    elseif any(cmd(k,:)<0)
        labels(i)="RETRACT";
    elseif any(rho(k,:)>.150001)
        labels(i)="HOLD";
    elseif any(any(abs(cmd(1:k,:))>0))
        labels(i)="RECOVERY";
    else
        labels(i)="NONE";
    end
end
end

function f=dominant_frequency(y,t)
y=double(y(:));t=double(t(:));f=NaN;
if numel(y)<8||numel(y)~=numel(t),return;end
dt=median(diff(t));if ~isfinite(dt)||dt<=0,return;end
y=y-mean(y);N=numel(y);w=.5-.5*cos(2*pi*(0:N-1)'/(N-1));
z=abs(fft(y.*w));nFreq=floor(N/2)+1;z=z(1:nFreq);freq=(0:nFreq-1)'/(N*dt);
valid=freq>=.05&freq<=min(100,1/(2*dt));if ~any(valid),return;end
ids=find(valid);[power,k]=max(z(ids));if power<=eps,return;end;f=freq(ids(k));
end

function v=safe_improvement(base,candidate)
if ~isfinite(base)||abs(base)<eps,v=NaN;else,v=(base-candidate)/base;end
end

function x=field_or(s,name,default)
if isfield(s,name),x=s.(name);else,x=default;end
end
