function report=audit_head_attempt(sceneId)
% Root raw replay: rederive legal features, past residual, and pre-update output.
here=fileparts(mfilename('fullpath'));study=fileparts(here);
out=fullfile(here,[sceneId '_AUDIT.json']);assert(~isfile(out));
release=jsondecode(fileread(fullfile(study,'RELEASE.json')));
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));
rec=manifest.records(strcmp({manifest.records.scene_id},sceneId));assert(isscalar(rec));
runDir=fullfile(study,'runs',sceneId);status=jsondecode(fileread(fullfile(runDir,'run_status.json')));
rawPath=fullfile(runDir,'raw_run.mat');assert(strcmpi(hash_file(rawPath),status.raw_sha256));
raw=load(rawPath,'log','scene','runIdentity');L=raw.log;X=double(L.state);model=load(release.model_path);
assert(strcmpi(raw.runIdentity.release_sha256,hash_file(fullfile(study,'RELEASE.json')))&& ...
    strcmpi(raw.runIdentity.model_sha256,release.model_sha256)&&L.mlp15_causal_head_enabled&& ...
    ~L.mlp15_variable_inertia_reconstruction_used&&~L.gate_feedforward_enabled&&~L.gate_observer_enabled&& ...
    ~any(L.rbf_update_flag(:))&&all(abs(double(L.attitude_rbf_compensation_torque_Nm(:)))<1e-12));
J0=double(release.fixed_J0_kgm2);scale=double(model.target_rms(:));
traces=L.mlp15_attitude_trace;events=find(~cellfun(@isempty,traces));assert(numel(events)==1999);
history=zeros(13,14);W=zeros(33,3);P=10*eye(33);lastPhi=zeros(33,1);lastBase=zeros(3,1);prior=0;priorBeta=0;
featureError=0;outputError=0;observedError=0;weightError=0;torqueError=0;covarianceError=0;
updates=0;projections=0;clips=0;firstCorrection=20001;firstUpdateTime=NaN;
for i=1:numel(events)
    k=events(i);z=traces{k};d=z.causal_head;
    e=double(L.filtered_attitude_reference(k,:)-X(k,7:9)).';
    feature=[atan2(sin(e),cos(e));X(k,10:12).';double(L.attitude_bs_nominal_torque_Nm(k,:)).';double(L.arms.command(k,:)).'];
    assert(z.sample_index==k&&abs(z.time_s-L.time(k))<1e-12&&d.enabled&& ...
        ~z.rbf_output_enabled&&~z.rbf_update_enabled&&~z.time_varying_inertia_reconstruction_used);
    featureError=max(featureError,max(abs(feature-double(z.feature_raw(:)))));
    xnorm=(feature-double(model.input_mean(:)))./double(model.input_std(:));
    window=[history,xnorm];history=window(:,2:end);
    h=double(model.fc1_weight)*window(:)+double(model.fc1_bias(:));h=h./(1+exp(-h));
    h=double(model.fc2_weight)*h+double(model.fc2_bias(:));h=h./(1+exp(-h));
    base=(double(model.head_weight)*h+double(model.head_bias(:))).*scale;
    phi=[h;1];phi=phi/norm(phi);prediction=base+scale.*(W.'*phi);
    outputError=max(outputError,max(abs(prediction-double(z.raw_residual_rad_s2(:)))));
    weightError=max(weightError,max(abs(W-double(d.weight_before)),[],'all'));
    if norm(W,'fro')>1e-14,firstCorrection=min(firstCorrection,k);end
    clipped=min(max(prediction,-[45;45;4.7124]),[45;45;4.7124]);
    clips=clips+any(abs(prediction-clipped)>1e-12);
    torque=J0*(double(z.beta)*clipped);
    torqueError=max(torqueError,max(abs(torque-double(L.attitude_compensation_applied_torque_Nm(k,:)).')));
    if prior>0
        segment=X(prior:k-1,10:12);omegaEnd=X(k,10:12);omegaStart=X(prior,10:12);
        span=double(L.time(k)-L.time(prior));
        gyro=cross(segment,segment*J0.',2);issued=double(L.requested_generalized(prior:k-1,2:4));
        observed=((omegaEnd-omegaStart)/span+mean((gyro-issued)/J0.',1)).';
        observedError=max(observedError,max(abs(observed-double(d.observation_residual_rad_s2(:)))));
        assert(d.previous_feature_sample_index==prior&&d.issued_torque_max_sample_index==k-1&& ...
            abs(d.observation_start_time_s-L.time(prior))<1e-12&& ...
            abs(d.observation_end_time_s-L.time(k))<1e-12);
        eligible=priorBeta>=1&&z.beta>=1;assert(d.update_executed==eligible);
        if eligible
            Pprior=P/.999;K=(Pprior*lastPhi)/(1+lastPhi.'*Pprior*lastPhi);
            W=W+K*(observed./scale-lastBase-W.'*lastPhi).';
            A=eye(33)-K*lastPhi.';P=A*Pprior*A.'+K*K.';P=(P+P.')/2;
            [~,flag]=chol(P);assert(flag==0);
            normW=norm(W,'fro');projected=normW>20;
            if projected,W=W*(20/normW);end
            assert(d.projection_active==projected);projections=projections+projected;
            covarianceError=max(covarianceError,max(abs(diag(P)-double(d.covariance_diagonal_after))));
            updates=updates+1;if isnan(firstUpdateTime),firstUpdateTime=L.time(k);end
        end
    end
    weightError=max(weightError,max(abs(W-double(d.weight_after)),[],'all'));
    lastPhi=phi;lastBase=base./scale;prior=k;priorBeta=z.beta;
end
assert(featureError<1e-10&&outputError<1e-8&&observedError<1e-8&&weightError<1e-7&& ...
    torqueError<1e-10&&covarianceError<1e-7&&updates>0);
frozen=load(rec.frozen_raw_path,'log','scene');b=load(rec.b_raw_path,'log','scene');c5=load(rec.c5_raw_path,'log','scene');
for other={frozen.scene,b.scene,c5.scene}
    for field={'time','initial_state','reference','arms','environment_wind_I'}
        name=field{1};assert(isequaln(raw.scene.(name),other{1}.(name)));
    end
end
assert(strcmpi(hash_file(rec.frozen_raw_path),rec.frozen_raw_sha256)&& ...
    strcmpi(hash_file(rec.b_raw_path),rec.b_raw_sha256)&&strcmpi(hash_file(rec.c5_raw_path),rec.c5_raw_sha256));
warmupError=max(abs(X(1:firstCorrection,:)-double(frozen.log.state(1:firstCorrection,:))),[],'all');
assert(warmupError<1e-10,'HeadAudit:Warmup','Candidate differs before the head can affect control.');
safe=strcmp(L.status,'STABLE')&&isempty(L.safety_stop_reason)&&L.complete_transitions&& ...
    ~any(L.motor_saturated(:))&&~any(L.generalized_clipped(:));
report=struct('scene_id',sceneId,'engineering_pass',safe,'raw_sha256',status.raw_sha256, ...
    'Plant_calls_by_audit',0,'TEST_read',false,'candidate',metrics(L,raw.scene,release), ...
    'frozen_MLP',metrics(frozen.log,raw.scene,release),'B',metrics(b.log,raw.scene,release), ...
    'C5',metrics(c5.log,raw.scene,release),'head_update_count',updates,'weight_projection_count',projections, ...
    'residual_dmax_clipped_event_count',clips,'tilt_projection_samples',nnz(L.tilt_limited), ...
    'first_update_time_s',firstUpdateTime,'first_corrected_output_time_s',double(L.time(firstCorrection)), ...
    'max_feature_error',featureError,'max_raw_output_replay_error_rad_s2',outputError, ...
    'max_observed_residual_replay_error_rad_s2',observedError,'max_weight_replay_error',weightError, ...
    'max_applied_torque_replay_error_Nm',torqueError,'max_covariance_diagonal_replay_error',covarianceError, ...
    'max_state_difference_before_first_corrected_output',warmupError, ...
    'source_script_sha256',hash_file([mfilename('fullpath') '.m']));
fid=fopen(out,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));
end

function s=metrics(L,scene,release)
X=double(L.state);t=double(L.time(:));assert(size(X,1)==20001&&L.last_transition==20000&&all(isfinite(X(:))));
e=X(:,1:3)-double(scene.reference.position);acc=double(scene.reference.acceleration);
yaw=double(scene.reference.yaw(:));acc(:,3)=acc(:,3)+release.gravity_mps2;
A=cos(yaw).*acc(:,1)+sin(yaw).*acc(:,2);B=sin(yaw).*acc(:,1)-cos(yaw).*acc(:,2);
r=atan2(B,hypot(acc(:,3),A));p=atan2(A,acc(:,3));scale=min(1,release.max_tilt_rad./max(hypot(r,p),eps));
theta=angle_error(X(:,7:9),[r.*scale,p.*scale,yaw]);
inner=angle_error(X(1:20000,7:9),double(L.filtered_attitude_reference));
s=struct('Q_m',sqrt(mean(sum(e.^2,2))),'SO3_rad',sqrt(mean(theta.^2)), ...
    'inner_tracking_rad',sqrt(mean(inner.^2)),'RMSE_xyz_m',sqrt(mean(e.^2,1)), ...
    'Q_0_5_m',sqrt(mean(sum(e(t<5,:).^2,2))),'Q_15_20_m',sqrt(mean(sum(e(t>=15,:).^2,2))), ...
    'peak_position_error_m',max(vecnorm(e,2,2)),'peak_SO3_rad',max(theta), ...
    'motor_saturation_samples',nnz(any(L.motor_saturated,2)),'generalized_clip_samples',nnz(any(L.generalized_clipped,2)));
end

function theta=angle_error(a,b)
qa=quat(a);qb=quat(b);theta=2*acos(min(1,abs(sum(qa.*qb,2))));
end

function q=quat(e)
c=cos(e/2);s=sin(e/2);
q=[c(:,1).*c(:,2).*c(:,3)+s(:,1).*s(:,2).*s(:,3), ...
    s(:,1).*c(:,2).*c(:,3)-c(:,1).*s(:,2).*s(:,3), ...
    c(:,1).*s(:,2).*c(:,3)+s(:,1).*c(:,2).*s(:,3), ...
    c(:,1).*c(:,2).*s(:,3)-s(:,1).*s(:,2).*c(:,3)];
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
