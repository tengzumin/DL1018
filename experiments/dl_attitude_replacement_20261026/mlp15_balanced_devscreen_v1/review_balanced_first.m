function review=review_balanced_first()
% Root review: independent quaternion scoring and deployed nominal-model audit.
study=fileparts(mfilename('fullpath'));research=fileparts(study);
release=jsondecode(fileread(fullfile(study,'RELEASE_v2.json')));
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));rec=manifest.records(1);
status=jsondecode(fileread(fullfile(study,'runs',rec.scene_id,'run_status.json')));
rawPath=fullfile(study,'runs',rec.scene_id,'raw_run.mat');
assert(strcmpi(hash_file(rawPath),status.raw_sha256));
raw=load(rawPath,'log','scene');
addpath(fullfile(release.runtime_root,'matlab','runtime'));activate_paired_runner();
p=prepare_mlp15_dev72_no_plant(rec.payload_path);
teacher=jsondecode(fileread(fullfile(research,'mlp15_c5_teacher_redistill_v1','DATASET_MANIFEST_v1.json')));
expectedJ0=diag(double(teacher.fixed_J0_reference.diagonal_kg_m2));
j0Error=max(abs(double(p.cfg.attitude_replacement.J0_controller_fixed_kgm2)-expectedJ0),[],'all');
assert(j0Error<1e-14,'Review:J0','Deployed fixed J0 differs from the C5 teacher.');
L=raw.log;X=double(L.state);acc=double(raw.scene.reference.acceleration);
yaw=double(raw.scene.reference.yaw(:));acc(:,3)=acc(:,3)+p.cfg.plant.g;
A=cos(yaw).*acc(:,1)+sin(yaw).*acc(:,2);B=sin(yaw).*acc(:,1)-cos(yaw).*acc(:,2);
roll=atan2(B,hypot(acc(:,3),A));pitch=atan2(A,acc(:,3));normTilt=hypot(roll,pitch);
scale=min(1,p.cfg.control.limits.max_tilt./max(normTilt,eps));
targetQ=quat([roll.*scale,pitch.*scale,yaw]);actualQ=quat(X(:,7:9));
theta=2*acos(min(1,abs(sum(targetQ.*actualQ,2))));so3=sqrt(mean(theta.^2));
q=sqrt(mean(sum((X(:,1:3)-double(raw.scene.reference.position)).^2,2)));
assert(abs(q-status.score.Q_m)<1e-12&&abs(so3-status.score.SO3_rad)<1e-10);
review=struct('root_approved',logical(status.engineering_pass),'first_raw_sha256',status.raw_sha256, ...
    'review_type','ROOT_INDEPENDENT_QUATERNION_SCORE_AND_J0','Plant_calls',0,'TEST_read',false, ...
    'independent_Q_m',q,'independent_SO3_rad',so3,'fixed_J0_max_abs_difference_kgm2',j0Error, ...
    'command_filter_acceleration_limit_rads2',double(p.cfg.control.command_filter.acceleration_limit(:)).', ...
    'command_filter_wn_radps',double(p.cfg.control.command_filter.wn(:)).', ...
    'source_script_sha256',hash_file([mfilename('fullpath') '.m']));
path=fullfile(study,'FIRST_REVIEW.json');assert(~isfile(path));
fid=fopen(path,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(review,'PrettyPrint',true));disp(review);
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
