function result = run_a1t_screen12_control_v1(sceneId,releasePath,expectedReleaseSha256)
% One scene per Root release. Existing attempts are never retried.
if nargin~=3||isempty(sceneId)||isempty(releasePath)||isempty(expectedReleaseSha256)
    error('A1T:ReleaseRequired','Pass one scene ID and the exact Root release path and SHA-256.');
end
here=fileparts(mfilename('fullpath')); expRoot=fileparts(here); repoRoot=fileparts(fileparts(expRoot));
reportDir=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','a1t_screen12_control_v1');
taskbookPath=fullfile(reportDir,'A1T_SCREEN12_CONTROL_TASKBOOK_v2_ZH.md');
manifestPath=fullfile(repoRoot,'reports','attitude_cm18_a1_20261024','CM18_A1_DEV_SCREEN12_v1.json');
a1rReportDir=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','a1r_screen12_control_v1');
a1rPrepPath=fullfile(a1rReportDir,'A1R_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json');
c5SnapshotPath=fullfile(repoRoot,'experiments','position_axis_coordinate_c5_dev72_20261023','C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
deploymentPath=fullfile(repoRoot,'experiments','attitude_cm18_datarepair_20261024','postselection_a1t_v1','deployment_parameters_v1.json');
parityPath=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','ROOT_A1T_ACTUAL_MATLAB_PARITY_v1.json');
fixturePath=fullfile(repoRoot,'experiments','attitude_cm18_datarepair_20261024','postselection_a1t_v1','matlab_parity_fixture_v1.json');
enginePath=fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','run_cm18_closed_loop_v1.m');
forwardPath=fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','matlab','cm18_a1_forward_v1.m');
predictionPath=fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','delayed_prediction_step_candidate.m');
preparePath=fullfile(here,'prepare_a1t_screen12_control_v1.m'); runnerPath=fullfile(here,'run_a1t_screen12_control_v1.m');
prepPath=fullfile(reportDir,'A1T_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json');
runRoot=fullfile(here,'runs'); ledgerPath=fullfile(runRoot,'A1T_SCREEN12_CONTROL_LEDGER.jsonl');
expectedIds={'DL1018_DEV_T1_C01_W15','DL1018_DEV_T1_C00_W03','DL1018_DEV_T1_C15_W14', ...
    'DL1018_DEV_T1_C05_W06','DL1018_DEV_T2_C00_W04','DL1018_DEV_T2_C02_W15', ...
    'DL1018_VAL_T2_C15_W09','DL1018_DEV_T2_C06_W07','DL1018_DEV_T3_C00_W05', ...
    'DL1018_DEV_T3_C03_W15','DL1018_DEV_T3_C15_W14','DL1018_DEV_T3_C05_W02'};
sceneId=char(sceneId); sequenceIndex=find(strcmp(expectedIds,sceneId));
assert(isscalar(sequenceIndex),'A1T:SceneScope','Scene is outside the fixed A1T SCREEN12 set.');
releaseExpected=fullfile(reportDir,['ROOT_A1T_SCREEN12_CONTROL_RELEASE_' sceneId '_v1.json']);
releasePath=char(releasePath); if ~isfile(releasePath), releasePath=fullfile(repoRoot,releasePath); end
assert(same_path(releasePath,releaseExpected)&&isfile(releaseExpected), ...
    'A1T:ReleasePath','The fixed per-scene Root release is missing or a different path was supplied.');
expectedReleaseSha256=lower(char(expectedReleaseSha256));
assert(~isempty(regexp(expectedReleaseSha256,'^[0-9a-f]{64}$','once'))&& ...
    strcmpi(sha256_file(releaseExpected),expectedReleaseSha256), ...
    'A1T:ReleaseSHA','Root release SHA-256 does not match the explicit launch pin.');
release=read_json(releaseExpected);
assert(strcmp(release.schema,'A1T_SCREEN12_CONTROL_ROOT_RELEASE_V1')&& ...
    strcmp(release.decision,'APPROVE_ONE_A1T_SCREEN12_FLIGHT')&&logical(release.plant_authorized)&& ...
    strcmp(release.scene_id,sceneId)&&double(release.sequence_index)==sequenceIndex&& ...
    ~logical(field_or(release,'training_authorized',false))&& ...
    double(field_or(release,'optimizer_steps_authorized',0))==0&& ...
    ~logical(field_or(release,'TEST_accessed',false)), ...
    'A1T:ReleaseScope','Root release does not approve this exact single scene.');

prep=read_json(prepPath); a1rPrep=read_json(a1rPrepPath); manifest=read_json(manifestPath);
deployment=read_json(deploymentPath); parity=read_json(parityPath);
expectedTaskbookSha='060ae7dbd36df7000711c961967a694186239af3520bdd581cf7d04b7b3e75fd';
expectedManifestSha='fdca3f17c0f39d19eb5b08e94e7e5b1f148ec03cf861eacec64d86ab7922f923';
expectedA1rPrepSha='4792a168e5057827cbec184d9c7354e76641c02a7c6509680642585c6b7c1b2b';
expectedC5SnapshotSha='842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a';
expectedDeploymentSha='dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42';
expectedC5SourceSha='6790dc2e5d3bdc5afece8f2577e9e3fa9694bda94a26433f723f271f2850a804';
expectedCheckpointSha='58c72450fcc1e9aaa04f7454ad2a8aa551f161a95e52bb9946f0c99c23957cea';
expectedNormalizerSha='12c864b9c2404235e0ea3f313bb0801a99902eca7cfdfbf43f0d8d584d5d609a';
expectedFixtureSha='a94ef0be146563ea2fe9f6cb43a78c43d2918e77e42b44a85ad3a3cbc4d55996';
expectedParitySha='e9fac82b7d713195b8de0a79a213693138ef49001b02a3c1437d58fd9e9e5323';
expectedEngineSha='4f72db75f176e76de03f77b45e0b82f05ff0e3206907714f3c7faf786ba1092a';
expectedForwardSha='1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9';
expectedPredictionSha='48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d';
verify_file(taskbookPath,expectedTaskbookSha); verify_file(manifestPath,expectedManifestSha);
verify_file(a1rPrepPath,expectedA1rPrepSha); verify_file(c5SnapshotPath,expectedC5SnapshotSha);
verify_file(deploymentPath,expectedDeploymentSha); verify_file(parityPath,expectedParitySha);
verify_file(fixturePath,expectedFixtureSha);
verify_file(enginePath,expectedEngineSha); verify_file(forwardPath,expectedForwardSha); verify_file(predictionPath,expectedPredictionSha);
verify_file(preparePath,char(release.prepare_script_sha256)); verify_file(runnerPath,char(release.runner_sha256));
assert(strcmp(prep.schema,'CM18_A1T_SCREEN12_CONTROL_PREPARATION_V1')&& ...
    strcmp(prep.status,'PREPARED_A1T_SCREEN12_CONTROL_NO_PLANT_V1')&&double(prep.scene_count)==12&& ...
    double(prep.plant_calls)==0&&double(prep.engine_calls)==0&&double(prep.run_episode_calls)==0&& ...
    double(prep.training_steps)==0&&double(prep.optimizer_steps)==0&&~logical(prep.TEST_accessed)&& ...
    strcmpi(prep.taskbook_sha256,expectedTaskbookSha)&&strcmpi(prep.a1r_preparation_sha256,expectedA1rPrepSha)&& ...
    strcmpi(prep.c5_active_source_inventory_sha256,expectedC5SourceSha)&& ...
    strcmpi(prep.c5_snapshot_sha256,expectedC5SnapshotSha)&& ...
    strcmpi(prep.deployment_parameters_sha256,expectedDeploymentSha)&& ...
    strcmpi(prep.forward_fixture_sha256,expectedFixtureSha)&& ...
    strcmpi(prep.matlab_parity_receipt_sha256,char(release.matlab_parity_receipt_sha256))&& ...
    strcmpi(prep.matlab_parity_receipt_sha256,expectedParitySha)&& ...
    strcmpi(prep.engine_sha256,expectedEngineSha)&&strcmpi(prep.forward_sha256,expectedForwardSha)&& ...
    strcmpi(prep.prediction_helper_sha256,expectedPredictionSha)&& ...
    strcmpi(prep.prepare_script_sha256,char(release.prepare_script_sha256))&& ...
    strcmpi(prep.runner_sha256,char(release.runner_sha256))&& ...
    strcmpi(a1rPrep.screen12_manifest_sha256,expectedManifestSha)&& ...
    strcmpi(a1rPrep.c5_snapshot_sha256,char(release.c5_snapshot_sha256))&& ...
    strcmpi(deployment.identity.checkpoint_sha256,expectedCheckpointSha)&& ...
    double(deployment.identity.selected_step)==40000&& ...
    strcmpi(deployment.identity.canonical_normalizer_float64_sha256,expectedNormalizerSha)&& ...
    strcmp(parity.status,'PASS')&&strcmpi(parity.deployment_sha256,expectedDeploymentSha)&& ...
    strcmpi(parity.checkpoint_sha256,expectedCheckpointSha)&&double(parity.selected_step)==40000&& ...
    strcmpi(parity.canonical_normalizer_float64_sha256,expectedNormalizerSha)&&double(parity.case_count)==11&& ...
    ~logical(deployment.identity.deployment_authorized), ...
    'A1T:PreparedScope','Prepared model, A1R baseline, parity or no-Plant scope is invalid.');
assert_release(release,'taskbook_sha256',expectedTaskbookSha);
assert_release(release,'preparation_result_sha256',sha256_file(prepPath));
assert_release(release,'a1r_preparation_result_sha256',sha256_file(a1rPrepPath));
assert_release(release,'screen12_manifest_sha256',expectedManifestSha);
assert_release(release,'c5_snapshot_sha256',expectedC5SnapshotSha);
assert_release(release,'c5_active_source_inventory_sha256',prep.c5_active_source_inventory_sha256);
assert_release(release,'deployment_parameters_sha256',expectedDeploymentSha);
assert_release(release,'checkpoint_sha256',expectedCheckpointSha); assert_release(release,'selected_step',40000);
assert_release(release,'canonical_normalizer_float64_sha256',expectedNormalizerSha);
assert_release(release,'matlab_parity_receipt_sha256',expectedParitySha);
assert_release(release,'forward_fixture_sha256',sha256_file(fixturePath));
assert_release(release,'engine_sha256',expectedEngineSha); assert_release(release,'forward_sha256',expectedForwardSha);
assert_release(release,'prediction_helper_sha256',expectedPredictionSha);
assert_release(release,'prepare_script_sha256',sha256_file(preparePath));
assert_release(release,'runner_sha256',sha256_file(runnerPath));
assert(strcmp(manifest.schema,'CM18_A1_FUTURE_DEVELOPMENT_SCREEN12_V1')&& ...
    strcmp(manifest.first_engineering_scene,expectedIds{1})&&numel(manifest.scenes)==12, ...
    'A1T:Manifest','SCREEN12 manifest changed.');
rowIx=find(strcmp({prep.scene_rows.scene_id},sceneId));
assert(isscalar(rowIx)&&double(prep.scene_rows(rowIx).sequence_index)==sequenceIndex, ...
    'A1T:SceneBinding','This scene is absent or reordered in the A1T preparation result.');
row=prep.scene_rows(rowIx);
assert_release(release,'prepared_snapshot_sha256',row.prepared_snapshot_sha256);
verify_file(row.prepared_snapshot_path,row.prepared_snapshot_sha256);
verify_file(row.a1r_snapshot_path,row.a1r_snapshot_sha256);
assert_release(release,'baseline_C5_raw_sha256',row.baseline_C5_raw_sha256);
verify_file(row.baseline_C5_raw_path,row.baseline_C5_raw_sha256);

[a1rStatus,a1rAudit,a1rStatusPath,a1rAuditPath]=same_scene_a1r_pass(repoRoot,a1rReportDir,sceneId);
assert_release(release,'same_scene_a1r_raw_sha256',a1rStatus.raw_sha256);
assert_release(release,'same_scene_a1r_audit_sha256',sha256_file(a1rAuditPath));
assert(strcmpi(a1rAudit.raw_sha256,a1rStatus.raw_sha256)&&strcmp(a1rAudit.status,'PASS'), ...
    'A1T:A1rAudit','Same-scene A1R audit is not a PASS for this raw.');
assert(isfield(release,'prior_a1t_audit_sha256'),'A1T:PriorAudit','Release must include prior_a1t_audit_sha256.');
priorHashes=string(release.prior_a1t_audit_sha256); priorHashes=priorHashes(:);
assert(numel(priorHashes)==sequenceIndex-1,'A1T:PriorAudit','Release must pin every earlier A1T audit.');
verify_prior_a1t(repoRoot,reportDir,runRoot,priorHashes,expectedIds,sequenceIndex);
ledger=read_ledger(ledgerPath); ledger_gate(ledger,sceneId,expectedIds,sequenceIndex);

attemptDir=fullfile(runRoot,sceneId,'attempt_01');
assert(~isfolder(attemptDir)&&~isfile(attemptDir), ...
    'A1T:NoRetry','This scene attempt already exists; preserve it and do not retry.');
pack=load(row.prepared_snapshot_path,'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity');
a1rPack=load(row.a1r_snapshot_path,'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity');
rawBase=load(row.baseline_C5_raw_path,'scene','runIdentity');
c5=load(c5SnapshotPath,'cfg','opts','sceneIdentity');
model=deployment_model(deployment.parameters);
sceneIdentityIx=find(strcmp({c5.sceneIdentity.scene_id},sceneId));
assert(isscalar(sceneIdentityIx),'A1T:SceneIdentity','C5 scene identity is missing or duplicated.');
assert(all(isfield(pack,{'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity'}))&& ...
    all(isfield(a1rPack,{'cfg','opts','scene','sceneIdentity','modelIdentity','sourceIdentity'}))&& ...
    all(isfield(rawBase,{'scene','runIdentity'}))&&all(isfield(c5,{'cfg','opts','sceneIdentity'}))&& ...
    strcmp(char(pack.scene.scene_id),sceneId)&&strcmp(char(a1rPack.scene.scene_id),sceneId)&& ...
    isequaln(pack.scene,rawBase.scene)&&isequaln(pack.scene,a1rPack.scene)&& ...
    isequaln(pack.cfg,c5.cfg)&&isequaln(pack.cfg,a1rPack.cfg)&& ...
    isequaln(pack.sceneIdentity,a1rPack.sceneIdentity)&& ...
    isequaln(pack.sceneIdentity,c5.sceneIdentity(sceneIdentityIx))&& ...
    strcmpi(pack.modelIdentity.deployment_parameters_sha256,expectedDeploymentSha)&& ...
    strcmpi(pack.modelIdentity.checkpoint_sha256,expectedCheckpointSha)&& ...
    double(pack.modelIdentity.selected_step)==40000&& ...
    strcmpi(pack.modelIdentity.canonical_normalizer_float64_sha256,expectedNormalizerSha)&& ...
    isequaln(pack.opts.cm18_attitude_v1.model,model)&&logical(pack.opts.cm18_attitude_v1.enabled)&& ...
    strcmpi(pack.sourceIdentity.c5_active_source_inventory_sha256,prep.c5_active_source_inventory_sha256)&& ...
    islogical(pack.opts.rbf_attitude_enabled)&&~pack.opts.rbf_attitude_enabled&& ...
    islogical(pack.opts.rbf_attitude_output_enabled)&&~pack.opts.rbf_attitude_output_enabled&& ...
    islogical(pack.opts.rbf_attitude_update_enabled)&&~pack.opts.rbf_attitude_update_enabled&& ...
    isequal(double(pack.opts.position_coordinate_mask(:)),[1;1;0]), ...
    'A1T:Snapshot','Snapshot differs from the exact same-scene A1R/C5 contract.');
assert(isfield(a1rPack.opts,'cm18_attitude_v1')&&logical(a1rPack.opts.cm18_attitude_v1.enabled)&& ...
    strcmpi(a1rPack.modelIdentity.deployment_parameters_sha256,a1rPrep.deployment_parameters_sha256), ...
    'A1T:A1rSnapshot','A1R source snapshot identity changed.');
active=pack.sourceIdentity.c5_active_source_inventory; shared=pack.sourceIdentity.c5_shared_inputs;
verify_inventory(active); verify_inventory(shared);
configure_runtime(repoRoot,here,enginePath,forwardPath,predictionPath,active);

budgetBytes=1610612736;
if ~isfolder(runRoot), mkdir(runRoot); end
usedBytes=directory_bytes(runRoot);
assert(usedBytes<budgetBytes&&java.io.File(repoRoot).getFreeSpace()>=budgetBytes-usedBytes, ...
    'A1T:OutputBudget','The fixed 1.5 GiB output reserve is unavailable.');
lockPath=fullfile(runRoot,'.a1t_screen12_plant_lock');
assert(java.io.File(lockPath).createNewFile(),'A1T:Busy','Another A1T flight is active or left a lock; do not remove it.');
lockToken=char(java.util.UUID.randomUUID().toString());
lockCleanup=onCleanup(@()delete_lock(lockPath,lockToken)); %#ok<NASGU>
write_lock_token(lockPath,lockToken);
ledger=read_ledger(ledgerPath); ledger_gate(ledger,sceneId,expectedIds,sequenceIndex);
assert(~isfolder(attemptDir)&&~isfile(attemptDir),'A1T:NoRetry','Attempt appeared while locking; retain it.');
mkdir(attemptDir); attemptCreated=true; invocationEntered=false;
startMarker=fullfile(attemptDir,'attempt_started.marker'); firstPlantMarker=fullfile(attemptDir,'first_plant_step.marker');
runStartPath=fullfile(attemptDir,'run_start.mat'); rawOutPath=fullfile(attemptDir,'raw_run.mat');
statusPath=fullfile(attemptDir,'run_status.json'); opts=pack.opts; opts.r2e_first_plant_step_marker=firstPlantMarker;
startedUtc=utc_now();
runStart=struct('schema','A1T_SCREEN12_CONTROL_RUN_START_V1','scene_id',sceneId, ...
    'sequence_index',sequenceIndex,'started_utc',startedUtc,'root_release_path',releaseExpected, ...
    'root_release_sha256',expectedReleaseSha256,'taskbook_sha256',sha256_file(taskbookPath), ...
    'preparation_result_sha256',sha256_file(prepPath),'screen12_manifest_sha256',sha256_file(manifestPath), ...
    'same_scene_a1r_status_path',a1rStatusPath,'same_scene_a1r_audit_path',a1rAuditPath, ...
    'same_scene_a1r_raw_sha256',a1rStatus.raw_sha256,'same_scene_a1r_audit_sha256',sha256_file(a1rAuditPath), ...
    'baseline_C5_raw_path',row.baseline_C5_raw_path,'baseline_C5_raw_sha256',sha256_file(row.baseline_C5_raw_path), ...
    'a1r_snapshot_path',row.a1r_snapshot_path,'a1r_snapshot_sha256',sha256_file(row.a1r_snapshot_path), ...
    'prepared_snapshot_path',row.prepared_snapshot_path,'prepared_snapshot_sha256',sha256_file(row.prepared_snapshot_path), ...
    'model_identity',pack.modelIdentity,'scene_identity',pack.sceneIdentity,'cfg',pack.cfg,'opts',opts, ...
    'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
try
save(runStartPath,'runStart','-v7.3');
write_new(startMarker,[startedUtc newline 'ABOUT_TO_CALL_ONE_A1T_SCREEN12_SCENE' newline]);
append_ledger(ledgerPath,struct('schema','A1T_SCREEN12_CONTROL_LEDGER_V1','event','RUN_STARTED', ...
    'status','RUN_STARTED','scene_id',sceneId,'root_release_sha256',expectedReleaseSha256, ...
    'run_start_path',runStartPath,'created_utc',utc_now()));
    invocationEntered=true;
    log=run_cm18_closed_loop_v1(pack.scene,'B2-RBF-Full-SPLIT',pack.cfg,opts);
    log.scene_id=sceneId; log.collector='CM18_A1T_SCREEN12_CONTROL'; scene=pack.scene;
    runIdentity=struct('schema','A1T_SCREEN12_CONTROL_RUN_IDENTITY_V1','scene_id',sceneId, ...
        'sequence_index',sequenceIndex,'root_release_sha256',expectedReleaseSha256, ...
        'taskbook_sha256',sha256_file(taskbookPath),'preparation_result_sha256',sha256_file(prepPath), ...
        'baseline_C5_raw_sha256',sha256_file(row.baseline_C5_raw_path), ...
        'a1r_raw_sha256',a1rStatus.raw_sha256,'a1r_audit_sha256',sha256_file(a1rAuditPath), ...
        'prepared_snapshot_sha256',sha256_file(row.prepared_snapshot_path), ...
        'model_identity',pack.modelIdentity,'scene_identity',pack.sceneIdentity, ...
        'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
    save(rawOutPath,'log','scene','runStart','runIdentity','-v7.3');
    transitions=numel(field_or(log,'transition_time',[])); samples=numel(field_or(log,'time',[]));
    events=sum(double(field_or(log,'cm18_event_flag',[])));
    logStatus=char(field_or(log,'status',''));
    stopReason=char(field_or(log,'safety_stop_reason',''));
    complete=strcmpi(logStatus,'STABLE')&&isempty(stopReason)&&transitions==20000&& ...
        samples==20001&&double(field_or(log,'last_transition',NaN))==20000&&events==1999&& ...
        all(isfinite(log.state(:)))&&all(isfinite(log.reference.position(:)))&&isfile(firstPlantMarker);
    label='FAILED_NO_RETRY'; if complete, label='RUN_COMPLETE_PENDING_ROOT_AUDIT'; end
    runStatus=struct('schema','A1T_SCREEN12_CONTROL_RUN_STATUS_V1','status',label,'scene_id',sceneId, ...
        'sequence_index',sequenceIndex,'log_status',logStatus,'safety_stop_reason',stopReason, ...
        'transitions',transitions,'state_samples',samples,'cm18_events',events,'raw_path',rawOutPath, ...
        'raw_sha256',sha256_file(rawOutPath),'run_start_sha256',sha256_file(runStartPath), ...
        'first_plant_step_confirmed',isfile(firstPlantMarker),'root_release_sha256',expectedReleaseSha256, ...
        'engine_invocation_entered',invocationEntered,'plant_calls',double(isfile(firstPlantMarker)), ...
        'training_steps',0,'optimizer_steps',0,'TEST_accessed',false, ...
        'output_directory_bytes',directory_bytes(runRoot),'created_utc',utc_now());
    if double(runStatus.output_directory_bytes)>budgetBytes, runStatus.status='FAILED_OUTPUT_BUDGET'; end
    write_json_new(statusPath,runStatus);
    append_ledger(ledgerPath,struct('schema','A1T_SCREEN12_CONTROL_LEDGER_V1','event','RUN_TERMINAL', ...
        'status',runStatus.status,'scene_id',sceneId,'run_status_path',statusPath, ...
        'raw_sha256',runStatus.raw_sha256,'created_utc',utc_now()));
    assert(complete&&strcmp(runStatus.status,'RUN_COMPLETE_PENDING_ROOT_AUDIT'), ...
        'A1T:Incomplete','Flight failed or exceeded output budget; retain evidence and stop.');
    result=runStatus;
catch ME
    if attemptCreated&&~isfile(statusPath)
        failure=struct('schema','A1T_SCREEN12_CONTROL_RUN_STATUS_V1','status','FAILED_NO_RETRY', ...
            'scene_id',sceneId,'sequence_index',sequenceIndex,'error_identifier',ME.identifier, ...
            'error_message',ME.message,'first_plant_step_confirmed',isfile(firstPlantMarker), ...
            'root_release_sha256',expectedReleaseSha256,'engine_invocation_entered',invocationEntered, ...
            'plant_calls',double(isfile(firstPlantMarker)),'training_steps',0,'optimizer_steps',0, ...
            'TEST_accessed',false,'created_utc',utc_now());
        write_json_new(statusPath,failure);
        append_ledger(ledgerPath,struct('schema','A1T_SCREEN12_CONTROL_LEDGER_V1','event','RUN_TERMINAL', ...
            'status','FAILED_NO_RETRY','scene_id',sceneId,'run_status_path',statusPath,'created_utc',utc_now()));
    end
    rethrow(ME);
end
end

function [status,audit,statusPath,auditPath]=same_scene_a1r_pass(repoRoot,reportDir,sceneId)
runDir=fullfile(repoRoot,'experiments','attitude_cm18_datarepair_20261024','a1r_screen12_control_v1','runs',sceneId);
d=dir(fullfile(runDir,'attempt_*','run_status.json')); valid={}; statuses=cell(1,numel(d));
for k=1:numel(d)
    p=fullfile(d(k).folder,d(k).name); s=read_json(p); statuses{k}=s;
    if strcmp(field_or(s,'status',''),'RUN_COMPLETE_PENDING_ROOT_AUDIT')&&strcmp(field_or(s,'scene_id',''),sceneId)
        valid{end+1}=p; %#ok<AGROW>
    end
end
assert(numel(valid)==1,'A1T:A1rStatus','Expected exactly one complete same-scene A1R run status.');
statusPath=valid{1}; status=read_json(statusPath);
auditPath=fullfile(reportDir,['A1R_SCREEN12_LOG_AUDIT_' sceneId '_v1.json']); audit=read_json(auditPath);
assert(strcmp(audit.schema,'A1R_SCREEN12_INDEPENDENT_LOG_AUDIT_V1')&& ...
    strcmp(audit.status,'PASS')&&strcmp(audit.scene_id,sceneId)&& ...
    strcmp(status.status,'RUN_COMPLETE_PENDING_ROOT_AUDIT')&&status.first_plant_step_confirmed&& ...
    strcmpi(audit.raw_sha256,status.raw_sha256)&&isfile(status.raw_path), ...
    'A1T:A1rAudit','Same-scene A1R run/audit identity is not a complete PASS.');
verify_file(status.raw_path,status.raw_sha256);
end
function verify_prior_a1t(repoRoot,reportDir,runRoot,auditHashes,ids,sequenceIndex)
for k=1:sequenceIndex-1
    sid=ids{k}; statusPath=fullfile(runRoot,sid,'attempt_01','run_status.json');
    auditPath=fullfile(reportDir,['A1T_SCREEN12_LOG_AUDIT_' sid '_v1.json']);
    verify_file(auditPath,char(auditHashes(k))); s=read_json(statusPath); a=read_json(auditPath);
    assert(strcmp(s.schema,'A1T_SCREEN12_CONTROL_RUN_STATUS_V1')&& ...
        strcmp(s.status,'RUN_COMPLETE_PENDING_ROOT_AUDIT')&&strcmp(s.scene_id,sid)&& ...
        strcmp(a.status,'PASS')&&strcmp(a.scene_id,sid)&&strcmpi(a.raw_sha256,s.raw_sha256), ...
        'A1T:StopOnFailure','Earlier A1T flight or independent raw audit did not PASS.');
    verify_file(s.raw_path,s.raw_sha256);
end
end
function ledger_gate(ledger,sceneId,ids,sequenceIndex)
assert(numel(ledger)==2*(sequenceIndex-1),'A1T:Ledger','Ledger does not contain exactly the prior completed scenes.');
for k=1:sequenceIndex-1
    startIx=2*k-1; terminalIx=2*k; sid=ids{k};
    assert(strcmp(ledger(startIx).event,'RUN_STARTED')&&strcmp(ledger(startIx).scene_id,sid)&& ...
        strcmp(ledger(terminalIx).event,'RUN_TERMINAL')&&strcmp(ledger(terminalIx).scene_id,sid)&& ...
        strcmp(ledger(terminalIx).status,'RUN_COMPLETE_PENDING_ROOT_AUDIT'), ...
        'A1T:StopOnFailure','A1T ledger contains an out-of-order or incomplete prior flight.');
end
assert(~any(strcmp({ledger.scene_id},sceneId)),'A1T:NoRetry','This scene already has a start record.');
end
function items=read_ledger(path)
items=struct('event',{},'status',{},'scene_id',{}); if ~isfile(path), return; end
lines=splitlines(string(fileread(path))); lines=lines(strlength(strtrim(lines))>0);
for k=1:numel(lines)
    r=jsondecode(char(lines(k)));
    assert(all(isfield(r,{'schema','event','status','scene_id'}))&& ...
        strcmp(r.schema,'A1T_SCREEN12_CONTROL_LEDGER_V1'), ...
        'A1T:Ledger','Ledger is malformed; preserve it and stop.');
    items(end+1)=struct('event',char(r.event),'status',char(r.status),'scene_id',char(r.scene_id)); %#ok<AGROW>
end
end
function append_ledger(path,row)
fid=fopen(path,'a'); assert(fid>=0,'A1T:LedgerWrite','Cannot append %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(row) newline],'char');
end
function model=deployment_model(p)
model=struct('W1',double(p.W1),'b1',double(p.b1(:)),'W2',double(p.W2),'b2',double(p.b2(:)), ...
    'W3',double(p.W3),'b3',double(p.b3(:)),'input_mean',double(p.input_mean(:)), ...
    'input_std',double(p.input_std(:)),'train_axis_rms_rad_s2',double(p.train_axis_rms_rad_s2(:)));
expected={[32 18],32,[32 32],32,[24 32],24,18,18,3};
names={'W1','b1','W2','b2','W3','b3','input_mean','input_std','train_axis_rms_rad_s2'};
for k=1:numel(names)
    x=model.(names{k}); shape=expected{k};
    if isscalar(shape)&&shape~=1, ok=numel(x)==shape; else, ok=isequal(size(x),shape); end
    assert(ok&&all(isfinite(x(:))),'A1T:ModelShape','Invalid deployment model field %s.',names{k});
end
assert(all(model.input_std(:)>=1e-6)&&all(model.train_axis_rms_rad_s2(:)>0), ...
    'A1T:Normalizer','Canonical float64 normalizer/axis RMS is invalid.');
end
function configure_runtime(repoRoot,here,enginePath,forwardPath,predictionPath,active)
addpath(fullfile(repoRoot,'matlab','runtime'),'-end'); addpath(fullfile(repoRoot,'matlab','core'),'-end');
for k=1:numel(active)
    p=char(active(k).path); if endsWith(lower(p),'.m'), addpath(fileparts(p),'-end'); end
end
addpath(fileparts(source_path(active,'position_only_search_options.m')),'-begin');
addpath(fileparts(source_path(active,'position_only_search_head_step.m')),'-begin');
addpath(fileparts(source_path(active,'position_stage1_model_forward_v2.m')),'-begin');
addpath(fileparts(source_path(active,'run_dl1018_closed_loop.m')),'-begin');
addpath(fileparts(predictionPath),'-begin'); addpath(fileparts(forwardPath),'-begin');
addpath(fileparts(enginePath),'-begin'); addpath(here,'-begin');
clear run_cm18_closed_loop_v1 delayed_prediction_step_candidate cm18_a1_forward_v1; rehash;
assert(same_path(which('run_cm18_closed_loop_v1'),enginePath)&& ...
    same_path(which('cm18_a1_forward_v1'),forwardPath)&& ...
    same_path(which('delayed_prediction_step_candidate'),predictionPath), ...
    'A1T:RuntimePath','Pinned engine/forward/prediction helper did not resolve.');
for k=1:numel(active)
    p=char(active(k).path); [~,n,e]=fileparts(p);
    if strcmpi(e,'.m')
        expected=p; if strcmp(n,'delayed_prediction_step_candidate'), expected=predictionPath; end
        assert(same_path(which(n),expected),'A1T:C5Path','C5 helper %s resolved outside its pin.',n);
    end
end
end
function path=source_path(items,name)
ix=[];
for k=1:numel(items)
    [~,n,e]=fileparts(char(items(k).path));
    if strcmpi([n e],name), ix(end+1)=k; end %#ok<AGROW>
end
assert(isscalar(ix),'A1T:SourceName','Expected one pinned C5 source named %s.',name);
path=char(items(ix).path);
end
function verify_inventory(items)
for k=1:numel(items), verify_file(char(items(k).path),char(items(k).sha256)); end
end
function assert_release(r,name,value)
assert(isfield(r,name),'A1T:ReleaseField','Root release is missing %s.',name);
actual=r.(name);
if isnumeric(value), ok=isnumeric(actual)&&isequal(double(actual),double(value));
else, ok=strcmpi(char(actual),char(value)); end
assert(ok,'A1T:ReleasePin','Root release field %s differs from the prepared identity.',name);
end
function verify_file(path,expected)
assert(isfile(path),'A1T:MissingFile','Missing pinned input: %s.',path);
assert(strcmpi(sha256_file(path),expected),'A1T:SHA','SHA-256 mismatch: %s.',path);
end
function value=read_json(path)
assert(isfile(path),'A1T:MissingJSON','Missing JSON input: %s.',path); value=jsondecode(fileread(path));
end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r');
assert(fid>=0,'A1T:ReadFile','Cannot read %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(b); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json_new(path,value)
assert(~isfile(path),'A1T:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'A1T:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char');
end
function write_new(path,text)
assert(~isfile(path),'A1T:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'A1T:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,text,'char');
end
function n=directory_bytes(path)
d=dir(fullfile(path,'**','*')); d=d(~[d.isdir]); n=sum(double([d.bytes]));
end
function write_lock_token(path,token)
fid=fopen(path,'w'); assert(fid>=0,'A1T:Lock','Cannot write lock token.'); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,token,'char');
end
function delete_lock(path,token)
if isfile(path)&&strcmp(fileread(path),token), delete(path); end
end
function tf=same_path(a,b)
tf=strcmpi(char(java.io.File(char(a)).getCanonicalPath()),char(java.io.File(char(b)).getCanonicalPath()));
end
function v=field_or(s,name,default)
if isfield(s,name), v=s.(name); else, v=default; end
end
function t=utc_now()
t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end
