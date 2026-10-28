function result=causal_head_study(action)
% Staged release of one frozen-trunk, causal-residual adaptive-head candidate.
study=fileparts(mfilename('fullpath'));research=fileparts(study);
releasePath=fullfile(study,'RELEASE.json');result=struct;
runtime=fullfile(study,'candidate_runner_work','matlab','runtime');
if strcmp(action,'freeze')
    assert(~isfile(releasePath));
    assert(isempty(checkcode([mfilename('fullpath') '.m'],'-id')));
    checksPath=fullfile(study,'audits','NO_PLANT_CHECK.json');checks=jsondecode(fileread(checksPath));
    assert(strcmp(checks.status,'PASS_NO_PLANT_CAUSAL_HEAD')&&checks.Plant_calls==0&&~checks.TEST_read);
    parent=fullfile(research,'mlp15_distribution_countercheck_v1');
    parentManifestPath=fullfile(parent,'MANIFEST.json');parentManifest=jsondecode(fileread(parentManifestPath));
    records=parentManifest.records;ids=string({records.scene_id});
    windless=find(endsWith(ids,'W15'));highFrequency=find(~endsWith(ids,'W15'));
    order=[windless(:);highFrequency(:)];records=records(order);
    assert(numel(records)==6&&strcmp(records(1).scene_id,'DL1018_VAL_T1_C08_W15'));
    for i=1:6
        records(i).frozen_raw_path=fullfile(parent,'runs',records(i).scene_id,'raw_run.mat');
        status=jsondecode(fileread(fullfile(parent,'runs',records(i).scene_id,'run_status.json')));
        records(i).frozen_raw_sha256=status.raw_sha256;verify_record(records(i));
    end
    modelPath=fullfile(research,'mlp15_c5_teacher_full72_v1','runs', ...
        'C5_MLP15_FULL72_SEED2026102001','mlp15_attitude_weights_v1.mat');
    assert(strcmpi(hash_file(modelPath),checks.model_sha256));
    model=load(modelPath);addpath(runtime);activate_paired_runner();
    for i=1:6
        p=prepare_candidate(records(i),model,checks.model_sha256);
        assert(isequal(double(p.cfg.rbf.attitude.dmax(:)),[45;45;4.7124])&& ...
            abs(p.cfg.control.limits.max_tilt-pi/6)<1e-12);
        fprintf('HEAD_PREFLIGHT %d/6 %s\n',i,records(i).scene_id);
    end
    files=dir(fullfile(study,'candidate_runner_work','matlab','**','*.m'));
    extra={[mfilename('fullpath') '.m'],fullfile(study,'TASKBOOK.md'),modelPath,checksPath, ...
        fullfile(study,'audits','check_causal_head_v1.m'),fullfile(study,'audits','HEAD_FIXTURE.mat'), ...
        fullfile(study,'audits','audit_head_attempt.m'),parentManifestPath, ...
        fullfile(study,'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json'), ...
        fullfile(study,'MLP15_DEV72_PAYLOAD_MANIFEST_PARENT_v1.json'), ...
        fullfile(study,'MLP15_DEV72_EXPLORATORY_TASKBOOK_v2.md')};
    sources=repmat(struct('path','','sha256',''),numel(files)+numel(extra),1);
    for i=1:numel(files)
        path=fullfile(files(i).folder,files(i).name);sources(i)=struct('path',path,'sha256',hash_file(path));
    end
    for i=1:numel(extra),sources(numel(files)+i)=struct('path',extra{i},'sha256',hash_file(extra{i}));end
    write_json(fullfile(study,'MANIFEST.json'),struct('records',records,'TEST_read',false));
    result=struct('status','ROOT_STAGED_RELEASE_FIRST_THEN_W15_THEN_HIGH_FREQUENCY', ...
        'max_Plant_calls',6,'model_path',modelPath,'model_sha256',checks.model_sha256, ...
        'manifest_sha256',hash_file(fullfile(study,'MANIFEST.json')),'sources',sources, ...
        'fixed_J0_kgm2',double(p.cfg.attitude_replacement.J0_controller_fixed_kgm2), ...
        'gravity_mps2',p.cfg.plant.g,'max_tilt_rad',p.cfg.control.limits.max_tilt, ...
        'TEST_read',false,'Plant_calls_at_release',0,'new_training_jobs',0);
    write_json(releasePath,result);return;
end
release=jsondecode(fileread(releasePath));assert(release.max_Plant_calls==6&&~release.TEST_read);
for i=1:numel(release.sources)
    assert(strcmpi(hash_file(release.sources(i).path),release.sources(i).sha256), ...
        'HeadStudy:FrozenSource','Source/input changed: %s.',release.sources(i).path);
end
assert(strcmpi(hash_file(fullfile(study,'MANIFEST.json')),release.manifest_sha256));
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));records=manifest.records;
if strcmp(action,'run_first')
    indices=1;
elseif strcmp(action,'run_remaining_w15')
    review=jsondecode(fileread(fullfile(study,'FIRST_REVIEW.json')));
    assert(review.root_approved&&strcmpi(review.raw_sha256, ...
        hash_file(fullfile(study,'runs',records(1).scene_id,'raw_run.mat'))));indices=2:3;
elseif strcmp(action,'run_high_frequency')
    review=jsondecode(fileread(fullfile(study,'W15_REVIEW.json')));assert(review.root_approved);
    for i=1:3
        assert(strcmpi(review.raw_sha256{i},hash_file(fullfile(study,'runs',records(i).scene_id,'raw_run.mat'))));
    end
    indices=4:6;
else
    error('HeadStudy:Action','Unknown action.');
end
addpath(runtime);activate_paired_runner();model=load(release.model_path);
for i=indices
    rec=records(i);verify_record(rec);p=prepare_candidate(rec,model,release.model_sha256);
    assert(isequal(double(p.cfg.attitude_replacement.J0_controller_fixed_kgm2),double(release.fixed_J0_kgm2)));
    runDir=fullfile(study,'runs',rec.scene_id);assert(~isfolder(runDir));
    markers=dir(fullfile(study,'runs','**','attempt_started.marker'));assert(numel(markers)<6);
    disk=java.io.File(study);assert(disk.getFreeSpace()>30*1024^3,'HeadStudy:Disk','Disk threshold reached.');
    mkdir(runDir);runIdentity=struct('scene_id',rec.scene_id,'model_sha256',release.model_sha256, ...
        'release_sha256',hash_file(releasePath),'started_utc',utc_now(), ...
        'payload_sha256',rec.payload_sha256,'b_raw_sha256',rec.b_raw_sha256, ...
        'c5_raw_sha256',rec.c5_raw_sha256,'frozen_raw_sha256',rec.frozen_raw_sha256, ...
        'position_options_sha256',p.identity.common.position_options_sha256, ...
        'head_protocol','PAST_10MS_RESIDUAL_RLS_JOSEPH_OUTPUT_BEFORE_UPDATE_V1','TEST_read',false);
    write_json(fullfile(runDir,'attempt_started.marker'),runIdentity);
    write_json(fullfile(runDir,'run_start.json'),runIdentity);
    try
        timer=tic;log=run_mlp15_dev72_closed_loop(p.scene,p.cfg,p.opts);elapsed=toc(timer);
        scene=p.scene;rawPath=fullfile(runDir,'raw_run.mat');save(rawPath,'log','scene','runIdentity','-v7.3');
        assert(log.complete_transitions&&size(log.state,1)==20001&&all(isfinite(log.state(:))));
        safe=strcmp(log.status,'STABLE')&&isempty(log.safety_stop_reason)&& ...
            ~any(log.motor_saturated(:))&&~any(log.generalized_clipped(:));
        e=double(log.state(:,1:3))-double(scene.reference.position);
        result=struct('state','COMPLETED','engineering_pass',safe,'raw_sha256',hash_file(rawPath), ...
            'wall_seconds',elapsed,'score',struct('Q_m',sqrt(mean(sum(e.^2,2)))), ...
            'Plant_calls',1,'TEST_read',false);
        write_json(fullfile(runDir,'run_status.json'),result);
        addpath(fullfile(study,'audits'));audit=audit_head_attempt(rec.scene_id);
        assert(safe&&audit.engineering_pass,'HeadStudy:Engineering','Actual engineering gate failed.');
        fprintf('CAUSAL_HEAD %s Q=%.5f mm; SO3=%.5f mrad; inner=%.5f mrad; updates=%d; safe=%d\n', ...
            rec.scene_id,1e3*audit.candidate.Q_m,1e3*audit.candidate.SO3_rad, ...
            1e3*audit.candidate.inner_tracking_rad,audit.head_update_count,audit.engineering_pass);
    catch ME
        write_json(fullfile(runDir,'failure.json'),struct('identifier',ME.identifier,'message',ME.message));
        rethrow(ME);
    end
end
end

function p=prepare_candidate(rec,model,modelHash)
p=prepare_mlp15_dev72_no_plant(rec.payload_path);
p.opts=make_gate_holdout_options(p.cfg,p.model,'DL_MLP15','ACTIVE',struct,model,modelHash);
identity=gate_holdout_identity_hashes(p.cfg,p.model,p.opts);
assert(strcmpi(identity.common.position_options_sha256,p.identity.common.position_options_sha256));
p.opts.gate_identity_lock=identity;p.identity=identity;
for path={rec.b_raw_path,rec.c5_raw_path,rec.frozen_raw_path}
    other=load(path{1},'scene');
    for field={'time','initial_state','reference','arms','environment_wind_I'}
        name=field{1};assert(isequaln(p.scene.(name),other.scene.(name)));
    end
end
end

function verify_record(rec)
for prefix={'payload','b_raw','b_status','c5_raw','c5_status','frozen_raw'}
    key=prefix{1};assert(strcmpi(hash_file(rec.([key '_path'])),rec.([key '_sha256'])));
end
end

function write_json(path,value)
assert(~isfile(path));fid=fopen(path,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));
end

function value=utc_now()
value=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss''Z'''));
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
