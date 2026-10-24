function out = run_dssm_tail16_v1()
% Recovery-only DSSM tail. Frozen numerical code and source files remain unchanged.
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(here));
reportDir=fullfile(root,'reports','paper_continuation_20261023','test_handoff_incident_v1','recovery_v1');
scopePath=fullfile(reportDir,'RECOVERY208_SCOPE_v1.json');
releasePath=fullfile(reportDir,'PARENT_RECOVERY208_RUN_RELEASE_v1.json');
launcherPath=fullfile(here,'RUN_UNSTARTED208_RECOVERY_v1.ps1');
entryPath=[mfilename('fullpath') '.m'];
v9Dir=fullfile(root,'experiments','c5_test48_v9');
v9EntryPath=fullfile(v9Dir,'test48_entry_v4.m');
v9LauncherPath=fullfile(v9Dir,'RUN_TEST48_EXACT_v1.ps1');
contractPath=fullfile(v9Dir,'TEST48_RUN_CONTRACT_v4.json');
manifestPath=fullfile(root,'reports','paper_continuation_20261023','test_entry_v9','TEST_METHOD_SOURCE_MANIFEST_v4.json');
v9ReleasePath=fullfile(root,'reports','paper_continuation_20261023','test_entry_v9','RUN_UNSTARTED_TEST_PARENT_RELEASE_v1.json');
taskbookPath=fullfile(root,'reports','paper_continuation_20261023','test_handoff_incident_v1','UNSTARTED208_RECOVERY_CODE_ONLY_TASKBOOK_v1_ZH.md');
incidentDir=fileparts(taskbookPath);
assert(isfile(releasePath),'RECOVERY208:ParentRelease','The separate recovery release is absent.');
release=jsondecode(fileread(releasePath)); scope=jsondecode(fileread(scopePath));
contract=jsondecode(fileread(contractPath)); manifest=jsondecode(fileread(manifestPath));
verify_recovery_release(release,scope,scopePath,entryPath,launcherPath,v9EntryPath,v9LauncherPath,contractPath,manifestPath,v9ReleasePath,taskbookPath,incidentDir);
assert(strcmp(version('-release'),'2025b'),'RECOVERY208:MATLABRelease','Frozen controller requires MATLAB R2025b.');
assert(double(contract.execution.max_unique_plant_calls)==240&&double(contract.execution.scene_count)==48&&logical(contract.execution.B48_reused), ...
    'RECOVERY208:V9Contract','The frozen v9 scientific contract changed.');
assert(strcmpi(char(manifest.v3_frozen_inputs.index_sha256),'90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68')&& ...
    strcmpi(char(manifest.v3_frozen_inputs.shared_scenes_sha256),'da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c')&& ...
    strcmpi(char(manifest.v3_frozen_inputs.cfg_opts_sha256),'389fdfabd9fbd350d3bdd6df934cfe718eb7208bef2b7b4af02f1192cbb1b9e4'), ...
    'RECOVERY208:InputLock','Frozen TEST input identity changed.');
method=find_method(manifest,'CORRECTED_DSSM14_G12_R32'); verify_method_sources(root,method,manifest);
inputDir=fullfile(root,'experiments','c5_test48_v3','input');
sharedPath=fullfile(inputDir,'TEST_SCENES_SHARED_v1.mat'); cfgPath=fullfile(inputDir,'TEST_METHOD_CFG_OPTS_v1.mat');
indexPath=fullfile(inputDir,'TEST_INPUT_INDEX_v1.json');
freezeDir=fullfile(root,'reports','paper_continuation_20261023','test_entry_v3');
freezeResult=fullfile(freezeDir,'TEST_INPUT_FREEZE_RESULT_v1.json');
freezeExit=fullfile(freezeDir,'TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json');
verify_file(sharedPath,char(manifest.v3_frozen_inputs.shared_scenes_sha256));
verify_file(cfgPath,char(manifest.v3_frozen_inputs.cfg_opts_sha256));
verify_file(indexPath,char(manifest.v3_frozen_inputs.index_sha256));
verify_file(freezeResult,char(manifest.v3_frozen_inputs.freeze_result_sha256));
verify_file(freezeExit,char(manifest.v3_frozen_inputs.freeze_os_sha256));
idx=jsondecode(fileread(indexPath)); freeze=jsondecode(fileread(freezeResult)); freezeOS=jsondecode(fileread(freezeExit));
assert(double(idx.scene_count)==48&&logical(idx.TEST_accessed)&&double(freezeOS.matlab_os_exit_code)==0&& ...
    strcmp(char(freeze.status),'PREPARED_TEST48_INPUTS_NO_PLANT')&&double(freeze.plant_calls)==0, ...
    'RECOVERY208:FrozenInputStatus','The frozen input package is not the pinned natural-OS0 package.');
sceneIds=cellstr(string(idx.scene_ids(:)));
assert(numel(sceneIds)==48&&strcmpi(char(idx.scene_set_sha256),char(manifest.v3_frozen_inputs.scene_set_sha256)), ...
    'RECOVERY208:SceneSet','The frozen 48-scene index changed.');
if iscell(scope.blocks), scopeBlocks=scope.blocks; else, scopeBlocks=num2cell(scope.blocks); end
tailScope=scopeBlocks{1};
assert(isequal(string(tailScope.scene_ids(:)),string(sceneIds(33:48)))&& ...
    isequal(double(tailScope.canonical_batch_indices(:)),(33:48)')&& ...
    isequal(double(tailScope.tail_local_indices(:)),(1:16)'), ...
    'RECOVERY208:TailScope','DSSM tail scope is not exactly canonical indices 33-48.');
assert(strcmp(char(tailScope.old_DSSM_natural_os_exit),'UNKNOWN')&& ...
    logical(tailScope.do_not_rerun_or_modify_old_records), ...
    'RECOVERY208:OldRunState','Original DSSM receipt state must remain UNKNOWN; old records are immutable.');
verify_old_dssm_state(root,sceneIds,incidentDir);
pack=load(sharedPath,'scenePacks','sceneIds','digests','sceneSetSha');
snapshots=load(cfgPath,'methodSnapshots','sceneSetSha');
assert(numel(pack.scenePacks)==48&&numel(pack.sceneIds)==48&&numel(pack.digests)==48&& ...
    numel(snapshots.methodSnapshots)==6&&isequal(pack.sceneSetSha,snapshots.sceneSetSha)&& ...
    isequal(pack.sceneSetSha,idx.scene_set_sha256), ...
    'RECOVERY208:FrozenPackage','Frozen scene/config package schema or scene-set identity changed.');
methodIndex=find(strcmp({manifest.methods.method_id},method.method_id));
assert(numel(methodIndex)==1,'RECOVERY208:MethodIndex','DSSM method is not unique in the frozen manifest.');
snap=snapshots.methodSnapshots{methodIndex}; validate_dssm_snapshot(method,snap);
whichBindings=bind_method_path(root,method);
platformBindings=verify_global_platform_which(root,manifest,method);
candidate='DSSM14_G12_R32'; collector='DSSM14_G12_R32';
recoveryRunRoot=fullfile(here,'runs','DSSM_TAIL16'); assert_short(recoveryRunRoot);
assert(~isfolder(recoveryRunRoot)&&~isfile(fullfile(reportDir,'DSSM_TAIL16_RECOVERY208_PROCESS_OS_EXIT_v1.json')), ...
    'RECOVERY208:NoRetry','DSSM tail output/receipt exists; preserve it and do not retry.');
attemptNames={'attempt_started.marker','first_plant_step.marker','run_start.mat','raw_run.mat','run_status_v1.json','FAILURE_NO_RETRY_v1.json'};
for k=33:48
    attempt=fullfile(recoveryRunRoot,sceneIds{k},'attempt_01'); assert_short(attempt);
    for q=1:numel(attemptNames), assert_short(fullfile(attempt,attemptNames{q})); end
    assert(~isfolder(attempt),'RECOVERY208:NoRetry','DSSM tail attempt already exists: %s.',attempt);
end
if ~isfolder(fileparts(recoveryRunRoot)), mkdir(fileparts(recoveryRunRoot)); end
mkdir(recoveryRunRoot);
batchPath=fullfile(recoveryRunRoot,'METHOD_BATCH_STATUS_v1.json');
bodyPath=fullfile(recoveryRunRoot,'METHOD_BODY_COMPLETE_v1.json');
failurePath=fullfile(recoveryRunRoot,'FAILURE_NO_RETRY_v1.json');
assert(~isfile(batchPath)&&~isfile(bodyPath)&&~isfile(failurePath),'RECOVERY208:NoRetry','DSSM tail batch artifacts already exist.');
releaseSha=sha256_file(releasePath); scopeSha=sha256_file(scopePath);
machine=struct('matlab_version',version,'matlab_release',version('-release'),'computer',computer,'thread_argument','-singleCompThread');
batch=struct('schema','RECOVERY208_DSSM_TAIL16_BATCH_STATUS_V1','status','RUNNING', ...
    'method_id','CORRECTED_DSSM14_G12_R32','alias','DSSM_TAIL16','phase','RECOVERY208_RUN_AFTER_PARENT_RELEASE', ...
    'canonical_batch_start',33,'canonical_batch_end',48,'tail_local_start',1,'tail_local_end',16, ...
    'TEST_accessed',true,'plant_calls',0,'training_steps',0,'optimizer_steps',0, ...
    'recovery_parent_release_sha256',releaseSha,'recovery_scope_sha256',scopeSha, ...
    'source_manifest_sha256',sha256_file(manifestPath),'v9_scientific_entry_sha256',sha256_file(v9EntryPath), ...
    'v9_parent_release_sha256',sha256_file(v9ReleasePath),'machine_info',machine,'thread_argument','-singleCompThread', ...
    'controller_timer_boundary','Frozen run_episode_dl1018 timing boundary unchanged.', ...
    'scene_count',16,'completed_scenes',0,'records',struct([]), ...
    'old_DSSM_committed_scenes_reused',31,'old_DSSM_scene32_numeric_integrity_independently_audited',true, ...
    'original_DSSM_natural_os_exit','UNKNOWN','DSSM_full_48_complete',false,'created_utc',utc_now());
write_json_new(batchPath,batch); records=struct([]); plantStartedUnrecorded=0;
try
    for tailLocal=1:16
        canonicalIndex=32+tailLocal;
        remainingCalls=(17-tailLocal)+192; % this tail remainder plus four untouched 48-scene methods
        assert_budget(root,recoveryRunRoot,reportDir,contract,remainingCalls,5);
        scenePack=pack.scenePacks{canonicalIndex}; id=char(pack.sceneIds(canonicalIndex));
        assert(strcmp(char(scenePack.scene.scene_id),id)&& ...
            strcmpi(sha256_bytes(getByteStreamFromArray(scenePack)),char(idx.scene_digests(canonicalIndex))), ...
            'RECOVERY208:SceneDigest','Frozen scene digest/order mismatch at canonical batch %d.',canonicalIndex);
        valid_scene(scenePack.scene,id);
        attempt=fullfile(recoveryRunRoot,id,'attempt_01'); assert_short(attempt);
        paths=struct('attempt',fullfile(attempt,'attempt_started.marker'), ...
            'plant',fullfile(attempt,'first_plant_step.marker'),'run_start',fullfile(attempt,'run_start.mat'), ...
            'raw',fullfile(attempt,'raw_run.mat'),'status',fullfile(attempt,'run_status_v1.json'), ...
            'failure',fullfile(attempt,'FAILURE_NO_RETRY_v1.json'));
        for f=struct2cell(paths).', assert_short(char(f{1})); end
        assert(~isfolder(attempt)&&~any(cellfun(@isfile,struct2cell(paths))), ...
            'RECOVERY208:NoRetry','An artifact already exists for %s.',id);
        mkdir(attempt);
        started=utc_now(); scene=scenePack.scene; sceneMeta=scenePack.metadata; spec=scenePack.spec;
        cfg=snap.cfg; opts=snap.opts;
        if isfield(opts,'r2e_first_plant_step_marker'), opts=rmfield(opts,'r2e_first_plant_step_marker'); end
        opts.r2e_first_plant_step_marker=paths.plant;
        runIdentity=struct('schema','RECOVERY208_DSSM_TAIL_RUN_IDENTITY_V1', ...
            'method_id','CORRECTED_DSSM14_G12_R32','alias','DSSM_TAIL16','scene_id',id, ...
            'canonical_batch_index',canonicalIndex,'tail_local_index',tailLocal,'scene_digest_sha256',char(idx.scene_digests(canonicalIndex)), ...
            'recovery_entry_path',entryPath,'recovery_entry_sha256',sha256_file(entryPath), ...
            'recovery_launcher_path',launcherPath,'recovery_launcher_sha256',sha256_file(launcherPath), ...
            'recovery_scope_sha256',scopeSha,'recovery_parent_release_sha256',releaseSha, ...
            'v9_scientific_entry_path',v9EntryPath,'v9_scientific_entry_sha256',sha256_file(v9EntryPath), ...
            'v9_method_source_manifest_sha256',sha256_file(manifestPath), ...
            'method_cfg_pack_sha256',sha256_file(cfgPath), ...
            'historical_reference_run_start_path',char(method.cfg_opts_snapshot_path), ...
            'historical_reference_run_start_sha256',char(method.cfg_opts_snapshot_sha256), ...
            'model_identity',snap.modelIdentity,'model_mat_sha256',snap.model_sha256, ...
            'normalizer_sha256',snap.normalizer_sha256,'global_platform_lock_sha256',char(manifest.global_platform_lock_sha256), ...
            'which_bindings',whichBindings,'global_platform_which_bindings',platformBindings, ...
            'candidate',candidate,'collector_tag',collector,'machine_info',machine,'thread_argument','-singleCompThread', ...
            'TEST_accessed',true,'plant_calls',1,'training_steps',0,'optimizer_steps',0, ...
            'parameter_or_seed_search',false,'started_utc',started);
        meta=struct('schema','RECOVERY208_DSSM_TAIL_RUN_START_METADATA_V1','method_id','CORRECTED_DSSM14_G12_R32', ...
            'alias','DSSM_TAIL16','scene_id',id,'candidate',candidate,'collector_tag',collector, ...
            'canonical_batch_index',canonicalIndex,'tail_local_index',tailLocal,'tail_total',16, ...
            'controller_constructor','DSSM14_G12_R32','modelIdentity',snap.modelIdentity, ...
            'scene_digest_sha256',char(idx.scene_digests(canonicalIndex)), ...
            'recovery_entry_path',entryPath,'recovery_entry_sha256',runIdentity.recovery_entry_sha256, ...
            'recovery_launcher_path',launcherPath,'recovery_launcher_sha256',runIdentity.recovery_launcher_sha256, ...
            'recovery_parent_release_sha256',releaseSha,'v9_method_source_manifest_sha256',runIdentity.v9_method_source_manifest_sha256, ...
            'which_bindings',whichBindings,'global_platform_which_bindings',platformBindings,'machine_info',machine, ...
            'thread_argument','-singleCompThread','attempt_started_marker_path',paths.attempt, ...
            'first_plant_step_marker_path',paths.plant,'raw_path',paths.raw,'run_status_path',paths.status, ...
            'plant_calls_before_invocation',0,'TEST_accessed',true,'training_steps',0,'optimizer_steps',0,'created_utc',started);
        save(paths.run_start,'scene','sceneMeta','spec','cfg','opts','meta','-v7.3');
        write_text_new(paths.attempt,sprintf('ABOUT_TO_CALL_EPISODE\nTEST_accessed=true\n%s\n',started));
        status=struct('schema','RECOVERY208_DSSM_TAIL_RUN_STATUS_V1','status','RUNNING_PREPLANT', ...
            'method_id','CORRECTED_DSSM14_G12_R32','scene_id',id,'canonical_batch_index',canonicalIndex, ...
            'tail_local_index',tailLocal,'TEST_accessed',true,'plant_calls',0,'training_steps',0,'optimizer_steps',0, ...
            'raw_path',paths.raw,'run_start_path',paths.run_start,'attempt_started_marker_path',paths.attempt, ...
            'first_plant_step_marker_path',paths.plant,'recovery_parent_release_sha256',releaseSha,'started_utc',started);
        write_json_new(paths.status,status);
        try
            clear run_episode_dl1018 run_dl1018_closed_loop position_filter_realization_pcf_step_v3_5;
            log=run_episode_dl1018(scene,collector,cfg,opts,paths.raw);
            plantStartedUnrecorded=double(isfile(paths.plant));
            assert(isfile(paths.raw)&&isfile(paths.plant),'RECOVERY208:PlantEvidence','Episode lacks raw or first-Plant marker.');
            runIdentity.pre_identity_append_sha256=sha256_file(paths.raw);
            runIdentity.run_start_sha256=sha256_file(paths.run_start);
            runIdentity.first_plant_step_marker_sha256=sha256_file(paths.plant);
            save(paths.raw,'sceneMeta','spec','runIdentity','-append');
            complete=isfield(log,'status')&&strcmpi(char(log.status),'STABLE')&& ...
                isfield(log,'time')&&numel(log.time)==20001&&isfield(log,'transition_time')&& ...
                numel(log.transition_time)==20000&&isfield(log,'last_transition')&&double(log.last_transition)==20000&& ...
                all(isfinite(log.state(:)))&&all(isfinite(log.reference.position(:)));
            assert(complete,'RECOVERY208:IncompleteRun','Frozen raw completeness contract failed for %s.',id);
            rawSha=sha256_file(paths.raw);
            status.status='RECOVERY_TAIL_RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT';
            status.plant_calls=1; status.last_transition=double(log.last_transition);
            status.transition_count=numel(log.transition_time); status.state_sample_count=numel(log.time);
            status.log_status=char(log.status); status.raw_sha256=rawSha;
            status.run_start_sha256=sha256_file(paths.run_start); status.attempt_started_marker_sha256=sha256_file(paths.attempt);
            status.first_plant_step_marker_sha256=sha256_file(paths.plant); status.completed_utc=utc_now();
            write_json_replace(paths.status,status);
        catch ME
            plantStartedUnrecorded=double(isfile(paths.plant));
            fail=struct('schema','RECOVERY208_DSSM_TAIL_SCENE_FAILURE_V1','status','FAILED_NO_RETRY', ...
                'method_id','CORRECTED_DSSM14_G12_R32','scene_id',id,'canonical_batch_index',canonicalIndex, ...
                'tail_local_index',tailLocal,'identifier',ME.identifier,'message',ME.message, ...
                'plant_start_confirmed',isfile(paths.plant),'partial_raw_preserved',isfile(paths.raw), ...
                'partial_raw_sha256',file_sha_if_exists(paths.raw),'TEST_accessed',true,'failed_utc',utc_now());
            write_json_new(paths.failure,fail); status.status='FAILED_NO_RETRY'; status.failure=fail;
            status.plant_calls=double(isfile(paths.plant)); status.updated_utc=utc_now(); write_json_replace(paths.status,status);
            rethrow(ME);
        end
        rec=struct('canonical_batch_index',canonicalIndex,'tail_local_index',tailLocal,'scene_id',id, ...
            'status',status.status,'raw_path',paths.raw,'raw_sha256',status.raw_sha256, ...
            'run_start_path',paths.run_start,'run_start_sha256',status.run_start_sha256, ...
            'run_status_path',paths.status,'run_status_sha256',sha256_file(paths.status), ...
            'attempt_started_marker_path',paths.attempt,'attempt_started_marker_sha256',status.attempt_started_marker_sha256, ...
            'first_plant_step_marker_path',paths.plant,'first_plant_step_marker_sha256',status.first_plant_step_marker_sha256, ...
            'plant_calls',1,'TEST_accessed',true,'created_utc',utc_now());
        if isempty(records), records=rec; else, records(end+1)=rec; end %#ok<AGROW>
        plantStartedUnrecorded=0; batch.records=records; batch.completed_scenes=tailLocal;
        batch.plant_calls=tailLocal; batch.updated_utc=utc_now(); write_json_replace(batchPath,batch);
    end
    batch.status='RECOVERY_TAIL16_COMPLETE_RAW_PENDING_PARENT_AUDIT'; batch.completed_scenes=16;
    batch.plant_calls=16; batch.records=records; batch.completed_utc=utc_now(); write_json_replace(batchPath,batch);
    out=struct('schema','RECOVERY208_DSSM_TAIL16_BODY_V1','status','RECOVERY_TAIL16_COMPLETE_RAW_PENDING_PARENT_AUDIT', ...
        'method_id','CORRECTED_DSSM14_G12_R32','alias','DSSM_TAIL16','scene_count',16,'completed_scenes',16, ...
        'canonical_batch_indices',(33:48),'tail_local_indices',(1:16),'scene_ids',{sceneIds(33:48)}, ...
        'records',records,'recovery_parent_release_sha256',releaseSha,'recovery_scope_sha256',scopeSha, ...
        'source_manifest_sha256',sha256_file(manifestPath),'recovery_entry_sha256',sha256_file(entryPath), ...
        'recovery_launcher_sha256',sha256_file(launcherPath),'TEST_accessed',true,'plant_calls',16, ...
        'training_steps',0,'optimizer_steps',0,'parameter_or_seed_search',false, ...
        'old_DSSM_first31_committed_file_audit_sha256','5e0e2299c397375eafc680b617dba6e99cb8b3d2e434fc54b8541e63339746d5', ...
        'old_DSSM_scene32_identity_no_score_sha256','09fbc3c51cd029cbd79da5adb43ad7a43937efaafdd28fb92608250944d12e15', ...
        'old_DSSM_scenes_1_32_reused_without_rerun',true,'original_DSSM_natural_os_exit','UNKNOWN', ...
        'DSSM_full_48_complete',false,'created_utc',utc_now());
    write_json_new(bodyPath,out);
catch ME
    batch.status='FAILED_STOP_NO_RETRY'; batch.completed_scenes=numel(records);
    batch.plant_calls=numel(records)+plantStartedUnrecorded; batch.records=records;
    batch.failure=struct('identifier',ME.identifier,'message',ME.message,'failed_utc',utc_now());
    write_json_replace(batchPath,batch);
    if ~isfile(failurePath)
        write_json_new(failurePath,struct('schema','RECOVERY208_DSSM_TAIL16_FAILURE_V1', ...
            'status','FAILED_NO_RETRY','identifier',ME.identifier,'message',ME.message, ...
            'plant_calls',batch.plant_calls,'completed_scenes',batch.completed_scenes, ...
            'partial_output_preserved',true,'failed_utc',utc_now()));
    end
    rethrow(ME);
end
end
function verify_recovery_release(r,s,scopePath,entryPath,launcherPath,v9Entry,v9Launcher,contractPath,manifestPath,v9Release,taskbook,incidentDir)
assert(strcmp(char(r.schema),'RECOVERY208_RUN_RELEASE_V1')&&strcmp(char(r.status),'APPROVED_RUN_RECOVERY208')&& ...
    logical(r.MATLAB_authorized)&&logical(r.Plant_authorized)&&logical(r.TEST_run_authorized)&& ...
    ~logical(r.TEST_generation_authorized)&&~logical(r.training_authorized)&&double(r.training_steps)==0&& ...
    double(r.optimizer_steps)==0&&~logical(r.parameter_or_seed_search)&&double(r.max_plant_calls)==208&& ...
    double(r.scene_count)==48&&logical(r.B48_reused)&&logical(r.no_retry)&& ...
    strcmp(char(r.original_DSSM_natural_os_exit),'UNKNOWN')&&logical(r.scene32_reuse_without_rerun), ...
    'RECOVERY208:ReleaseFields','Parent release does not authorize the reviewed recovery scope.');
assert_string_array(r.block_order,{'DSSM_TAIL16','KAN','C5M110','C5FREEZE','C5NOPRED'},'block order');
assert_string_array(r.method_ids,{'CORRECTED_DSSM14_G12_R32','CORRECTED_KAN14_G12_R32','C5_M110','C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION'},'method order');
assert(isequal(double(r.plant_calls_by_block(:)),[16;48;48;48;48]),'RECOVERY208:ReleaseCounts','Per-block calls differ from 208.');
must_match(r,'scope_sha256',sha256_file(scopePath));
must_match(r,'recovery_launcher_sha256',sha256_file(launcherPath));
must_match(r,'dssm_tail_entry_sha256',sha256_file(entryPath));
must_match(r,'v9_entry_sha256',sha256_file(v9Entry));
must_match(r,'v9_launcher_sha256',sha256_file(v9Launcher));
must_match(r,'v9_contract_sha256',sha256_file(contractPath));
must_match(r,'v9_manifest_sha256',sha256_file(manifestPath));
must_match(r,'v9_parent_release_sha256',sha256_file(v9Release));
must_match(r,'taskbook_sha256',sha256_file(taskbook));
must_match(r,'first31_parent_audit_sha256',sha256_file(fullfile(incidentDir,'PARENT_FIRST31_COMMITTED_FILE_AUDIT_v1.json')));
must_match(r,'scene32_parent_identity_sha256',sha256_file(fullfile(incidentDir,'PARENT_SCENE32_IDENTITY_NO_SCORE_v1.json')));
assert(strcmp(char(s.schema),'RECOVERY208_SCOPE_V1')&&strcmp(char(s.status),'FIXED_SCOPE_CODE_ONLY_NO_PLANT')&& ...
    double(s.total_new_plant_calls)==208,'RECOVERY208:Scope','Fixed scope document changed.');
end
function must_match(s,name,value)
assert(isfield(s,name)&&strcmpi(char(s.(name)),value),'RECOVERY208:ReleaseBinding','Recovery release SHA binding differs: %s.',name);
end
function assert_string_array(actual,expected,name)
a=string(actual(:)); b=string(expected(:));
assert(isequal(a,b),'RECOVERY208:ArrayBinding','Recovery release %s differs.',name);
end
function verify_method_sources(root,m,manifest)
for k=1:numel(m.source_refs), verify_file(repo_path(root,char(m.source_refs(k).path)),char(m.source_refs(k).sha256)); end
for k=1:numel(m.model_refs), verify_file(repo_path(root,char(m.model_refs(k).path)),char(m.model_refs(k).sha256)); end
verify_file(repo_path(root,char(m.cfg_opts_snapshot_path)),char(m.cfg_opts_snapshot_sha256));
assert(strcmpi(sha256_tree(char(m.runtime_tree_path)),char(m.runtime_tree_sha256)), ...
    'RECOVERY208:RuntimeTree','Frozen DSSM local runtime tree changed.');
for k=1:numel(manifest.shared_source_refs), verify_file(repo_path(root,char(manifest.shared_source_refs(k).path)),char(manifest.shared_source_refs(k).sha256)); end
for k=1:numel(manifest.global_platform_refs), verify_file(repo_path(root,char(manifest.global_platform_refs(k).path)),char(manifest.global_platform_refs(k).sha256)); end
assert(strcmpi(char(m.global_platform_lock_sha256),char(manifest.global_platform_lock_sha256)), ...
    'RECOVERY208:PlatformLock','DSSM global platform lock changed.');
end
function verify_old_dssm_state(root,sceneIds,incidentDir)
runRoot=fullfile(root,'experiments','c5_test48_v9','runs','DSSM');
batch=jsondecode(fileread(fullfile(runRoot,'METHOD_BATCH_STATUS_v4.json')));
assert(strcmp(char(batch.status),'RUNNING')&&double(batch.completed_scenes)==31&&double(batch.plant_calls)==31&& ...
    numel(batch.records)==31,'RECOVERY208:OldBatch','Original DSSM batch no longer has exactly 31 committed scenes.');
for k=1:31
    assert(double(batch.records(k).batch_index)==k&&strcmp(char(batch.records(k).scene_id),sceneIds{k})&& ...
        strcmp(char(batch.records(k).status),'RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT'), ...
        'RECOVERY208:OldRecord','Original DSSM committed metadata changed at index %d.',k);
end
scene32=sceneIds{32}; attempt=fullfile(runRoot,scene32,'attempt_01');
st=jsondecode(fileread(fullfile(attempt,'run_status_v4.json')));
assert(strcmp(char(st.status),'RUNNING_PREPLANT')&&strcmp(char(st.scene_id),scene32)&& ...
    double(st.batch_index)==32&&isfile(fullfile(attempt,'first_plant_step.marker')), ...
    'RECOVERY208:Scene32State','Original DSSM scene32 status changed; do not rerun/modify it.');
markers=dir(fullfile(runRoot,'**','first_plant_step.marker')); found=cell(numel(markers),1);
for k=1:numel(markers), [~,found{k}]=fileparts(fileparts(markers(k).folder)); end
assert(isequal(sort(string(found)),sort(string(sceneIds(1:32)))), ...
    'RECOVERY208:OldMarkers','Original marker inventory is not exactly the first 32 scenes.');
verify_file(fullfile(incidentDir,'PARENT_FIRST31_COMMITTED_FILE_AUDIT_v1.json'), ...
    '5e0e2299c397375eafc680b617dba6e99cb8b3d2e434fc54b8541e63339746d5');
verify_file(fullfile(incidentDir,'PARENT_SCENE32_IDENTITY_NO_SCORE_v1.json'), ...
    '09fbc3c51cd029cbd79da5adb43ad7a43937efaafdd28fb92608250944d12e15');
oldReceipt=fullfile(root,'reports','paper_continuation_20261023','test_entry_v9','RUN_DSSM_MATLAB_OS_EXIT_v1.json');
assert(~isfile(oldReceipt),'RECOVERY208:OldReceipt','Original DSSM receipt appeared; parent review is required.');
end
function validate_dssm_snapshot(m,snap)
template=load(char(m.cfg_opts_snapshot_path),'cfg','opts');
snapOpts=snap.opts; templateOpts=template.opts;
if isfield(snapOpts,'r2e_first_plant_step_marker'), snapOpts=rmfield(snapOpts,'r2e_first_plant_step_marker'); end
if isfield(templateOpts,'r2e_first_plant_step_marker'), templateOpts=rmfield(templateOpts,'r2e_first_plant_step_marker'); end
assert(isstruct(snap.cfg)&&isstruct(snap.opts)&&isequaln(snap.cfg,template.cfg)&&isequaln(snapOpts,templateOpts), ...
    'RECOVERY208:Snapshot','DSSM cfg/opts differs from its frozen run_start template outside the marker path.');
modelRef=find_model_ref(m,'model_mat'); pack=load(char(modelRef.path),'model'); model=pack.model;
expected=char(m.model_identity.model_id);
assert(isstruct(model)&&strcmp(char(model.model_id),expected)&&strcmp(expected,'DSSM14')&& ...
    double(model.seed)==2026102001&&double(model.selected_step)==60000&&double(model.input_dim)==14&& ...
    double(model.window)==32&&double(model.context_length)==32&&isequal(size(model.output_W),[33 3])&& ...
    numel(fieldnames(model))==double(m.model_identity.model_field_count), ...
    'RECOVERY208:ModelIdentity','DSSM model schema differs from frozen identity.');
w0=sha256_bytes(typecast(double(model.output_W(:)),'uint8'));
assert(strcmpi(w0,char(m.model_identity.W0_sha256))&& ...
    isfield(snap.opts,'stage1_position_runtime')&&isstruct(snap.opts.stage1_position_runtime)&& ...
    isequaln(snap.opts.stage1_position_runtime.model,model)&& ...
    isequal(double(snap.opts.stage1_position_runtime.weight),double(model.output_W))&& ...
    isequal(double(snap.opts.stage1_position_runtime.position_only_search_head.W0),double(model.output_W)), ...
    'RECOVERY208:W0','Frozen DSSM opts/model/W0 identity changed.');
assert(isstruct(snap.modelIdentity)&&strcmp(char(snap.modelIdentity.model_id),'DSSM14')&& ...
    double(snap.modelIdentity.seed)==2026102001&&double(snap.modelIdentity.selected_step)==60000&& ...
    strcmpi(char(snap.modelIdentity.W0_sha256),w0)&& ...
    strcmpi(char(snap.modelIdentity.normalizer_arrays_sha256),hash_normalizer_arrays(model)), ...
    'RECOVERY208:SnapshotModel','Frozen package DSSM identity differs from model.');
end
function method=find_method(manifest,id)
ix=find(strcmp({manifest.methods.method_id},id));
assert(numel(ix)==1,'RECOVERY208:MethodManifest','DSSM method is not unique in manifest.');
method=manifest.methods(ix);
end
function ref=find_model_ref(method,role)
ix=find(strcmp({method.model_refs.role},role));
assert(numel(ix)==1,'RECOVERY208:ModelRef','Locked DSSM model reference is absent/duplicated.');
ref=method.model_refs(ix);
end
function ref=find_function_ref(method,name)
ref=[];
for k=1:numel(method.source_refs)
    [~,n,e]=fileparts(char(method.source_refs(k).path));
    if strcmpi([n e],[name '.m']), ref=method.source_refs(k); return; end
end
assert(~isempty(ref),'RECOVERY208:FunctionRef','Locked DSSM source lacks %s.',name);
end
function bindings=bind_method_path(root,m)
clear run_episode_dl1018 run_dl1018_closed_loop delayed_prediction_step_candidate ...
    position_stage1_model_forward_v2 position_only_search_head_step position_only_search_options ...
    position_stage1_update_head_transfer controller_options_dl1018 init_dl1018 position_filter_realization_pcf_step_v3_5;
refs=m.source_refs;
for k=numel(refs):-1:1
    p=char(refs(k).path); [~,~,ext]=fileparts(p);
    if strcmpi(ext,'.m'), addpath(fileparts(p),'-begin'); end
end
addpath(fullfile(root,'matlab','runtime'),'-end'); addpath(fullfile(root,'matlab','core'),'-end'); rehash;
bindings=struct('function_name',{},'expected_path',{},'resolved_first_path',{},'which_all_paths',{});
seen=containers.Map('KeyType','char','ValueType','char');
for k=1:numel(refs)
    p=char(refs(k).path); [~,name,ext]=fileparts(p); if ~strcmpi(ext,'.m'), continue; end
    if isKey(seen,name)
        assert(same_path(seen(name),p),'RECOVERY208:AmbiguousSource','Different locked paths share basename %s.',name);
        continue
    end
    seen(name)=p; first=which(name);
    assert(~isempty(first)&&same_path(first,p),'RECOVERY208:WhichBinding','%s resolved to another source.',name);
    allPaths=which(name,'-all');
    if ischar(allPaths), allPaths=cellstr(allPaths); elseif isstring(allPaths), allPaths=cellstr(allPaths); end
    if isempty(allPaths), allPaths={first}; end
    bindings(end+1)=struct('function_name',name,'expected_path',p,'resolved_first_path',first,'which_all_paths',{allPaths}); %#ok<AGROW>
end
wrapperRef=find_function_ref(m,'run_episode_dl1018'); coreRef=find_function_ref(m,'run_dl1018_closed_loop');
assert(isKey(seen,'run_episode_dl1018')&&same_path(seen('run_episode_dl1018'),char(wrapperRef.path))&& ...
    isKey(seen,'run_dl1018_closed_loop')&&same_path(seen('run_dl1018_closed_loop'),char(coreRef.path)), ...
    'RECOVERY208:RequiredFunction','Frozen wrapper/core is not bound.');
wrapperHandle=functions(@run_episode_dl1018); coreHandle=functions(@run_dl1018_closed_loop);
assert(same_path(wrapperHandle.file,char(wrapperRef.path))&&same_path(coreHandle.file,char(coreRef.path)), ...
    'RECOVERY208:FunctionHandle','Frozen wrapper/core function handles differ from locked paths.');
end
function bindings=verify_global_platform_which(root,manifest,method)
bindings=struct('function_name',{},'expected_path',{},'resolved_first_path',{},'source_role',{});
refs=manifest.global_platform_refs; rehash;
for k=1:numel(refs)
    ref=refs(k); if ~any(strcmp(char(ref.role),{'frozen_plant','frozen_runtime'})), continue; end
    p=repo_path(root,char(ref.path)); [~,name,ext]=fileparts(p); if ~strcmpi(ext,'.m'), continue; end
    active=which(name);
    assert(~isempty(active)&&same_path(active,p),'RECOVERY208:GlobalPlatformWhich','Global function is shadowed: %s.',name);
    bindings(end+1)=struct('function_name',name,'expected_path',p,'resolved_first_path',active,'source_role',char(ref.role)); %#ok<AGROW>
end
for name={'run_episode_dl1018','run_dl1018_closed_loop'}
    ref=find_function_ref(method,name{1}); active=which(name{1});
    assert(~isempty(active)&&same_path(active,char(ref.path)),'RECOVERY208:MethodCoreWhich','Method source is shadowed: %s.',name{1});
end
end
function valid_scene(scene,id)
assert(isstruct(scene)&&isfield(scene,'scene_id')&& ...
    (strcmp(char(scene.scene_id),id)||strcmp(char(scene.scene_id),[id '_ACC_FIX_V1']))&& ...
    isfield(scene,'time')&&numel(scene.time)==20001&&abs(double(scene.time(1)))<1e-12&& ...
    abs(double(scene.time(end))-20)<1e-12&&isfield(scene,'initial_state')&&numel(scene.initial_state)==12&& ...
    isfield(scene,'environment_wind_I')&&isequal(size(scene.environment_wind_I),[20001 3])&& ...
    isfield(scene,'reference')&&all(isfield(scene.reference,{'position','velocity','acceleration','yaw','yaw_rate','yaw_acceleration'}))&& ...
    isequal(size(scene.reference.position),[20001 3])&&isequal(size(scene.reference.velocity),[20001 3])&& ...
    isequal(size(scene.reference.acceleration),[20001 3])&&isfield(scene,'arms')&& ...
    all(isfield(scene.arms,{'command','rhoDot_hat','rhoDot_true','rho_hat','rho_true'})), ...
    'RECOVERY208:SceneSchema','Scene schema/time dimensions differ for %s.',id);
numeric={scene.time,scene.initial_state,scene.environment_wind_I,scene.reference.position, ...
    scene.reference.velocity,scene.reference.acceleration,scene.reference.yaw,scene.reference.yaw_rate, ...
    scene.reference.yaw_acceleration,scene.arms.command,scene.arms.rhoDot_hat,scene.arms.rhoDot_true,scene.arms.rho_hat,scene.arms.rho_true};
for k=1:numel(numeric), assert(all(isfinite(double(numeric{k}(:)))),'RECOVERY208:SceneFinite','Nonfinite scene field for %s.',id); end
assert(all(ismember(unique(scene.arms.command(:)),[-1 0 1]))&&all(scene.arms.rho_true(:)>=.15-1e-12)&& ...
    all(scene.arms.rho_true(:)<=.25+1e-12),'RECOVERY208:SceneActuation','Scene actuator/morphology identity failed for %s.',id);
end
function assert_budget(root,outputRoot,reportRoot,contract,remainingCalls,remainingProcesses)
limits=contract.limits; deadline=datetime(char(limits.hard_deadline_utc),'InputFormat',"yyyy-MM-dd'T'HH:mm:ss'Z'",'TimeZone','UTC');
reserve=double(remainingCalls)*double(limits.per_scene_output_reserve_bytes);
free=double(java.io.File(outputRoot).getUsableSpace());
assert(free-reserve>=double(limits.minimum_free_bytes_after_reserve),'RECOVERY208:DiskReserve','Reserve-adjusted free-space floor failed.');
dirs={'experiments/c5_test48_v3','reports/paper_continuation_20261023/test_entry_v3', ...
    'experiments/c5_test48_v4','reports/paper_continuation_20261023/test_entry_v4', ...
    'experiments/c5_test48_v5','reports/paper_continuation_20261023/test_entry_v5', ...
    'experiments/c5_test48_v6','reports/paper_continuation_20261023/test_entry_v6', ...
    'experiments/c5_test48_v7','reports/paper_continuation_20261023/test_entry_v7', ...
    'experiments/c5_test48_v8','reports/paper_continuation_20261023/test_entry_v8', ...
    'experiments/c5_test48_v9','reports/paper_continuation_20261023/test_entry_v9', ...
    'experiments/c5_test48_recovery_v1','reports/paper_continuation_20261023/test_handoff_incident_v1/recovery_v1'};
total=double(limits.prior_created_bytes);
for k=1:numel(dirs), total=total+directory_bytes(fullfile(root,dirs{k})); end
assert(total+reserve<=double(limits.max_output_bytes),'RECOVERY208:OutputCap','Cycle-wide output cap plus reserve exceeded.');
required=double(remainingCalls)*double(limits.per_scene_seconds_guard)+double(remainingProcesses)*double(limits.process_exit_buffer_seconds);
assert(seconds(deadline-datetime('now','TimeZone','UTC'))>=required, ...
    'RECOVERY208:Deadline','Deadline guard failed; preserve current state and stop.');
end
function n=directory_bytes(path)
n=0; if ~isfolder(path), return; end
d=dir(fullfile(path,'**','*')); for k=1:numel(d), if ~d(k).isdir, n=n+double(d(k).bytes); end, end
end
function verify_file(path,expected)
assert(isfile(path),'RECOVERY208:MissingFile','Missing frozen file: %s.',path);
assert(strcmpi(sha256_file(path),expected),'RECOVERY208:SHA','SHA mismatch: %s.',path);
end
function p=repo_path(root,path)
p=char(path); winRoot=numel(p)>=3&&p(2)==':'&&(p(3)=='/'||p(3)=='\');
if ~winRoot&&~startsWith(p,filesep)&&~startsWith(p,'\\'), p=fullfile(root,p); end
end
function tf=same_path(a,b)
try, tf=strcmpi(char(java.io.File(char(a)).getCanonicalPath()),char(java.io.File(char(b)).getCanonicalPath())); catch, tf=false; end
end
function h=sha256_tree(path)
files=dir(fullfile(path,'**','*.m')); [~,ord]=sort(string({files.name})); files=files(ord); parts=cell(numel(files),1);
for k=1:numel(files), p=fullfile(files(k).folder,files(k).name); parts{k}=[p ':' sha256_file(p) newline]; end
h=sha256_bytes(uint8(unicode2native([parts{:}],'UTF-8')));
end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0,'RECOVERY208:Read','Cannot read %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(typecast(b(:),'int8')); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=sha256_bytes(bytes)
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(typecast(uint8(bytes(:)),'int8'));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=hash_normalizer_arrays(model)
md=java.security.MessageDigest.getInstance('SHA-256');
for name={'input_mu','input_sigma'}
    field=name{1}; a=reshape(double(model.(field)),1,[]);
    assert(numel(a)==14&&all(isfinite(a)),'RECOVERY208:Normalizer','Invalid normalizer field %s.',field);
    header=[field char(0) '((1, 14), ''float64'')' char(0)];
    md.update(typecast(uint8(unicode2native(header,'UTF-8')),'int8')); md.update(typecast(a(:),'int8'));
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=file_sha_if_exists(path)
h=''; if isfile(path), h=sha256_file(path); end
end
function write_json_new(path,value)
assert(~isfile(path),'RECOVERY208:NoRetry','Artifact already exists: %s.',path); write_json(path,value);
end
function write_json_replace(path,value)
write_json(path,value);
end
function write_json(path,value)
fid=fopen(path,'w','n','UTF-8'); assert(fid>=0,'RECOVERY208:Write','Cannot write %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');
end
function write_text_new(path,value)
assert(~isfile(path),'RECOVERY208:NoRetry','Artifact already exists: %s.',path);
fid=fopen(path,'w','n','UTF-8'); assert(fid>=0,'RECOVERY208:Write','Cannot write %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,value,'char');
end
function assert_short(path)
assert(strlength(string(path))<240,'RECOVERY208:PathLength','Output path exceeds 239 chars: %s.',path);
end
function t=utc_now()
t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end

