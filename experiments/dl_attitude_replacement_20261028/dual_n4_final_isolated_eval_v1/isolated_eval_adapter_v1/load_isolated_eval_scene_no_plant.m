function [scene,meta]=load_isolated_eval_scene_no_plant(sceneId)
% Load and shape-check one frozen isolated scene; this function never calls a runner.
adapterRoot=fileparts(mfilename('fullpath'));studyRoot=fileparts(adapterRoot);
indexPath=fullfile(adapterRoot,'SCENE_INDEX_v1.json');
index=jsondecode(fileread(indexPath));
assert(strcmp(index.schema,'ISOLATED_EVAL_ADAPTER_SCENE_INDEX_V1')&& ...
    strcmp(index.status,'PASS_STATIC_INPUT_VALIDATION_NOT_RUN_AUTHORIZED')&& ...
    index.record_count==72,'IsoEval:Index','Expected the audited 72-scene adapter index.');
assert(strcmpi(sha256_file(fullfile(studyRoot,'SOURCE_LOCK_v1.json')),index.source_lock_sha256)&& ...
    strcmpi(sha256_file(fullfile(studyRoot,'SCENE_SPECS_v1.json')),index.spec_sha256)&& ...
    strcmpi(sha256_file(fullfile(studyRoot,'GENERATOR_CONFIG_v1.json')),index.generator_config_sha256), ...
    'IsoEval:SourceHash','Frozen scene input or source lock changed.');
sceneId=char(string(sceneId));
hit=find(strcmp({index.records.scene_id},sceneId));
assert(numel(hit)==1,'IsoEval:SceneId','Scene ID must be one exact member of the isolated scene index.');
meta=index.records(hit);
payloadPath=fullfile(studyRoot,char(meta.payload_path));
assert(isfile(payloadPath)&&strcmpi(sha256_file(payloadPath),char(meta.payload_sha256)), ...
    'IsoEval:PayloadHash','Scene payload is missing or differs from the frozen hash.');
payload=load(payloadPath,'scene');scene=payload.scene;
assert(strcmp(char(string(scene.scene_id)),sceneId)&& ...
    strcmp(char(string(scene.reference_contract_id)),char(meta.reference_contract_id)), ...
    'IsoEval:PayloadIdentity','Payload does not match the scene index.');
N=double(meta.time_samples);dt=double(meta.dt_s);
t=double(scene.time(:));
assert(N==20001&&abs(dt-.001)<1e-12&&numel(t)==N&&all(isfinite(t))&& ...
    max(abs(t-(0:N-1)'*dt))<1e-12,'IsoEval:Time','Expected 20,001 samples from 0 to 20 s at 1 ms.');
assert(numel(scene.initial_state)==12&&all(isfinite(double(scene.initial_state(:)))), ...
    'IsoEval:InitialState','Initial state must contain 12 finite values.');
assert(isstruct(scene.reference)&&all(isfield(scene.reference, ...
    {'position','velocity','acceleration','yaw','yaw_rate','yaw_acceleration'}), ...
    'IsoEval:Reference','Missing reference arrays.');
for name={'position','velocity','acceleration'}
    value=double(scene.reference.(name{1}));
    assert(isequal(size(value),[N,3])&&all(isfinite(value),'all'), ...
        'IsoEval:ReferenceShape','Invalid reference.%s array.',name{1});
end
for name={'yaw','yaw_rate','yaw_acceleration'}
    value=double(scene.reference.(name{1}));
    assert(numel(value)==N&&all(isfinite(value(:))), ...
        'IsoEval:ReferenceShape','Invalid reference.%s array.',name{1});
end
assert(isstruct(scene.arms)&&all(isfield(scene.arms, ...
    {'command','rho_true','rho_hat','rhoDot_true','rhoDot_hat'}), ...
    'IsoEval:Arms','Missing morphology arrays.');
for name={'command','rho_true','rho_hat','rhoDot_true','rhoDot_hat'}
    value=double(scene.arms.(name{1}));
    assert(isequal(size(value),[N,4])&&all(isfinite(value),'all'), ...
        'IsoEval:ArmsShape','Invalid arms.%s array.',name{1});
end
assert(isfield(scene,'environment_wind_I')&&isequal(size(scene.environment_wind_I),[N,3])&& ...
    all(isfinite(double(scene.environment_wind_I)),'all'), ...
    'IsoEval:Wind','Expected finite Plant-only environment wind samples.');
allowed={'scene_id','time','initial_state','reference','arms','environment_wind_I','reference_contract_id'};
assert(isequal(sort(fieldnames(scene)),sort(allowed(:))), ...
    'IsoEval:UnexpectedField','Scene payload contains an unapproved field.');
meta.source_split='ISOLATED_EVAL72';
meta.Plant_calls=0;meta.controller_calls=0;meta.score_calls=0;meta.TEST_read=false;
meta.environment_wind_role='Plant environment only; do not pass future samples as controller features.';
end

function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'IsoEval:Read','Cannot open %s.',path);
c=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear c;
end
