function [E,meta]=attitude_events_v311(log,scene,cfg,teacher,split)
% Rebuild lawful X29 and physical angular-acceleration residuals at attitude events.
repoRoot=fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
addpath(fullfile(repoRoot,'RBF-BS0','code','code'), ...
    fullfile(repoRoot,'RBF-BS0','experiments','attitude_kan_legal_input_reuse_upgrade_v3_6','local_runtime'));
assert(isfield(log,'rbf_update_flag')&&isfield(log,'requested_generalized')&& ...
    isfield(log,'realized_generalized')&&isfield(log,'attitude_rbf_compensation_torque_Nm')&& ...
    isfield(log,'wind_force_I')&&isfield(log,'wind_torque_B')&&isfield(log,'motor_setpoint'), ...
    'V311:AttitudeLogFields','Required attitude teacher log fields are missing.');
eventMask=logical(log.rbf_update_flag(:));idx=find(eventMask);
assert(~isempty(idx)&&numel(log.transition_time)==size(log.state,1)-1, ...
    'V311:AttitudeEvents','Attitude event schedule or Plant log lengths are invalid.');
time=double(log.transition_time(:));assert(all(diff(time)>0),'V311:EventOrder','Attitude event times are not strictly increasing.');
Pp=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));P=controller_parameters(cfg,Pp,'fixed');
N=numel(idx);X=zeros(N,29);raw=zeros(N,3);clip=raw;normalized=raw;
closureTorque=0;closureDynamics=0;filterEuler=0;filterRate=0;
filter=command_filter_init(double(log.state(1,7:9)).');lastSetpoint=zeros(4,1);eventPos=0;
dmax=double(cfg.rbf.attitude.dmax(:));
for k=1:numel(time)
    irTarget=double(log.raw_outer_attitude(k,:)).';
    [ir,filter]=command_filter_step(irTarget,filter,P);
    filterEuler=max(filterEuler,max(abs(ir.euler(:)-double(log.filtered_attitude_reference(k,:)).')));
    filterRate=max(filterRate,max(abs(ir.euler_rate(:)-double(log.filtered_attitude_rate(k,:)).')));
    if ~eventMask(k),continue;end
    eventPos=eventPos+1;x=double(log.state(k,:)).';
    [~,ai0]=attitude_bs_step(x,ir,zeros(3,1),P);
    X(eventPos,:)=attitude_feature_row_v3_6(ai0,x,ir, ...
        double(log.requested_generalized(k,1)),lastSetpoint,zeros(0,1), ...
        cfg.plant.mass,cfg.plant.limits.motor_max,29).';
    tauBehavior=double(log.attitude_rbf_compensation_torque_Nm(k,:)).';
    tauVirtual=double(ai0.nominal_moment(:))-tauBehavior;
    tauRequested=double(log.requested_generalized(k,2:4)).';
    closureTorque=max(closureTorque,max(abs(tauRequested-tauVirtual)));
    omega=x(10:12);Jdot=double(ai0.inertia_dot_for_bs);
    omegaDotVirtual=P.inertia\(tauVirtual-cross(omega,P.inertia*omega)-Jdot*omega);
    Ptrue=simulation_parameters(cfg,double(scene.arms.rho_true(k,:)).',double(scene.arms.rhoDot_true(k,:)).');
    dx=vehicle_derivative(x,double(log.realized_generalized(k,:)).', ...
        double(log.wind_force_I(k,:)).',double(log.wind_torque_B(k,:)).',Ptrue);
    omegaDotTrue=dx(10:12);
    omegaDotDirect=Ptrue.inertia\(double(log.realized_generalized(k,2:4)).'+ ...
        double(log.wind_torque_B(k,:)).'-cross(omega,Ptrue.inertia*omega)-Ptrue.inertia_dot*omega);
    closureDynamics=max(closureDynamics,max(abs(omegaDotTrue-omegaDotDirect)));
    raw(eventPos,:)=(omegaDotTrue-omegaDotVirtual).';
    clip(eventPos,:)=min(max(raw(eventPos,:),-dmax.'),dmax.');
    normalized(eventPos,:)=clip(eventPos,:)./dmax.';
    lastSetpoint=double(log.motor_setpoint(k,:)).';
end
assert(eventPos==N&&filterEuler<=1e-10&&filterRate<=1e-10&& ...
    closureTorque<=1e-8&&closureDynamics<=1e-8, ...
    'V311:AttitudeLabelClosure','Feature replay or physical attitude-label closure failed.');
assert(all(isfinite([X(:);raw(:);clip(:);normalized(:)])), ...
    'V311:AttitudeFinite','Attitude labels contain non-finite values.');
phase=strings(N,1);rho=double(scene.arms.rho_true);cmd=double(scene.arms.command);
for q=1:N
    k=idx(q);
    if any(cmd(k,:)>0)
        phase(q)="EXTEND";
    elseif any(cmd(k,:)<0)
        phase(q)="RETRACT";
    elseif any(rho(k,:)>.150001)
        phase(q)="HOLD";
    elseif any(any(abs(cmd(1:k,:))>0))
        phase(q)="RECOVERY";
    else
        phase(q)="NONE";
    end
end
E=table();E.scene_id=repmat(string(scene.scene_id),N,1);E.split=repmat(string(split),N,1);
E.teacher=repmat(string(teacher),N,1);E.event_index=(1:N).';E.plant_index=idx;E.event_time_s=time(idx);
E.ready=E.event_index>=32;E.phase=phase;E.target_raw_1=raw(:,1);E.target_raw_2=raw(:,2);E.target_raw_3=raw(:,3);
E.target_clip_1=clip(:,1);E.target_clip_2=clip(:,2);E.target_clip_3=clip(:,3);
E.target_normalized_1=normalized(:,1);E.target_normalized_2=normalized(:,2);E.target_normalized_3=normalized(:,3);
for j=1:29,E.(sprintf('x29_%d',j))=X(:,j);end
meta=struct('event_count',N,'ready_count',nnz(E.ready),'eligible_for_32_event_windows',N>=32, ...
    'max_filter_euler_replay_error_rad',filterEuler,'max_filter_rate_replay_error_rad_s',filterRate, ...
    'max_requested_torque_closure_Nm',closureTorque,'max_dynamics_closure_rads2',closureDynamics);
end
