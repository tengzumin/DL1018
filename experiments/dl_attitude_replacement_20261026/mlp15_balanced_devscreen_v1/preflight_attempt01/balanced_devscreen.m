function result=balanced_devscreen(action)
% Frozen-model DEV screen; all control code and baseline raw are reused read-only.
study=fileparts(mfilename('fullpath'));releasePath=fullfile(study,'RELEASE.json');
release=jsondecode(fileread(releasePath));
assert(release.max_Plant_calls==12&&~release.TEST_read);
lockPath=fullfile(study,'SOURCE_LOCK.json');
assert(strcmpi(hash_file(lockPath),release.source_lock_sha256));
lock=jsondecode(fileread(lockPath));
for i=1:numel(lock.files)
    assert(strcmpi(hash_file(lock.files(i).path),lock.files(i).sha256), ...
        'Screen:SourceIdentity','Changed frozen input: %s.',lock.files(i).path);
end
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));records=manifest.records;
assert(numel(records)==12&&~manifest.TEST_read);
addpath(fullfile(release.runtime_root,'matlab','runtime'));activate_paired_runner();
weights=load(release.model_path);result=struct;
switch action
    case 'preflight'
        assert(~isfile(fullfile(study,'PREFLIGHT.json')));
        diag=checkcode(fullfile(study,'balanced_devscreen.m'),'-id');
        assert(isempty(diag),'Screen:CodeAnalyzer','New runner has Code Analyzer diagnostics.');
        for i=1:numel(records)
            p=prepare(records(i),weights,release); %#ok<NASGU>
            fprintf('PREFLIGHT %02d/12 %s\n',i,records(i).scene_id);
        end
        result=struct('status','PASS_NO_PLANT','Plant_calls',0,'TEST_read',false, ...
            'source_lock_sha256',release.source_lock_sha256,'scene_count',12);
        write_json(fullfile(study,'PREFLIGHT.json'),result);
    case {'run_first','run_remaining'}
        preflight=jsondecode(fileread(fullfile(study,'PREFLIGHT.json')));
        assert(strcmp(preflight.status,'PASS_NO_PLANT')&& ...
            strcmpi(preflight.source_lock_sha256,release.source_lock_sha256));
        if strcmp(action,'run_first')
            indices=1;assert(strcmp(records(1).scene_id,release.first_scene_id));
        else
            review=jsondecode(fileread(fullfile(study,'FIRST_REVIEW.json')));
            first=jsondecode(fileread(fullfile(study,'runs',records(1).scene_id,'run_status.json')));
            assert(review.root_approved&&first.engineering_pass&& ...
                strcmpi(review.first_raw_sha256,first.raw_sha256));
            indices=2:12;
        end
        for i=indices
            rec=records(i);runDir=fullfile(study,'runs',rec.scene_id);
            assert(~isfolder(runDir),'Screen:Duplicate','Existing attempt must be preserved.');
            markers=dir(fullfile(study,'runs','**','attempt_started.marker'));
            assert(numel(markers)<release.max_Plant_calls);
            p=prepare(rec,weights,release);mkdir(runDir);
            start=struct('scene_id',rec.scene_id,'started_utc',utc_now(), ...
                'model_sha256',release.model_sha256,'release_sha256',hash_file(releasePath), ...
                'source_lock_sha256',release.source_lock_sha256,'payload_sha256',rec.payload_sha256, ...
                'b_raw_sha256',rec.b_raw_sha256,'c5_raw_sha256',rec.c5_raw_sha256, ...
                'external_identity_sha256',rec.external_identity_sha256,'TEST_read',false, ...
                'position_options_sha256',p.identity.common.position_options_sha256, ...
                'max_tilt_deg',30,'dmax_rad_s2',[45 45 4.7124]);
            write_json(fullfile(runDir,'attempt_started.marker'),start);
            write_json(fullfile(runDir,'run_start.json'),start);
            try
                started=tic;log=run_mlp15_dev72_closed_loop(p.scene,p.cfg,p.opts);
                elapsed=toc(started);scene=p.scene;runIdentity=start;
                rawPath=fullfile(runDir,'raw_run.mat');save(rawPath,'log','scene','runIdentity','-v7.3');
                row=score(log,scene,p.cfg,rec);
                status=struct('state','COMPLETED','scene_id',rec.scene_id,'Plant_calls',1, ...
                    'finished_utc',utc_now(),'wall_seconds',elapsed,'raw_sha256',hash_file(rawPath), ...
                    'engineering_pass',row.engineering_pass,'score',row,'TEST_read',false);
                write_json(fullfile(runDir,'run_status.json'),status);
                fprintf('DONE %s Q %.4f B %.4f C5 %.4f mm; SO3 %.4f B %.4f C5 %.4f mrad; safe=%d\n', ...
                    rec.scene_id,1e3*row.Q_m,1e3*row.B_Q_m,1e3*row.C5_Q_m, ...
                    1e3*row.SO3_rad,1e3*row.B_SO3_rad,1e3*row.C5_SO3_rad,row.engineering_pass);
                assert(row.engineering_pass,'Screen:Engineering','Actual engineering gate failed.');
            catch ME
                write_json(fullfile(runDir,'failure.json'),struct('identifier',ME.identifier, ...
                    'message',ME.message,'Plant_calls_started',1,'TEST_read',false));
                rethrow(ME);
            end
        end
    case 'audit'
        rows=cell(numel(records),1);
        for i=1:numel(records)
            rec=records(i);dirPath=fullfile(study,'runs',rec.scene_id);
            status=jsondecode(fileread(fullfile(dirPath,'run_status.json')));
            rawPath=fullfile(dirPath,'raw_run.mat');assert(strcmpi(hash_file(rawPath),status.raw_sha256));
            raw=load(rawPath,'log','scene','runIdentity');p=prepare(rec,weights,release);
            assert(strcmpi(raw.runIdentity.model_sha256,release.model_sha256)&& ...
                strcmpi(raw.runIdentity.source_lock_sha256,release.source_lock_sha256));
            same_scene(raw.scene,p.scene);rows{i}=score(raw.log,raw.scene,p.cfg,rec);
        end
        rows=[rows{:}];q=[rows.Q_m];b=[rows.B_Q_m];c5=[rows.C5_Q_m];
        a=[rows.SO3_rad];ab=[rows.B_SO3_rad];a5=[rows.C5_SO3_rad];
        summary=struct('scene_count',12,'all_engineering_pass',all([rows.engineering_pass]), ...
            'Q_mean_m',mean(q),'B_Q_mean_m',mean(b),'C5_Q_mean_m',mean(c5), ...
            'SO3_mean_rad',mean(a),'B_SO3_mean_rad',mean(ab),'C5_SO3_mean_rad',mean(a5), ...
            'position_wins_B',nnz(q<b-1e-12),'attitude_wins_B',nnz(a<ab-1e-12), ...
            'position_wins_C5',nnz(q<c5-1e-12),'attitude_wins_C5',nnz(a<a5-1e-12), ...
            'candidate_tilt_samples',sum([rows.tilt_samples]),'B_tilt_samples',sum([rows.B_tilt_samples]), ...
            'C5_tilt_samples',sum([rows.C5_tilt_samples]), ...
            'tilt_constraint_gap_scenes',nnz([rows.tilt_samples]>[rows.B_tilt_samples]));
        summary.performance_pass=summary.all_engineering_pass&&mean(q)<mean(b)&& ...
            mean(a)<mean(ab)&&mean(q)<=1.1*mean(c5)&&mean(a)<mean(a5);
        result=struct('schema','BALANCED_DEVSCREEN_AUDIT_V1','TEST_read',false, ...
            'independent_TEST',false,'Plant_calls_by_audit',0,'summary',summary,'rows',rows);
        write_json(fullfile(study,'AUDIT.json'),result);
        writetable(struct2table(rows),fullfile(study,'PAIRED.csv'));disp(summary);
    otherwise
        error('Screen:Action','Unknown action.');
end
end

function p=prepare(rec,weights,release)
for pair={'payload','b_raw','b_status','c5_raw','c5_status'}
    name=pair{1};assert(strcmpi(hash_file(rec.([name '_path'])),rec.([name '_sha256'])));
end
p=prepare_mlp15_dev72_no_plant(rec.payload_path);
assert(abs(p.cfg.control.limits.max_tilt-pi/6)<1e-12&& ...
    isequal(double(p.cfg.rbf.attitude.dmax(:)),[45;45;4.7124]));
p.opts=make_gate_holdout_options(p.cfg,p.model,'DL_MLP15','ACTIVE',struct,weights,release.model_sha256);
identity=gate_holdout_identity_hashes(p.cfg,p.model,p.opts);
assert(strcmpi(identity.common.position_options_sha256,p.identity.common.position_options_sha256));
p.identity=identity;p.opts.gate_identity_lock=identity;
b=load(rec.b_raw_path,'scene');c5=load(rec.c5_raw_path,'scene');
same_scene(p.scene,b.scene);same_scene(p.scene,c5.scene);
end

function row=score(L,scene,cfg,rec)
b=load(rec.b_raw_path,'log','scene');c5=load(rec.c5_raw_path,'log','scene');
same_scene(scene,b.scene);same_scene(scene,c5.scene);
[q,a,xyz,peak,early,late]=metrics(L,scene,cfg);[bq,ba]=metrics(b.log,scene,cfg);[cq,ca]=metrics(c5.log,scene,cfg);
trace=L.mlp15_attitude_trace;events=find(~cellfun(@isempty,trace));maxFeature=0;maxTorque=0;clip=0;
last=0;
for i=1:numel(events)
    z=trace{events(i)};k=double(z.sample_index);assert(k==events(i)&&k>last&& ...
        abs(z.time_s-L.time(k))<1e-12&&~z.rbf_output_enabled&&~z.rbf_update_enabled&& ...
        ~z.time_varying_inertia_reconstruction_used);last=k;
    e=double(L.filtered_attitude_reference(k,:)-L.state(k,7:9)).';
    expected=[atan2(sin(e),cos(e));double(L.state(k,10:12)).'; ...
        double(L.attitude_bs_nominal_torque_Nm(k,:)).';double(L.arms.command(k,:)).'];
    assert(numel(z.feature_raw)==13&&all(isfinite([z.feature_raw(:);z.estimateTorque_Nm(:)])));
    maxFeature=max(maxFeature,max(abs(expected-double(z.feature_raw(:)))));
    maxTorque=max(maxTorque,max(abs(double(L.attitude_compensation_applied_torque_Nm(k,:)).'-double(z.estimateTorque_Nm(:)))));
    clip=clip+double(any(abs(double(z.raw_residual_rad_s2(:))-double(z.clipped_residual_rad_s2(:)))>1e-12));
end
assert(numel(events)==1999&&maxFeature<1e-10&&maxTorque<1e-12&& ...
    ~L.mlp15_variable_inertia_reconstruction_used&&~L.gate_observer_enabled&& ...
    ~L.gate_feedforward_enabled&&~any(L.rbf_update_flag(:))&& ...
    all(abs(double(L.attitude_rbf_compensation_torque_Nm(:)))<1e-12));
motor=nnz(any(L.motor_saturated,2));general=nnz(any(L.generalized_clipped,2));
safe=strcmp(L.status,'STABLE')&&isempty(L.safety_stop_reason)&&L.complete_transitions&&motor==0&&general==0;
row=struct('scene_id',rec.scene_id,'Q_m',q,'B_Q_m',bq,'C5_Q_m',cq, ...
    'SO3_rad',a,'B_SO3_rad',ba,'C5_SO3_rad',ca,'RMSE_xyz_m',xyz, ...
    'peak_position_m',peak,'Q_0_5_m',early,'Q_15_20_m',late, ...
    'tilt_samples',nnz(L.tilt_limited),'B_tilt_samples',nnz(b.log.tilt_limited), ...
    'C5_tilt_samples',nnz(c5.log.tilt_limited),'motor_saturated_samples',motor, ...
    'generalized_clip_samples',general,'dmax_clipped_events',clip, ...
    'event_count',numel(events),'max_feature_reconstruction_error',maxFeature, ...
    'max_applied_torque_error_Nm',maxTorque,'engineering_pass',safe);
end

function [q,a,xyz,peak,early,late]=metrics(L,scene,cfg)
X=double(L.state);t=double(L.time(:));assert(size(X,1)==20001&& ...
    numel(L.transition_time)==20000&&L.last_transition==20000&& ...
    max(abs(t-double(scene.time(:))))<1e-12&&all(isfinite(X(:))));
e=X(:,1:3)-double(scene.reference.position);xyz=sqrt(mean(e.^2,1));q=sqrt(mean(sum(e.^2,2)));
peak=max(vecnorm(e,2,2));early=sqrt(mean(sum(e(t<5,:).^2,2)));late=sqrt(mean(sum(e(t>=15,:).^2,2)));
acc=double(scene.reference.acceleration);yaw=double(scene.reference.yaw(:));acc(:,3)=acc(:,3)+cfg.plant.g;
A=cos(yaw).*acc(:,1)+sin(yaw).*acc(:,2);B=sin(yaw).*acc(:,1)-cos(yaw).*acc(:,2);
r=atan2(B,hypot(acc(:,3),A));p=atan2(A,acc(:,3));tilt=hypot(r,p);
scale=min(1,cfg.control.limits.max_tilt./max(tilt,eps));target=[r.*scale,p.*scale,yaw];
u=rotation_rows(target);v=rotation_rows(X(:,7:9));theta=acos(max(-1,min(1,(sum(u.*v,2)-1)/2)));
a=sqrt(mean(theta.^2));
end

function R=rotation_rows(e)
p=e(:,1);q=e(:,2);y=e(:,3);cp=cos(p);sp=sin(p);cq=cos(q);sq=sin(q);cy=cos(y);sy=sin(y);
R=[cy.*cq,cy.*sq.*sp-sy.*cp,cy.*sq.*cp+sy.*sp, ...
   sy.*cq,sy.*sq.*sp+cy.*cp,sy.*sq.*cp-cy.*sp,-sq,cq.*sp,cq.*cp];
end

function same_scene(a,b)
for name={'time','initial_state','reference','arms','environment_wind_I'}
    f=name{1};assert(isequaln(a.(f),b.(f)),'Screen:PhysicalInputs','Paired physical input differs: %s.',f);
end
end

function write_json(path,value)
assert(~isfile(path),'Screen:Preserve','Refuse to overwrite an artifact.');
fid=fopen(path,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));
end

function value=utc_now()
value=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss''Z'''));
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0,'Screen:Read','Cannot read %s.',path);
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
