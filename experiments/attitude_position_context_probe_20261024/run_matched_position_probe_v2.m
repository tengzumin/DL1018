function result = run_matched_position_probe_v2(releasePath,expectedReleaseSha256,flightId)
% Execute exactly one Root-released flight. Each ID has one attempt and no retry.
assert(nargin==3,'MatchedProbe:Arguments','Usage: run_matched_position_probe_v2(releasePath,expectedSHA,flightId).');
here=fileparts(mfilename('fullpath'));repoRoot=fileparts(fileparts(here));
reportDir=fullfile(repoRoot,'reports','attitude_position_context_probe_20261024');
preparePath=fullfile(reportDir,'PREPARED_MATCHED_POSITION_PROBE_v1.json');
taskbookPath=fullfile(repoRoot,'reports','attitude_cm18_a2_20261024','ROOT_MATCHED_POSITION_PROBE_TASKBOOK_v1_ZH.md');
flightId=char(string(flightId));
flightIds={'T1_B','T1_C5','T3_B','T3_C5'};sceneIds={'DL1018_TRAIN_T1_C15_W14','DL1018_TRAIN_T1_C15_W14','DL1018_TRAIN_T3_C15_W14','DL1018_TRAIN_T3_C15_W14'};
modeIds={'B_POSITION_RBF','C5_POSITION_M110','B_POSITION_RBF','C5_POSITION_M110'};
ix=find(strcmp(flightIds,flightId));assert(numel(ix)==1,'MatchedProbe:Flight','Flight ID is not in the fixed four-flight allowlist.');
if strcmp(flightId,'T1_B'),attemptNumber=2;else,attemptNumber=1;end
expectedReleasePath=fullfile(reportDir,['ROOT_RELEASE_' flightId '_v2.json']);
assert(same_path(releasePath,expectedReleasePath),'MatchedProbe:ReleasePath','Release path must be the fixed per-flight Root file.');
assert(isfile(expectedReleasePath),'MatchedProbe:MissingRelease','Root release is missing; refusing to run.');
expectedReleaseSha256=lower(char(expectedReleaseSha256));
assert(numel(expectedReleaseSha256)==64&&all(isstrprop(expectedReleaseSha256,'xdigit')), ...
    'MatchedProbe:ReleaseSHA','Expected release SHA-256 is invalid.');
assert(strcmpi(sha256_file(expectedReleasePath),expectedReleaseSha256), ...
    'MatchedProbe:ReleaseSHA','Root release SHA-256 mismatch.');
release=jsondecode(fileread(expectedReleasePath));
assert(strcmp(release.schema,'MATCHED_POSITION_PROBE_RELEASE_V1')&& ...
    strcmp(release.decision,'APPROVE_ONE_FLIGHT')&&strcmp(release.flight_id,flightId), ...
    'MatchedProbe:ReleaseDecision','Root release schema/decision/flight_id mismatch.');
assert(isfile(preparePath),'MatchedProbe:Prepare','No prepared input snapshot exists.');
prepared=jsondecode(fileread(preparePath));prepSha=sha256_file(preparePath);
assert(strcmp(prepared.schema,'MATCHED_POSITION_PROBE_PREPARE_RESULT_V1')&& ...
    strcmp(prepared.status,'PREPARED_NO_PLANT'),'MatchedProbe:PrepareStatus','Preparation is not complete.');
sourcePrepare=fullfile(here,'prepare_matched_position_probe_v1.m');
sourceRunnerV1=fullfile(here,'run_matched_position_probe_v1.m');
sourceRunnerV2=fullfile(here,'run_matched_position_probe_v2.m');
assert(strcmpi(sha256_file(sourcePrepare),prepared.source_hashes.prepare_matlab_sha256)&& ...
    strcmpi(sha256_file(sourceRunnerV1),prepared.source_hashes.runner_matlab_sha256), ...
    'MatchedProbe:ProbeSource','Frozen v1 preparation/runner source changed after snapshot.');
assert(isfield(release,'pins')&&isfield(release.pins,'runner_v2_sha256')&& ...
    strcmpi(sha256_file(sourceRunnerV2),char(release.pins.runner_v2_sha256)), ...
    'MatchedProbe:RunnerV2Pin','Release does not pin this v2 runner source.');
assert(isfield(release,'attempt_id')&&double(release.attempt_id)==attemptNumber, ...
    'MatchedProbe:AttemptId','Release attempt_id does not match the fixed attempt number.');
assert(strcmpi(sha256_file(taskbookPath),prepared.taskbook_sha256), ...
    'MatchedProbe:Taskbook','Frozen taskbook changed after preparation.');
assert_sha(prepared.input_manifest_path,prepared.input_manifest_sha256);
assert_sha(prepared.all816_manifest_path,prepared.all816_manifest_sha256);
snapshotRows=prepared.snapshot_rows;si=find(strcmp({snapshotRows.flight_id},flightId));
assert(numel(si)==1,'MatchedProbe:Snapshot','Prepared snapshot for flight is missing.');
snapshotPath=snapshotRows(si).path;snapshotSha=snapshotRows(si).sha256;
assert_sha(snapshotPath,snapshotSha);
expectedPins=struct('taskbook_sha256',prepared.taskbook_sha256, ...
    'prepare_result_sha256',prepSha,'snapshot_sha256',snapshotSha, ...
    'input_manifest_sha256',prepared.input_manifest_sha256, ...
    'all816_manifest_sha256',prepared.all816_manifest_sha256, ...
    'c5_release_sha256',prepared.C5_release_sha256, ...
    'c5_source_binding_sha256',prepared.C5_source_binding_sha256, ...
    'c5_engine_sha256',prepared.source_hashes.c5_engine_sha256, ...
    'c5_episode_wrapper_sha256',prepared.source_hashes.c5_episode_wrapper_sha256, ...
    'model_mat_sha256',prepared.C5_model_mat_sha256, ...
    'normalizer_npz_sha256',prepared.C5_normalizer_npz_sha256, ...
    'runner_v2_sha256',sha256_file(sourceRunnerV2));
assert(isfield(release,'pins'),'MatchedProbe:ReleasePins','Root release has no pins object.');
for f=fieldnames(expectedPins).'
    key=f{1};assert(isfield(release.pins,key)&&strcmpi(char(release.pins.(key)),char(expectedPins.(key))), ...
        'MatchedProbe:ReleasePin','Root release pin %s mismatch.',key);
end

pack=load(snapshotPath,'cfg','opts','W0','c5ModelIdentity','sourceIdentity','snapshotMeta');
assert(strcmp(pack.snapshotMeta.flight_id,flightId)&&strcmp(pack.snapshotMeta.scene_id,sceneIds{ix})&& ...
    strcmp(pack.snapshotMeta.position_mode,modeIds{ix}), ...
    'MatchedProbe:SnapshotIdentity','Snapshot flight identity differs.');
assert(strcmp(pack.c5ModelIdentity.W0_sha256,prepared.C5_model_identity.W0_sha256)&& ...
    strcmp(pack.c5ModelIdentity.normalizer_arrays_sha256,prepared.C5_model_identity.normalizer_arrays_sha256), ...
    'MatchedProbe:ModelIdentity','C5 model/normalizer identity changed.');
verify_c5_sources(pack.sourceIdentity,repoRoot,pack.cfg,prepared.C5_source_paths);
verify_c5_files(repoRoot,prepared);

sceneId=sceneIds{ix};modeId=modeIds{ix};input=pack.snapshotMeta.input_identity;
assert(strcmp(input.scene_id,sceneId),'MatchedProbe:InputScene','Snapshot scene differs from flight.');
assert_sha(input.raw_path,input.raw_sha256);assert_sha(input.run_start_path,input.run_start_sha256);
scenePack=load(input.raw_path,'scene');assert(isfield(scenePack,'scene'),'MatchedProbe:Scene','Source raw has no scene variable.');
scene=scenePack.scene;
assert(strcmp(char(scene.scene_id),sceneId)&&numel(scene.time)==20001&& ...
    abs(double(scene.time(1)))<1e-12&&abs(double(scene.time(end))-20)<1e-12&& ...
    isequal(double(scene.initial_state(:)),double(pack.snapshotMeta.mutable_initial_state.initial_state(:))), ...
    'MatchedProbe:SceneIdentity','Raw scene id, timebase, or initial state differs.');
runPack=load(input.run_start_path,'runStart');runStartInput=runPack.runStart;
assert(strcmp(normalize_rel(char(runStartInput.raw_path)),normalize_rel(input.raw_path_rel))&& ...
    isequaln(runStartInput.cfg,pack.cfg), ...
    'MatchedProbe:RunStartIdentity','Original run_start no longer matches the pinned raw/cfg.');

runsDir=fullfile(reportDir,'runs');flightDir=fullfile(runsDir,flightId);
attemptName=sprintf('attempt_%02d',attemptNumber);attemptDir=fullfile(flightDir,attemptName);
startMarker=fullfile(attemptDir,'attempt_started.marker');firstPlantMarker=fullfile(attemptDir,'first_plant_step.marker');
rawPath=fullfile(attemptDir,'raw_run.mat');runStartPath=fullfile(attemptDir,'run_start.mat');
runStatusPath=fullfile(attemptDir,'run_status.json');terminalPath=fullfile(attemptDir,'terminal.marker');
if strcmp(flightId,'T1_B')
    priorDir=fullfile(flightDir,'attempt_01');priorStatusPath=fullfile(priorDir,'run_status.json');
    priorRawPath=fullfile(priorDir,'raw_run.mat');priorPlantMarker=fullfile(priorDir,'first_plant_step.marker');
    assert(isfile(priorStatusPath),'MatchedProbe:RetryEvidence','T1_B attempt_01 status is missing.');
    prior=jsondecode(fileread(priorStatusPath));
    assert(strcmp(prior.status,'FAILED_NO_RETRY')&&strcmp(prior.flight_id,'T1_B')&& ...
        isfield(prior,'plant_calls_started')&&~logical(prior.plant_calls_started)&& ...
        isfield(prior,'raw_exists')&&~logical(prior.raw_exists)&& ...
        ~isfile(priorPlantMarker)&&~isfile(priorRawPath), ...
        'MatchedProbe:RetryEvidence','T1_B attempt_01 is not a confirmed pre-Plant/no-raw failure.');
end
assert(~isfolder(attemptDir)&&~isfile(startMarker)&&~isfile(rawPath)&&~isfile(runStartPath), ...
    'MatchedProbe:NoRetry','This flight attempt directory or START marker already exists.');
freeBytes=java.io.File(reportDir).getFreeSpace();usedBytes=folder_bytes(reportDir);
assert(freeBytes>=30000000000&&usedBytes<1073741824, ...
    'MatchedProbe:Resources','Need >=30 GB free and <1 GiB current probe output before launching.');
if ~isfolder(runsDir),mkdir(runsDir);end;if ~isfolder(flightDir),mkdir(flightDir);end;mkdir(attemptDir);
opts=pack.opts;
opts.r2e_first_plant_step_marker=firstPlantMarker;
mutableInitial=pack.snapshotMeta.mutable_initial_state;
runStart=struct('schema','MATCHED_POSITION_PROBE_RUN_START_V1','flight_id',flightId, ...
    'scene_id',sceneId,'position_mode',modeId,'started_utc',utc_now(), ...
    'release_path',expectedReleasePath,'release_sha256',expectedReleaseSha256, ...
    'prepare_result_sha256',prepSha,'snapshot_path',snapshotPath,'snapshot_sha256',snapshotSha, ...
    'attempt_id',attemptNumber,'runner_v2_sha256',expectedPins.runner_v2_sha256, ...
    'input_identity',input,'cfg',pack.cfg,'opts',opts,'model_identity',pack.c5ModelIdentity, ...
    'mutable_initial_state',mutableInitial,'probe_source_sha256',prepared.source_hashes);
save(runStartPath,'runStart','-v7.3');
write_text_new(startMarker,sprintf('flight_id=%s\nrelease_sha256=%s\nstarted_utc=%s\n',flightId,expectedReleaseSha256,runStart.started_utc));
try
    addpath(fileparts(which('run_episode_dl1018')),'-begin');clear run_episode_dl1018 run_dl1018_closed_loop;rehash;
    wrapperPath=which('run_episode_dl1018');
    assert(same_path(wrapperPath,prepared.C5_source_paths.episode_wrapper), ...
        'MatchedProbe:WrapperPath','C5 episode wrapper resolved to an unexpected path.');
    log=run_episode_dl1018(scene,modeId,pack.cfg,opts,rawPath);
    assert(isfile(firstPlantMarker)&&isfile(rawPath)&&numel(log.time)==20001&& ...
        numel(log.transition_time)==20000&&double(log.last_transition)==20000&& ...
        strcmp(log.status,'STABLE')&&all(isfinite(log.state(:))), ...
        'MatchedProbe:EpisodeIncomplete','Episode did not finish the complete stable 20,000-step run.');
    assert(folder_bytes(reportDir)<=1073741824,'MatchedProbe:OutputBudget','Probe output exceeded 1 GiB.');
    status=struct('schema','MATCHED_POSITION_PROBE_RUN_STATUS_V1','status','RUN_COMPLETE_STABLE', ...
        'flight_id',flightId,'attempt_id',attemptNumber,'scene_id',sceneId,'position_mode',modeId,'release_sha256',expectedReleaseSha256, ...
        'raw_path',rawPath,'raw_sha256',sha256_file(rawPath),'transitions',numel(log.transition_time), ...
        'state_samples',numel(log.time),'engine_status',log.status,'safety_stop_reason',log.safety_stop_reason, ...
        'finished_utc',utc_now(),'plant_calls',1,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
    write_json_new(runStatusPath,status);write_text_new(terminalPath,'RUN_COMPLETE_STABLE');
    result=status;
catch ME
    failure=struct('schema','MATCHED_POSITION_PROBE_RUN_STATUS_V1','status','FAILED_NO_RETRY', ...
        'flight_id',flightId,'attempt_id',attemptNumber,'scene_id',sceneId,'position_mode',modeId, ...
        'release_sha256',expectedReleaseSha256,'error_identifier',ME.identifier, ...
        'error_message',ME.message,'failed_utc',utc_now(),'raw_exists',isfile(rawPath), ...
        'raw_sha256',file_sha_if_exists(rawPath),'plant_calls_started',isfile(firstPlantMarker), ...
        'automatic_retry',false);
    write_json_new(runStatusPath,failure);write_text_new(terminalPath,'FAILED_NO_RETRY');rethrow(ME);
end
end

function verify_c5_sources(si,repoRoot,expectedCfg,c5Paths)
paths=cellstr(string(si.active_paths(:)));hashes=cellstr(string(si.active_sha256(:)));
assert(numel(paths)==32&&numel(paths)==numel(hashes),'MatchedProbe:C5SourceCount','Expected 32 C5 active source pins.');
active=repmat(struct('path','','sha256',''),numel(paths),1);
for k=1:numel(paths),active(k)=struct('path',paths{k},'sha256',hashes{k});verify_file(paths{k},hashes{k});end
add_active_paths(active);addpath(fullfile(repoRoot,'matlab','runtime'),'-end');addpath(fullfile(repoRoot,'matlab','core'),'-end');
initPath=source_path(active,'init_dl1018.m');optionsPath=source_path(active,'position_only_search_options.m');
headPath=source_path(active,'position_only_search_head_step.m');forwardPath=source_path(active,'position_stage1_model_forward_v2.m');
addpath(fileparts(initPath),'-begin');clear init_dl1018;rehash;
[cfgNow,~,resolvedRoot]=init_dl1018();
assert(same_path(resolvedRoot,repoRoot),'MatchedProbe:ProjectRoot','C5 init resolved another project root.');
add_active_paths(active);addpath(fullfile(repoRoot,'matlab','runtime'),'-end');addpath(fullfile(repoRoot,'matlab','core'),'-end');
addpath(fileparts(optionsPath),'-begin');addpath(fileparts(headPath),'-begin');addpath(fileparts(forwardPath),'-begin');
addpath(fileparts(c5Paths.engine),'-begin');
clear run_episode_dl1018 run_dl1018_closed_loop delayed_prediction_step_candidate ...
    position_only_search_options position_only_search_head_step position_stage1_model_forward_v2 init_dl1018;rehash;
whichCount=0;
for k=1:numel(active)
    [~,n,e]=fileparts(active(k).path);
    if strcmpi(e,'.m'),assert(same_path(which(n),active(k).path), ...
            'MatchedProbe:WhichShadow','C5 source %s resolves outside its locked path.',n);whichCount=whichCount+1;end
end
assert(whichCount==31&&isequaln(cfgNow,expectedCfg)&& ...
    same_path(which('run_dl1018_closed_loop'),c5Paths.engine)&& ...
    same_path(which('run_episode_dl1018'),c5Paths.episode_wrapper), ...
    'MatchedProbe:WhichCount','C5 active sources, cfg, engine, or episode wrapper changed.');
end
function verify_c5_files(repoRoot,prepared)
c5Dir=fullfile(repoRoot,'experiments','position_axis_coordinate_c5_dev72_20261023');
assert_sha(fullfile(c5Dir,'run_dl1018_closed_loop.m'),prepared.source_hashes.c5_engine_sha256);
assert_sha(fullfile(c5Dir,'run_episode_dl1018.m'),prepared.source_hashes.c5_episode_wrapper_sha256);
assert_sha(fullfile(c5Dir,'C5_DEV72_SOURCE_BINDING_v3.json'),prepared.C5_source_binding_sha256);
assert_sha(prepared.C5_input_lock_path,prepared.C5_input_lock_sha256);
assert_sha(prepared.C5_prepare_result_path,prepared.C5_prepare_result_sha256);
assert_sha(prepared.C5_snapshot_path,prepared.C5_snapshot_sha256);
assert_sha(prepared.C5_model_mat_path,prepared.C5_model_mat_sha256);
assert_sha(prepared.C5_normalizer_npz_path,prepared.C5_normalizer_npz_sha256);
assert_sha(fullfile(c5Dir,'C5_DEV72_RUN_CONTRACT_v3.json'),prepared.C5_contract_sha256);
assert_sha(fullfile(c5Dir,'C5_DEV72_RELEASE_v3.json'),prepared.C5_release_sha256);
end
function path=source_path(items,name)
ix=[];for k=1:numel(items),[~,n,e]=fileparts(items(k).path);if strcmpi([n e],name),ix(end+1)=k;end,end %#ok<AGROW>
assert(numel(ix)==1,'MatchedProbe:SourcePath','Expected one active C5 source %s.',name);path=items(ix).path;
end
function add_active_paths(items)
for k=1:numel(items),[~,~,e]=fileparts(items(k).path);if strcmpi(e,'.m'),addpath(fileparts(items(k).path),'-end');end,end
end
function row=folder_bytes(path)
d=dir(fullfile(path,'**','*'));d=d(~[d.isdir]);row=sum([d.bytes]);
end
function p=repo_file(root,rel),p=fullfile(root,strrep(char(rel),'/',filesep));end
function x=normalize_rel(x),x=strrep(char(x),'\','/');end
function verify_ref(x),verify_file(x.path,x.sha256);end
function verify_file(path,expected)
assert(isfile(path)&&strcmpi(sha256_file(path),char(expected)), ...
    'MatchedProbe:SHA','Missing file or SHA mismatch: %s.',path);
end
function assert_sha(path,expected),verify_file(path,expected);end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0,'MatchedProbe:Read','Cannot read %s.',path);c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function tf=same_path(a,b),tf=strcmpi(char(java.io.File(a).getCanonicalPath()),char(java.io.File(b).getCanonicalPath()));end
function h=file_sha_if_exists(path),if isfile(path),h=sha256_file(path);else,h='';end,end
function write_json_new(path,value)
assert(~isfile(path),'MatchedProbe:NoOverwrite','Refusing to overwrite %s.',path);fid=fopen(path,'wt');assert(fid>=0,'MatchedProbe:Write','Cannot write %s.',path);c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char');
end
function write_text_new(path,value)
assert(~isfile(path),'MatchedProbe:NoOverwrite','Refusing to overwrite %s.',path);fid=fopen(path,'wt');assert(fid>=0,'MatchedProbe:Write','Cannot write %s.',path);c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,value,'char');
end
function t=utc_now(),t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));end
