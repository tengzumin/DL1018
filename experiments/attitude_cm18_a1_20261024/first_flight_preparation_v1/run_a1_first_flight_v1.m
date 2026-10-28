function result = run_a1_first_flight_v1(rootReleasePath,expectedReleaseSha256)
% Single-scene entry; ROOT release and its exact SHA are mandatory before Plant.
if nargin~=2||isempty(rootReleasePath)||isempty(expectedReleaseSha256)
    error('A1FirstFlight:ReleaseRequired','Pass the exact ROOT first-flight release path and SHA256.');
end
here=fileparts(mfilename('fullpath')); experimentDir=fileparts(here);
repoRoot=fileparts(fileparts(experimentDir)); reportDir=fullfile(repoRoot,'reports','attitude_cm18_a1_20261024','first_flight_preparation_v1');
target='DL1018_DEV_T1_C01_W15';
releasePath=fullfile(reportDir,'ROOT_A1_FIRST_FLIGHT_RELEASE_v1.json');
assert(same_path(rootReleasePath,releasePath)&&isfile(releasePath), ...
    'A1FirstFlight:ReleasePath','The one exact ROOT release is missing or a different file was supplied.');
expectedReleaseSha256=lower(char(expectedReleaseSha256));
assert(~isempty(regexp(expectedReleaseSha256,'^[0-9a-f]{64}$','once'))&& ...
    strcmpi(sha256_file(releasePath),expectedReleaseSha256), ...
    'A1FirstFlight:ReleaseSHA','ROOT release SHA256 does not match the explicit launch pin.');
release=jsondecode(fileread(releasePath));
assert(strcmp(release.schema,'CM18_A1_FIRST_FLIGHT_ROOT_RELEASE_V1')&& ...
    strcmp(release.state,'APPROVED_A1_FIRST_FLIGHT_V1')&&logical(release.plant_authorized)&& ...
    double(release.max_new_flights)==1&&strcmp(release.scene_id,target), ...
    'A1FirstFlight:ReleaseScope','ROOT release does not authorize exactly this single fixed scene.');

prepResultPath=fullfile(reportDir,'A1_FIRST_FLIGHT_PREPARATION_RESULT_v1.json');
snapshotPath=fullfile(here,'prepared_a1_first_flight_v1.mat');
modelPath=fullfile(experimentDir,'deployment_v1','deployment_parameters_v1.json');
enginePath=fullfile(experimentDir,'run_cm18_closed_loop_v1.m');
forwardPath=fullfile(experimentDir,'matlab','cm18_a1_forward_v1.m');
helperPath=fullfile(experimentDir,'delayed_prediction_step_candidate.m');
c5Dir=fullfile(repoRoot,'experiments','position_axis_coordinate_c5_dev72_20261023');
c5SnapshotPath=fullfile(c5Dir,'C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
rawPath=fullfile(c5Dir,'runs_dev72_v3',target,'C5_AXIS_MASK_M110','attempt_01','raw_run.mat');
assert(isfile(prepResultPath)&&isfile(snapshotPath),'A1FirstFlight:PreparationMissing','No verified no-Plant preparation exists.');
prep=jsondecode(fileread(prepResultPath));
assert(strcmp(prep.schema,'CM18_A1_FIRST_FLIGHT_PREPARATION_V1')&& ...
    strcmp(prep.status,'PREPARED_A1_FIRST_FLIGHT_NO_PLANT_V1')&&strcmp(prep.scene_id,target)&& ...
    double(prep.plant_calls)==0&&~logical(prep.engine_called)&&~logical(prep.run_episode_called)&& ...
    ~logical(prep.TEST_accessed), ...
    'A1FirstFlight:PreparationStatus','Preparation report is incomplete or has an invalid scope.');
assert_release_hash(release,'preparation_result_sha256',sha256_file(prepResultPath));
assert_release_hash(release,'prepared_snapshot_sha256',sha256_file(snapshotPath));
assert_release_hash(release,'runner_sha256',sha256_file([mfilename('fullpath') '.m']));
assert_release_hash(release,'engine_sha256',sha256_file(enginePath));
assert_release_hash(release,'deployment_parameters_sha256',sha256_file(modelPath));
assert_release_hash(release,'c5_snapshot_sha256',sha256_file(c5SnapshotPath));
assert_release_hash(release,'c5_raw_sha256',sha256_file(rawPath));
assert_release_hash(release,'active_source_inventory_sha256',prep.active_source_inventory_sha256);

source=prep.source_identity;
active=source.c5_active_source_inventory;
assert(numel(active)==32&&numel(source.c5_shared_inputs)==6&& ...
    strcmpi(inventory_sha(active),prep.active_source_inventory_sha256), ...
    'A1FirstFlight:Inventory','Prepared C5 active-source inventory is incomplete or changed.');
for k=1:numel(active), verify_file(char(active(k).path),char(active(k).sha256)); end
for k=1:numel(source.c5_shared_inputs)
    item=source.c5_shared_inputs(k); verify_file(char(item.path),char(item.sha256));
end
verify_file(enginePath,source.a1_engine_sha256); verify_file(forwardPath,source.a1_forward_sha256);
verify_file(helperPath,source.a1_prediction_helper_sha256); verify_file(modelPath,source.deployment_json_sha256);
for k=1:numel(source.deployment_source_inventory)
    item=source.deployment_source_inventory(k);
    verify_file(fullfile(repoRoot,strrep(char(item.path),'/',filesep)),char(item.sha256));
end
verify_file(c5SnapshotPath,prep.c5_snapshot_sha256); verify_file(rawPath,prep.c5_raw_scene_sha256);

pack=load(snapshotPath,'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity');
assert(all(isfield(pack,{'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity'}))&& ...
    strcmp(char(pack.scene.scene_id),target)&&logical(pack.opts.cm18_attitude_v1.enabled)&& ...
    islogical(pack.opts.cm18_attitude_v1.enabled)&& ...
    isequal(double(pack.opts.position_coordinate_mask(:)),[1;1;0])&& ...
    ~pack.opts.rbf_attitude_enabled&&~pack.opts.rbf_attitude_output_enabled&&~pack.opts.rbf_attitude_update_enabled, ...
    'A1FirstFlight:PreparedSnapshot','Prepared cfg/opts/scene snapshot does not match the fixed A1 contract.');
rawPack=load(rawPath,'scene','runIdentity');
assert(all(isfield(rawPack,{'scene','runIdentity'}))&&isequaln(rawPack.scene,pack.scene)&& ...
    strcmp(char(rawPack.runIdentity.scene_id),target), ...
    'A1FirstFlight:RawScene','The prepared scene differs from the pinned C5 raw scene.');
scene=pack.scene; cfg=pack.cfg; opts=pack.opts;

runRoot=fullfile(here,'runs');
attemptDir=fullfile(runRoot,target,'attempt_01');
assert(~isfolder(runRoot)&&~isfile(runRoot),'A1FirstFlight:NoRetry','A1 first-flight output already exists; never retry.');
freeBytes=java.io.File(repoRoot).getFreeSpace(); minimumFreeBytes=30000000000; outputBudgetBytes=100*1024^2;
assert(freeBytes>=minimumFreeBytes+outputBudgetBytes,'A1FirstFlight:Disk','Less than 30 GB plus the one-flight output reserve is free.');

add_active_paths(active); addpath(fullfile(repoRoot,'matlab','runtime'),'-end'); addpath(fullfile(repoRoot,'matlab','core'),'-end');
addpath(fileparts(source_path(active,'position_only_search_options.m')),'-begin');
addpath(fileparts(source_path(active,'position_only_search_head_step.m')),'-begin');
addpath(fileparts(source_path(active,'position_stage1_model_forward_v2.m')),'-begin');
addpath(fileparts(source_path(active,'run_dl1018_closed_loop.m')),'-begin');
addpath(experimentDir,'-begin'); addpath(fullfile(experimentDir,'matlab'),'-begin');
clear run_cm18_closed_loop_v1 delayed_prediction_step_candidate cm18_a1_forward_v1; rehash;
assert(same_path(which('run_cm18_closed_loop_v1'),enginePath)&& ...
    same_path(which('delayed_prediction_step_candidate'),helperPath)&& ...
    same_path(which('cm18_a1_forward_v1'),forwardPath), ...
    'A1FirstFlight:RuntimePath','A1 engine or helper resolved outside the reviewed source.');
for k=1:numel(active)
    if endsWith(lower(char(active(k).path)),'.m')
        [~,n]=fileparts(char(active(k).path)); expectedPath=char(active(k).path);
        if strcmp(n,'delayed_prediction_step_candidate'), expectedPath=helperPath; end
        assert(same_path(which(n),expectedPath),'A1FirstFlight:C5Path','C5 dependency %s resolved outside its bound path.',n);
    end
end

if ~isfolder(runRoot), mkdir(runRoot); end
if ~isfolder(fileparts(attemptDir)), mkdir(fileparts(attemptDir)); end
mkdir(attemptDir);
attemptMarker=fullfile(attemptDir,'attempt_started.marker'); firstStepMarker=fullfile(attemptDir,'first_plant_step.marker');
runStartPath=fullfile(attemptDir,'run_start.mat'); rawOutPath=fullfile(attemptDir,'raw_run.mat'); statusPath=fullfile(attemptDir,'run_status.json');
assert(~isfile(attemptMarker)&&~isfile(firstStepMarker)&&~isfile(runStartPath)&&~isfile(rawOutPath)&&~isfile(statusPath), ...
    'A1FirstFlight:NoOverwrite','One-flight attempt output exists already.');
opts.r2e_first_plant_step_marker=firstStepMarker;
startedUtc=utc_now();
runStart=struct('schema','CM18_A1_FIRST_FLIGHT_RUN_START_V1','scene_id',target, ...
    'started_utc',startedUtc,'root_release_path',releasePath,'root_release_sha256',expectedReleaseSha256, ...
    'preparation_result_sha256',sha256_file(prepResultPath),'prepared_snapshot_sha256',sha256_file(snapshotPath), ...
    'c5_raw_scene_path',rawPath,'c5_raw_scene_sha256',sha256_file(rawPath), ...
    'deployment_parameters_sha256',sha256_file(modelPath),'engine_sha256',sha256_file(enginePath), ...
    'active_source_inventory_sha256',prep.active_source_inventory_sha256, ...
    'runtime_source_path',enginePath,'scene_identity',pack.sceneIdentity,'model_identity',pack.modelIdentity, ...
    'cfg',cfg,'opts',opts,'plant_calls_before_invocation',0,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
save(runStartPath,'runStart','-v7.3');
write_text_new(attemptMarker,[startedUtc newline 'ABOUT_TO_CALL_SINGLE_A1_ENGINE' newline]);
invocationEntered=true;
try
    log=run_cm18_closed_loop_v1(scene,'B2-RBF-Full-SPLIT',cfg,opts);
    log.scene_id=target; log.collector='CM18_A1_FIRST_FLIGHT';
    runIdentity=struct('schema','CM18_A1_FIRST_FLIGHT_RUN_IDENTITY_V1','scene_id',target, ...
        'root_release_sha256',expectedReleaseSha256,'preparation_result_sha256',sha256_file(prepResultPath), ...
        'model_identity',pack.modelIdentity,'scene_identity',pack.sceneIdentity, ...
        'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
    save(rawOutPath,'log','scene','runStart','runIdentity','-v7.3');
    transitions=numel(log.transition_time); samples=numel(log.time); statusLabel='FAILED_NO_RETRY';
    complete=isfield(log,'status')&&strcmpi(char(log.status),'STABLE')&& ...
        isfield(log,'safety_stop_reason')&&isempty(char(log.safety_stop_reason))&& ...
        transitions==20000&&samples==20001&&double(log.last_transition)==20000&& ...
        all(isfinite(log.state(:)))&&all(isfinite(log.reference.position(:)));
    if complete, statusLabel='RUN_COMPLETE_PENDING_ROOT_AUDIT'; end
    runStatus=struct('schema','CM18_A1_FIRST_FLIGHT_RUN_STATUS_V1','status',statusLabel, ...
        'scene_id',target,'log_status',char(log.status),'safety_stop_reason',char(log.safety_stop_reason), ...
        'transitions',transitions,'state_samples',samples,'raw_path',rawOutPath, ...
        'raw_sha256',sha256_file(rawOutPath),'run_start_sha256',sha256_file(runStartPath), ...
        'first_plant_step_marker_path',firstStepMarker,'first_plant_step_confirmed',isfile(firstStepMarker), ...
        'root_release_sha256',expectedReleaseSha256,'preparation_result_sha256',sha256_file(prepResultPath), ...
        'plant_invocation_entered',true,'plant_calls',1,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false, ...
        'output_directory_bytes',directory_bytes(attemptDir),'created_utc',utc_now());
    assert(double(runStatus.output_directory_bytes)<=outputBudgetBytes, ...
        'A1FirstFlight:OutputBudget','First-flight artifacts exceed the fixed 100 MiB budget; retain all output.');
    write_json_new(statusPath,runStatus);
    assert(complete&&isfile(firstStepMarker),'A1FirstFlight:Incomplete','First flight stopped or lacked its first-transition marker; retain evidence and do not retry.');
    result=runStatus;
catch ME
    if invocationEntered&&~isfile(statusPath)
        failure=struct('schema','CM18_A1_FIRST_FLIGHT_RUN_STATUS_V1','status','FAILED_NO_RETRY', ...
            'scene_id',target,'error_identifier',ME.identifier,'error_message',ME.message, ...
            'first_plant_step_confirmed',isfile(firstStepMarker),'attempt_started_marker_path',attemptMarker, ...
            'root_release_sha256',expectedReleaseSha256,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false, ...
            'created_utc',utc_now());
        write_json_new(statusPath,failure);
    end
    rethrow(ME);
end
end

function assert_release_hash(release,name,actual)
assert(isfield(release,name)&&strcmpi(char(release.(name)),char(actual)), ...
    'A1FirstFlight:ReleaseIdentity','ROOT release field %s does not bind the current source/artifact.',name);
end
function add_active_paths(items)
for k=1:numel(items), if endsWith(lower(char(items(k).path)),'.m'), addpath(fileparts(char(items(k).path)),'-end'); end, end
end
function path=source_path(items,name)
idx=[]; for k=1:numel(items), [~,n,e]=fileparts(char(items(k).path)); if strcmpi([n e],name), idx(end+1)=k; end, end %#ok<AGROW>
assert(numel(idx)==1,'A1FirstFlight:SourceName','Expected one inventoried C5 source %s.',name); path=char(items(idx).path);
end
function verify_file(path,expected)
assert(isfile(path),'A1FirstFlight:MissingFile','Missing bound input: %s.',path);
assert(strcmpi(sha256_file(path),expected),'A1FirstFlight:SHA','SHA-256 mismatch: %s.',path);
end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0,'A1FirstFlight:ReadFile','Cannot read %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(b); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=inventory_sha(items)
parts=cell(1,3*numel(items));
for k=1:numel(items), parts{3*k-2}=char(items(k).role); parts{3*k-1}=char(items(k).path); parts{3*k}=lower(char(items(k).sha256)); end
h=sha256_text(strjoin(parts,char(10)));
end
function h=sha256_text(text)
bytes=unicode2native(char(text),'UTF-8'); md=java.security.MessageDigest.getInstance('SHA-256'); md.update(typecast(uint8(bytes(:)),'int8'));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json_new(path,value)
assert(~isfile(path),'A1FirstFlight:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'A1FirstFlight:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char');
end
function write_text_new(path,text)
assert(~isfile(path),'A1FirstFlight:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'A1FirstFlight:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,text,'char');
end
function n=directory_bytes(path)
d=dir(fullfile(path,'**','*')); d=d(~[d.isdir]); n=sum(double([d.bytes]));
end
function tf=same_path(a,b), tf=strcmpi(char(java.io.File(char(a)).getCanonicalPath()),char(java.io.File(char(b)).getCanonicalPath())); end
function t=utc_now(), t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')); end
