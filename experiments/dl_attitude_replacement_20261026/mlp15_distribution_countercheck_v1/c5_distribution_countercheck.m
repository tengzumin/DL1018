function result=c5_distribution_countercheck(action)
% One-factor closed-loop countercheck of two existing frozen training runs.
study=fileparts(mfilename('fullpath'));research=fileparts(study);
parent=fullfile(research,'mlp15_balanced_devscreen_v1');
releasePath=fullfile(study,'RELEASE.json');result=struct;
if strcmp(action,'freeze')
    assert(~isfile(releasePath));
    assert(isempty(checkcode([mfilename('fullpath') '.m'],'-id')));
    input=jsondecode(fileread(fullfile(parent,'MANIFEST.json')));
    wind=regexp(string({input.records.scene_id}),'W(\d+)$','tokens','once');
    selected=cellfun(@(x)str2double(x{1})>=12,wind);
    records=input.records(selected);assert(numel(records)==6);
    ids=string({records.scene_id});first=find(ids=="DL1018_VAL_T1_C08_W15");
    records=records([first,setdiff(1:6,first,'stable')]);
    parentRelease=jsondecode(fileread(fullfile(parent,'RELEASE_v2.json')));
    modelPath=fullfile(research,'mlp15_c5_teacher_full72_v1','runs', ...
        'C5_MLP15_FULL72_SEED2026102001','mlp15_attitude_weights_v1.mat');
    modelHash='67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b';
    assert(strcmpi(hash_file(modelPath),modelHash));
    configPath=fullfile(fileparts(modelPath),'training_config.json');config=jsondecode(fileread(configPath));
    assert(strcmp(config.status,'PASS')&&config.optimizer_steps==60000&&~config.TEST48_read);
    oldLock=jsondecode(fileread(fullfile(research,'mlp15_dev72_v2','MLP15_DEV72_CANDIDATE_SOURCE_LOCK_v1.json')));
    files=repmat(struct('path','','sha256',''),numel(oldLock.files)+6,1);
    for i=1:numel(oldLock.files)
        files(i).path=fullfile(parentRelease.runtime_root,oldLock.files(i).relative_path);
        files(i).sha256=oldLock.files(i).sha256;
        assert(strcmpi(hash_file(files(i).path),files(i).sha256));
    end
    extra={modelPath,configPath,fullfile(fileparts(modelPath),'run_receipt.json'), ...
        [mfilename('fullpath') '.m'],fullfile(study,'TASKBOOK.md'),fullfile(parent,'MANIFEST.json')};
    for i=1:numel(extra)
        files(numel(oldLock.files)+i)=struct('path',extra{i},'sha256',hash_file(extra{i}));
    end
    for i=1:numel(records),verify_inputs(records(i));end
    write_json(fullfile(study,'MANIFEST.json'),struct('records',records,'TEST_read',false));
    result=struct('status','ROOT_RELEASED_SIX_CALLS_FIRST_THEN_REVIEW','max_Plant_calls',6, ...
        'model_path',modelPath,'model_sha256',modelHash,'runtime_root',parentRelease.runtime_root, ...
        'source_files',files,'manifest_sha256',hash_file(fullfile(study,'MANIFEST.json')),'TEST_read',false);
    write_json(releasePath,result);return;
end
release=jsondecode(fileread(releasePath));assert(release.max_Plant_calls==6&&~release.TEST_read);
for i=1:numel(release.source_files)
    assert(strcmpi(hash_file(release.source_files(i).path),release.source_files(i).sha256));
end
assert(strcmpi(hash_file(fullfile(study,'MANIFEST.json')),release.manifest_sha256));
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));records=manifest.records;
addpath(fullfile(release.runtime_root,'matlab','runtime'));activate_paired_runner();
model=load(release.model_path);
if strcmp(action,'run_first')
    indices=1;
elseif strcmp(action,'run_remaining')
    review=jsondecode(fileread(fullfile(study,'FIRST_REVIEW.json')));
    first=jsondecode(fileread(fullfile(study,'runs',records(1).scene_id,'run_status.json')));
    assert(review.root_approved&&first.engineering_pass&&strcmpi(review.first_raw_sha256,first.raw_sha256));
    indices=2:6;
else
    error('Countercheck:Action','Unknown action.');
end
for i=indices
    rec=records(i);verify_inputs(rec);
    p=prepare_mlp15_dev72_no_plant(rec.payload_path);
    p.opts=make_gate_holdout_options(p.cfg,p.model,'DL_MLP15','ACTIVE',struct,model,release.model_sha256);
    identity=gate_holdout_identity_hashes(p.cfg,p.model,p.opts);
    assert(strcmpi(identity.common.position_options_sha256,p.identity.common.position_options_sha256));
    p.opts.gate_identity_lock=identity;
    b=load(rec.b_raw_path,'scene');c5=load(rec.c5_raw_path,'scene');
    for field={'time','initial_state','reference','arms','environment_wind_I'}
        f=field{1};assert(isequaln(p.scene.(f),b.scene.(f))&&isequaln(p.scene.(f),c5.scene.(f)));
    end
    runDir=fullfile(study,'runs',rec.scene_id);assert(~isfolder(runDir));
    markers=dir(fullfile(study,'runs','**','attempt_started.marker'));assert(numel(markers)<6);
    mkdir(runDir);runIdentity=struct('scene_id',rec.scene_id,'model_sha256',release.model_sha256, ...
        'release_sha256',hash_file(releasePath),'payload_sha256',rec.payload_sha256, ...
        'b_raw_sha256',rec.b_raw_sha256,'c5_raw_sha256',rec.c5_raw_sha256,'TEST_read',false);
    write_json(fullfile(runDir,'attempt_started.marker'),runIdentity);
    write_json(fullfile(runDir,'run_start.json'),runIdentity);
    try
        timer=tic;log=run_mlp15_dev72_closed_loop(p.scene,p.cfg,p.opts);elapsed=toc(timer);
        scene=p.scene;rawPath=fullfile(runDir,'raw_run.mat');save(rawPath,'log','scene','runIdentity','-v7.3');
        assert(log.complete_transitions&&size(log.state,1)==20001&&all(isfinite(log.state(:))));
        events=find(~cellfun(@isempty,log.mlp15_attitude_trace));assert(numel(events)==1999);
        featureError=0;torqueError=0;
        for j=1:numel(events)
            k=events(j);z=log.mlp15_attitude_trace{k};e=log.filtered_attitude_reference(k,:)-log.state(k,7:9);
            expected=[atan2(sin(e),cos(e)),log.state(k,10:12),log.attitude_bs_nominal_torque_Nm(k,:),log.arms.command(k,:)];
            featureError=max(featureError,max(abs(expected-double(z.feature_raw(:)).')));
            torqueError=max(torqueError,max(abs(log.attitude_compensation_applied_torque_Nm(k,:)-double(z.estimateTorque_Nm(:)).')));
            assert(z.sample_index==k&&abs(z.time_s-log.time(k))<1e-12&& ...
                ~z.rbf_output_enabled&&~z.rbf_update_enabled&&~z.time_varying_inertia_reconstruction_used);
        end
        assert(featureError<1e-10&&torqueError<1e-12);
        safe=strcmp(log.status,'STABLE')&&isempty(log.safety_stop_reason)&& ...
            ~any(log.motor_saturated(:))&&~any(log.generalized_clipped(:));
        err=double(log.state(:,1:3))-double(scene.reference.position);q=sqrt(mean(sum(err.^2,2)));
        result=struct('state','COMPLETED','engineering_pass',safe,'raw_sha256',hash_file(rawPath), ...
            'score',struct('Q_m',q),'wall_seconds',elapsed,'max_feature_error',featureError, ...
            'max_torque_error_Nm',torqueError,'Plant_calls',1,'TEST_read',false);
        write_json(fullfile(runDir,'run_status.json'),result);
        fprintf('COUNTERCHECK %s Q=%.5f mm safe=%d\n',rec.scene_id,q*1e3,safe);
        assert(safe,'Countercheck:Safety','Engineering gate failed.');
    catch ME
        write_json(fullfile(runDir,'failure.json'),struct('identifier',ME.identifier,'message',ME.message));
        rethrow(ME);
    end
end
end

function verify_inputs(rec)
for name={'payload','b_raw','b_status','c5_raw','c5_status'}
    key=name{1};assert(strcmpi(hash_file(rec.([key '_path'])),rec.([key '_sha256'])));
end
end

function write_json(path,value)
assert(~isfile(path));fid=fopen(path,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
