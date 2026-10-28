function report=review_balanced_twelve(studyOverride,candidateName)
% Independently score external task attitude and actual inner-loop tracking.
study=fileparts(mfilename('fullpath'));research=fileparts(study);project=fileparts(fileparts(research));
if nargin>=1,study=studyOverride;end
if nargin<2,candidateName='BALANCED_MLP15';end
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));
receipt=jsondecode(fileread(fullfile(project,'experiments','attitude_physics_inertia_observer_20261025', ...
    'holdout_gate_inspection_v2','C5_R_TASK_BINDING_PILOT_RECEIPT_v5.json')));
snapshot=load(receipt.input_records.c5_snapshot_mat.path,'cfg');cfg=snapshot.cfg;
nScenes=numel(manifest.records);rows=cell(nScenes,3);
for i=1:nScenes
    rec=manifest.records(i);candidate=fullfile(study,'runs',rec.scene_id,'raw_run.mat');
    status=jsondecode(fileread(fullfile(study,'runs',rec.scene_id,'run_status.json')));
    paths={candidate,rec.b_raw_path,rec.c5_raw_path};names={candidateName,'B','C5_RBF'};
    hashes={status.raw_sha256,rec.b_raw_sha256,rec.c5_raw_sha256};
    for j=1:3
        assert(strcmpi(hash_file(paths{j}),hashes{j}));pack=load(paths{j},'log','scene');L=pack.log;
        if j==1,referenceScene=pack.scene;else,same_scene(pack.scene,referenceScene);end
        n=numel(L.transition_time);assert(n==20000&&size(L.state,1)==20001);
        e=double(L.state(:,1:3))-double(pack.scene.reference.position);
        q=sqrt(mean(sum(e.^2,2)));xyz=sqrt(mean(e.^2,1));
        acc=double(pack.scene.reference.acceleration);yaw=double(pack.scene.reference.yaw(:));
        acc(:,3)=acc(:,3)+double(cfg.plant.g);
        A=cos(yaw).*acc(:,1)+sin(yaw).*acc(:,2);B=sin(yaw).*acc(:,1)-cos(yaw).*acc(:,2);
        roll=atan2(B,hypot(acc(:,3),A));pitch=atan2(A,acc(:,3));
        scale=min(1,double(cfg.control.limits.max_tilt)./max(hypot(roll,pitch),eps));
        taskError=geodesic(double(L.state(:,7:9)),[roll.*scale,pitch.*scale,yaw]);
        innerError=geodesic(double(L.state(1:n,7:9)),double(L.filtered_attitude_reference));
        outerError=geodesic(double(L.state(1:n,7:9)),double(L.command_filter_target_euler));
        filterError=geodesic(double(L.filtered_attitude_reference),double(L.command_filter_target_euler));
        erpy=double(L.filtered_attitude_reference)-double(L.state(1:n,7:9));
        erpy=atan2(sin(erpy),cos(erpy));
        rpy=double(L.state(:,7:9));cosInclination=cos(rpy(:,1)).*cos(rpy(:,2));
        physicalTilt=acos(min(1,max(-1,cosInclination)));
        cost=double(L.controller_call_time_s(:));cost=cost(isfinite(cost)&cost>0);
        row=struct('scene_id',rec.scene_id,'method',names{j},'raw_sha256',hashes{j}, ...
            'Q_m',q,'position_axis_RMSE_m',xyz,'task_SO3_RMSE_rad',sqrt(mean(taskError.^2)), ...
            'inner_filtered_reference_SO3_RMSE_rad',sqrt(mean(innerError.^2)), ...
            'inner_filtered_reference_euler_RMSE_xyz_rad',sqrt(mean(erpy.^2,1)), ...
            'outer_target_SO3_RMSE_rad',sqrt(mean(outerError.^2)), ...
            'filter_to_outer_SO3_RMSE_rad',sqrt(mean(filterError.^2)), ...
            'peak_position_error_m',max(vecnorm(e,2,2)),'peak_inner_tracking_error_rad',max(innerError), ...
            'actual_max_physical_tilt_deg',max(physicalTilt)*180/pi, ...
            'tilt_samples',nnz(L.tilt_limited),'motor_saturation_samples',nnz(any(L.motor_saturated,2)), ...
            'generalized_clip_samples',nnz(any(L.generalized_clipped,2)), ...
            'controller_call_median_s',median(cost), ...
            'controller_call_p95_s',prctile(cost,95));
        if j==1
            assert(abs(q-status.score.Q_m)<1e-12);
            if isfield(status.score,'SO3_rad')
                assert(abs(row.task_SO3_RMSE_rad-status.score.SO3_rad)<1e-10);
            end
        end
        rows{i,j}=row;
    end
end
summary=cell(1,3);
for j=1:3
    r=[rows{:,j}];summary{j}=struct('method',r(1).method,'scene_count',nScenes, ...
        'macro_Q_m',mean([r.Q_m]),'macro_task_SO3_rad',mean([r.task_SO3_RMSE_rad]), ...
        'macro_inner_tracking_SO3_rad',mean([r.inner_filtered_reference_SO3_RMSE_rad]), ...
        'macro_filter_to_outer_SO3_rad',mean([r.filter_to_outer_SO3_RMSE_rad]));
end
report=struct('schema','ROOT_BALANCED_DEVSCREEN_TARGET_REVIEW_V1','Plant_calls',0,'TEST_read',false, ...
    'independent_quaternion_recomputation',true,'rows',[rows{:}],'summary',[summary{:}], ...
    'interpretation','External task pose, filtered-reference tracking and filter lag are distinct metrics; they are not additive.', ...
    'source_script_sha256',hash_file([mfilename('fullpath') '.m']));
path=fullfile(study,'ROOT_TARGET_REVIEW.json');assert(~isfile(path));
fid=fopen(path,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));
writetable(struct2table(report.rows),fullfile(study,'ROOT_TARGET_REVIEW.csv'));disp([summary{:}]);
end

function theta=geodesic(a,b)
qa=quat(a);qb=quat(b);theta=2*acos(min(1,abs(sum(qa.*qb,2))));
end

function q=quat(e)
c=cos(e/2);s=sin(e/2);
q=[c(:,1).*c(:,2).*c(:,3)+s(:,1).*s(:,2).*s(:,3), ...
    s(:,1).*c(:,2).*c(:,3)-c(:,1).*s(:,2).*s(:,3), ...
    c(:,1).*s(:,2).*c(:,3)+s(:,1).*c(:,2).*s(:,3), ...
    c(:,1).*c(:,2).*s(:,3)-s(:,1).*s(:,2).*c(:,3)];
end

function same_scene(a,b)
for name={'time','initial_state','reference','arms','environment_wind_I'}
    f=name{1};assert(isequaln(a.(f),b.(f)));
end
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
