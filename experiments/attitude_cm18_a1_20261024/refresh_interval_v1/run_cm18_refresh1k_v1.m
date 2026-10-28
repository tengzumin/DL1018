function result = run_cm18_refresh1k_v1(rootReleasePath,expectedReleaseSha256,sceneId)
% One scene per invocation. A ROOT release with exact hashes is mandatory before Plant.
if nargin~=3||isempty(rootReleasePath)||isempty(expectedReleaseSha256)||isempty(sceneId)
    error('CM18Refresh1k:ReleaseRequired','Pass ROOT release path, its SHA256, and one fixed scene ID.');
end
here=fileparts(mfilename('fullpath')); experimentDir=fileparts(here); repoRoot=fileparts(fileparts(experimentDir));
reportDir=fullfile(repoRoot,'reports','attitude_cm18_a1_20261024','refresh_interval_v1');
sceneIds={'DL1018_DEV_T3_C15_W14','DL1018_DEV_T1_C15_W14', ...
    'DL1018_VAL_T2_C15_W09','DL1018_DEV_T1_C01_W15'};
sceneIndex=find(strcmp(sceneIds,char(sceneId)));
assert(numel(sceneIndex)==1,'CM18Refresh1k:Scene','Unknown fixed scene ID.');
releaseFile=fullfile(reportDir,['ROOT_REFRESH1K_RELEASE_' char(sceneId) '_v1.json']);
assert(same_path(rootReleasePath,releaseFile)&&isfile(releaseFile), ...
    'CM18Refresh1k:ReleasePath','The fixed ROOT refresh release is missing or a different file was supplied.');
expectedReleaseSha256=lower(char(expectedReleaseSha256));
assert(~isempty(regexp(expectedReleaseSha256,'^[0-9a-f]{64}$','once'))&& ...
    strcmpi(sha256_file(releaseFile),expectedReleaseSha256), ...
    'CM18Refresh1k:ReleaseSHA','ROOT release SHA256 does not match the explicit launch pin.');
release=jsondecode(fileread(releaseFile));
assert(strcmp(release.schema,'CM18_A1_REFRESH1K_ROOT_RELEASE_V1')&& ...
    strcmp(release.state,'APPROVED_A1_REFRESH1K_V1')&&logical(release.plant_authorized)&& ...
    double(release.max_new_flights)==1&&strcmp(release.candidate,'A1_REFRESH1K_DIAGNOSTIC')&& ...
    strcmp(char(release.scene_id),char(sceneId))&&double(release.scene_index)==sceneIndex, ...
    'CM18Refresh1k:ReleaseScope','ROOT release must authorize one exact scene and this diagnostic only.');
prepPath=fullfile(reportDir,'REFRESH1K_PREPARATION_RESULT_v1.json');
assert(isfile(prepPath),'CM18Refresh1k:Preparation','No frozen no-Plant preparation exists.');
prep=jsondecode(fileread(prepPath)); prepSha=sha256_file(prepPath);
assert(strcmp(prep.schema,'CM18_A1_REFRESH1K_PREPARATION_V1')&& ...
    strcmp(prep.status,'PREPARED_A1_REFRESH1K_NO_PLANT_V1')&&double(prep.scene_count)==4&& ...
    double(prep.plant_calls)==0&&~logical(prep.engine_called)&&~logical(prep.run_episode_called)&& ...
    double(prep.training_steps)==0&&double(prep.optimizer_steps)==0&&~logical(prep.TEST_accessed)&& ...
    double(prep.cm18_expected_event_count)==19990&&double(prep.scene_rows(sceneIndex).baseline_A1_event_count)==1999, ...
    'CM18Refresh1k:PreparationStatus','Preparation is incomplete or has an invalid scope.');
runnerPath=[mfilename('fullpath') '.m']; enginePath=fullfile(here,'run_cm18_refresh1k_closed_loop_v1.m');
forwardPath=fullfile(here,'matlab','cm18_a1_forward_v1.m'); helperPath=fullfile(here,'delayed_prediction_step_candidate.m');
modelPath=fullfile(experimentDir,'deployment_v1','deployment_parameters_v1.json');
row=prep.scene_rows(sceneIndex); sid=char(row.scene_id);
assert(strcmp(sid,char(sceneId)),'CM18Refresh1k:SceneOrder','Preparation scene order differs from the fixed task order.');
snapshotPath=char(row.prepared_snapshot_path); c5RawPath=char(row.baseline_C5_raw_path); a1RawPath=char(row.baseline_A1_raw_path);
assert_release_hash(release,'preparation_result_sha256',prepSha);
assert_release_hash(release,'prepared_snapshot_sha256',char(row.prepared_snapshot_sha256));
assert_release_hash(release,'runner_sha256',sha256_file(runnerPath));
assert_release_hash(release,'engine_sha256',sha256_file(enginePath));
assert_release_hash(release,'forward_sha256',sha256_file(forwardPath));
assert_release_hash(release,'helper_sha256',sha256_file(helperPath));
assert_release_hash(release,'deployment_parameters_sha256',sha256_file(modelPath));
assert_release_hash(release,'taskbook_sha256',char(prep.taskbook_sha256));
assert_release_hash(release,'baseline_C5_raw_sha256',char(row.baseline_C5_raw_sha256));
assert_release_hash(release,'baseline_A1_raw_sha256',char(row.baseline_A1_raw_sha256));
verify_file(snapshotPath,char(row.prepared_snapshot_sha256));
verify_file(c5RawPath,char(row.baseline_C5_raw_sha256));
verify_file(a1RawPath,char(row.baseline_A1_raw_sha256));
verify_file(modelPath,char(prep.deployment_parameters_sha256));
verify_file(char(row.baseline_A1_audit_path),char(row.baseline_A1_audit_sha256));
verify_file(enginePath,char(prep.engine_sha256)); verify_file(forwardPath,char(prep.forward_sha256));
verify_file(helperPath,char(prep.helper_sha256));
pack=load(snapshotPath,'cfg','opts','opts100Hz','scene','sceneIdentity','modelIdentity','sourceIdentity','baselineIdentity','refreshSourceIdentity');
assert(all(isfield(pack,{'cfg','opts','opts100Hz','scene','sceneIdentity','modelIdentity','sourceIdentity','baselineIdentity','refreshSourceIdentity'}))&& ...
    strcmp(char(pack.scene.scene_id),sid)&&strcmp(char(pack.sceneIdentity.scene_id),sid)&& ...
    strcmpi(char(pack.modelIdentity.checkpoint_sha256),char(prep.model_identity.checkpoint_sha256))&& ...
    double(pack.modelIdentity.selected_step)==30000&&logical(pack.opts.cm18_attitude_v1.enabled)&& ...
    double(pack.opts.cm18_attitude_v1.refresh_hz)==1000&& ...
    isequal(double(pack.opts.position_coordinate_mask(:)),[1;1;0])&& ...
    ~pack.opts.rbf_attitude_enabled&&~pack.opts.rbf_attitude_output_enabled&&~pack.opts.rbf_attitude_update_enabled, ...
    'CM18Refresh1k:PreparedSnapshot','Snapshot identity or fixed CM18/C5 options do not match.');
opts=pack.opts; opts100Hz=pack.opts100Hz;
if isfield(opts,'r2e_first_plant_step_marker'),opts=rmfield(opts,'r2e_first_plant_step_marker');end
restored=opts; restored.cm18_attitude_v1=rmfield(restored.cm18_attitude_v1,'refresh_hz');
assert(isequaln(restored,opts100Hz),'CM18Refresh1k:OptionDelta','Only CM18 refresh_hz and first-step marker may differ.');
c5=load(c5RawPath,'scene','runIdentity'); a1=load(a1RawPath,'scene','runIdentity');
assert(isequaln(c5.scene,pack.scene)&&isequaln(a1.scene,pack.scene)&& ...
    strcmp(char(c5.runIdentity.scene_id),sid)&&strcmp(char(a1.runIdentity.scene_id),sid)&& ...
    strcmp(char(c5.runIdentity.candidate),'C5_AXIS_MIXED_COORDINATE_M110'), ...
    'CM18Refresh1k:SceneBinding','Prepared scene does not match pinned C5 and A1 source raws.');
source=pack.sourceIdentity; active=source.c5_active_source_inventory;
assert(numel(active)==32&&numel(source.c5_shared_inputs)==6&& ...
    strcmpi(inventory_sha(active),char(source.c5_active_source_inventory_sha256)), ...
    'CM18Refresh1k:SourceInventory','Pinned C5 active source inventory is incomplete or changed.');
for k=1:numel(active), verify_file(char(active(k).path),char(active(k).sha256)); end
for k=1:numel(source.c5_shared_inputs), verify_file(char(source.c5_shared_inputs(k).path),char(source.c5_shared_inputs(k).sha256)); end
verify_file(char(source.a1_engine_path),char(source.a1_engine_sha256));
verify_file(char(source.a1_forward_path),char(source.a1_forward_sha256));
verify_file(char(source.a1_prediction_helper_path),char(source.a1_prediction_helper_sha256));
for k=1:numel(source.deployment_source_inventory)
    item=source.deployment_source_inventory(k); sourceFile=char(item.path);
    if ~isfile(sourceFile), sourceFile=fullfile(repoRoot,strrep(sourceFile,'/',filesep)); end
    verify_file(sourceFile,char(item.sha256));
end
add_active_paths(active); addpath(fullfile(repoRoot,'matlab','runtime'),'-end'); addpath(fullfile(repoRoot,'matlab','core'),'-end');
addpath(fileparts(source_path(active,'position_only_search_options.m')),'-begin');
addpath(fileparts(source_path(active,'position_only_search_head_step.m')),'-begin');
addpath(fileparts(source_path(active,'position_stage1_model_forward_v2.m')),'-begin');
addpath(fileparts(source_path(active,'run_dl1018_closed_loop.m')),'-begin');
addpath(here,'-begin'); addpath(fullfile(here,'matlab'),'-begin');
clear run_cm18_refresh1k_closed_loop_v1 delayed_prediction_step_candidate cm18_a1_forward_v1; rehash;
assert(same_path(which('run_cm18_refresh1k_closed_loop_v1'),enginePath)&& ...
    same_path(which('delayed_prediction_step_candidate'),helperPath)&& ...
    same_path(which('cm18_a1_forward_v1'),forwardPath), ...
    'CM18Refresh1k:RuntimePath','Refresh engine or helper resolved outside its pinned isolated source.');
for k=1:numel(active)
    if endsWith(lower(char(active(k).path)),'.m')
        [~,n,e]=fileparts(char(active(k).path)); expectedPath=char(active(k).path);
        if strcmpi([n e],'delayed_prediction_step_candidate.m'), expectedPath=helperPath; end
        assert(same_path(which(n),expectedPath),'CM18Refresh1k:C5Path','C5 dependency %s resolved outside its pinned path.',n);
    end
end
runRoot=fullfile(here,'runs'); attemptDir=fullfile(runRoot,sid,'attempt_01');
assert(~isfolder(attemptDir)&&~isfile(attemptDir),'CM18Refresh1k:NoRetry','This scene attempt already exists; retain it and do not retry.');
freeBytes=java.io.File(repoRoot).getFreeSpace(); outputBudgetBytes=100*1024^2;
assert(freeBytes>=30*1024^3+outputBudgetBytes,'CM18Refresh1k:Disk','Insufficient free space for the fixed one-scene reserve.');
if ~isfolder(runRoot), mkdir(runRoot); end
if ~isfolder(fileparts(attemptDir)), mkdir(fileparts(attemptDir)); end
mkdir(attemptDir);
marker=fullfile(attemptDir,'first_plant_step.marker'); attemptMarker=fullfile(attemptDir,'attempt_started.marker');
runStartPath=fullfile(attemptDir,'run_start.mat'); rawPath=fullfile(attemptDir,'raw_run.mat'); statusPath=fullfile(attemptDir,'run_status.json');
opts.r2e_first_plant_step_marker=marker; scene=pack.scene; cfg=pack.cfg;
startedUtc=utc_now();
runStart=struct('schema','CM18_A1_REFRESH1K_RUN_START_V1','scene_id',sid,'scene_index',sceneIndex, ...
    'candidate','A1_REFRESH1K_DIAGNOSTIC','started_utc',startedUtc,'root_release_path',releaseFile, ...
    'root_release_sha256',expectedReleaseSha256,'preparation_result_sha256',prepSha, ...
    'prepared_snapshot_sha256',sha256_file(snapshotPath),'deployment_parameters_sha256',sha256_file(modelPath), ...
    'engine_sha256',sha256_file(enginePath),'runner_sha256',sha256_file(runnerPath), ...
    'baseline_C5_raw_sha256',sha256_file(c5RawPath),'baseline_A1_raw_sha256',sha256_file(a1RawPath), ...
    'scene_identity',pack.sceneIdentity,'model_identity',pack.modelIdentity,'cfg',cfg,'opts',opts, ...
    'plant_calls_before_invocation',0,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
save(runStartPath,'runStart','-v7.3'); write_text_new(attemptMarker,[startedUtc newline 'ABOUT_TO_CALL_SINGLE_REFRESH1K_ENGINE' newline]);
invocationEntered=true;
try
    log=run_cm18_refresh1k_closed_loop_v1(scene,'B2-RBF-Full-SPLIT',cfg,opts);
    log.scene_id=sid; log.collector='CM18_A1_REFRESH1K_DIAGNOSTIC';
    runIdentity=struct('schema','CM18_A1_REFRESH1K_RUN_IDENTITY_V1','scene_id',sid,'scene_index',sceneIndex, ...
        'candidate','A1_REFRESH1K_DIAGNOSTIC','root_release_sha256',expectedReleaseSha256, ...
        'preparation_result_sha256',prepSha,'model_identity',pack.modelIdentity,'scene_identity',pack.sceneIdentity, ...
        'engine_sha256',sha256_file(enginePath),'runner_sha256',sha256_file(runnerPath), ...
        'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
    save(rawPath,'log','scene','runStart','runIdentity','-v7.3');
    expectedRefresh=(11:20000)'; expectedLegacy=(11:10:19991)';
    complete=isfield(log,'status')&&strcmpi(char(log.status),'STABLE')&& ...
        isfield(log,'safety_stop_reason')&&isempty(char(log.safety_stop_reason))&& ...
        numel(log.transition_time)==20000&&numel(log.time)==20001&&double(log.last_transition)==20000&& ...
        all(isfinite(log.state(:)))&&all(isfinite(log.reference.position(:)))&& ...
        double(log.cm18_refresh_expected_event_count)==19990&&double(log.cm18_event_count)==19990&& ...
        isequal(find(log.cm18_event_flag(:)),expectedRefresh)&& ...
        isequal(find(log.attitude_event_flag(:)),expectedLegacy)&&isequal(find(log.position_event_flag(:)),expectedLegacy)&& ...
        isfile(marker);
    bytes=directory_bytes(attemptDir); complete=complete&&bytes<=outputBudgetBytes;
    status=struct('schema','CM18_A1_REFRESH1K_RUN_STATUS_V1','status','FAILED_NO_RETRY', ...
        'scene_id',sid,'scene_index',sceneIndex,'candidate','A1_REFRESH1K_DIAGNOSTIC', ...
        'log_status',char(log.status),'safety_stop_reason',char(log.safety_stop_reason), ...
        'transitions',numel(log.transition_time),'state_samples',numel(log.time), ...
        'refresh_event_count',double(log.cm18_event_count),'legacy_attitude_event_count',sum(log.attitude_event_flag), ...
        'raw_path',rawPath,'raw_sha256',sha256_file(rawPath),'run_start_sha256',sha256_file(runStartPath), ...
        'first_plant_step_confirmed',isfile(marker),'root_release_sha256',expectedReleaseSha256, ...
        'plant_invocation_entered',true,'plant_calls',1,'training_steps',0,'optimizer_steps',0, ...
        'TEST_accessed',false,'output_directory_bytes',bytes,'created_utc',utc_now());
    if complete, status.status='RUN_COMPLETE_PENDING_ROOT_AUDIT'; end
    write_json_new(statusPath,status);
    assert(complete,'CM18Refresh1k:Incomplete','The one-scene run failed completion/schedule/budget checks; retain evidence and do not retry.');
    result=status;
catch ME
    if invocationEntered&&~isfile(statusPath)
        failure=struct('schema','CM18_A1_REFRESH1K_RUN_STATUS_V1','status','FAILED_NO_RETRY', ...
            'scene_id',sid,'scene_index',sceneIndex,'candidate','A1_REFRESH1K_DIAGNOSTIC', ...
            'error_identifier',ME.identifier,'error_message',ME.message,'first_plant_step_confirmed',isfile(marker), ...
            'attempt_started_marker_path',attemptMarker,'root_release_sha256',expectedReleaseSha256, ...
            'plant_calls',double(isfile(marker)),'training_steps',0,'optimizer_steps',0,'TEST_accessed',false, ...
            'created_utc',utc_now());
        write_json_new(statusPath,failure);
    end
    rethrow(ME);
end
end
function assert_release_hash(release,name,actual)
assert(isfield(release,name)&&strcmpi(char(release.(name)),char(actual)), ...
    'CM18Refresh1k:ReleaseIdentity','ROOT release field %s does not bind this exact source/artifact.',name);
end
function add_active_paths(items)
for k=1:numel(items), if endsWith(lower(char(items(k).path)),'.m'), addpath(fileparts(char(items(k).path)),'-end'); end, end
end
function path=source_path(items,name)
idx=[]; for k=1:numel(items), [~,n,e]=fileparts(char(items(k).path)); if strcmpi([n e],name), idx(end+1)=k; end, end %#ok<AGROW>
assert(numel(idx)==1,'CM18Refresh1k:SourceName','Expected one inventoried C5 source %s.',name); path=char(items(idx).path);
end
function verify_file(path,expected)
assert(isfile(path),'CM18Refresh1k:MissingFile','Missing pinned input: %s.',path);
assert(strcmpi(sha256_file(path),expected),'CM18Refresh1k:SHA','SHA256 mismatch: %s.',path);
end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0,'CM18Refresh1k:ReadFile','Cannot read %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(b); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=sha256_text(text)
bytes=unicode2native(char(text),'UTF-8'); md=java.security.MessageDigest.getInstance('SHA-256'); md.update(typecast(uint8(bytes(:)),'int8'));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=inventory_sha(items)
parts=cell(1,3*numel(items));
for k=1:numel(items), parts{3*k-2}=char(items(k).role); parts{3*k-1}=char(items(k).path); parts{3*k}=lower(char(items(k).sha256)); end
h=sha256_text(strjoin(parts,char(10)));
end
function tf=same_path(a,b), tf=strcmpi(char(java.io.File(char(a)).getCanonicalPath()),char(java.io.File(char(b)).getCanonicalPath())); end
function write_json_new(path,value)
assert(~isfile(path),'CM18Refresh1k:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'CM18Refresh1k:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char');
end
function write_text_new(path,text)
assert(~isfile(path),'CM18Refresh1k:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'CM18Refresh1k:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,text,'char');
end
function n=directory_bytes(path)
d=dir(fullfile(path,'**','*')); d=d(~[d.isdir]); n=sum(double([d.bytes]));
end
function t=utc_now(), t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')); end
