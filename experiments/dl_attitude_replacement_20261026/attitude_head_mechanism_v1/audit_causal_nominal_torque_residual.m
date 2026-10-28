function report=audit_causal_nominal_torque_residual()
% Past-only nominal residual observable from gyro and issued body torque.
% This is an interval-average approximation, not instantaneous Plant truth.
here=fileparts(mfilename('fullpath'));research=fileparts(here);
out=fullfile(here,'CAUSAL_NOMINAL_TORQUE_RESIDUAL.json');assert(~isfile(out));
manifestPath=fullfile(research,'mlp15_distribution_countercheck_v1','MANIFEST.json');
manifest=jsondecode(fileread(manifestPath));
teacher=jsondecode(fileread(fullfile(research,'mlp15_c5_teacher_redistill_v1','DATASET_MANIFEST_v1.json')));
J0=diag(double(teacher.fixed_J0_reference.diagonal_kg_m2));
% Synthetic nominal dynamics: backward interval accounting must return zero.
omega=[linspace(0,.2,31).',sin((0:30)'*.01),cos((0:30)'*.01)];dt=.001;
gyro=cross(omega(1:end-1,:),omega(1:end-1,:)*J0.',2);
torque=(diff(omega)/dt)*J0.'+gyro;
synthetic=interval_residual(omega,torque,J0,1,31,dt);
assert(max(abs(synthetic))<1e-12,'Target:Sign','Nominal zero-residual accounting failed.');
rows=cell(numel(manifest.records),1);
for i=1:numel(manifest.records)
    rec=manifest.records(i);assert(strcmpi(hash_file(rec.c5_raw_path),rec.c5_raw_sha256));
    raw=load(rec.c5_raw_path,'log');L=raw.log;X=double(L.state);time=double(L.time(:));
    moments=double(L.requested_generalized(:,2:4));
    assert(size(X,1)==20001&&size(moments,1)==20000&&all(isfinite(moments(:))));
    events=find(logical(L.attitude_event_flag));assert(numel(events)==1999);
    target=zeros(numel(events),3);applied=zeros(numel(events),3);predictionIndex=zeros(numel(events),1);
    for j=1:numel(events)
        k=events(j);prior=max(1,k-10);span=time(k)-time(prior);
        assert(span>0&&span<=.0100000001);
        target(j,:)=interval_residual(X(:,10:12),moments,J0,prior,k,.001);
        applied(j,:)=mean(double(L.attitude_compensation_applied_torque_Nm(prior:k-1,:))/J0.',1);
        predictionIndex(j)=prior;
    end
    assert(all(predictionIndex<events)&&all(isfinite(target(:))));
    mature=time(events)>=3;difference=target(mature,:)-applied(mature,:);
    correlation=zeros(1,3);
    for axis=1:3
        C=corrcoef(target(mature,axis),applied(mature,axis));correlation(axis)=C(1,2);
    end
    dmax=[45,45,4.7124];
    rows{i}=struct('scene_id',rec.scene_id,'source_raw_sha256',rec.c5_raw_sha256, ...
        'event_count',numel(events),'interval_s',.01,'all_observations_strictly_after_feature_index',true, ...
        'mature_observed_residual_RMS_rad_s2',sqrt(mean(target(mature,:).^2,1)), ...
        'mature_RBF_applied_RMS_rad_s2',sqrt(mean(applied(mature,:).^2,1)), ...
        'mature_observed_minus_RBF_RMSE_rad_s2',sqrt(mean(difference.^2,1)), ...
        'mature_observed_RBF_correlation',correlation, ...
        'observed_target_outside_dmax_axis_counts',sum(abs(target)>dmax,1), ...
        'maximum_abs_interval_residual_rad_s2',max(abs(target),[],1));
end
report=struct('schema','CAUSAL_FIXED_J0_TORQUE_RESIDUAL_AUDIT_V1', ...
    'status','PASS_PAST_ONLY_NOMINAL_ACCOUNTING','Plant_calls',0,'TEST_read',false, ...
    'training_jobs',0,'inertia_reconstruction_used',false,'Plant_truth_read',false, ...
    'inputs',{{'past measured body omega','past issued controller body torque','fixed nominal J0','timestamps'}}, ...
    'target_formula','mean(J0^-1*(J0*omega_dot + omega cross (J0*omega) - tau_issued)) over the preceding 10 ms', ...
    'deployment_assumption','Ideal gyro/state feedback as in the existing simulation; noisy derivative robustness not established.', ...
    'interpretation','Interval-average nominal-model residual. RBF output is an offline comparator only; no claim that it is a deployable measurement.', ...
    'synthetic_nominal_zero_residual_max_abs',max(abs(synthetic)), ...
    'fixed_J0_kgm2',J0,'source_script_sha256',hash_file([mfilename('fullpath') '.m']), ...
    'manifest_sha256',hash_file(manifestPath),'rows',[rows{:}]);
fid=fopen(out,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));
fprintf('%s: %d scenes, zero Plant calls.\n',report.status,numel(rows));
end

function residual=interval_residual(omega,torque,J0,first,last,dt)
segment=omega(first:last-1,:);span=(last-first)*dt;
gyro=cross(segment,segment*J0.',2);
residual=(omega(last,:)-omega(first,:))/span+mean((gyro-torque(first:last-1,:))/J0.',1);
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
