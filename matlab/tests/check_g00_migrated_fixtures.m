function result=check_g00_migrated_fixtures(projectRoot,fixturePath)
% Compare isolated DL1018 MATLAB calculations with source-generated fixtures.
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
fixturePath=char(java.io.File(fixturePath).getCanonicalPath());
addpath(fullfile(projectRoot,'matlab','runtime'));
[cfg,~,root]=init_dl1018();F=load(fixturePath,'inputs','expected');I=F.inputs;E=F.expected;
assert(strcmp(root,projectRoot),'DL1018:RootMismatch','Unexpected project root.');
assert(~contains(path,'DL1009','IgnoreCase',true),'DL1018:PathLeak','Source root remains on the MATLAB path.');

Pplant=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));P0=controller_parameters(cfg,Pplant,'fixed');
assert_close(P0.mass,E.mass,1e-12,'mass');assert_close(P0.inertia,E.J0,1e-12,'J0');
assert_close(P0.allocation.C,E.C0,1e-12,'C0');
actual=struct('cog',Pplant.cog,'inertia',Pplant.inertia, ...
    'inertia_dot',Pplant.inertia_dot,'cog_rate',Pplant.cog_rate);
assert_close(actual,E.nominal_mass_properties,1e-12,'nominal mass properties');
Pm=simulation_parameters(cfg,I.morph_lengths,I.morph_rates);
actual=struct('cog',Pm.cog,'inertia',Pm.inertia,'inertia_dot',Pm.inertia_dot, ...
    'cog_rate',Pm.cog_rate,'C',Pm.allocation.C);
assert_close(actual,E.morph_mass_properties,1e-12,'morph mass properties');
[windProfile,windProfileDetails]=wind_velocity_profile([0;.2;.8;1.2],I.wind_profile_cfg);
assert_close(struct('velocity',windProfile,'details',windProfileDetails), ...
    E.wind_profile,1e-12,'wind velocity profile');
plants={Pplant,Pm};
for i=1:2
    [windForce,windTorque,windDetails]=morphology_aware_wind_load( ...
        I.wind_state,plants{i},E.wind_profile.velocity(:,3),I.wind_load_cfg);
    assert_close(struct('force',windForce,'torque',windTorque,'details',windDetails), ...
        E.wind_load{i},1e-12,'morphology-aware wind load');
end

for i=1:3
    [pc,pi]=position_bs_step(I.states(:,i),I.reference,zeros(3,1),P0);
    assert_close(struct('command',pc,'info',pi),E.position{i},1e-12,'position BS');
    attRef=struct('euler',I.states(7:9,i)+[.08;-.06;.03], ...
        'euler_rate',[.1;-.05;.02],'euler_acceleration',[-.2;.12;.04]);
    [moment,ai]=attitude_bs_step(I.states(:,i),attRef,zeros(3,1),P0);
    assert_close(struct('moment',moment,'info',ai),E.attitude{i},1e-12,'attitude BS');
    [thrust,euler,limited]=baseline_force_to_attitude(pi.commanded_acceleration,I.states(9,i),P0);
    assert_close(struct('thrust',thrust,'euler',euler,'limited',limited), ...
        E.force_to_attitude{i},1e-12,'force-to-attitude');
end
filter=command_filter_init(I.filter_state.euler);
[ir,next,requested]=command_filter_step(I.filter_target,filter,P0);
assert_close(struct('reference',ir,'next',next,'requested',requested),E.filter,1e-12,'command filter');

net=struct('W',I.rbf_position_W);
for i=1:3
    z=I.rbf_position_z+(i-1)*[.1;-.05;.08];
    [y,net,info]=rbf_mimo_update(z,I.rbf_position_surfaces(i,:).',net,I.rbf_position_cfg,.01);
    assert_close(struct('y',y,'W',net.W,'info',info),E.rbf_position{i},1e-12,'position RBF event');
end
net=struct('W',I.rbf_attitude_W);
for i=1:3
    z=I.rbf_attitude_z+(i-1)*[.01;-.02;.03;-.01;.02;-.03];
    [y,net,info]=rbf_mimo_update(z,I.rbf_attitude_surfaces(i,:).',net,I.rbf_attitude_cfg,.01);
    assert_close(struct('y',y,'W',net.W,'info',info),E.rbf_attitude{i},1e-12,'attitude RBF event');
end

phi=position_stage1_model_forward_v2(I.position_model,I.position_window);
assert_close(phi,I.position_phi,1e-12,'position KAN forward');
[raw,applied,W,projection,info]=position_stage1_update_head_pcf_v3_5( ...
    phi,I.position_head_W,I.position_head_surface,.01,.85,[3;3;3],I.position_eta,true);
assert_close(struct('raw',raw,'applied',applied,'W',W,'projection',projection,'info',info), ...
    E.position_head,1e-12,'position PCF Head');
[af,rf,eta,rotation]=position_filter_realization_pcf_step_v3_5( ...
    I.eta_step.thrust,I.eta_step.euler,I.eta_step.a_requested,I.eta_step.eta, ...
    I.eta_step.k2,P0.mass,P0.g,.001,true);
assert_close(struct('a_filtered',af,'r_filtered',rf,'eta_next',eta,'rotation',rotation), ...
    E.eta_step,1e-12,'PCF eta');

[phiA,W0,readout]=attitude_model_feature_x29_v39(I.attitude_model,I.attitude_history);
assert_close(struct('phi',phiA,'W0',W0,'readout',readout), ...
    struct('phi',I.attitude_phi,'W0',I.attitude_W0,'readout',I.attitude_readout), ...
    1e-12,'X29 forward');
[~,ai]=attitude_bs_step(I.attitude_state,I.attitude_ir,zeros(3,1),P0);
feat=attitude_feature_row_v3_6(ai,I.attitude_state,I.attitude_ir,P0.mass*9.3, ...
    [120;130;140;150],zeros(0,1),P0.mass,cfg.plant.limits.motor_max,29);
assert_close(feat,I.attitude_feature,1e-12,'X29 feature row');
ai.J0=P0.inertia;
[raw,applied,tau,DeltaW,d]=attitude_kan_head_step_v39(phiA,W0,zeros(33,3), ...
    ai,.8,.01,I.attitude_model.dmax,true,false);
assert_close(struct('raw',raw,'applied',applied,'torque',tau,'DeltaW',DeltaW,'diag',d), ...
    E.attitude_frozen,1e-12,'frozen v39 Head');
ai.surface=[2.3;2.3;1.4];
[raw,applied,tau,DeltaW,d]=attitude_kan_head_step_v39(phiA,W0,I.attitude_DeltaW_boundary, ...
    ai,.8,.01,I.attitude_model.dmax,true,true);
assert_close(struct('raw',raw,'applied',applied,'torque',tau,'DeltaW',DeltaW,'diag',d), ...
    E.attitude_projected,1e-12,'projected v39 Head');
assert(isequal(E.trim_empty,trim_head_audit_v39(make_audit(),0))&& ...
    isequaln(E.trim_single,trim_head_audit_v39(make_audit(),1))&& ...
    isequaln(E.trim_multi,trim_head_audit_v39(make_audit(),3)), ...
    'DL1018:TrimParity','Head audit trimming differs for empty, single, or multiple events.');

phase=-.1;last=0;eventTimes=zeros(1,0);
for k=1:20000
    t=(k-1)*cfg.plant.dt;
    [event,phase,~,last]=rbf_event_scheduler_step(phase,100,cfg.plant.dt,t,last);
    if event,eventTimes(end+1)=t;end %#ok<AGROW>
end
assert(numel(eventTimes)==1999&&abs(eventTimes(1)-.01)<=1e-12&& ...
    abs(eventTimes(32)-.32)<=1e-12&&abs(eventTimes(end)-19.99)<=1e-12, ...
    'DL1018:SchedulerContract','100-Hz event schedule differs from the locked clock.');

check_options(cfg,I);
active={'run_dl1018_closed_loop','controller_options_dl1018','position_stage1_model_forward_v2', ...
    'position_stage1_update_head','position_stage1_update_head_pcf_v3_5', ...
    'position_filter_realization_pcf_step_v3_5','attitude_feature_row_v3_6', ...
    'attitude_model_feature_x29_v39','attitude_kan_head_step_v39','trim_head_audit_v39', ...
    'export_position_events_dl1018','export_attitude_events_dl1018','write_events_h5_dl1018', ...
    'run_episode_dl1018','write_gate_report_dl1018'};
resolved=struct();
for i=1:numel(active)
    allPaths=which(active{i},'-all');
    assert(~isempty(allPaths),'DL1018:PathIsolation','%s did not resolve.',active{i});
    for j=1:numel(allPaths)
        p=allPaths{j};assert(startsWith(lower(p),lower(projectRoot)), ...
            'DL1018:PathIsolation','%s resolved outside DL1018: %s',active{i},p);
    end
    resolved.(active{i})=allPaths;
end
entries={fullfile(projectRoot,'matlab','runtime','run_dl1018_closed_loop.m'), ...
    fullfile(projectRoot,'matlab','data','export_position_events_dl1018.m'), ...
    fullfile(projectRoot,'matlab','data','export_attitude_events_dl1018.m'), ...
    fullfile(projectRoot,'matlab','data','write_events_h5_dl1018.m'), ...
    fullfile(projectRoot,'matlab','runtime','write_gate_report_dl1018.m')};
dependencyCount=0;
for i=1:numel(entries)
    dependencies=matlab.codetools.requiredFilesAndProducts(entries{i});
    dependencyCount=dependencyCount+numel(dependencies);
    assert(~any(contains(string(dependencies),'DL1009','IgnoreCase',true)), ...
        'DL1018:DependencyLeak','An active entrypoint depends on DL1009.');
end
result=struct('status','PASS','fixture_file',fixturePath,'resolved',resolved, ...
    'required_dependency_entries_checked',numel(entries),'dependency_paths_checked',dependencyCount, ...
    'source_path_on_target_path',false,'event_count',numel(eventTimes), ...
    'ready_count',numel(eventTimes)-31,'position_head_frozen_nonzero_output', ...
    norm(E.position_head.raw)>0,'attitude_head_frozen_nonzero_output',norm(E.attitude_frozen.raw)>0, ...
    'attitude_projection_fixture_active',E.attitude_projected.diag.projection_active);
end

function check_options(cfg,I)
B=controller_options_dl1018(cfg,'B');OFF=controller_options_dl1018(cfg,'POS_OFF');
assert(B.rbf_position_output_enabled&&B.rbf_position_update_enabled&& ...
    ~isfield(B,'stage1_position_runtime')&&OFF.rbf_attitude_output_enabled&& ...
    ~OFF.rbf_position_output_enabled&&~OFF.rbf_position_update_enabled, ...
    'DL1018:BaselineMatrix','B/POS_OFF switch matrix is wrong.');
zeroModel=I.position_model;zeroModel.output_W=zeros(33,3);
zero=controller_options_dl1018(cfg,'P_F',zeroModel,[],'frozen');
assert(zero.stage1_position_runtime.enabled&&~zero.rbf_position_output_enabled&& ...
    ~zero.rbf_position_update_enabled&&norm(zero.stage1_position_runtime.weight.'*I.position_phi)==0, ...
    'DL1018:ZeroCounterfactual','Zero-output KAN must stay on the POS_OFF route.');
student=controller_options_dl1018(cfg,'P_INIT_STUDENT',I.position_model);
frozen=controller_options_dl1018(cfg,'P_F',I.position_model,[],'frozen');
online=controller_options_dl1018(cfg,'P_A',I.position_model);
assert(student.stage1_position_runtime.update_enabled&& ...
    ~frozen.stage1_position_runtime.update_enabled&&online.stage1_position_runtime.update_enabled&& ...
    frozen.stage1_position_runtime.command_filter_coordination_v3_5.enabled, ...
    'DL1018:PositionHeadSwitch','Position Head freeze/online mode is wrong.');
attFrozen=controller_options_dl1018(cfg,'PA_F',I.position_model,I.attitude_model,'frozen');
attOnline=controller_options_dl1018(cfg,'PA_A',I.position_model,I.attitude_model,'frozen');
assert(attFrozen.attitude_fusion_v3_6.lambda==1&& ...
    ~attFrozen.rbf_attitude_output_enabled&&~attFrozen.rbf_attitude_update_enabled&& ...
    ~attFrozen.attitude_head_v39.enabled&&attOnline.attitude_head_v39.enabled, ...
    'DL1018:AttitudeSwitch','X29 replacement and attitude Head switch matrix is wrong.');
end

function audit=make_audit()
audit=struct('time',[.01;.02;.03],'dt_event_s',[.01;.01;.01], ...
    'weight_before',reshape(1:297,33,3,3),'weight_after',reshape(298:594,33,3,3), ...
    'phi',reshape(1:99,33,3),'y_raw',reshape(1:9,3,3));
end

function assert_close(actual,expected,tol,label)
if isstruct(actual)
    assert(isstruct(expected)&&isequal(sort(fieldnames(actual)),sort(fieldnames(expected))), ...
        'DL1018:FixtureShape','Struct fields differ in %s.',label);
    fields=fieldnames(actual);
    for i=1:numel(fields),assert_close(actual.(fields{i}),expected.(fields{i}),tol,[label '.' fields{i}]);end
elseif iscell(actual)
    assert(iscell(expected)&&isequal(size(actual),size(expected)), ...
        'DL1018:FixtureShape','Cell shape differs in %s.',label);
    for i=1:numel(actual),assert_close(actual{i},expected{i},tol,label);end
elseif isnumeric(actual)||islogical(actual)
    assert(isequal(size(actual),size(expected)), ...
        'DL1018:FixtureShape','Array shape differs in %s.',label);
    if isnumeric(actual)
        finite=isfinite(actual)&isfinite(expected);
        assert(all(isfinite(actual(:))==isfinite(expected(:)))&& ...
            all(isnan(actual(:))==isnan(expected(:)))&& ...
            all(isinf(actual(:))==isinf(expected(:))), ...
            'DL1018:FixtureFinite','Finite/Inf/NaN patterns differ in %s.',label);
        if any(finite,'all'),err=max(abs(double(actual(finite))-double(expected(finite))));else,err=0;end
        assert(err<=tol,'DL1018:FixtureValue','%s differs by %.17g (limit %.3g).',label,err,tol);
    else
        assert(isequal(actual,expected),'DL1018:FixtureValue','Logical values differ in %s.',label);
    end
else
    assert(isequaln(actual,expected),'DL1018:FixtureValue','Values differ in %s.',label);
end
end
