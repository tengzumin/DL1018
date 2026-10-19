function result=check_g00_exporters(projectRoot)
% Synthetic-log checks for actual applied inputs and independent event masks.
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
addpath(fullfile(projectRoot,'matlab','runtime'));
[cfg,~,root]=init_dl1018();Pp=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
P=controller_parameters(cfg,Pp,'fixed');n=4;scene=make_scene(n);
log=make_log(scene,cfg,P,n);
row=struct('scene_id',scene.scene_id);
[posB,posMeta]=export_position_events_dl1018(log,scene,cfg,'B','TRAIN',row);
[posAlt,~]=export_position_events_dl1018(log,scene,cfg,'changed-method-label','TRAIN',row);
assert(height(posB)==3&&isequal(posB.target_raw_1,posAlt.target_raw_1)&& ...
    isequal(posB.target_raw_2,posAlt.target_raw_2)&&isequal(posB.target_raw_3,posAlt.target_raw_3), ...
    'DL1018:PositionMethodMapping','Position labels changed with method text.');
clipDelta=max(abs([posB.target_raw_1-posB.target_clip_1; ...
    posB.target_raw_2-posB.target_clip_2;posB.target_raw_3-posB.target_clip_3]));
assert(clipDelta>0&& ...
    posMeta.max_applied_force_acceleration_error_mps2<=1e-12&& ...
    posMeta.max_label_closure_mps2<=1e-9, ...
    'DL1018:PositionSyntheticLabels','Position raw/clip or physical closure check failed.');

[att,attMeta]=export_attitude_events_dl1018(log,scene,cfg,'A_INIT_STUDENT','TRAIN');
assert(height(att)==3&&isequal(att.plant_index,[1;3;4])&& ...
    attMeta.event_count==3&&~any(att.head_update_executed)&& ...
    attMeta.max_requested_torque_closure_Nm<=1e-8&&attMeta.max_dynamics_closure_rads2<=1e-8, ...
    'DL1018:AttitudeIndependentEvent','Attitude KAN events disappeared when RBF update was false.');
rbfOnly=log;rbfOnly.attitude_compensation_applied_torque_Nm(:)=0;
filter=command_filter_init(rbfOnly.state(1,7:9).');
for k=1:n
    [ir,filter]=command_filter_step(rbfOnly.raw_outer_attitude(k,:).',filter,P);
    [~,ai]=attitude_bs_step(rbfOnly.state(k,:).',ir,zeros(3,1),P);
    rbfOnly.requested_generalized(k,2:4)=ai.nominal_moment.';
end
[attZero,~]=export_attitude_events_dl1018(rbfOnly,scene,cfg,'B','TRAIN');
assert(max(abs(att.target_raw_1-attZero.target_raw_1))>0, ...
    'DL1018:AttitudeAppliedSource','Labels ignored actual KAN torque and used the zero RBF signal.');
assert(abs(att.x29_26(2)-log.motor_setpoint(1,1)/cfg.plant.limits.motor_max)<=1e-12&& ...
    abs(att.x29_26(3)-log.motor_setpoint(3,1)/cfg.plant.limits.motor_max)<=1e-12, ...
    'DL1018:PreviousSetpoint','X29 did not use the previous event setpoint.');

h5path=fullfile(projectRoot,'reports','G00_H5_ORIENTATION_FIXTURE.h5');
if ~isfolder(fileparts(h5path)),mkdir(fileparts(h5path));end
metadata=struct('scene_id',scene.scene_id,'collector_id','A_INIT_STUDENT', ...
    'contract_version','DL1018_V311_R2E_PAPER_FINAL','split','TRAIN');
if ~isfile(h5path),write_events_h5_dl1018(att,h5path,metadata);end
info=h5info(h5path);datasets=string({info.Datasets.Name});xInfo=h5info(h5path,'/x');
expectedX=zeros(height(att),29);for j=1:29,expectedX(:,j)=att.(sprintf('x29_%d',j));end
actualX=h5read(h5path,'/x');
assert(all(ismember(["event_time_s","target_raw_1","x29_29"],datasets))&& ...
    isequal(h5read(h5path,'/plant_index'),att.plant_index)&& ...
    isequal(xInfo.Dataspace.Size,[29,height(att)])&&isequal(actualX,expectedX.')&& ...
    strcmp(h5readatt(h5path,'/','scene_id'),scene.scene_id), ...
    'DL1018:EventH5Write','H5 event columns did not round-trip.');
result=struct('status','PASS','position_events',height(posB),'attitude_events',height(att), ...
    'rbf_update_flag_all_false',all(~log.rbf_update_flag), ...
    'attitude_events_retained',height(att)==nnz(log.attitude_event_flag), ...
    'position_label_closure_mps2',posMeta.max_label_closure_mps2, ...
    'attitude_torque_closure_Nm',attMeta.max_requested_torque_closure_Nm, ...
    'attitude_dynamics_closure_rads2',attMeta.max_dynamics_closure_rads2, ...
    'actual_kan_torque_changes_label',true,'h5_datasets',numel(datasets), ...
    'h5_event_major_X29_shape',[height(att),29],'h5_metadata_round_trip',true, ...
    'h5_orientation_fixture',h5path, ...
    'project_root',root);
end

function scene=make_scene(n)
scene=struct('scene_id','G00_SYNTHETIC_EXPORT_FIXTURE','time',(0:n)'*.01, ...
    'arms',struct('command',zeros(n+1,4),'rho_true',.15*ones(n+1,4), ...
    'rhoDot_true',zeros(n+1,4)));
scene.arms.command(2,1)=1;scene.arms.command(4,2)=-1;
end

function log=make_log(scene,cfg,P,n)
log=struct();log.transition_time=(1:n)'*.01;
log.state=zeros(n+1,12);
log.state(:,1:3)=[linspace(0,.02,n+1).',linspace(.01,-.01,n+1).',linspace(0,.03,n+1).'];
log.state(:,4:6)=repmat([.04,-.03,.02],n+1,1);
log.state(:,7:9)=repmat([.04,-.03,.1],n+1,1);
log.state(:,10:12)=repmat([.08,-.06,.03],n+1,1);
ref=struct('position',repmat([.15,-.1,.35],n+1,1), ...
    'velocity',repmat([.08,-.02,.01],n+1,1),'acceleration',repmat([.1,-.04,.02],n+1,1), ...
    'yaw',repmat(.2,n+1,1),'yaw_rate',zeros(n+1,1),'yaw_acceleration',zeros(n+1,1));
log.reference=ref;log.position_event_flag=logical([1;0;1;1]);
log.attitude_event_flag=logical([1;0;1;1]);log.rbf_update_flag=false(n,1);
log.position_event_beta=[.5;NaN;.8;.9];log.attitude_event_beta=[.2;NaN;.3;.4];
log.position_compensation_applied_force_N=[1.2,0,-.4;0,0,0;-.4,.2,.1;.3,-.1,.2];
log.position_compensation_applied_acceleration_mps2= ...
    log.position_compensation_applied_force_N/P.mass;
log.position_nominal_acceleration_mps2=zeros(n,3);log.position_commanded_force_N=zeros(n,3);
for k=1:n
    r=struct('position',ref.position(k,:).','velocity',ref.velocity(k,:).', ...
        'acceleration',ref.acceleration(k,:).','yaw',ref.yaw(k), ...
        'yaw_rate',ref.yaw_rate(k),'yaw_acceleration',ref.yaw_acceleration(k));
    [~,pi]=position_bs_step(log.state(k,:).',r,zeros(3,1),P);
    log.position_nominal_acceleration_mps2(k,:)=pi.nominal_acceleration.';
    log.position_commanded_force_N(k,:)=P.mass*pi.nominal_acceleration.'- ...
        log.position_compensation_applied_force_N(k,:);
end
log.position_head_update_executed=false(n,1);log.attitude_head_update_executed=false(n,1);
log.requested_generalized=zeros(n,4);log.controller_clipped_generalized=zeros(n,4);
log.realized_generalized=repmat([100,.05,-.03,.01],n,1);
log.wind_force_I=repmat([.02;-.03;.01].',n,1);log.wind_torque_B=repmat([.01;-.02;.005].',n,1);
log.raw_outer_attitude=repmat([.02,-.04,.2],n,1);
log.filtered_attitude_reference=zeros(n,3);log.filtered_attitude_rate=zeros(n,3);
log.motor_setpoint=repmat([100,200,300,400],n,1);log.motor_setpoint(3,:)=[500,600,700,800];
log.motor_setpoint(4,:)=[900,1000,1100,1200];
log.attitude_compensation_applied_torque_Nm=repmat([1.2,-.5,.25],n,1);
log.attitude_rbf_compensation_torque_Nm=zeros(n,3);
filter=command_filter_init(log.state(1,7:9).');
for k=1:n
    [ir,filter]=command_filter_step(log.raw_outer_attitude(k,:).',filter,P);
    log.filtered_attitude_reference(k,:)=ir.euler.';
    log.filtered_attitude_rate(k,:)=ir.euler_rate.';
    [~,ai]=attitude_bs_step(log.state(k,:).',ir,zeros(3,1),P);
    log.requested_generalized(k,:)=[6.9,(ai.nominal_moment- ...
        log.attitude_compensation_applied_torque_Nm(k,:).').'];
    log.controller_clipped_generalized(k,:)=log.requested_generalized(k,:);
end
end

