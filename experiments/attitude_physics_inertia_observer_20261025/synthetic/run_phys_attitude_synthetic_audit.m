function audit = run_phys_attitude_synthetic_audit(outputPath)
% Synthetic-only audit. Uses default_config, arm_mass_properties and the
% existing attitude_bs_step interface; never starts Plant/scene/runtime code.
if nargin<1, outputPath='synthetic/PHYS_ATT_OBSERVER_SYNTH_AUDIT_v1.json'; end
profile clear
profile on
cfg=default_config();
cfg.plant.inertia=[.012 .0011 -.0004;.0011 .014 .0007;-.0004 .0007 .024];
assert(all(eig(cfg.plant.inertia)>0),'PHYSATT:Test','Synthetic J0 must be SPD.');
interface=check_interface_and_acceleration_mapping(cfg);
sequence=check_causality_and_observer(cfg);
profile off
p=profile('info');
called={p.FunctionTable.FunctionName};
calledLower=cellfun(@lower,called,'UniformOutput',false);
forbidden={'run_dl1018_closed_loop','vehicle_derivative','make_scenes_dl1018', ...
    'tcn0916_morphology_scenario','simulation_parameters','load','matfile', ...
    'readmatrix','readtable','readstruct'};
forbiddenCalls={};
for q=1:numel(forbidden)
    if any(contains(calledLower,lower(forbidden{q})))
        forbiddenCalls{end+1}=forbidden{q}; %#ok<AGROW>
    end
end
assert(isempty(forbiddenCalls),'PHYSATT:TestScope', ...
    'Synthetic call trace included forbidden Plant/scene/data function(s).');
audit=struct('status','PASS','started_utc',datestr(now,30), ...
    'scope','synthetic only; no Plant/scene/closed-loop run or external data read', ...
    'interface_test',interface,'causality_observer_test',sequence, ...
    'executed_m_functions',{called},'forbidden_functions_checked',{forbidden}, ...
    'forbidden_calls_found',{forbiddenCalls},'external_data_files_opened',{{}}, ...
    'notes','Only audit JSON is written. No TEST, MAT, raw, scene log, or flight data is read.');
folder=fileparts(outputPath);
if ~isempty(folder) && ~exist(folder,'dir'), mkdir(folder); end
fid=fopen(outputPath,'w');
assert(fid>=0,'PHYSATT:AuditWrite','Cannot create synthetic audit JSON.');
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(audit,'PrettyPrint',true),'char');
fprintf('PHYS_ATT_SYNTHETIC_AUDIT_PASS\n');
end

function result=check_interface_and_acceleration_mapping(cfg)
J0=cfg.plant.inertia;
P0=struct('inertia',J0,'inertia_dot',zeros(3), ...
    'inertia_dot_for_bs',zeros(3),'bs',cfg.control.bs);
state=zeros(12,1);
state(7:9)=[.31;-.24;.47];
state(10:12)=[.71;-.43;.62];
reference=struct('euler',[-.17;.22;-.35], ...
    'euler_rate',[.13;-.21;.18],'euler_acceleration',[-.4;.6;-.2]);
[Mnom,baseInfo]=attitude_bs_step(state,reference,zeros(3,1),P0);
alphaBS=baseInfo.nominal_body_angular_acceleration;
omega=state(10:12);
Jhat=[.018 .0017 -.0005;.0017 .023 .0011;-.0005 .0011 .031];
Jdothat=[1.1e-4 2e-5 -1e-5;2e-5 -1.5e-4 3e-5;-1e-5 3e-5 2e-4];
assert(all(eig(Jhat)>0),'PHYSATT:Test','Synthetic Jhat must be SPD.');
tauShape=(Jhat-J0)*alphaBS+cross(omega,(Jhat-J0)*omega)+Jdothat*omega;
dZero=zeros(3,1);
dKnown=[.003;-.004;.006];
dWrong=[-.002;.005;-.003];
cases={ ...
    struct('name','zero disturbance and estimate','dtrue',dZero,'dhat',dZero), ...
    struct('name','known disturbance exactly estimated','dtrue',dKnown,'dhat',dKnown), ...
    struct('name','known disturbance estimate mismatch','dtrue',dKnown,'dhat',dWrong)};
caseErrors=zeros(numel(cases),2);
for q=1:numel(cases)
    tauComp=tauShape-cases{q}.dhat;
    [tauCommand,info]=attitude_bs_step(state,reference,-tauComp,P0);
    expectedCommand=Mnom+tauComp;
    alphaActual=Jhat\(tauCommand+cases{q}.dtrue- ...
        cross(omega,Jhat*omega)-Jdothat*omega);
    alphaExpected=alphaBS+Jhat\(cases{q}.dtrue-cases{q}.dhat);
    caseErrors(q,:)=[norm(tauCommand-expectedCommand,inf), ...
        norm(alphaActual-alphaExpected,inf)];
    assert(caseErrors(q,1)<1e-11 && caseErrors(q,2)<1e-10, ...
        'PHYSATT:SignAxis','attitude_bs_step sign/axis or synthetic rigid-body equation mismatch.');
    assert(norm(info.estimate_torque+tauComp,inf)<1e-12, ...
        'PHYSATT:SignAxis','estimateTorque must be negative compensation at this subtracting port.');
end

memory=phys_attitude_replacement_candidate('init',[],struct(),cfg);
in=struct('time_s',0,'omega_body',omega,'alpha_bs_body',alphaBS, ...
    'morph_command',[1;-1;0;1],'sample_index',1100,'is_attitude_event',true);
[memory,candidate]=phys_attitude_replacement_candidate('prepare',memory,in,cfg);
assert(~candidate.observer.updated && all(memory.dhat_a==0), ...
    'PHYSATT:Init','First event must not fabricate a residual.');
dmax=cfg.rbf.attitude.dmax(:);
assert(all(abs(candidate.a_extra_rads2)<=dmax+1e-12), ...
    'PHYSATT:Units','Acceleration-equivalent clip exceeded dmax.');
assert(norm(J0\candidate.tau_comp_Nm-candidate.beta*candidate.a_extra_rads2,inf)<1e-10, ...
    'PHYSATT:Units','Torque must be J0 times beta-scaled acceleration-equivalent output.');
assert(norm(candidate.estimateTorque_Nm+candidate.tau_comp_Nm,inf)<1e-12, ...
    'PHYSATT:SignAxis','Candidate signed interface output is inconsistent.');

% Exercise the helper's actual torque through the existing BS torque port.
candidateTauShapeRef=(candidate.Jhat_kgm2-J0)*alphaBS + ...
    cross(omega,(candidate.Jhat_kgm2-J0)*omega) + ...
    candidate.Jdothat_kgm2ps*omega;
candidateTauShapeError=abs(candidate.tau_shape_Nm-candidateTauShapeRef);
assert(all(candidateTauShapeError<1e-12), ...
    'PHYSATT:TauShape','Candidate tau_shape differs from the independent per-axis reference.');
[candidateTorqueFromBs,candidateInterfaceInfo]=attitude_bs_step( ...
    state,reference,candidate.estimateTorque_Nm,P0);
candidateTorqueDelta=abs(candidateTorqueFromBs-Mnom-candidate.tau_comp_Nm);
assert(all(abs(candidateInterfaceInfo.estimate_torque-candidate.estimateTorque_Nm)<1e-12) && ...
    all(candidateTorqueDelta<1e-11), ...
    'PHYSATT:SignAxis','Actual candidate compensation must add to the BS nominal torque axis by axis.');

[memory,~]=phys_attitude_replacement_candidate('commit',memory, ...
    struct('time_s',0,'tau_cmd_clipped_Nm',[.1;-.2;.03]),cfg);
rhoExpected=min(max(cfg.plant.arm_initial+.001*.05*in.morph_command, ...
    cfg.plant.arm_length_min),cfg.plant.arm_length_max);
assert(norm(memory.rho_hat-rhoExpected,inf)<1e-14, ...
    'PHYSATT:Causality','commit did not advance rho_hat from the current command.');
result=struct('case_names',{cellfun(@(x)x.name,cases,'UniformOutput',false)}, ...
    'max_torque_interface_error_Nm',max(caseErrors(:,1)), ...
    'max_synthetic_alpha_error_rads2',max(caseErrors(:,2)), ...
    'J0_nondiagonal',J0,'Jhat_nondiagonal',Jhat,'Jdothat_kgm2ps',Jdothat, ...
    'acceleration_clip_dmax_rads2',dmax,'beta',candidate.beta, ...
    'candidate_tau_shape_error_by_axis_Nm',candidateTauShapeError.', ...
    'candidate_torque_delta_error_by_axis_Nm',candidateTorqueDelta.', ...
    'candidate_torque_mapping_error_Nm',norm(J0\candidate.tau_comp_Nm- ...
        candidate.beta*candidate.a_extra_rads2,inf), ...
    'first_event_updated_observer',candidate.observer.updated, ...
    'morphology_commit_error_m',norm(memory.rho_hat-rhoExpected,inf));
end

function result=check_causality_and_observer(cfg)
dt=double(cfg.plant.dt);
nIntervals=20;
nSamples=nIntervals+1;
u=zeros(4,nSamples);
u(1,2:6)=1;
u(2,7:10)=-1;
u(1,11:15)=1;
u(3,16:20)=-1;
u(4,18:21)=1;
rho=zeros(4,nSamples+1);
rho(:,1)=cfg.plant.arm_initial(:);
J=zeros(3,3,nSamples);
Jdot=zeros(3,3,nSamples);
for k=1:nSamples
    [J(:,:,k),~,Jdot(:,:,k)]=arm_mass_properties(rho(:,k),cfg.plant,.05*u(:,k));
    if k<=nIntervals
        rho(:,k+1)=min(max(rho(:,k)+dt*.05*u(:,k), ...
            cfg.plant.arm_length_min),cfg.plant.arm_length_max);
    end
end
omega=zeros(3,nSamples);
alpha=zeros(3,nSamples);
for k=1:nSamples
    q=k-1;
    omega(:,k)=[.4*sin(.31*q)+.2;-.33*cos(.23*q);.15+.02*sin(.17*q)];
    alpha(:,k)=[.7*sin(.19*q);-.4*cos(.11*q);.2+.1*sin(.07*q)];
end
dTrue=cfg.plant.inertia*[600;-600;100];
tauCmd=zeros(3,nIntervals);
for k=1:nIntervals
    g0=cross(omega(:,k),J(:,:,k)*omega(:,k));
    g1=cross(omega(:,k+1),J(:,:,k+1)*omega(:,k+1));
    tauCmd(:,k)=(J(:,:,k+1)*omega(:,k+1)-J(:,:,k)*omega(:,k))/dt ...
        +.5*(g0+g1)-dTrue;
end

memory=phys_attitude_replacement_candidate('init',[],struct(),cfg);
expectedDhat=zeros(3,1);
eventErrors=[];
causalBranchChecked=false;
for k=1:nSamples
    t=(k-1)*dt;
    isEvent=mod(k-1,10)==0;
    in=struct('time_s',t,'omega_body',omega(:,k),'alpha_bs_body',alpha(:,k), ...
        'morph_command',u(:,k),'sample_index',k,'is_attitude_event',isEvent);
    altResidual=[];
    altDhat=[];
    if k==11
        fork=memory;
        altIn=in;
        altIn.morph_command=zeros(4,1);
        [~,altOut]=phys_attitude_replacement_candidate('prepare',fork,altIn,cfg);
        altResidual=altOut.observer.r_tau_Nm;
        altDhat=altOut.observer.dhat_a_rads2;
        expectedResidual=expected_event_residual(memory,t,omega(:,k),J(:,:,k),tauCmd(:,1:10));
        assert(all(isfinite(altResidual)) && norm(altResidual-expectedResidual,inf)<2e-7, ...
            'PHYSATT:Causality','Altered event-time command changed the expected past residual.');
    end
    [memory,out]=phys_attitude_replacement_candidate('prepare',memory,in,cfg);
    assert(norm(out.rho_hat_m-rho(:,k),inf)<1e-12 && ...
        norm(out.Jhat_kgm2-J(:,:,k),'fro')<1e-12 && ...
        norm(out.Jdothat_kgm2ps-Jdot(:,:,k),'fro')<1e-12, ...
        'PHYSATT:Causality','Command-derived morphology/inertia reconstruction mismatch.');
    if k==11
        causalBranchChecked=norm(out.observer.r_tau_Nm-altResidual,inf)<2e-12 && ...
            norm(out.observer.dhat_a_rads2-altDhat,inf)<2e-12;
        assert(causalBranchChecked,'PHYSATT:Causality', ...
            'Changing current command altered the completed-interval residual.');
    end
    if out.observer.updated
        delta=.01;
        gamma=1-exp(-delta/.10);
        rAExpected=cfg.plant.inertia\dTrue;
        expectedDhat=min(max((1-gamma)*expectedDhat+gamma*rAExpected, ...
            -cfg.rbf.attitude.dmax(:)),cfg.rbf.attitude.dmax(:));
        eventErrors(end+1,:)=[norm(out.observer.r_tau_Nm-dTrue,inf), ...
            norm(out.observer.r_a_rads2-rAExpected,inf), ...
            norm(out.observer.dhat_a_rads2-expectedDhat,inf), ...
            norm(out.observer.tau_cmd_bar_Nm-mean(tauCmd(:,k-10:k-1),2),inf)]; %#ok<AGROW>
        assert(max(eventErrors(end,:))<2e-7,'PHYSATT:Observer', ...
            'Synthetic event residual/filter/command average mismatch.');
    elseif k>1 && isEvent
        error('PHYSATT:Observer','A completed interval was not consumed at an attitude event.');
    end
    if k<=nIntervals
        [memory,~]=phys_attitude_replacement_candidate('commit',memory, ...
            struct('time_s',t,'tau_cmd_clipped_Nm',tauCmd(:,k)),cfg);
    end
end
assert(causalBranchChecked,'PHYSATT:Causality', ...
    'Current event command causality was not checked.');
assert(size(eventErrors,1)==2,'PHYSATT:Observer','Expected exactly two completed event updates.');
assert(all(abs(expectedDhat)<=cfg.rbf.attitude.dmax(:)+1e-12), ...
    'PHYSATT:Projection','Observer acceleration estimate escaped its projection box.');
result=struct('n_samples',nSamples,'n_completed_observer_intervals',size(eventErrors,1), ...
    'dt_s',dt,'synthetic_lumped_disturbance_Nm',dTrue, ...
    'expected_projected_dhat_a_rads2',expectedDhat, ...
    'max_residual_error_Nm',max(eventErrors(:,1)), ...
    'max_residual_acceleration_error_rads2',max(eventErrors(:,2)), ...
    'max_observer_update_error_rads2',max(eventErrors(:,3)), ...
    'max_interval_command_average_error_Nm',max(eventErrors(:,4)), ...
    'current_event_command_causality_checked',causalBranchChecked, ...
    'morphology_command_scale_mps',.05,'plant_or_scene_called',false);
end

function r=expected_event_residual(memory,t,omegaEnd,JEnd,commands)
n=numel(memory.node_time);
assert(size(commands,2)==n && abs(t-memory.node_time(1)-.01)<1e-12, ...
    'PHYSATT:Test','Unexpected synthetic causal fork interval.');
tNodes=[memory.node_time,t];
h=diff(tNodes);
omegaNodes=[memory.node_omega,omegaEnd];
JNodes=cat(3,memory.node_Jhat,JEnd);
g=zeros(3,n+1);
for q=1:n+1
    g(:,q)=cross(omegaNodes(:,q),JNodes(:,:,q)*omegaNodes(:,q));
end
gIntegral=sum(.5*(g(:,1:n)+g(:,2:n+1)).*h,2);
r=(JEnd*omegaEnd-memory.node_Jhat(:,:,1)*memory.node_omega(:,1))/sum(h) ...
    +gIntegral/sum(h)-sum(commands.*h,2)/sum(h);
end

