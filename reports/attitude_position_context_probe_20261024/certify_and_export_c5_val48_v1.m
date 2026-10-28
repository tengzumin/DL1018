function result = certify_and_export_c5_val48_v1()
% Read-only certification and offline event-cache export for existing C5 VAL runs.
% Does not call an episode, engine, Plant, trainer, optimizer, or TEST data.
scriptPath = [mfilename('fullpath') '.m'];
scriptDir = fileparts(scriptPath);
repoRoot = fileparts(fileparts(scriptDir));
exportRoot=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','c5_val48_c5_teacher_v1');
cacheDir=fullfile(exportRoot,'cache');
outPath=fullfile(exportRoot,'C5_VAL48_EVENT_CACHE_MANIFEST_v1.json');
assert(~isfolder(exportRoot)&&~isfile(outPath),'ROOT:C5ValAuditOutputExists', ...
    'Refusing to reuse or overwrite output directory %s.',exportRoot);
aggregateBudgetBytes=512*1024^2; manifestReserveBytes=1024^2; minFreeBytes=30*1024^3;
result = struct('schema','C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V1','status','INCOMPLETE', ...
    'scope','Read-only certification and event extraction only; no Plant, episode, training, optimizer, or TEST.', ...
    'candidate_manifest_path','','candidate_manifest_sha256','','audit_source_path',scriptPath, ...
    'audit_source_sha256',sha256_file(scriptPath),'extractor_source_path','','extractor_source_sha256','', ...
    'source_pin_checks',[],'output_directory',exportRoot,'cache_directory',cacheDir, ...
    'aggregate_datarepair_budget_bytes',aggregateBudgetBytes,'manifest_reserve_bytes',manifestReserveBytes, ...
    'minimum_free_disk_bytes',minFreeBytes,'free_disk_bytes_at_start',0, ...
    'datarepair_bytes_before_export',0,'datarepair_bytes_before_manifest',0, ...
    'cache_bytes_total',0,'training_eligible',false, ...
    'summary',struct(),'scenes',[],'global_error','');
try
    result.free_disk_bytes_at_start=double(java.io.File(repoRoot).getUsableSpace());
    assert(isfinite(result.free_disk_bytes_at_start)&&result.free_disk_bytes_at_start>=minFreeBytes, ...
        'ROOT:C5ValFreeDisk','Free disk space is below the required 30 GiB.');
    reportRepairRoot=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024');
    eventRepairRoot=fullfile(repoRoot,'data','events','attitude_cm18_datarepair_20261024');
    result.datarepair_bytes_before_export=repair_datarepair_bytes(reportRepairRoot,exportRoot,eventRepairRoot);
    assert(result.datarepair_bytes_before_export+manifestReserveBytes<=aggregateBudgetBytes, ...
        'ROOT:C5ValAggregateBudget','Existing datarepair outputs plus manifest reserve exceed 512 MiB.');
    manifestPath = fullfile(scriptDir,'C5_MATCHED_VAL_REUSE_CANDIDATES_v1.json');
    manifestShaExpected = '80ef7a37cb0fff237086ccc138772c71494cacd50a916ed2dba4037d4f833494';
    assert(isfile(manifestPath)&&strcmpi(sha256_file(manifestPath),manifestShaExpected), ...
        'ROOT:C5ValManifestSha','Candidate manifest is missing or its reviewed SHA changed.');
    M = jsondecode(fileread(manifestPath));
    assert(strcmp(M.schema,'ROOT_C5_MATCHED_VAL_REUSE_CANDIDATES_V1')&& ...
        numel(M.scenes)==48&&double(M.summary.val_candidates)==48&& ...
        double(M.summary.C5_new_DEV72_runs)==36&&double(M.summary.C5_reused_SCREEN12_runs)==12, ...
        'ROOT:C5ValManifestSchema','Unexpected candidate manifest schema/count.');
    result.candidate_manifest_path=manifestPath;
    result.candidate_manifest_sha256=manifestShaExpected;
    result.source_pin_checks=verify_manifest_pins(M.source_pins);

    extractorPath=fullfile(repoRoot,'experiments','attitude_cm18_datarepair_20261024','extract_cm18_events_v1.m');
    parityPath=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','CM18_EVENT_EXTRACTION_PARITY_v1.json');
    extractorSha='15d8fb369b93e3a251d70c7eb7a590f732da839d35a5bebfb2011f25123e37c1';
    paritySha='a9a691175b9b7dc7d1ee669cf8834d3a79d5b29676976eec262ff366575d5f05';
    [extractorActual,~]=verify_file_pin(extractorPath,extractorSha,[],'CM18 event extractor');
    [parityActual,~]=verify_file_pin(parityPath,paritySha,[],'CM18 extractor parity report');
    parity=jsondecode(fileread(parityPath));
    assert(strcmp(parity.schema,'CM18_EVENT_EXTRACTION_PARITY_V1')&&strcmp(parity.status,'PASS')&& ...
        strcmpi(parity.extractor_sha256,extractorSha),'ROOT:C5ValExtractorParity','Extractor parity pin failed.');
    result.extractor_source_path=extractorPath;
    result.extractor_source_sha256=extractorActual;
    result.source_pin_checks(end+1)=struct('name','CM18_EVENT_EXTRACTOR','path',extractorPath, ...
        'expected_sha256',extractorSha,'actual_sha256',extractorActual,'pass',true);
    result.source_pin_checks(end+1)=struct('name','CM18_EXTRACTOR_PARITY_REPORT','path',parityPath, ...
        'expected_sha256',paritySha,'actual_sha256',parityActual,'pass',true);

    lineagePath=fullfile(scriptDir,'ROOT_T2_REFERENCE_DATA_LINEAGE_AUDIT_v1.json');
    lineageActual=verify_file_pin(lineagePath, ...
        'b193ae3f0e3dc0af57bd5fb976695f083e4c35173d2058439268ba82fa4844b2',[],'T2 lineage report');
    extraPins=struct('name','T2_LINEAGE_REPORT','path',lineagePath, ...
        'expected_sha256','b193ae3f0e3dc0af57bd5fb976695f083e4c35173d2058439268ba82fa4844b2', ...
        'actual_sha256',lineageActual,'pass',true);
    helperPins={ ...
        'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\sources\validation\audit_reference_original.m', ...
        '50cf0f0a618acf4546fef1e8a9c99bb837feec45b1ae6e6ad879c37c6fc6ab5c'; ...
        'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\sources\validation\audit_reference_fixed.m', ...
        'ce7f1b680155ec0bff8a70dc3794c00898e4c3e7befa7d09c50160b7aabdf26e'};
    for i=1:size(helperPins,1)
        actual=verify_file_pin(helperPins{i,1},helperPins{i,2},[],'T2 formula helper');
        extraPins(end+1)=struct('name',sprintf('T2_FORMULA_HELPER_%d',i), ...
            'path',helperPins{i,1},'expected_sha256',helperPins{i,2},'actual_sha256',actual,'pass',true); %#ok<AGROW>
    end
    result.source_pin_checks=[result.source_pin_checks(:);extraPins(:)];

    snapshot=load(M.source_pins.C5_SNAPSHOT.path,'cfg','opts','W0','modelIdentity','sourceIdentity');
    binding=jsondecode(fileread(M.source_pins.C5_SOURCE_BINDING.path));
    required={'cfg','opts','W0','modelIdentity','sourceIdentity'};
    assert(all(isfield(snapshot,required)),'ROOT:C5ValSnapshotSchema','C5 snapshot lacks required variables.');
    snapPaths=text_cells(snapshot.sourceIdentity.active_paths); snapHashes=text_cells(snapshot.sourceIdentity.active_sha256);
    sourceCache=containers.Map('KeyType','char','ValueType','char');
    verify_source_entries(snapPaths,snapHashes,sourceCache,'C5 snapshot source identity');
    bindingFiles=collect_file_refs(binding.source_files);
    verify_source_entries(bindingFiles.paths,bindingFiles.hashes,sourceCache,'C5 source binding files');
    for i=1:numel(parity.physical_helper_sources)
        ref=parity.physical_helper_sources(i);
        helperPath=fullfile(repoRoot,strrep(char(ref.path),'/',filesep));
        [helperActual,~]=verify_file_pin(helperPath,char(ref.sha256),[],'CM18 physical extraction helper');
        result.source_pin_checks(end+1)=struct('name',char(ref.name),'path',helperPath, ...
            'expected_sha256',char(ref.sha256),'actual_sha256',helperActual,'pass',true); %#ok<AGROW>
    end
    parentAudit=jsondecode(fileread(M.source_pins.C5_PARENT_AUDIT.path));
    screenSummary=jsondecode(fileread(M.source_pins.C5_SCREEN12_SUMMARY.path));
    sharedOpts={'formal_rbf_baseline','attitude_rbf_frequency_hz','rbf_phase_start', ...
        'rbf_full_phase_start','rbf_attitude_gamma_scale','rbf_attitude_enabled', ...
        'rbf_attitude_output_enabled','rbf_attitude_update_enabled','v1_adaptive'};
    addpath(fileparts(helperPins{1,1}),'-begin');
    coreDir=fullfile(repoRoot,'matlab','core'); extractorDir=fileparts(extractorPath);
    addpath(coreDir,'-begin'); addpath(extractorDir,'-begin'); rehash;
    helperCleanup=onCleanup(@()cleanup_paths({fileparts(helperPins{1,1}),extractorDir,coreDir})); %#ok<NASGU>
    assert(strcmp(which('audit_reference_original'),helperPins{1,1})&& ...
        strcmp(which('audit_reference_fixed'),helperPins{2,1}), ...
        'ROOT:C5ValHelperResolution','Pinned T2 formula helpers are not active functions.');
    assert(strcmp(which('extract_cm18_events_v1'),extractorPath)&& ...
        same_path(which('arm_mass_properties'),fullfile(coreDir,'arm_mass_properties.m'))&& ...
        same_path(which('distributed_mass_properties'),fullfile(coreDir,'distributed_mass_properties.m'))&& ...
        same_path(which('arm_directions'),fullfile(coreDir,'arm_directions.m')), ...
        'ROOT:C5ValExtractorResolution','Event extractor or physical helper resolution differs from audited sources.');
    assert(double(M.summary.same_A1_B_raw_sha)==32&&double(M.summary.T2_ACC_FIX_V1_sha_different)==16&& ...
        sum(arrayfun(@(x)logical(x.C5_candidate.reused),M.scenes))==12, ...
        'ROOT:C5ValClassification','Manifest source classification counts changed.');

    scenes=repmat(empty_scene_result(),numel(M.scenes),1);
    mkdir(exportRoot); mkdir(cacheDir);
    for k=1:numel(M.scenes)
        scenes(k)=audit_one_scene(M.scenes(k),k,repoRoot,snapshot,sharedOpts, ...
            parentAudit,screenSummary,sourceCache,cacheDir,manifestShaExpected,extractorSha, ...
            char(M.source_pins.C5_SNAPSHOT.sha256),char(M.source_pins.C5_SOURCE_BINDING.sha256),aggregateBudgetBytes);
    end
    result.scenes=scenes;
    pass=arrayfun(@(x)strcmp(x.status,'PASS'),scenes);
    result.cache_bytes_total=cache_bytes(cacheDir);
    result.datarepair_bytes_before_manifest=repair_datarepair_bytes(reportRepairRoot,exportRoot,eventRepairRoot);
    aggregateWithinBudget=result.datarepair_bytes_before_manifest+manifestReserveBytes<=aggregateBudgetBytes;
    cacheFiles=dir(fullfile(cacheDir,'*.mat'));
    cacheFileCount=numel(cacheFiles);
    result.summary=struct('scene_count',numel(scenes),'passed',sum(pass),'failed',sum(~pass), ...
        'same_source_sha_count',sum(strcmp({scenes.source_classification},'SAME_SHA_AS_A1_B_SOURCE')), ...
        'T2_acc_fix_count',sum(strcmp({scenes.source_classification},'T2_ACC_FIX_V1_SHA_DIFFERENT')), ...
        'attitude_event_count_expected_each',1999, ...
        'parent_event_count_semantics','Parent event_count=1968 means valid position-inference events, not attitude events.', ...
        'cache_count',cacheFileCount,'cache_scene_count',sum([scenes.cache_written]), ...
        'cache_bytes_total',result.cache_bytes_total, ...
        'datarepair_aggregate_bytes_before_manifest',result.datarepair_bytes_before_manifest, ...
        'within_512MiB_budget_with_manifest_reserve',aggregateWithinBudget, ...
        'new_DEV72_run_count',sum(~[scenes.reused_screen]),'reused_SCREEN12_count',sum([scenes.reused_screen]), ...
        'runtime_source_caveat','The 12 reused SCREEN12 rows retain their recorded older runtime source identity and parent reuse proof; this does not claim all 48 ran from identical source bytes.', ...
        'complete_48',all(pass)&&sum([scenes.cache_written])==48&&cacheFileCount==48, ...
        'all_pass',all(pass)&&sum([scenes.cache_written])==48&&cacheFileCount==48);
    if result.summary.complete_48&&aggregateWithinBudget
        result.status='PASS';
    else
        result.status='FAIL';
    end
catch ME
    result.status='INCOMPLETE';
    result.global_error=sprintf('%s: %s',ME.identifier,ME.message);
end
write_json_no_overwrite(outPath,result);
end

function out=audit_one_scene(row,rowIndex,repoRoot,snapshot,sharedOpts,parentAudit,screenSummary,sourceCache,cacheDir,manifestSha,extractorSha,snapshotSha,bindingSha,aggregateBudgetBytes)
out=empty_scene_result(); out.scene_id=char(row.scene_id);
out.source_classification=char(row.C5_physical_B_source.classification);
out.reused_screen=logical(row.C5_candidate.reused); failures={}; candidate=row.C5_candidate;
isT2=startsWith(out.scene_id,'DL1018_VAL_T2_');
try
    assert(strcmp(char(row.split),'VAL')&&strcmp(char(row.collector),'B'), ...
        'ROOT:C5ValSplit','Candidate row is not a VAL/B source.');
    a1Raw=fullfile(repoRoot,char(row.A1_B_source.repo_relative_raw_path));
    a1Start=fullfile(repoRoot,char(row.A1_B_source.run_start_path));
    physicalRaw=char(row.C5_physical_B_source.path);
    rawPath=char(candidate.raw_path); startPath=char(candidate.run_start_path); statusPath=char(candidate.run_status_path);
    [out.a1_source_raw_sha256,out.a1_source_raw_bytes]=verify_file_pin(a1Raw, ...
        char(row.A1_B_source.sha256),double(row.A1_B_source.size_bytes),'A1 source raw');
    out.a1_source_run_start_sha256=verify_file_pin(a1Start,char(row.A1_B_source.run_start_sha256),[],'A1 source run_start');
    [out.physical_B_source_sha256,out.physical_B_source_bytes]=verify_file_pin(physicalRaw, ...
        char(row.C5_physical_B_source.sha256),[],'physical B source raw');
    sameA1Source=strcmpi(char(row.A1_B_source.sha256),char(row.C5_physical_B_source.sha256));
    if isT2
        assert(~sameA1Source&&strcmp(out.source_classification,'T2_ACC_FIX_V1_SHA_DIFFERENT'), ...
            'ROOT:C5ValT2SourceClass','T2 source is not the pinned ACC_FIX_V1 different-SHA class.');
    else
        assert(sameA1Source&&strcmp(out.source_classification,'SAME_SHA_AS_A1_B_SOURCE'), ...
            'ROOT:C5ValSameSourceClass','Non-T2 source is not byte-identical to A1 B source.');
    end
    [out.candidate_raw_sha256,out.candidate_raw_bytes]=verify_file_pin(rawPath,char(candidate.raw_sha256),[],'candidate raw');
    out.candidate_run_start_sha256=verify_file_pin(startPath,char(candidate.run_start_sha256),[],'candidate run_start');
    out.candidate_run_status_sha256=verify_file_pin(statusPath,char(candidate.run_status_sha256),[],'candidate run_status');
    assert(logical(candidate.raw_exists),'ROOT:C5ValRawMissing','Manifest says candidate raw is missing.');

    status=jsondecode(fileread(statusPath));
    assert(same_path(char(status.raw_path),rawPath)&&same_path(char(status.run_start_path),startPath)&& ...
        strcmpi(char(status.raw_sha256),out.candidate_raw_sha256)&& ...
        strcmpi(char(status.run_start_sha256),out.candidate_run_start_sha256), ...
        'ROOT:C5ValStatusIdentity','run_status path/hash differs from candidate raw/run_start.');
    assert(any(strcmp(char(status.status),{'RUN_COMPLETE_RAW_PENDING_AUDIT','RUN_COMPLETE_STABLE'}))&& ...
        strcmp(char(status.scene_id),out.scene_id)&&strcmp(char(status.log_status),'STABLE')&& ...
        double(status.transitions)==20000&&double(status.state_samples)==20001&& ...
        isempty(char(status.safety_stop_reason)),'ROOT:C5ValRunStatus','Run is not complete/stable for 20 s.');
    assert(strcmpi(char(status.physical_B_source_sha256),char(row.C5_physical_B_source.sha256))&& ...
        double(status.plant_calls)==1&&double(status.training_steps)==0&& ...
        double(status.optimizer_steps)==0&&~logical(status.TEST_accessed), ...
        'ROOT:C5ValRunCounters','Unexpected source identity or Plant/training/TEST counter.');
    verify_file_pin(char(status.first_plant_step_marker_path),char(status.first_plant_step_marker_sha256),[],'Plant marker');
    if isfield(status,'raw_bytes')&&isnumeric(status.raw_bytes)&&isscalar(status.raw_bytes)&&isfinite(status.raw_bytes)
        assert(double(status.raw_bytes)==out.candidate_raw_bytes,'ROOT:C5ValStatusBytes', ...
            'run_status raw_bytes differs from actual raw file size.');
    end
    out.run_status=char(status.status);

    q=load(startPath,'runStart'); assert(isfield(q,'runStart'),'ROOT:C5ValRunStartSchema','No runStart in MAT.');
    runStart=q.runStart;
    assert(strcmp(char(runStart.scene_id),out.scene_id),'ROOT:C5ValRunStartScene','runStart scene id mismatch.');
    assert(isequaln(runStart.cfg,snapshot.cfg),'ROOT:C5ValCfgMismatch','runStart cfg differs from C5 snapshot.');
    out.cfg_exact=true; optsDiff={};
    for j=1:numel(sharedOpts)
        n=sharedOpts{j};
        if ~isfield(runStart.opts,n)||~isfield(snapshot.opts,n)||~isequaln(runStart.opts.(n),snapshot.opts.(n))
            optsDiff{end+1}=n; %#ok<AGROW>
        end
    end
    out.shared_attitude_opts_differing_fields=optsDiff;
    out.shared_attitude_opts_exact=isempty(optsDiff);
    assert(isempty(optsDiff),'ROOT:C5ValAttitudeOptsMismatch','Shared opts differ: %s.',strjoin(optsDiff,', '));
    [out.position_model_W0_exact,out.position_model_W0_sha256_expected]=verify_model_W0(runStart,snapshot);
    assert(out.position_model_W0_exact,'ROOT:C5ValW0Mismatch','Initial position-model W0 differs from snapshot.');

    out.run_start_schema='UNSPECIFIED';
    if isfield(runStart,'schema'), out.run_start_schema=char(string(runStart.schema)); end
    if isfield(runStart,'source_paths')&&isfield(runStart,'source_sha256')
        srcPaths=text_cells(runStart.source_paths); srcHashes=text_cells(runStart.source_sha256);
        assert(same_paths(srcPaths,text_cells(snapshot.sourceIdentity.active_paths))&& ...
            same_hashes(srcHashes,text_cells(snapshot.sourceIdentity.active_sha256)), ...
            'ROOT:C5ValRunSourceBinding','DEV72 run_start source pins differ from the pinned C5 snapshot.');
        out.runtime_source_identity_type='DEV72_SOURCE_PATHS_SHA256';
        out.runtime_source_active_count=numel(srcPaths);
        out.runtime_source_binding_sha256=bindingSha;
        out.parent_reuse_basis='NOT_REUSED_NEW_DEV72_RUN';
    elseif isfield(runStart,'source_identity')&&isfield(runStart.source_identity,'active_paths')&& ...
            isfield(runStart.source_identity,'active_sha256')
        srcPaths=text_cells(runStart.source_identity.active_paths); srcHashes=text_cells(runStart.source_identity.active_sha256);
        out.runtime_source_identity_type='REUSED_SCREEN_RUN_START_SOURCE_IDENTITY';
        out.runtime_source_active_count=numel(srcPaths);
        assert(isfield(runStart.source_identity,'c5_core_path')&&isfield(runStart.source_identity,'c5_core_sha256'), ...
            'ROOT:C5ValReuseCoreIdentity','Reused run_start does not expose its C5 core identity.');
        out.runtime_source_core_path=char(runStart.source_identity.c5_core_path);
        out.runtime_source_core_sha256=char(runStart.source_identity.c5_core_sha256);
        verify_file_pin(out.runtime_source_core_path,out.runtime_source_core_sha256,[],'reused runtime C5 core');
        out.parent_reuse_basis='SCREEN12_SUMMARY_PINNED_PARENT_AUDIT_PASS_FOR_EXACT_RAW';
    else
        error('ROOT:C5ValRunSourceIdentity','run_start has no recognized active source identity.');
    end
    verify_source_entries(srcPaths,srcHashes,sourceCache,'run_start active source');
    out.active_source_count=numel(srcPaths);

    [out.parent_audit_status,out.parent_audit_raw_sha256,out.parent_audit_raw_path]= ...
        find_parent_audit(row.scene_id,logical(candidate.reused),parentAudit,screenSummary);
    assert(strcmp(out.parent_audit_status,'PASS_C5_RAW_ALL_EVENTS')&& ...
        strcmpi(out.parent_audit_raw_sha256,out.candidate_raw_sha256)&& ...
        same_path(out.parent_audit_raw_path,rawPath)&& ...
        strcmp(char(candidate.parent_event_audit_status),out.parent_audit_status), ...
        'ROOT:C5ValParentAudit','Parent audit does not PASS for this exact raw.');
    out.parent_audit_event_count=double(candidate.parent_audit_event_count);
    assert((logical(candidate.reused)&&strcmp(out.parent_reuse_basis, ...
        'SCREEN12_SUMMARY_PINNED_PARENT_AUDIT_PASS_FOR_EXACT_RAW'))|| ...
        (~logical(candidate.reused)&&strcmp(out.parent_reuse_basis,'NOT_REUSED_NEW_DEV72_RUN')), ...
        'ROOT:C5ValReuseBasis','Reuse status and parent evidence basis disagree.');

    B=load(physicalRaw,'scene'); C=load(rawPath,'scene');
    assert(isfield(B,'scene')&&isfield(C,'scene'),'ROOT:C5ValSceneMissing','Raw lacks embedded scene.');
    sourceScene=B.scene; candidateScene=C.scene;
    out.physical_source_scene_id=char(string(sourceScene.scene_id));
    out.candidate_raw_scene_id=char(string(candidateScene.scene_id));
    [out.physical_scene_id_alias_ok,out.physical_scene_id_alias]=scene_alias(sourceScene.scene_id,out.scene_id);
    [out.candidate_scene_id_alias_ok,out.candidate_scene_id_alias]=scene_alias(candidateScene.scene_id,out.scene_id);
    assert(out.physical_scene_id_alias_ok&&out.candidate_scene_id_alias_ok, ...
        'ROOT:C5ValSceneAlias','Scene id is not canonical or explicit ACC_FIX_V1 alias.');
    sourceCompare=sourceScene; candidateCompare=candidateScene;
    sourceCompare.scene_id=out.scene_id; candidateCompare.scene_id=out.scene_id;
    out.candidate_scene_differing_fields=scene_diff_paths(candidateCompare,sourceCompare,'scene');
    assert(isempty(out.candidate_scene_differing_fields),'ROOT:C5ValEmbeddedSceneMismatch', ...
        'Candidate embedded scene differs from physical B source: %s.',strjoin(out.candidate_scene_differing_fields,', '));

    t=double(h5read(rawPath,'/log/time')); t=t(:);
    event=double(h5read(rawPath,'/log/attitude_event_flag')); event=event(:)~=0;
    stateInfo=h5info(rawPath,'/log/state'); stateDims=sort(double(stateInfo.Dataspace.Size(:)'));
    out.transitions=numel(event); out.state_samples=max(stateDims);
    out.log_time_start_s=t(1); out.log_time_end_s=t(end);
    out.log_dt_max_abs_error_s=max(abs(diff(t)-0.001));
    out.attitude_event_count=sum(event); out.attitude_first_event_transition=find(event,1,'first');
    stateData=h5read(rawPath,'/log/state');
    assert(numel(t)==20001&&abs(t(1))<=1e-12&&abs(t(end)-20)<=1e-9&& ...
        out.log_dt_max_abs_error_s<=1e-9&&numel(event)==20000&& ...
        isequal(stateDims,[12 20001])&&out.attitude_event_count==1999&& ...
        out.attitude_first_event_transition==11&&all(isfinite(stateData(:))), ...
        'ROOT:C5ValRawTiming','Raw is not finite full 20 s/20001 states/20000 transitions/1999 attitude events.');
    out.t2_acc_fix_check='NOT_APPLICABLE_SAME_SOURCE_SHA';
    if isT2, out.t2_acc_fix_check=verify_t2_reference(a1Raw,physicalRaw,out.scene_id); end
    D=load(rawPath,'log','scene');
    assert(isfield(D,'log')&&isfield(D,'scene'),'ROOT:C5ValExtractInput','Raw lacks extraction inputs.');
    assert(isfield(D.log,'rbf_event_count')&&double(D.log.rbf_event_count)==1999&& ...
        isfield(D.log,'rbf_event_audit')&&isfield(D.log.rbf_event_audit,'weight_before'), ...
        'ROOT:C5ValInitialAttitudeAudit','Raw lacks the 1999-event attitude RBF weight audit.');
    weightBefore=double(D.log.rbf_event_audit.weight_before);
    assert(size(weightBefore,3)==1999,'ROOT:C5ValInitialAttitudeShape', ...
        'Attitude RBF weight audit does not have one row per 1,999 events.');
    firstWeight=weightBefore(:,:,1);
    out.initial_attitude_rbf_weight_shape=size(firstWeight);
    out.initial_attitude_rbf_weight_max_abs=max(abs(firstWeight(:)));
    out.initial_attitude_rbf_weight_zero=all(firstWeight(:)==0);
    assert(all(isfinite(firstWeight(:)))&&out.initial_attitude_rbf_weight_zero, ...
        'ROOT:C5ValInitialAttitudeNonzero','Actual initial attitude RBF weights are not all exact zero.');
    events=extract_cm18_events_v1(runStart.cfg,D.scene,D.log);
    [eventAliasOK,eventAlias]=scene_alias(events.scene_id,out.scene_id);
    assert(eventAliasOK&&numel(events.event_index)==1999&& ...
        isequal(size(events.X18),[1999 18])&&isequal(size(events.target_raw),[1999 3])&& ...
        isequal(events.plant_index,(11:10:19991).')&&all(isfinite([events.X18(:);events.target_raw(:)])), ...
        'ROOT:C5ValExtractShape','Pure extractor did not return canonical finite 1999-event arrays.');
    out.extractor_scene_alias=eventAlias;
    out.extracted_event_count=numel(events.event_index);
    out.extractor_closure=events.closure;

    cacheIdentity=struct('schema','CM18_VAL_C5_EVENT_CACHE_IDENTITY_V1','split','VAL', ...
        'training_eligible',false,'scene_id',out.scene_id,'candidate_manifest_sha256',manifestSha, ...
        'candidate_raw_path',rawPath,'candidate_raw_sha256',out.candidate_raw_sha256, ...
        'candidate_run_start_path',startPath,'candidate_run_start_sha256',out.candidate_run_start_sha256, ...
        'candidate_run_status_path',statusPath,'candidate_run_status_sha256',out.candidate_run_status_sha256, ...
        'physical_B_source_path',physicalRaw,'physical_B_source_sha256',out.physical_B_source_sha256, ...
        'source_classification',out.source_classification,'reused_screen',out.reused_screen, ...
        'run_start_schema',out.run_start_schema,'runtime_source_identity_type',out.runtime_source_identity_type, ...
        'runtime_source_core_path',out.runtime_source_core_path,'runtime_source_core_sha256',out.runtime_source_core_sha256, ...
        'runtime_source_active_count',out.runtime_source_active_count,'parent_audit_status',out.parent_audit_status, ...
        'parent_reuse_basis',out.parent_reuse_basis,'parent_audit_event_count_semantics', ...
        'Parent count 1968 is position inference only; attitude events are independently extracted as 1999.', ...
        'C5_snapshot_sha256',snapshotSha,'C5_source_binding_sha256',bindingSha, ...
        'extractor_sha256',extractorSha,'cfg_matches_snapshot',out.cfg_exact, ...
        'shared_attitude_opts_match_snapshot',out.shared_attitude_opts_exact, ...
        'position_model_W0_matches_snapshot',out.position_model_W0_exact, ...
        'initial_attitude_rbf_weight_zero_from_raw_log',out.initial_attitude_rbf_weight_zero, ...
        'initial_attitude_rbf_weight_max_abs',out.initial_attitude_rbf_weight_max_abs);
    cache=struct('schema','CM18_VAL_C5_EVENT_CACHE_V1','identity',cacheIdentity,'events',events);
    cacheInfo=whos('cache'); estimatedBytes=2*double(cacheInfo.bytes)+65536;
    currentBytes=repair_datarepair_bytes(fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024'), ...
        fileparts(cacheDir),fullfile(repoRoot,'data','events','attitude_cm18_datarepair_20261024'));
    out.cache_estimated_upper_bytes=estimatedBytes;
    assert(currentBytes+estimatedBytes+1024^2<=aggregateBudgetBytes,'ROOT:C5ValCacheBudgetEstimate', ...
        'Conservative datarepair output bound plus manifest reserve exceeds 512 MiB.');
    cacheName=sprintf('%02d_%s_v7.mat',rowIndex,regexprep(out.scene_id,'[^A-Za-z0-9_.-]','_'));
    cachePath=fullfile(cacheDir,cacheName);
    assert(~isfile(cachePath),'ROOT:C5ValCacheExists','Refusing to overwrite event cache: %s',cachePath);
    save(cachePath,'cache','-v7');
    cacheInfo=dir(cachePath); out.cache_bytes=double(cacheInfo.bytes);
    out.cache_sha256=sha256_file(cachePath);
    out.cache_path_relative=strrep(cachePath,[repoRoot filesep],'');
    out.cache_written=true;
    actualRepairBytes=repair_datarepair_bytes(fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024'), ...
        fileparts(cacheDir),fullfile(repoRoot,'data','events','attitude_cm18_datarepair_20261024'));
    assert(actualRepairBytes+1024^2<=aggregateBudgetBytes,'ROOT:C5ValCacheBudgetActual', ...
        'Actual datarepair output bytes plus manifest reserve exceed 512 MiB.');
    out.status='PASS';
catch ME
    failures{end+1}=sprintf('%s: %s',ME.identifier,ME.message);
    out.status='FAIL';
end
out.failures=failures;
end

function out=empty_scene_result()
out=struct('scene_id','','status','INCOMPLETE','reused_screen',false,'source_classification','', ...
    'a1_source_raw_sha256','','a1_source_raw_bytes',0,'a1_source_run_start_sha256','', ...
    'physical_B_source_sha256','','physical_B_source_bytes',0,'candidate_raw_sha256','', ...
    'candidate_raw_bytes',0,'candidate_run_start_sha256','','candidate_run_status_sha256','', ...
    'run_status','','cfg_exact',false,'shared_attitude_opts_exact',false, ...
    'shared_attitude_opts_differing_fields',{{}},'position_model_W0_exact',false, ...
    'position_model_W0_sha256_expected','','active_source_count',0,'parent_audit_status','', ...
    'parent_audit_raw_sha256','','parent_audit_raw_path','','parent_audit_event_count',0, ...
    'physical_source_scene_id','','candidate_raw_scene_id','','physical_scene_id_alias_ok',false, ...
    'physical_scene_id_alias','','candidate_scene_id_alias_ok',false,'candidate_scene_id_alias','', ...
    'candidate_scene_differing_fields',{{}},'transitions',0,'state_samples',0, ...
    'log_time_start_s',0,'log_time_end_s',0,'log_dt_max_abs_error_s',0, ...
    'attitude_event_count',0,'attitude_first_event_transition',0,'t2_acc_fix_check','', ...
    'run_start_schema','','runtime_source_identity_type','','runtime_source_active_count',0, ...
    'runtime_source_binding_sha256','','runtime_source_core_path','','runtime_source_core_sha256','', ...
    'parent_reuse_basis','','extractor_scene_alias','','extracted_event_count',0,'extractor_closure',struct(), ...
    'initial_attitude_rbf_weight_shape',[],'initial_attitude_rbf_weight_max_abs',NaN, ...
    'initial_attitude_rbf_weight_zero',false, ...
    'cache_estimated_upper_bytes',0,'cache_path_relative','','cache_sha256','','cache_bytes',0, ...
    'cache_written',false,'failures',{{}});
end

function checks=verify_manifest_pins(pins)
names=fieldnames(pins);
checks=repmat(struct('name','','path','','expected_sha256','','actual_sha256','','pass',false),numel(names),1);
for k=1:numel(names)
    r=pins.(names{k}); [actual,bytes]=verify_file_pin(char(r.path),char(r.sha256),double(r.bytes),names{k});
    assert(bytes==double(r.bytes),'ROOT:C5ValPinBytes','Pinned byte count changed: %s.',names{k});
    checks(k)=struct('name',names{k},'path',char(r.path),'expected_sha256',char(r.sha256), ...
        'actual_sha256',actual,'pass',true);
end
end

function [actual,bytes]=verify_file_pin(path,expectedSha,expectedBytes,label)
assert(isfile(path),'ROOT:C5ValFileMissing','%s is missing: %s',label,path);
d=dir(path); bytes=double(d.bytes); actual=sha256_file(path);
assert(strcmpi(actual,expectedSha),'ROOT:C5ValFileSha','%s SHA mismatch: %s',label,path);
if ~isempty(expectedBytes), assert(bytes==double(expectedBytes),'ROOT:C5ValFileBytes','%s byte count mismatch.',label); end
end

function verify_source_entries(paths,hashes,cache,label)
assert(numel(paths)==numel(hashes)&&~isempty(paths),'ROOT:C5ValSourceShape','%s path/hash counts differ.',label);
for k=1:numel(paths)
    key=lower(strrep(paths{k},'/','\'));
    if isKey(cache,key), actual=cache(key);
    else
        assert(isfile(paths{k}),'ROOT:C5ValSourceMissing','%s missing: %s',label,paths{k});
        actual=sha256_file(paths{k}); cache(key)=actual;
    end
    assert(strcmpi(actual,hashes{k}),'ROOT:C5ValSourceSha','%s SHA mismatch: %s',label,paths{k});
end
end

function refs=collect_file_refs(x)
refs=struct('paths',{{}},'hashes',{{}});
if isstruct(x)
    for q=1:numel(x)
        if isfield(x,'path')&&isfield(x,'sha256')
            refs.paths{end+1}=char(string(x(q).path)); %#ok<AGROW>
            refs.hashes{end+1}=char(string(x(q).sha256)); %#ok<AGROW>
        else
            names=fieldnames(x(q));
            for j=1:numel(names)
                child=collect_file_refs(x(q).(names{j}));
                refs.paths=[refs.paths child.paths]; %#ok<AGROW>
                refs.hashes=[refs.hashes child.hashes]; %#ok<AGROW>
            end
        end
    end
elseif iscell(x)
    for q=1:numel(x)
        child=collect_file_refs(x{q});
        refs.paths=[refs.paths child.paths]; %#ok<AGROW>
        refs.hashes=[refs.hashes child.hashes]; %#ok<AGROW>
    end
end
end

function bytes=cache_bytes(cacheDir)
bytes=0;
if ~isfolder(cacheDir), return; end
d=dir(fullfile(cacheDir,'*.mat'));
if ~isempty(d), bytes=sum(double([d.bytes])); end
end

function bytes=repair_datarepair_bytes(reportRoot,newOutputRoot,eventRoot)
% Bound the scan to flat report receipts, this new output directory, and the datarepair event store.
bytes=direct_file_bytes(reportRoot)+recursive_file_bytes(newOutputRoot)+recursive_file_bytes(eventRoot);
end

function bytes=direct_file_bytes(folder)
bytes=0;
if ~isfolder(folder), return; end
d=dir(folder);
for k=1:numel(d)
    if ~d(k).isdir, bytes=bytes+double(d(k).bytes); end
end
end

function bytes=recursive_file_bytes(folder)
bytes=0;
if ~isfolder(folder), return; end
d=dir(folder);
for k=1:numel(d)
    if strcmp(d(k).name,'.')||strcmp(d(k).name,'..'), continue; end
    child=fullfile(folder,d(k).name);
    if d(k).isdir, bytes=bytes+recursive_file_bytes(child);
    else, bytes=bytes+double(d(k).bytes);
    end
end
end

function [status,rawSha,rawPath]=find_parent_audit(sceneId,reused,parentAudit,screenSummary)
if reused, rows=screenSummary.audits; else, rows=parentAudit.rows; end
ids=arrayfun(@(x)char(x.scene_id),rows,'UniformOutput',false);
idx=find(strcmp(ids,char(sceneId)));
assert(isscalar(idx),'ROOT:C5ValParentScene','Expected one parent audit row for %s.',sceneId);
r=rows(idx); status=char(r.status); rawSha=''; rawPath='';
if isfield(r,'C5_metrics'), rawSha=char(r.C5_metrics.sha256); rawPath=char(r.C5_metrics.path);
elseif isfield(r,'raw_sha256'), rawSha=char(r.raw_sha256); if isfield(r,'raw_path'), rawPath=char(r.raw_path); end
end
assert(~isempty(rawSha)&&~isempty(rawPath),'ROOT:C5ValParentSchema','Parent audit lacks raw identity for %s.',sceneId);
end

function [ok,description]=scene_alias(value,canonical)
id=char(string(value)); canonical=char(canonical);
if strcmp(id,canonical), ok=true; description='EXACT_CANONICAL_ID';
elseif strcmp(id,[canonical '_ACC_FIX_V1']), ok=true; description='EXPLICIT_ACC_FIX_V1_SUFFIX_ALIAS';
else, ok=false; description=['UNEXPECTED_ID:' id];
end
end

function out=verify_t2_reference(a1Path,fixedPath,sceneId)
A=load(a1Path,'scene'); F=load(fixedPath,'scene'); old=A.scene; fixed=F.scene;
[okOld,aliasOld]=scene_alias(old.scene_id,sceneId); [okFixed,aliasFixed]=scene_alias(fixed.scene_id,sceneId);
assert(okOld&&okFixed,'ROOT:C5ValT2Alias','Unexpected T2 scene id alias.');
oldCompare=old; fixedCompare=fixed; oldCompare.scene_id=sceneId; fixedCompare.scene_id=sceneId;
diffs=scene_diff_paths(oldCompare,fixedCompare,'scene');
assert(isequal(diffs,{'scene.reference.acceleration'}),'ROOT:C5ValT2UnexpectedDiff', ...
    'T2 A1 vs ACC_FIX differs outside reference.acceleration: %s.',strjoin(diffs,', '));
assert(isequaln(old.time,fixed.time),'ROOT:C5ValT2TimeDiff','T2 source time grids differ.');
t=double(old.time(:)); ro=audit_reference_original('FIG8_3D',t); rf=audit_reference_fixed('FIG8_3D',t);
accOld=to_3_by_n(old.reference.acceleration,numel(t));
accFixed=to_3_by_n(fixed.reference.acceleration,numel(t));
oldResidual=max(abs(accOld-double(ro.acceleration')),[],'all');
fixedResidual=max(abs(accFixed-double(rf.acceleration')),[],'all');
assert(oldResidual<=2e-12&&fixedResidual<=2e-12,'ROOT:C5ValT2Formula', ...
    'T2 old/fixed scene does not match its pinned reference helper.');
assert(isequaln(accOld(1,:),accFixed(1,:)),'ROOT:C5ValT2XAxis','ACC_FIX changed X acceleration.');
assert(isequaln(old.reference.position,fixed.reference.position)&& ...
    isequaln(old.reference.velocity,fixed.reference.velocity)&&isequaln(old.reference.yaw,fixed.reference.yaw)&& ...
    isequaln(old.reference.yaw_rate,fixed.reference.yaw_rate)&& ...
    isequaln(old.reference.yaw_acceleration,fixed.reference.yaw_acceleration)&& ...
    isequaln(old.environment_wind_I,fixed.environment_wind_I)&&isequaln(old.arms,fixed.arms)&& ...
    isequaln(old.initial_state,fixed.initial_state),'ROOT:C5ValT2OtherInputs', ...
    'T2 non-acceleration physical inputs differ.');
out=sprintf('PASS_ONLY_REFERENCE_ACCELERATION_YZ_CHANGED; old_helper_max_abs=%.17g; fixed_helper_max_abs=%.17g; X_exact=true; old_id=%s; fixed_id=%s', ...
    oldResidual,fixedResidual,aliasOld,aliasFixed);
end

function A=to_3_by_n(x,n)
x=double(x);
if isequal(size(x),[3 n]), A=x; elseif isequal(size(x),[n 3]), A=x';
else, error('ROOT:C5ValAccelerationShape','Acceleration is not 3-by-N or N-by-3.'); end
end

function diffs=scene_diff_paths(a,b,prefix)
diffs={}; if isequaln(a,b), return; end
if isstruct(a)&&isstruct(b)
    if ~isequal(size(a),size(b)), diffs={[prefix '<shape>']}; return; end
    fa=sort(fieldnames(a)); fb=sort(fieldnames(b));
    if ~isequal(fa,fb), diffs={[prefix '<fields>']}; return; end
    for q=1:numel(a)
        for j=1:numel(fa)
            n=fa{j}; diffs=[diffs scene_diff_paths(a(q).(n),b(q).(n),[prefix '.' n])]; %#ok<AGROW>
        end
    end
elseif iscell(a)&&iscell(b)
    if ~isequal(size(a),size(b)), diffs={[prefix '<shape>']}; return; end
    for q=1:numel(a), diffs=[diffs scene_diff_paths(a{q},b{q},sprintf('%s{%d}',prefix,q))]; %#ok<AGROW>
    end
else
    diffs={prefix};
end
end

function [ok,shaExpected]=verify_model_W0(runStart,snapshot)
expected=snapshot.modelIdentity; ok=isfield(runStart,'model_identity'); shaExpected=char(expected.W0_sha256);
if ~ok, return; end
actual=runStart.model_identity; names={'model_id','W0_sha256','normalizer_arrays_sha256','selected_step'};
for k=1:numel(names), n=names{k}; if ~isfield(actual,n)||~isequaln(actual.(n),expected.(n)), ok=false; end, end
if isfield(runStart,'W0'), ok=ok&&isequaln(runStart.W0,snapshot.W0);
elseif isfield(runStart,'opts')&&isfield(runStart.opts,'stage1_position_runtime')&& ...
        isfield(runStart.opts.stage1_position_runtime,'position_only_search_head')&& ...
        isfield(runStart.opts.stage1_position_runtime.position_only_search_head,'W0')
    ok=ok&&isequaln(runStart.opts.stage1_position_runtime.position_only_search_head.W0,snapshot.W0);
else, ok=false;
end
if isfield(runStart,'initial_W0_sha256'), ok=ok&&strcmpi(char(runStart.initial_W0_sha256),shaExpected); end
if isfield(runStart,'W0_sha256'), ok=ok&&strcmpi(char(runStart.W0_sha256),shaExpected); end
end

function c=text_cells(x)
if iscell(x), c=cellfun(@(z)char(string(z)),x(:),'UniformOutput',false);
elseif isstring(x), c=cellstr(x(:)); elseif ischar(x), c={x}; else, c=cellstr(string(x(:))); end
end
function tf=same_paths(a,b)
a=text_cells(a); b=text_cells(b); tf=numel(a)==numel(b); if ~tf, return; end
for k=1:numel(a), if ~strcmpi(strrep(a{k},'/','\'),strrep(b{k},'/','\')), tf=false; return; end, end
end
function tf=same_hashes(a,b)
a=text_cells(a); b=text_cells(b); tf=numel(a)==numel(b); if ~tf, return; end
for k=1:numel(a), if ~strcmpi(a{k},b{k}), tf=false; return; end, end
end
function tf=same_path(a,b)
tf=strcmpi(strrep(char(a),'/','\'),strrep(char(b),'/','\'));
end
function sha=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256');
fid=fopen(path,'rb'); assert(fid>=0,'ROOT:C5ValHashOpen','Cannot open for SHA-256: %s',path);
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,1024*1024,'*uint8'); if isempty(b), break; end, md.update(typecast(b,'int8')); end
digest=typecast(md.digest(),'uint8'); sha=lower(reshape(dec2hex(digest,2).',1,[]));
end
function cleanup_paths(paths)
current=strsplit(path,pathsep);
for k=1:numel(paths)
    if any(strcmpi(current,paths{k})), rmpath(paths{k}); end
end
end
function write_json_no_overwrite(path,value)
assert(~isfile(path),'ROOT:C5ValAuditOutputExists','Refusing to overwrite %s.',path);
folder=fileparts(path); if ~isfolder(folder), mkdir(folder); end
fid=fopen(path,'w','n','UTF-8'); assert(fid>=0,'ROOT:C5ValOutputOpen','Cannot create report.');
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');
end
