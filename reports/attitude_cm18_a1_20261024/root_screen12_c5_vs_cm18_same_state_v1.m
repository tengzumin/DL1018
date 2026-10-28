function result = root_screen12_c5_vs_cm18_same_state_v1()
%ROOT_SCREEN12_C5_VS_CM18_SAME_STATE_V1 Frozen-map replay on old C5 states.
% Uses logged states only. It does not execute the engine or integrate state.
reportDir=fileparts(mfilename('fullpath')); root=fileparts(fileparts(reportDir));
expDir=fullfile(root,'experiments','attitude_cm18_a1_20261024');
oldDir=fullfile(root,'experiments','position_axis_coordinate_c5_dev72_20261023','runs_dev72_v3');
modelPath=fullfile(expDir,'deployment_v1','deployment_parameters_v1.json');
modelSha='ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae';
assert(strcmp(sha256_file(modelPath),modelSha),'OldC5Diag:ModelHash','Deployment artifact hash changed.');
model=jsondecode(fileread(modelPath)); p=model.parameters;
oldPath=path; pathCleanup=onCleanup(@()path(oldPath)); %#ok<NASGU>
addpath(fullfile(root,'matlab','core'),'-begin'); addpath(fullfile(expDir,'matlab'),'-begin');
ids={'DL1018_DEV_T1_C15_W14','DL1018_DEV_T3_C15_W14'};
expected={ ...
 '6c72ae52e3f39af36442935468af7d2a047af460b845223167ee206d0dc96707', ...
 '2df0e35d32bff888c3225638d468b2e796d8942387002a48cf53b4242d3c6a27'};
runs=cell(2,1);
for q=1:2
    runDir=fullfile(oldDir,ids{q},'C5_AXIS_MASK_M110','attempt_01');
    rawPath=fullfile(runDir,'raw_run.mat'); startPath=fullfile(runDir,'run_start.mat');
    assert(isfile(rawPath)&&isfile(startPath),'OldC5Diag:RawMissing','Missing C5 raw/start for %s.',ids{q});
    rawSha=sha256_file(rawPath); assert(strcmp(rawSha,expected{q}), ...
        'OldC5Diag:RawHash','Pinned old C5 raw hash changed for %s.',ids{q});
    runs{q}=diagnose(ids{q},rawPath,startPath,rawSha,model,p,root);
end
result=struct('schema','ROOT_SCREEN12_C5_VS_CM18_SAME_STATE_V1', ...
    'status','PASS_OFFLINE_SAME_STATE_ONLY','deployment_json_sha256',modelSha, ...
    'checkpoint_sha256',model.identity.checkpoint_sha256,'selected_step',model.identity.selected_step, ...
    'scenes',[runs{:}],'scope',struct('plant_calls',0,'engine_calls',0,'state_integrated',false, ...
    'episode_steps',0,'optimizer_steps',0,'training',false,'TEST_accessed',false, ...
    'interpretation','Compares actual old C5 compensation and a frozen CM18 current-action counterfactual at each same old C5 recorded state; this is not a closed-loop causal test.'));
out=fullfile(reportDir,'ROOT_SCREEN12_C5_VS_CM18_SAME_STATE_DIAGNOSTIC_v1.json');
assert(~isfile(out),'OldC5Diag:NoOverwrite','Refusing to overwrite existing output.');
write_json(out,result);
end

function R=diagnose(id,rawPath,startPath,rawSha,model,p,root)
rsP=load(startPath,'runStart'); raw=load(rawPath,'log','scene');
assert(isfield(rsP,'runStart')&&all(isfield(raw,{'log','scene'})), ...
    'OldC5Diag:MatSchema','Old C5 raw/start MAT structure incomplete.');
rs=rsP.runStart; L=raw.log; s=raw.scene; cfg=rs.cfg;
assert(strcmp(char(string(s.scene_id)),id)&&strcmpi(cfg.controller_morphology_mode,'fixed')&& ...
    strcmpi(cfg.controller_inertia_derivative_mode,'full')&& ...
    logical(rs.opts.formal_rbf_baseline)&&logical(rs.opts.rbf_attitude_enabled)&& ...
    isequal(double(rs.opts.position_coordinate_mask(:)).',[1,1,0]), ...
    'OldC5Diag:ControllerIdentity','Old C5 configuration differs from the matched fixed C5 controller.');
n=20000; dt=diff(double(s.time(:))); event=find(logical(L.attitude_event_flag(:)));
assert(numel(dt)==n&&isequal(event,(11:10:19991).')&&all(abs(dt-.001)<1e-12), ...
    'OldC5Diag:Schedule','Unexpected 1 ms/100 Hz old C5 trajectory schedule.');
required={'state','transition_time','requested_generalized','realized_generalized','wind_torque_B', ...
    'attitude_bs_nominal_torque_Nm','attitude_compensation_applied_torque_Nm', ...
    'filtered_attitude_reference','filtered_attitude_rate','command_filter_acceleration_applied_rads2', ...
    'motor_command','motor_time_constant_s'};
assert(all(isfield(L,required)),'OldC5Diag:LogFields','Old C5 raw lacks required physics fields.');
PplantNom=simulation_parameters(cfg,cfg.plant.arm_initial(:),zeros(4,1));
Pnom=controller_parameters(cfg,PplantNom,'fixed'); J0=double(Pnom.inertia); Jdot0=double(Pnom.inertia_dot_for_bs);
C0=double(Pnom.allocation.C); mass=double(Pnom.mass);
request=double(L.requested_generalized); command=double(s.arms.command);
assert(isequal(size(request),[n,4])&&isequal(size(command),[n+1,4]), ...
    'OldC5Diag:Shape','Old C5 request/command shapes differ.');
z=zeros(n,4); for k=2:n,z(k,:)=z(k-1,:)+dt(k-1)*command(k-1,:);end
motorTc=0; if isfield(rs.opts,'motor_time_constant_s'),motorTc=double(rs.opts.motor_time_constant_s);end
assert(motorTc==0&&all(abs(double(L.motor_time_constant_s(:)))<1e-12), ...
    'OldC5Diag:MotorDynamics','Old C5 raw does not have the pinned zero motor time constant.');
dmax=double(cfg.rbf.attitude.dmax(:)).'; betaRise=double(cfg.rbf.attitude.beta_rise_time);
assert(isequal(size(dmax),[1,3])&&all(dmax==[45,45,4.7124])&&betaRise==2.2, ...
    'OldC5Diag:OutputContract','Clip/beta limits do not match frozen CM18 output.');
oldComp=double(L.attitude_compensation_applied_torque_Nm);
assert(isequal(size(oldComp),[n,3]),'OldC5Diag:CompensationShape','Old compensation shape mismatch.');
ne=numel(event); alphaBS=zeros(ne,3); alphaOld=zeros(ne,3); alphaZero=zeros(ne,3); alphaCM=zeros(ne,3);
rawPred=zeros(ne,3); oldApplied=zeros(ne,3); cmApplied=zeros(ne,3); Gall=zeros(3,3,ne);
clipCount=zeros(1,3); genClip=false(ne,4); sat=false(ne,4);
maxOldClosure=0; maxRequestedClosure=0; maxFreshG=0;
for q=1:ne
    k=event(q); w=double(L.state(k,10:12)).';
    ref=struct('euler',double(L.filtered_attitude_reference(k,:)).', ...
        'euler_rate',double(L.filtered_attitude_rate(k,:)).', ...
        'euler_acceleration',double(L.command_filter_acceleration_applied_rads2(k,:)).');
    [~,info]=attitude_bs_step(double(L.state(k,:)).',ref,zeros(3,1),Pnom);
    alphaBS(q,:)=double(info.nominal_body_angular_acceleration(:)).'; tauNom=double(info.nominal_moment(:));
    past=(k-10):(k-1); pastDt=dt(past);
    aPrevious=sum(request(past,2:4).*pastDt,1)/sum(pastDt);
    X=[w.',alphaBS(q,:),request(k,1)/mass,command(k,:),z(k,:),aPrevious];
    rawPred(q,:)=cm18_a1_forward_v1(X,p);
    clipped=max(min(rawPred(q,:),dmax),-dmax); clipCount=clipCount+(clipped~=rawPred(q,:));
    beta=min(k*dt(k)/betaRise,1); cmApplied(q,:)=beta*clipped;
    oldApplied(q,:)=(J0\oldComp(k,:).').';
    maxRequestedClosure=max(maxRequestedClosure,max(abs(request(k,2:4).'- ...
        (tauNom-oldComp(k,:).'))));
    Ptrue=simulation_parameters(cfg,double(s.arms.rho_true(k,:)).',double(s.arms.rhoDot_true(k,:)).');
    J=double(Ptrue.inertia); Jdot=double(Ptrue.inertia_dot); Ctrue=double(Ptrue.allocation.C);
    Mc=Ctrue/C0; G=J\(Mc(2:4,2:4)*J0); Gall(:,:,q)=G;
    realized=double(L.realized_generalized(k,:)).'; wind=double(L.wind_torque_B(k,:)).';
    alphaOld(q,:)=(J\(realized(2:4)+wind-cross(w,J*w)-Jdot*w)).';
    prev=double(L.motor_command(k-1,:)).';
    [zeroMotor,~,~]=allocate_control([request(k,1);tauNom],Pnom,Ptrue,prev);
    zeroWrench=Ctrue*(zeroMotor(:).^2);
    alphaZero(q,:)=(J\(zeroWrench(2:4)+wind-cross(w,J*w)-Jdot*w)).';
    [cmMotor,~,cmInfo]=allocate_control([request(k,1);tauNom-J0*cmApplied(q,:).'],Pnom,Ptrue,prev);
    cmWrench=Ctrue*(cmMotor(:).^2);
    alphaCM(q,:)=(J\(cmWrench(2:4)+wind-cross(w,J*w)-Jdot*w)).';
    genClip(q,:)=logical(cmInfo.generalized_command_clipped(:)).';
    sat(q,:)=logical(cmInfo.motor_saturated(:)).';
    maxOldClosure=max(maxOldClosure,max(abs(alphaOld(q,:).'- ...
        (alphaZero(q,:).'-G*oldApplied(q,:).'))));
    maxFreshG=max(maxFreshG,max(abs(alphaCM(q,:).'- ...
        (alphaZero(q,:).'-G*cmApplied(q,:).'))));
end
assert(maxRequestedClosure<1e-9&&maxOldClosure<1e-7&&maxFreshG<1e-7&& ...
    ~any(genClip(:))&&~any(sat(:)), ...
    'OldC5Diag:ActionClosure','C5 action, candidate allocator, or affine G closure failed.');
edges=[0 5;5 10;10 15;15 20]; t=double(L.transition_time(event)); phases=cell(4,1);
err0=alphaZero-alphaBS; errOld=alphaOld-alphaBS; errCM=alphaCM-alphaBS;
for q=1:4
    mask=t>=edges(q,1)&t<edges(q,2);
    phases{q}=struct('interval_s',edges(q,:),'event_count',nnz(mask), ...
        'zero_action_error_rms_rad_s2',rms_axis(err0(mask,:)), ...
        'zero_action_error_mean_rad_s2',mean_axis(err0(mask,:)), ...
        'actual_C5_error_rms_rad_s2',rms_axis(errOld(mask,:)), ...
        'actual_C5_error_mean_rad_s2',mean_axis(errOld(mask,:)), ...
        'CM18_same_state_error_rms_rad_s2',rms_axis(errCM(mask,:)), ...
        'CM18_same_state_error_mean_rad_s2',mean_axis(errCM(mask,:)));
end
meanG=mean(Gall,3); singular=zeros(ne,3);
for q=1:ne,singular(q,:)=svd(Gall(:,:,q));end
R=struct('scene_id',id,'raw_path',relative_path(root,rawPath),'raw_sha256',rawSha, ...
    'run_start_sha256',sha256_file(startPath),'run_start_schema',rs.schema, ...
    'old_controller_identity',struct('morphology_mode',cfg.controller_morphology_mode, ...
    'inertia_derivative_mode',cfg.controller_inertia_derivative_mode,'position_mask',double(rs.opts.position_coordinate_mask(:)).', ...
    'attitude_bs_k1',double(cfg.control.bs.attitude.k1(:)).','attitude_bs_k2',double(cfg.control.bs.attitude.k2(:)).', ...
    'legacy_attitude_rbf_enabled',logical(rs.opts.rbf_attitude_enabled)), ...
    'reconstruction',struct('event_count',ne,'max_abs_requested_torque_closure_Nm',maxRequestedClosure, ...
    'max_abs_old_C5_action_vs_G_acceleration_rad_s2',maxOldClosure, ...
    'max_abs_CM18_action_vs_G_acceleration_rad_s2',maxFreshG, ...
    'all_CM18_candidate_allocations_unclipped_unsaturated',true,'CM18_clip_counts_by_axis',clipCount), ...
    'effective_G',struct('definition','Jtrue^{-1} * (Ctrue*C0^{-1})(2:4,2:4) * J0', ...
    'mean_event_G',meanG,'event_singular_value_quantiles_0_50_95_100',qtiles(singular)), ...
    'same_state_actions',struct('zero_action_error_rms_rad_s2',rms_axis(err0), ...
    'actual_C5_error_rms_rad_s2',rms_axis(errOld),'CM18_candidate_error_rms_rad_s2',rms_axis(errCM), ...
    'actual_C5_error_mean_rad_s2',mean_axis(errOld),'CM18_candidate_error_mean_rad_s2',mean_axis(errCM)), ...
    'phase_summaries',[phases{:}]);
end
function v=rms_axis(x),v=sqrt(mean(double(x).^2,1));end
function v=mean_axis(x),v=mean(double(x),1);end
function q=qtiles(x)
x=sort(double(x),1); n=size(x,1); ix=max(1,min(n,round([0 .5 .95 1]*(n-1))+1)); q=x(ix,:);
end
function s=sha256_file(p)
fid=fopen(p,'rb'); assert(fid>=0,'OldC5Diag:FileOpen','Cannot read %s.',p);
c=onCleanup(@()fclose(fid)); bytes=fread(fid,inf,'*uint8'); %#ok<NASGU>
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(bytes);
s=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function p=relative_path(root,p)
root=char(java.io.File(root).getCanonicalPath()); p=char(java.io.File(p).getCanonicalPath());
assert(startsWith(lower(p),[lower(root),filesep]),'OldC5Diag:Path','Path escapes repository.');
p=strrep(p(length(root)+2:end),filesep,'/');
end
function write_json(p,value)
fid=fopen(p,'w'); assert(fid>=0,'OldC5Diag:Output','Cannot create result.');
c=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(value),'char'); fwrite(fid,newline,'char');
end
