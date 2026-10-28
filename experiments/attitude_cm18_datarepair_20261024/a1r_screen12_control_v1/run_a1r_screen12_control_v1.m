function result = run_a1r_screen12_control_v1(sceneId,releasePath,expectedReleaseSha256)
% One scene per ROOT release. This runner never retries an existing attempt.
if nargin~=3||isempty(sceneId)||isempty(releasePath)||isempty(expectedReleaseSha256)
    error('A1R:ReleaseRequired','Pass one scene ID and the exact ROOT release path and SHA256.');
end
here=fileparts(mfilename('fullpath')); experimentDir=fileparts(here); repoRoot=fileparts(fileparts(experimentDir));
reportDir=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','a1r_screen12_control_v1');
taskbookPath=fullfile(reportDir,'A1R_SCREEN12_CONTROL_PREPARATION_TASKBOOK_v1_ZH.md');
approvalPath=fullfile(reportDir,'A1R_SCREEN12_CONTROL_IMPLEMENTATION_APPROVAL_v1.json');
manifestPath=fullfile(repoRoot,'reports','attitude_cm18_a1_20261024','CM18_A1_DEV_SCREEN12_v1.json');
oldPrepPath=fullfile(repoRoot,'reports','attitude_cm18_a1_20261024','screen12_remaining_v1','SCREEN12_REMAINING_PREPARATION_RESULT_v1.json');
c5SnapshotPath=fullfile(repoRoot,'experiments','position_axis_coordinate_c5_dev72_20261023','C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
deploymentPath=fullfile(repoRoot,'experiments','attitude_cm18_datarepair_20261024','postselection_a1r_v1','deployment_parameters_v1.json');
fixturePath=fullfile(here,'artifacts','a1r_forward_parity_fixture_v1.json');
parityPath=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','ROOT_A1R_ACTUAL_MATLAB_PARITY_v1.json');
enginePath=fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','run_cm18_closed_loop_v1.m');
forwardPath=fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','matlab','cm18_a1_forward_v1.m');
predictionPath=fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','delayed_prediction_step_candidate.m');
preparePath=fullfile(here,'prepare_a1r_screen12_control_v1.m'); runnerPath=fullfile(here,'run_a1r_screen12_control_v1.m');
prepPath=fullfile(reportDir,'A1R_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json');
runRoot=fullfile(here,'runs'); ledgerPath=fullfile(runRoot,'A1R_SCREEN12_CONTROL_LEDGER.jsonl');
releasePath=char(releasePath); expectedReleaseSha256=lower(char(expectedReleaseSha256)); sceneId=char(sceneId);
expectedIds={'DL1018_DEV_T1_C01_W15','DL1018_DEV_T1_C00_W03','DL1018_DEV_T1_C15_W14', ...
    'DL1018_DEV_T1_C05_W06','DL1018_DEV_T2_C00_W04','DL1018_DEV_T2_C02_W15', ...
    'DL1018_VAL_T2_C15_W09','DL1018_DEV_T2_C06_W07','DL1018_DEV_T3_C00_W05', ...
    'DL1018_DEV_T3_C03_W15','DL1018_DEV_T3_C15_W14','DL1018_DEV_T3_C05_W02'};
sequenceIndex=find(strcmp(expectedIds,sceneId));
assert(isscalar(sequenceIndex),'A1R:SceneScope','Scene is outside the fixed A1R SCREEN12 set.');
releaseExpected=fullfile(reportDir,['ROOT_A1R_SCREEN12_CONTROL_RELEASE_' sceneId '_v1.json']);
assert(same_path(releasePath,releaseExpected)&&isfile(releaseExpected), ...
    'A1R:ReleasePath','The fixed per-scene ROOT release is missing or a different path was supplied.');
assert(~isempty(regexp(expectedReleaseSha256,'^[0-9a-f]{64}$','once'))&& ...
    strcmpi(sha256_file(releasePath),expectedReleaseSha256), ...
    'A1R:ReleaseSHA','ROOT release SHA256 does not match the explicit launch pin.');
release=jsondecode(fileread(releasePath));
assert(strcmp(release.schema,'A1R_SCREEN12_CONTROL_ROOT_RELEASE_V1')&& ...
    strcmp(release.decision,'APPROVE_ONE_A1R_SCREEN12_FLIGHT')&&logical(release.plant_authorized)&& ...
    strcmp(release.scene_id,sceneId)&&double(release.sequence_index)==sequenceIndex&& ...
    ~logical(field_or(release,'training_authorized',false))&& ...
    double(field_or(release,'optimizer_steps_authorized',0))==0&& ...
    ~logical(field_or(release,'TEST_accessed',false)), ...
    'A1R:ReleaseScope','ROOT release does not approve this exact single scene.');

approval=read_json(approvalPath); prep=read_json(prepPath); manifest=read_json(manifestPath);
verify_file(taskbookPath,char(release.taskbook_sha256));
verify_file(approvalPath,char(release.approval_sha256));
verify_file(manifestPath,char(release.screen12_manifest_sha256));
verify_file(prepPath,char(release.preparation_result_sha256));
verify_file(c5SnapshotPath,char(release.c5_snapshot_sha256));
verify_file(deploymentPath,char(release.deployment_parameters_sha256));
verify_file(fixturePath,char(release.forward_fixture_sha256));
verify_file(parityPath,char(release.matlab_parity_receipt_sha256));
verify_file(enginePath,char(release.engine_sha256)); verify_file(forwardPath,char(release.forward_sha256));
verify_file(predictionPath,char(release.prediction_helper_sha256));
verify_file(preparePath,char(release.prepare_script_sha256)); verify_file(runnerPath,char(release.runner_sha256));
assert(strcmp(approval.status,'IMPLEMENTATION_APPROVED_PLANT_NOT_AUTHORIZED')&& ...
    ~logical(approval.training_authorized)&&double(approval.optimizer_steps_authorized)==0&& ...
    ~logical(approval.TEST_accessed)&& ...
    strcmpi(prep.taskbook_sha256,'f69704d003b880e263ba85fef17b79ebb59517d8b5fed871622ef40c5a1ada47')&& ...
    strcmpi(prep.approval_sha256,'30bee7c5d06a807c7ed6dc35ef15dc3a913a4c9956cc5afb1eab96d46938d84e')&& ...
    strcmp(prep.schema,'CM18_A1R_SCREEN12_CONTROL_PREPARATION_V1')&& ...
    strcmp(prep.status,'PREPARED_A1R_SCREEN12_CONTROL_NO_PLANT_V1')&&double(prep.scene_count)==12&& ...
    double(prep.plant_calls)==0&&double(prep.engine_calls)==0&&double(prep.training_steps)==0&& ...
    double(prep.optimizer_steps)==0&&~logical(prep.TEST_accessed)&& ...
    strcmp(manifest.schema,'CM18_A1_FUTURE_DEVELOPMENT_SCREEN12_V1')&&numel(manifest.scenes)==12, ...
    'A1R:PreparedScope','Preparation/approval does not match the fixed no-Plant scope.');
assert_release(release,'taskbook_sha256',sha256_file(taskbookPath));
assert_release(release,'approval_sha256',sha256_file(approvalPath));
assert_release(release,'preparation_result_sha256',sha256_file(prepPath));
assert_release(release,'screen12_manifest_sha256',sha256_file(manifestPath));
assert_release(release,'c5_snapshot_sha256',sha256_file(c5SnapshotPath));
assert_release(release,'c5_active_source_inventory_sha256',prep.c5_active_source_inventory_sha256);
assert_release(release,'deployment_parameters_sha256',sha256_file(deploymentPath));
assert_release(release,'forward_fixture_sha256',sha256_file(fixturePath));
assert_release(release,'matlab_parity_receipt_sha256',sha256_file(parityPath));
assert_release(release,'engine_sha256',sha256_file(enginePath)); assert_release(release,'forward_sha256',sha256_file(forwardPath));
assert_release(release,'prediction_helper_sha256',sha256_file(predictionPath));
assert_release(release,'prepare_script_sha256',sha256_file(preparePath)); assert_release(release,'runner_sha256',sha256_file(runnerPath));
identity=prep.model_identity;
assert_release(release,'checkpoint_sha256',identity.checkpoint_sha256);
assert_release(release,'selected_step',identity.selected_step);
assert_release(release,'normalizer_float64_sha256',identity.normalizer_float64_sha256);
assert(strcmpi(identity.deployment_parameters_sha256,sha256_file(deploymentPath))&& ...
    strcmpi(identity.deployment_parameters_sha256,'b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23')&& ...
    strcmpi(identity.normalizer_float64_sha256,'faf8748f640c944c745406247ab8486825966abd763088ad1f4e0cde626ad14c'), ...
    'A1R:ModelIdentity','Prepared model identity differs from the frozen A1R step-40000 deployment.');

rows=prep.scene_rows; rowIndex=find(strcmp({rows.scene_id},sceneId));
assert(numel(rowIndex)==1&&double(rows(rowIndex).sequence_index)==sequenceIndex, ...
    'A1R:SceneBinding','This scene is absent or reordered in the preparation result.');
row=rows(rowIndex);
assert_release(release,'baseline_C5_raw_sha256',row.baseline_C5_raw_sha256);
assert_release(release,'prepared_snapshot_sha256',row.prepared_snapshot_sha256);
verify_file(row.baseline_C5_raw_path,row.baseline_C5_raw_sha256);
verify_file(row.prepared_snapshot_path,row.prepared_snapshot_sha256);

% Require every earlier flight and its separate event audit to pass before advancing.
priorAuditHashes=string(field_or(release,'prior_audit_sha256',[])); priorAuditHashes=priorAuditHashes(:);
assert(numel(priorAuditHashes)==sequenceIndex-1,'A1R:PriorAudit','Release must bind every earlier independent audit.');
for k=1:sequenceIndex-1
    priorId=expectedIds{k}; priorStatus=fullfile(runRoot,priorId,'attempt_01','run_status.json');
    priorAudit=fullfile(reportDir,['A1R_SCREEN12_LOG_AUDIT_' priorId '_v1.json']);
    assert(isfile(priorStatus)&&isfile(priorAudit),'A1R:StopOnFailure','Earlier run/audit is missing; stop the series.');
    verify_file(priorAudit,char(priorAuditHashes(k)));
    ps=read_json(priorStatus); pa=read_json(priorAudit);
    assert(strcmp(ps.status,'RUN_COMPLETE_PENDING_ROOT_AUDIT')&&strcmp(ps.scene_id,priorId)&& ...
        strcmp(pa.status,'PASS')&&strcmp(pa.scene_id,priorId)&&strcmpi(pa.raw_sha256,ps.raw_sha256), ...
        'A1R:StopOnFailure','Earlier flight failed or its independent raw audit did not PASS.');
end
ledger=read_ledger(ledgerPath); ledger_gate(ledger,sceneId,expectedIds);

attemptDir=fullfile(runRoot,sceneId,'attempt_01');
assert(~isfolder(attemptDir)&&~isfile(attemptDir), ...
    'A1R:NoRetry','This scene attempt already exists; retain it and do not retry.');
pack=load(row.prepared_snapshot_path,'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity');
rawBase=load(row.baseline_C5_raw_path,'scene','runIdentity');
c5=load(c5SnapshotPath,'cfg','opts','sceneIdentity');
c5Ix=find(strcmp({c5.sceneIdentity.scene_id},sceneId));
assert(all(isfield(pack,{'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity'}))&& ...
    all(isfield(rawBase,{'scene','runIdentity'}))&&numel(c5Ix)==1&& ...
    strcmp(char(pack.scene.scene_id),sceneId)&&strcmp(char(pack.sceneIdentity.scene_id),sceneId)&& ...
    strcmp(char(rawBase.scene.scene_id),sceneId)&&isequaln(pack.scene,rawBase.scene)&& ...
    isequaln(pack.sceneIdentity,c5.sceneIdentity(c5Ix))&&isequaln(pack.cfg,c5.cfg)&& ...
    strcmpi(pack.modelIdentity.checkpoint_sha256,identity.checkpoint_sha256)&& ...
    double(pack.modelIdentity.selected_step)==40000&&logical(pack.opts.cm18_attitude_v1.enabled)&& ...
    isequal(double(pack.opts.position_coordinate_mask(:)),[1;1;0])&& ...
    islogical(pack.opts.rbf_attitude_enabled)&&~pack.opts.rbf_attitude_enabled&& ...
    islogical(pack.opts.rbf_attitude_output_enabled)&&~pack.opts.rbf_attitude_output_enabled&& ...
    islogical(pack.opts.rbf_attitude_update_enabled)&&~pack.opts.rbf_attitude_update_enabled, ...
    'A1R:Snapshot','Scene snapshot/model/options differ from the approved A1R/C5 contract.');
active=pack.sourceIdentity.c5_active_source_inventory; shared=pack.sourceIdentity.c5_shared_inputs;
verify_inventory(active); verify_inventory(shared);
configure_runtime(repoRoot,here,enginePath,forwardPath,predictionPath,active);

budgetBytes=double(approval.output_budget_bytes);
if ~isfolder(runRoot), mkdir(runRoot); end
usedBytes=directory_bytes(runRoot);
assert(usedBytes<budgetBytes&&java.io.File(repoRoot).getFreeSpace()>=budgetBytes-usedBytes, ...
    'A1R:OutputBudget','The fixed 1.5 GiB A1R output reserve is unavailable.');
lockPath=fullfile(runRoot,'.a1r_screen12_plant_lock');
assert(java.io.File(lockPath).createNewFile(),'A1R:Busy','Another flight is active or left a lock; do not remove it.');
lockToken=char(java.util.UUID.randomUUID().toString());
lockCleanup=onCleanup(@()delete_lock(lockPath,lockToken)); %#ok<NASGU>
write_lock_token(lockPath,lockToken);
ledger=read_ledger(ledgerPath); ledger_gate(ledger,sceneId,expectedIds);
assert(~isfolder(attemptDir)&&~isfile(attemptDir),'A1R:NoRetry','Attempt appeared while locking; retain it.');
mkdir(attemptDir);
startMarker=fullfile(attemptDir,'attempt_started.marker'); firstPlantMarker=fullfile(attemptDir,'first_plant_step.marker');
runStartPath=fullfile(attemptDir,'run_start.mat'); rawOutPath=fullfile(attemptDir,'raw_run.mat');
statusPath=fullfile(attemptDir,'run_status.json'); opts=pack.opts; opts.r2e_first_plant_step_marker=firstPlantMarker;
startedUtc=utc_now();
runStart=struct('schema','A1R_SCREEN12_CONTROL_RUN_START_V1','scene_id',sceneId, ...
    'sequence_index',sequenceIndex,'started_utc',startedUtc,'root_release_path',releasePath, ...
    'root_release_sha256',expectedReleaseSha256,'preparation_result_sha256',sha256_file(prepPath), ...
    'screen12_manifest_sha256',sha256_file(manifestPath),'baseline_C5_raw_path',row.baseline_C5_raw_path, ...
    'baseline_C5_raw_sha256',sha256_file(row.baseline_C5_raw_path), ...
    'prepared_snapshot_path',row.prepared_snapshot_path,'prepared_snapshot_sha256',sha256_file(row.prepared_snapshot_path), ...
    'model_identity',pack.modelIdentity,'scene_identity',pack.sceneIdentity,'cfg',pack.cfg,'opts',opts, ...
    'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
save(runStartPath,'runStart','-v7.3'); write_new(startMarker,[startedUtc newline 'ABOUT_TO_CALL_ONE_A1R_SCREEN12_SCENE' newline]);
append_ledger(ledgerPath,struct('schema','A1R_SCREEN12_CONTROL_LEDGER_V1','event','RUN_STARTED', ...
    'status','RUN_STARTED','scene_id',sceneId,'root_release_sha256',expectedReleaseSha256, ...
    'run_start_path',runStartPath,'created_utc',utc_now()));
invocationEntered=true;
try
    log=run_cm18_closed_loop_v1(pack.scene,'B2-RBF-Full-SPLIT',pack.cfg,opts);
    log.scene_id=sceneId; log.collector='CM18_A1R_SCREEN12_CONTROL'; scene=pack.scene;
    runIdentity=struct('schema','A1R_SCREEN12_CONTROL_RUN_IDENTITY_V1','scene_id',sceneId, ...
        'sequence_index',sequenceIndex,'root_release_sha256',expectedReleaseSha256, ...
        'preparation_result_sha256',sha256_file(prepPath),'baseline_C5_raw_sha256',sha256_file(row.baseline_C5_raw_path), ...
        'prepared_snapshot_sha256',sha256_file(row.prepared_snapshot_path),'model_identity',pack.modelIdentity, ...
        'scene_identity',pack.sceneIdentity,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
    save(rawOutPath,'log','scene','runStart','runIdentity','-v7.3');
    transitions=numel(log.transition_time); samples=numel(log.time); events=sum(log.cm18_event_flag(:));
    complete=isfield(log,'status')&&strcmpi(char(log.status),'STABLE')&& ...
        isfield(log,'safety_stop_reason')&&isempty(char(log.safety_stop_reason))&& ...
        transitions==20000&&samples==20001&&double(log.last_transition)==20000&&events==1999&& ...
        all(isfinite(log.state(:)))&&all(isfinite(log.reference.position(:)))&&isfile(firstPlantMarker);
    label='FAILED_NO_RETRY'; if complete, label='RUN_COMPLETE_PENDING_ROOT_AUDIT'; end
    runStatus=struct('schema','A1R_SCREEN12_CONTROL_RUN_STATUS_V1','status',label,'scene_id',sceneId, ...
        'sequence_index',sequenceIndex,'log_status',char(log.status),'safety_stop_reason',char(log.safety_stop_reason), ...
        'transitions',transitions,'state_samples',samples,'cm18_events',events,'raw_path',rawOutPath, ...
        'raw_sha256',sha256_file(rawOutPath),'run_start_sha256',sha256_file(runStartPath), ...
        'first_plant_step_confirmed',isfile(firstPlantMarker),'root_release_sha256',expectedReleaseSha256, ...
        'plant_invocation_entered',true,'plant_calls',1,'training_steps',0,'optimizer_steps',0, ...
        'TEST_accessed',false,'output_directory_bytes',directory_bytes(runRoot),'created_utc',utc_now());
    if double(runStatus.output_directory_bytes)>budgetBytes, runStatus.status='FAILED_OUTPUT_BUDGET'; end
    write_json_new(statusPath,runStatus);
    append_ledger(ledgerPath,struct('schema','A1R_SCREEN12_CONTROL_LEDGER_V1','event','RUN_TERMINAL', ...
        'status',runStatus.status,'scene_id',sceneId,'run_status_path',statusPath, ...
        'raw_sha256',runStatus.raw_sha256,'created_utc',utc_now()));
    assert(complete&&strcmp(runStatus.status,'RUN_COMPLETE_PENDING_ROOT_AUDIT'), ...
        'A1R:Incomplete','Flight failed, stopped, or exceeded output budget; retain all evidence and stop.');
    result=runStatus;
catch ME
    if invocationEntered&&~isfile(statusPath)
        failure=struct('schema','A1R_SCREEN12_CONTROL_RUN_STATUS_V1','status','FAILED_NO_RETRY', ...
            'scene_id',sceneId,'sequence_index',sequenceIndex,'error_identifier',ME.identifier, ...
            'error_message',ME.message,'first_plant_step_confirmed',isfile(firstPlantMarker), ...
            'root_release_sha256',expectedReleaseSha256,'plant_invocation_entered',true,'plant_calls',1, ...
            'training_steps',0,'optimizer_steps',0,'TEST_accessed',false,'created_utc',utc_now());
        write_json_new(statusPath,failure);
        append_ledger(ledgerPath,struct('schema','A1R_SCREEN12_CONTROL_LEDGER_V1','event','RUN_TERMINAL', ...
            'status','FAILED_NO_RETRY','scene_id',sceneId,'run_status_path',statusPath,'created_utc',utc_now()));
    end
    rethrow(ME);
end
end

function configure_runtime(repoRoot,here,enginePath,forwardPath,predictionPath,active)
addpath(fullfile(repoRoot,'matlab','runtime'),'-end'); addpath(fullfile(repoRoot,'matlab','core'),'-end');
addpath(fullfile(repoRoot,'matlab','models'),'-end');
for k=1:numel(active), path=char(active(k).path); if endsWith(lower(path),'.m'), addpath(fileparts(path),'-end'); end, end
addpath(fileparts(source_path(active,'position_only_search_options.m')),'-begin');
addpath(fileparts(source_path(active,'position_only_search_head_step.m')),'-begin');
addpath(fileparts(source_path(active,'position_stage1_model_forward_v2.m')),'-begin');
addpath(fileparts(source_path(active,'run_dl1018_closed_loop.m')),'-begin');
addpath(fileparts(predictionPath),'-begin'); addpath(fileparts(forwardPath),'-begin'); addpath(fileparts(enginePath),'-begin');
addpath(here,'-begin');
clear run_cm18_closed_loop_v1 delayed_prediction_step_candidate cm18_a1_forward_v1; rehash;
assert(same_path(which('run_cm18_closed_loop_v1'),enginePath)&& ...
    same_path(which('cm18_a1_forward_v1'),forwardPath)&& ...
    same_path(which('delayed_prediction_step_candidate'),predictionPath), ...
    'A1R:RuntimePath','A1 engine/forward/prediction helper resolved outside pinned paths.');
for k=1:numel(active)
    path=char(active(k).path); [~,name,ext]=fileparts(path);
    if strcmpi(ext,'.m')
        expectedPath=path; if strcmp(name,'delayed_prediction_step_candidate'), expectedPath=predictionPath; end
        assert(same_path(which(name),expectedPath),'A1R:C5Path','C5 helper %s resolved outside its pinned source.',name);
    end
end
end
function ledger_gate(ledger,sceneId,ids)
if isempty(ledger), return; end
assert(numel(ledger)<=24,'A1R:Ledger','Ledger has more than one start/terminal pair per scene.');
events={ledger.event}; scenes={ledger.scene_id}; statuses={ledger.status};
assert(all(ismember(events,{'RUN_STARTED','RUN_TERMINAL'}))&&all(ismember(scenes,ids)), ...
    'A1R:Ledger','Ledger contains an unknown event or scene.');
starts=find(strcmp(events,'RUN_STARTED')); terminals=find(strcmp(events,'RUN_TERMINAL'));
assert(numel(starts)==numel(terminals)||numel(starts)==numel(terminals)+1, ...
    'A1R:Ledger','Ledger start/terminal pairs are malformed.');
assert(numel(unique(scenes(starts)))==numel(starts)&&~any(strcmp(scenes(starts),sceneId)), ...
    'A1R:NoRetry','A scene already has a start record; do not retry.');
for k=1:numel(starts)
    ix=find(strcmp(scenes,scenes{starts(k)})&strcmp(events,'RUN_TERMINAL'));
    assert(numel(ix)==1&&ix>starts(k)&&strcmp(statuses{ix},'RUN_COMPLETE_PENDING_ROOT_AUDIT'), ...
        'A1R:StopOnFailure','A previous scene failed or is incomplete.');
end
assert(numel(terminals)==numel(starts),'A1R:StopOnFailure','A previous scene is still incomplete.');
startOrder=zeros(1,numel(starts));
for k=1:numel(starts)
    ix=find(strcmp(ids,scenes{starts(k)}));
    assert(isscalar(ix),'A1R:LedgerOrder','Ledger contains an unknown scene.');
    startOrder(k)=ix;
end
assert(all(startOrder>0)&&isequal(startOrder,1:numel(startOrder)), ...
    'A1R:LedgerOrder','Ledger contains an unknown or out-of-order scene.');
end
function items=read_ledger(path)
items=struct('event',{},'status',{},'scene_id',{}); if ~isfile(path), return; end
lines=splitlines(string(fileread(path))); lines=lines(strlength(strtrim(lines))>0);
for k=1:numel(lines)
    row=jsondecode(char(lines(k)));
    assert(all(isfield(row,{'schema','event','status','scene_id'}))&& ...
        strcmp(row.schema,'A1R_SCREEN12_CONTROL_LEDGER_V1'), ...
        'A1R:Ledger','Ledger is malformed; retain it and stop.');
    items(end+1)=struct('event',char(row.event),'status',char(row.status),'scene_id',char(row.scene_id)); %#ok<AGROW>
end
end
function assert_release(release,name,value)
assert(isfield(release,name),'A1R:ReleaseField','ROOT release is missing %s.',name);
actual=release.(name);
if isnumeric(value), ok=isnumeric(actual)&&isequal(double(actual),double(value));
else, ok=strcmpi(char(actual),char(value)); end
assert(ok,'A1R:ReleasePin','ROOT release field %s does not match current identity.',name);
end
function verify_inventory(items)
for k=1:numel(items), verify_file(char(items(k).path),char(items(k).sha256)); end
end
function path=source_path(items,name)
matches=[];
for k=1:numel(items)
    [~,n,e]=fileparts(char(items(k).path));
    if strcmpi([n e],name), matches(end+1)=k; end %#ok<AGROW>
end
assert(numel(matches)==1,'A1R:SourceName','Expected one pinned C5 source named %s.',name);
path=char(items(matches).path);
end
function verify_file(path,expected)
assert(isfile(path),'A1R:MissingFile','Missing pinned input: %s.',path);
assert(strcmpi(sha256_file(path),expected),'A1R:SHA','SHA-256 mismatch: %s.',path);
end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r');
assert(fid>=0,'A1R:ReadFile','Cannot read %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(b); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json_new(path,value)
assert(~isfile(path),'A1R:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'A1R:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char');
end
function write_new(path,text)
assert(~isfile(path),'A1R:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'A1R:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,text,'char');
end
function n=directory_bytes(path)
d=dir(fullfile(path,'**','*')); d=d(~[d.isdir]); n=sum(double([d.bytes]));
end
function write_lock_token(path,token)
fid=fopen(path,'w'); assert(fid>=0,'A1R:Lock','Cannot write the lock token.'); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,token,'char');
end
function delete_lock(path,token)
if isfile(path)&&strcmp(fileread(path),token), delete(path); end
end
function tf=same_path(a,b), tf=strcmpi(char(java.io.File(char(a)).getCanonicalPath()),char(java.io.File(char(b)).getCanonicalPath())); end
function v=field_or(s,name,default), if isfield(s,name), v=s.(name); else, v=default; end, end
function t=utc_now(), t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')); end
