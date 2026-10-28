function result = root_yaw_alpha_mask_t1_v1()
% Offline fixed-state yaw-input mask check on the pinned T1 C15 W14 A1 raw.
% No engine, episode, Plant step, optimizer, or state integration is called.
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(fileparts(here)));
diagnosticSourcePath=[mfilename('fullpath') '.m'];
experimentDir=fullfile(root,'experiments','attitude_cm18_a1_20261024');
rawPath=fullfile(experimentDir,'screen12_remaining_v1','runs', ...
    'DL1018_DEV_T1_C15_W14','attempt_01','raw_run.mat');
startPath=fullfile(fileparts(rawPath),'run_start.mat');
modelPath=fullfile(experimentDir,'deployment_v1','deployment_parameters_v1.json');
expectedRawSha='23150766d0b5e2888c35bc5bf96af30f9cc516ffca61e124f0d3d6e4f5ac9476';
expectedModelSha='ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae';
expectedCheckpoint='105585385157da3f1b404ab24606d0717287638e4a1ca710790633cd16d233a4';
outPath=fullfile(here,'ROOT_YAW_ALPHA_MASK_T1_C15_W14_v1.json');
assert(~isfile(outPath),'YawMask:NoOverwrite','Refusing to overwrite existing result.');
assert(strcmp(sha256_file(rawPath),expectedRawSha)&&strcmp(sha256_file(modelPath),expectedModelSha), ...
    'YawMask:InputSha','Pinned raw or deployment model SHA changed.');
model=jsondecode(fileread(modelPath));
assert(strcmp(model.schema,'CM18_A1_DEPLOYMENT_PARAMETERS_V1')&& ...
    strcmp(model.identity.checkpoint_sha256,expectedCheckpoint)&&double(model.identity.selected_step)==30000, ...
    'YawMask:Model','Deployment checkpoint/step mismatch.');

oldPath=path; c=onCleanup(@()path(oldPath)); %#ok<NASGU>
coreDir=fullfile(root,'matlab','core'); modelDir=fullfile(experimentDir,'matlab');
addpath(coreDir,'-begin'); addpath(modelDir,'-begin');
sources={'attitude_bs_step','simulation_parameters','controller_parameters','allocate_control','cm18_a1_forward_v1'};
for j=1:numel(sources), assert(~isempty(which(sources{j})),'YawMask:Source','Missing helper %s.',sources{j}); end
sourcePaths=cell(size(sources)); sourceSha=cell(size(sources));
for j=1:numel(sources), sourcePaths{j}=which(sources{j}); sourceSha{j}=sha256_file(sourcePaths{j}); end

pack=load(startPath,'runStart'); raw=load(rawPath,'log','scene');
assert(isfield(pack,'runStart')&&all(isfield(raw,{'log','scene'})), ...
    'YawMask:Mat','Raw/start MAT is incomplete.');
rs=pack.runStart; L=raw.log; s=raw.scene; cfg=rs.cfg; p=model.parameters;
assert(strcmp(rs.scene_id,'DL1018_DEV_T1_C15_W14')&& ...
    strcmpi(rs.model_identity.checkpoint_sha256,expectedCheckpoint)&&double(rs.model_identity.selected_step)==30000&& ...
    strcmpi(cfg.controller_morphology_mode,'fixed')&&strcmpi(cfg.controller_inertia_derivative_mode,'full')&& ...
    ~rs.opts.rbf_attitude_enabled&&~rs.opts.rbf_attitude_output_enabled&&~rs.opts.rbf_attitude_update_enabled&& ...
    ~rs.opts.rbf_position_output_enabled&&~rs.opts.rbf_position_update_enabled&& ...
    strcmp(rs.deployment_parameters_sha256,expectedModelSha), ...
    'YawMask:Identity','Raw does not match the fixed CM18/A1 controller identity.');
dt=diff(double(s.time(:))); n=numel(dt); event=find(logical(L.cm18_event_flag(:)));
assert(n==20000&&isequal(size(double(L.state)),[n+1,12])&& ...
    isequal(event,(11:10:19991).')&&all(abs(dt-.001)<1e-12)&& ...
    strcmp(char(L.status),'STABLE')&&double(L.last_transition)==n, ...
    'YawMask:Schedule','Expected a stable 20,000-transition 100-Hz A1 raw.');

P0=simulation_parameters(cfg,cfg.plant.arm_initial(:),zeros(4,1));
Pnom=controller_parameters(cfg,P0,'fixed'); J0=double(Pnom.inertia); mass=double(Pnom.mass);
motorTc=0; if isfield(rs.opts,'motor_time_constant_s'),motorTc=double(rs.opts.motor_time_constant_s);end
assert(motorTc==0&&all(abs(double(L.motor_time_constant_s(:)))<1e-12), ...
    'YawMask:MotorDynamics','Same-state allocator comparison requires the logged zero motor time constant.');
command=double(s.arms.command); requested=double(L.requested_generalized);
state=double(L.state); wind=double(L.wind_torque_B); nominalLog=double(L.attitude_bs_nominal_torque_Nm);
actualApplied=double(L.cm18_applied_acceleration_held_rad_s2);
loggedRaw=double(L.cm18_event_raw_acceleration_rad_s2);
loggedX=double(L.cm18_event_input_18); realized=double(L.realized_generalized);
dmax=double(L.cm18_dmax_rad_s2(1,:)); betaRise=double(L.cm18_beta_rise_time_s(1));
assert(max(abs(double(L.cm18_fixed_inertia_J0_kgm2(:))-J0(:)))<1e-12&& ...
    isequal(dmax,[45,45,4.7124])&&betaRise==2.2, ...
    'YawMask:ModelContract','Logged fixed J0/clip/beta contract differs from the original A1 setup.');
z=zeros(n,4); for k=2:n, z(k,:)=z(k-1,:)+dt(k-1)*command(k-1,:); end

E=zeros(numel(event),3,3); % candidate order: original, masked yaw, zero
rawYawDelta=zeros(numel(event),1); actionYawDelta=zeros(numel(event),1);
ctrlClip=false(numel(event),3,3); allocClip=false(numel(event),3,4); motorSat=false(numel(event),3,4);
maxXDelta=0; maxRawDelta=0; maxOriginalActionDelta=0; maxOriginalTorqueDelta=0; maxNominalDelta=0; maxOriginalWrenchDelta=0;
for q=1:numel(event)
    k=event(q); w=state(k,10:12).';
    ref=struct('euler',double(L.filtered_attitude_reference(k,:)).', ...
        'euler_rate',double(L.filtered_attitude_rate(k,:)).', ...
        'euler_acceleration',double(L.command_filter_acceleration_applied_rads2(k,:)).');
    [~,ai]=attitude_bs_step(state(k,:).',ref,zeros(3,1),Pnom);
    alphaBS=double(ai.nominal_body_angular_acceleration(:)); tauBS=double(ai.nominal_moment(:));
    maxNominalDelta=max(maxNominalDelta,max(abs(tauBS.'-nominalLog(k,:))));
    past=(k-10):(k-1); pastDt=dt(past);
    aPrevious=sum(requested(past,2:4).*pastDt,1).'/sum(pastDt);
    x=[w.',alphaBS.',requested(k,1)/mass,command(k,:),z(k,:),aPrevious.'];
    maxXDelta=max(maxXDelta,max(abs(x-loggedX(k,:))));
    rawOriginal=cm18_a1_forward_v1(x,p);
    maxRawDelta=max(maxRawDelta,max(abs(rawOriginal-loggedRaw(k,:))));
    xMask=x; xMask(4:5)=0; rawMaskFull=cm18_a1_forward_v1(xMask,p);
    % Preserve original roll/pitch and replace only yaw with the zero-alphaXY forward.
    candidateRaw=[rawOriginal(1:2),rawMaskFull(3)];
    rawYawDelta(q)=candidateRaw(3)-rawOriginal(3);
    beta=min(k*dt(k)/betaRise,1);
    clippedOriginal=max(min(rawOriginal,dmax),-dmax);
    clippedMasked=max(min(candidateRaw,dmax),-dmax);
    actionOriginal=beta*clippedOriginal; actionMasked=beta*clippedMasked; actionZero=zeros(1,3);
    actionYawDelta(q)=actionMasked(3)-actionOriginal(3);
    action={actionOriginal,actionMasked,actionZero};

    Ptrue=simulation_parameters(cfg,double(s.arms.rho_true(k,:)).',double(s.arms.rhoDot_true(k,:)).');
    prev=double(L.motor_command(k-1,:)).'; J=double(Ptrue.inertia); Jdot=double(Ptrue.inertia_dot);
    Ctrue=double(Ptrue.allocation.C); windK=wind(k,:).';
    for a=1:3
        tauCommand=tauBS-J0*action{a}.';
        [motor,~,info]=allocate_control([requested(k,1);tauCommand],Pnom,Ptrue,prev);
        wrench=Ctrue*(double(motor(:)).^2);
        alphaPhysical=J\(wrench(2:4)+windK-cross(w,J*w)-Jdot*w);
        E(q,a,:)=(alphaPhysical-alphaBS).';
        allocClip(q,a,:)=logical(info.generalized_command_clipped(:));
        motorSat(q,a,:)=logical(info.motor_saturated(:));
        if a==1
            maxOriginalTorqueDelta=max(maxOriginalTorqueDelta,max(abs(tauCommand-requested(k,2:4).')));
            maxOriginalWrenchDelta=max(maxOriginalWrenchDelta,max(abs(wrench(:)-realized(k,:).')));
            maxOriginalActionDelta=max(maxOriginalActionDelta,max(abs(action{a}-actualApplied(k,:))));
        end
    end
    ctrlClip(q,1,:)=rawOriginal~=clippedOriginal;
    ctrlClip(q,2,:)=candidateRaw~=clippedMasked;
end
assert(maxXDelta<1e-9&&maxRawDelta<1e-9&&maxOriginalActionDelta<1e-9&& ...
    maxOriginalTorqueDelta<1e-8&&maxNominalDelta<1e-8&&maxOriginalWrenchDelta<1e-8, ...
    'YawMask:Reconstruction','Original event action/allocator did not reconstruct from the pinned raw.');

times=double(L.transition_time(event)); bins=[0 5;5 10;10 15;15 20];
phase=repmat(struct('interval_s',[],'event_count',0,'actions',[]),1,4);
candidateNames={'original','masked_yaw_alphaXY_zero','zero'};
for b=1:4
    use=times>=bins(b,1)&times<bins(b,2); phase(b).interval_s=bins(b,:); phase(b).event_count=nnz(use);
    acts=repmat(struct('candidate','','physical_error_signed_mean_rad_s2',[], ...
        'physical_error_axis_rms_rad_s2',[],'controller_clip_count_by_axis',[], ...
        'allocator_clip_count_by_axis',[],'motor_saturation_count_by_motor',[]),1,3);
    for a=1:3
        err=squeeze(E(use,a,:)); acts(a).candidate=candidateNames{a};
        acts(a).physical_error_signed_mean_rad_s2=mean(err,1);
        acts(a).physical_error_axis_rms_rad_s2=sqrt(mean(err.^2,1));
        acts(a).controller_clip_count_by_axis=squeeze(sum(ctrlClip(use,a,:),1));
        acts(a).allocator_clip_count_by_axis=squeeze(sum(allocClip(use,a,:),1));
        acts(a).motor_saturation_count_by_motor=squeeze(sum(motorSat(use,a,:),1));
    end
    phase(b).actions=acts;
end
result=struct('schema','ROOT_CM18_YAW_ALPHA_MASK_DIAGNOSTIC_V1','status','PASS_OFFLINE_SAME_STATE_ONLY', ...
    'scene_id','DL1018_DEV_T1_C15_W14','created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'raw_path',rawPath,'raw_sha256',expectedRawSha,'run_start_sha256',sha256_file(startPath), ...
    'deployment_model_sha256',expectedModelSha,'checkpoint_sha256',expectedCheckpoint,'selected_step',30000, ...
    'diagnostic_source_path',diagnosticSourcePath,'diagnostic_source_sha256',sha256_file(diagnosticSourcePath), ...
    'helper_paths',{sourcePaths},'helper_sha256',{sourceSha}, ...
    'counterfactual','Only X18 current alphaBS_x/y are set to zero for a second frozen-network forward; the mask action keeps the original network roll/pitch outputs and replaces yaw only. Zero action is an additional fixed-state comparator.', ...
    'physical_error_definition','alpha_physical_from_actual_allocate_control - alpha_BS at the same recorded state, shape, thrust and wind.', ...
    'alpha_BS_source','Recomputed from attitude_bs_step using the logged filtered attitude/rate/acceleration reference; no plant state is advanced.', ...
    'reconstruction_max_abs',struct('X18',maxXDelta,'original_raw_forward_rad_s2',maxRawDelta, ...
        'original_held_action_rad_s2',maxOriginalActionDelta,'original_requested_torque_Nm',maxOriginalTorqueDelta, ...
        'original_BS_nominal_torque_Nm',maxNominalDelta,'original_realized_generalized',maxOriginalWrenchDelta), ...
    'summary_all_events',summarize_actions(E,ctrlClip,allocClip,motorSat,candidateNames), ...
    'masked_yaw_raw_delta_mean_rad_s2',mean(rawYawDelta),'masked_yaw_raw_delta_rms_rad_s2',sqrt(mean(rawYawDelta.^2)), ...
    'masked_yaw_applied_delta_mean_rad_s2',mean(actionYawDelta),'masked_yaw_applied_delta_rms_rad_s2',sqrt(mean(actionYawDelta.^2)), ...
    'phase_summaries',phase,'scope',struct('plant_calls',0,'engine_calls',0,'episode_steps',0, ...
        'state_integrated',false,'optimizer_steps',0,'training',false,'TEST_accessed',false, ...
        'interpretation','Same-state offline allocator diagnosis only; not a closed-loop causal or repair claim.'));
write_json_new(outPath,result);
end

function s=summarize_actions(E,ctrlClip,allocClip,motorSat,names)
s=repmat(struct('candidate','','physical_error_signed_mean_rad_s2',[], ...
    'physical_error_axis_rms_rad_s2',[],'controller_clip_count_by_axis',[], ...
    'allocator_clip_count_by_axis',[],'motor_saturation_count_by_motor',[]),1,3);
for a=1:3
    err=squeeze(E(:,a,:)); s(a).candidate=names{a};
    s(a).physical_error_signed_mean_rad_s2=mean(err,1);
    s(a).physical_error_axis_rms_rad_s2=sqrt(mean(err.^2,1));
    s(a).controller_clip_count_by_axis=squeeze(sum(ctrlClip(:,a,:),1));
    s(a).allocator_clip_count_by_axis=squeeze(sum(allocClip(:,a,:),1));
    s(a).motor_saturation_count_by_motor=squeeze(sum(motorSat(:,a,:),1));
end
end

function write_json_new(path,value)
assert(~isfile(path),'YawMask:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'YawMask:Output','Cannot create result JSON.');
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char'); fwrite(fid,newline,'char');
end

function h=sha256_file(path)
fid=fopen(path,'rb'); assert(fid>=0,'YawMask:File','Cannot read %s.',path);
c=onCleanup(@()fclose(fid)); bytes=fread(fid,inf,'*uint8'); %#ok<NASGU>
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(bytes);
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
