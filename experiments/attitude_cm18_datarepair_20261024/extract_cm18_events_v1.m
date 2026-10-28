function events=extract_cm18_events_v1(cfg,scene,log)
% Reconstruct CM18 X18 and physical residual labels from in-memory inputs.
% This pure helper performs no file I/O, simulation, Plant calls, or model inference.
requiredLog={'time','transition_time','state','attitude_event_flag', ...
    'attitude_bs_nominal_torque_Nm','attitude_compensation_applied_torque_Nm', ...
    'requested_generalized','realized_generalized','wind_torque_B'};
assert(isstruct(log)&&all(isfield(log,requiredLog)), ...
    'CM18Extract:LogFields','Required transition and attitude-label log fields are missing.');
assert(isstruct(scene)&&all(isfield(scene,{'scene_id','time','arms'}))&& ...
    isstruct(scene.arms)&&all(isfield(scene.arms,{'command','rho_true','rhoDot_true'})), ...
    'CM18Extract:SceneFields','Scene identity/time and arm command/shape trajectories are required.');
assert(isstruct(cfg)&&isfield(cfg,'plant')&&isfield(cfg,'controller_morphology_mode')&& ...
    strcmpi(char(string(cfg.controller_morphology_mode)),'fixed'), ...
    'CM18Extract:FixedNominal','CM18 extraction requires the fixed nominal morphology controller.');
assert(isfield(cfg.plant,'mass')&&isscalar(cfg.plant.mass)&&isfinite(cfg.plant.mass)&&cfg.plant.mass>0&& ...
    isfield(cfg.plant,'arm_initial')&&numel(cfg.plant.arm_initial)==4, ...
    'CM18Extract:PlantParameters','Positive mass and four nominal arm lengths are required.');
if isfield(cfg,'controller_inertia_derivative_mode')
    jdotMode=lower(char(string(cfg.controller_inertia_derivative_mode)));
else
    jdotMode='full';
end
assert(strcmp(jdotMode,'full'), ...
    'CM18Extract:JdotMode','The sealed CM18 protocol requires full controller Jdot.');

n=20000;time=double(log.transition_time(:));fullTime=double(log.time(:));
sceneTime=double(scene.time(:));state=double(log.state);
eventFlagRaw=double(log.attitude_event_flag(:));
assert(numel(eventFlagRaw)==n&&all(isfinite(eventFlagRaw))&&all(ismember(eventFlagRaw,[0,1])), ...
    'CM18Extract:EventFlags','Attitude event flags must be finite logical values.');
eventFlag=logical(eventFlagRaw);idx=find(eventFlag);
assert(numel(time)==n&&numel(fullTime)==n+1&&numel(sceneTime)==n+1&& ...
    isequal(size(state),[n+1,12])&&isequal(size(eventFlag),[n,1])&& ...
    abs(time(1))<=1e-12&&abs(time(end)-19.999)<=1e-12&& ...
    abs(fullTime(1))<=1e-12&&abs(fullTime(end)-20)<=1e-12&& ...
    max(abs(fullTime-sceneTime))<=1e-12&&max(abs(time-fullTime(1:n)))<=1e-12&& ...
    all(diff(time)>0), ...
    'CM18Extract:TimeShape','Expected 20,000 transition-left rows and 20,001 states aligned to the scene.');
dt=diff(sceneTime);
assert(all(isfinite(dt))&&all(dt>0)&&max(abs(dt-0.001))<=1e-12, ...
    'CM18Extract:TimeStep','The audited 1 ms scene timebase changed.');
assert(numel(idx)==1999&&isequal(idx,(11:10:19991).'), ...
    'CM18Extract:EventSchedule','Expected canonical 1,999-event schedule 11:10:19991.');

request=double(log.requested_generalized);realized=double(log.realized_generalized);
tauNom=double(log.attitude_bs_nominal_torque_Nm);
tauComp=double(log.attitude_compensation_applied_torque_Nm);
windTorque=double(log.wind_torque_B);
command=double(scene.arms.command);rho=double(scene.arms.rho_true);
rhoDot=double(scene.arms.rhoDot_true);
assert(isequal(size(request),[n,4])&&isequal(size(realized),[n,4])&& ...
    isequal(size(tauNom),[n,3])&&isequal(size(tauComp),[n,3])&& ...
    isequal(size(windTorque),[n,3])&&isequal(size(command),[n+1,4])&& ...
    isequal(size(rho),[n+1,4])&&isequal(size(rhoDot),[n+1,4])&& ...
    all(isfinite([state(:);request(:);realized(:);tauNom(:);tauComp(:); ...
    windTorque(:);command(:);rho(:);rhoDot(:)]))&&all(ismember(command(:),[-1,0,1])), ...
    'CM18Extract:RawShape','Raw arrays have invalid dimensions, values, or command levels.');

[J0,~,Jdot0]=arm_mass_properties(double(cfg.plant.arm_initial(:)),cfg.plant,zeros(4,1));
assert(isequal(size(J0),[3,3])&&isequal(size(Jdot0),[3,3])&& ...
    all(isfinite([J0(:);Jdot0(:)]))&&all(eig(0.5*(J0+J0.'))>0), ...
    'CM18Extract:NominalInertia','Fixed nominal inertia/Jdot are invalid.');

N=numel(idx);omega=state(idx,10:12);alphaBS=zeros(N,3);thrustMass=zeros(N,1);
u=command(idx,:);zAll=[zeros(1,4);cumsum(command(1:end-1,:).*repmat(dt,1,4),1)];
z=zAll(idx,:);a=zeros(N,3);target=zeros(N,3);phaseCode=classify_phase(scene,idx);
maxTrueEquationResidual=0;
for q=1:N
    k=idx(q);w=omega(q,:).';
    alphaBS(q,:)=(J0\(tauNom(k,:).'-cross(w,J0*w)-Jdot0*w)).';
    thrustMass(q)=request(k,1)/double(cfg.plant.mass);
    prior=(k-10):(k-1);
    a(q,:)=sum(request(prior,2:4).*dt(prior),1)/sum(dt(prior));

    [Jtrue,~,JdotTrue]=arm_mass_properties(rho(k,:).',cfg.plant,rhoDot(k,:).');
    forcing=realized(k,2:4).'+windTorque(k,:).'-cross(w,Jtrue*w)-JdotTrue*w;
    alphaTrue=Jtrue\forcing;
    tauVirtual=tauNom(k,:).'-tauComp(k,:).';
    alphaVirtual=J0\(tauVirtual-cross(w,J0*w)-Jdot0*w);
    target(q,:)=(alphaTrue-alphaVirtual).';
    maxTrueEquationResidual=max(maxTrueEquationResidual,max(abs(Jtrue*alphaTrue-forcing)));
end
X18=[omega,alphaBS,thrustMass,u,z,a];
requestClosure=max(abs(request(idx,2:4)-(tauNom(idx,:)-tauComp(idx,:))),[],'all');
assert(isequal(size(X18),[N,18])&&isequal(size(target),[N,3])&& ...
    all(isfinite([X18(:);target(:)]))&&requestClosure<=1e-8&& ...
    maxTrueEquationResidual<=1e-12, ...
    'CM18Extract:Closure','X18/labels are non-finite or request/physics closure failed.');

events=struct;
events.schema='CM18_RECONSTRUCTED_EVENTS_V1';
events.scene_id=char(string(scene.scene_id));
events.event_index=(1:N).';
events.plant_index=idx;
events.event_time_s=time(idx);
events.phase_code=phaseCode;
events.X18=X18;
events.target_raw=target;
events.closure=struct('requested_torque_vs_nominal_minus_applied_max_abs_Nm',requestClosure, ...
    'true_dynamics_equation_residual_max_abs_Nm',maxTrueEquationResidual);
assert(isscalar(events),'CM18Extract:OutputScalar','Expected a scalar events struct.');
end

function phaseCode=classify_phase(scene,idx)
rho=double(scene.arms.rho_true);command=double(scene.arms.command);
phaseCode=zeros(numel(idx),1,'uint8');
for q=1:numel(idx)
    k=idx(q);
    if ~any(abs(command(:))>0)
        code=0;
    elseif any(command(k,:)>0)
        code=2;
    elseif any(command(k,:)<0)
        code=4;
    elseif any(rho(k,:)>.150001)
        code=3;
    elseif any(any(abs(command(1:k,:))>0))&&~any(any(abs(command(k:end,:))>0))
        code=5;
    else
        code=1;
    end
    phaseCode(q)=uint8(code);
end
end
