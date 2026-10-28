function reportPath = replay_cm18_val_action_v1(rootReleasePath,sceneIds,outputDir)
%REPLAY_CM18_VAL_ACTION_V1 Static same-state replay on pinned C5 VAL48 records.
% No Plant/engine integration, optimizer, TEST, or trajectory advancement.
% Root release contract: schema/decision, approval_scope, source_sha256,
% models.A1R/A1T deployment_path/SHA/schema/release SHA/checkpoint SHA/step.
% Remainder44 release also pins the successful screen-four review.
sourcePath=[mfilename('fullpath') '.m']; experimentDir=fileparts(sourcePath);
repoRoot=fileparts(fileparts(experimentDir)); reportRoot=fullfile(repoRoot,'reports');
assert(nargin==3,'CM18Replay:Arguments','Expected Root release, explicit scene IDs, and a new output directory.');
rootReleasePath=repo_path(repoRoot,rootReleasePath); outputDir=repo_path(repoRoot,outputDir);
assert(isfile(rootReleasePath),'CM18Replay:ReleaseMissing','Root release file is missing.');
assert(ischar(sceneIds)||isstring(sceneIds)||iscell(sceneIds), ...
    'CM18Replay:SceneIds','sceneIds must be an explicit list of canonical IDs.');
sceneIds=cellstr(string(sceneIds(:))).';
assert(~isempty(sceneIds)&&numel(unique(sceneIds))==numel(sceneIds), ...
    'CM18Replay:SceneIds','Scene list must be non-empty and unique.');
release=jsondecode(fileread(rootReleasePath));
assert(strcmp(release.schema,'CM18_C5_VAL_ACTION_REPLAY_RELEASE_V1')&& ...
    strcmp(release.decision,'APPROVE_STATIC_ACTION_REPLAY')&& ...
    strcmpi(char(release.source_sha256),sha256_file(sourcePath)), ...
    'CM18Replay:RootRelease','Root release schema/decision/source SHA is invalid.');
models(1)=load_model_release(release.models.A1R,'A1R',repoRoot);
models(2)=load_model_release(release.models.A1T,'A1T',repoRoot);

valManifestPath=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024', ...
    'c5_val48_c5_teacher_v3','C5_VAL48_EVENT_CACHE_MANIFEST_v3.json');
valManifestSha='3e72f4726219cfd0e89476c70d24796a06c8f8447d4064cfdc471433a863a501';
candidateManifestPath=fullfile(repoRoot,'reports','attitude_position_context_probe_20261024', ...
    'C5_MATCHED_VAL_REUSE_CANDIDATES_v1.json');
candidateManifestSha='80ef7a37cb0fff237086ccc138772c71494cacd50a916ed2dba4037d4f833494';
sceneSelectionPath=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024', ...
    'CM18_C5_VAL_ACTION_REPLAY_SCREEN4_SCENES_v1.json');
sceneSelectionSha='6474acd596c263c4d440a94d91568f18b8f0ff3815830dfbd9ebc833b531b825';
assert_sha(valManifestPath,valManifestSha); assert_sha(candidateManifestPath,candidateManifestSha);
assert_sha(sceneSelectionPath,sceneSelectionSha); assert_sha(sourcePath,lower(char(release.source_sha256)));
M=jsondecode(fileread(valManifestPath)); C=jsondecode(fileread(candidateManifestPath));
Mrows=json_records(M.scenes); Crows=json_records(C.scenes);
selection=jsondecode(fileread(sceneSelectionPath)); screen4Ids=text_cells(selection.scene_ids);
assert(strcmp(M.schema,'C5_MATCHED_VAL48_EVENT_CACHE_MANIFEST_V3')&& ...
    strcmp(M.status,'PASS')&&~logical(M.training_eligible)&& ...
    double(M.summary.scene_count)==48&&double(M.summary.passed)==48&& ...
    double(M.summary.failed)==0&&double(M.summary.cache_count)==48&& ...
    double(M.summary.same_source_sha_count)==32&&double(M.summary.T2_acc_fix_count)==16&& ...
    strcmpi(M.candidate_manifest_sha256,candidateManifestSha)&& ...
    same_path(M.candidate_manifest_path,candidateManifestPath)&& ...
    strcmp(C.schema,'ROOT_C5_MATCHED_VAL_REUSE_CANDIDATES_V1')&& ...
    strcmp(C.status,'CANDIDATE_METADATA_ONLY_FULL_RAW_CFG_CERTIFICATION_PENDING')&& ...
    double(C.summary.val_candidates)==48&&double(C.summary.same_A1_B_raw_sha)==32&& ...
    double(C.summary.T2_ACC_FIX_V1_sha_different)==16&& ...
    strcmp(selection.schema,'CM18_C5_VAL_ACTION_REPLAY_SCREEN4_SCENES_V1')&& ...
    strcmp(selection.status,'SCENE_SELECTION_FROZEN'), ...
    'CM18Replay:VAL48Manifest','Pinned C5 VAL48 manifest or frozen scene selection is invalid.');
assert(numel(Crows)==48&&numel(Mrows)==48, ...
    'CM18Replay:Coverage','Expected the complete candidate/cache manifests.');
verify_manifest_source_pins(M);
valIds={Mrows.scene_id};
assert(numel(unique(valIds))==48&&all(ismember(screen4Ids,valIds)), ...
    'CM18Replay:VALIDs','VAL48 scene IDs are duplicated or fixed screen scenes are absent.');
validate_stage_release(release,sceneIds,screen4Ids,valIds,repoRoot,valManifestSha,models);
assert(~isfolder(outputDir)&&~isfile(outputDir)&&path_is_within(outputDir,reportRoot), ...
    'CM18Replay:OutputPath','Output must be a new directory under reports/.');

snapshotPath=fullfile(repoRoot,'experiments','position_axis_coordinate_c5_dev72_20261023', ...
    'C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
snapshotSha='842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a';
assert_sha(snapshotPath,snapshotSha); snapshot=load(snapshotPath,'cfg','opts','sourceIdentity');
assert(all(isfield(snapshot,{'cfg','opts','sourceIdentity'})), ...
    'CM18Replay:Snapshot','Frozen C5 cfg/opts/source identity is incomplete.');
helperPaths={ ...
    fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','matlab','cm18_a1_forward_v1.m'), ...
    fullfile(repoRoot,'experiments','attitude_cm18_datarepair_20261024','extract_cm18_events_v1.m'), ...
    fullfile(repoRoot,'matlab','core','allocate_control.m'), ...
    fullfile(repoRoot,'matlab','core','simulation_parameters.m'), ...
    fullfile(repoRoot,'matlab','core','controller_parameters.m'), ...
    fullfile(repoRoot,'matlab','core','arm_mass_properties.m')};
helperShas={ ...
    '1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9', ...
    '15d8fb369b93e3a251d70c7eb7a590f732da839d35a5bebfb2011f25123e37c1', ...
    '5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53', ...
    '962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae', ...
    '4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398', ...
    '8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5'};
for h=1:numel(helperPaths), assert_sha(helperPaths{h},helperShas{h}); end
helperDir=fileparts(helperPaths{1}); coreDir=fileparts(helperPaths{3}); extractorDir=fileparts(helperPaths{2});
addpath(helperDir,'-begin'); addpath(extractorDir,'-begin'); addpath(coreDir,'-begin'); rehash;
assert(same_path(which('cm18_a1_forward_v1'),helperPaths{1})&& ...
    same_path(which('extract_cm18_events_v1'),helperPaths{2})&& ...
    same_path(which('allocate_control'),helperPaths{3})&& ...
    same_path(which('simulation_parameters'),helperPaths{4})&& ...
    same_path(which('controller_parameters'),helperPaths{5}), ...
    'CM18Replay:HelperResolution','MATLAB resolved an unexpected helper implementation.');

mkdir(outputDir); currentScene=''; completed=struct([]); metricTables=cell(1,numel(sceneIds));
try
    for s=1:numel(sceneIds)
        currentScene=sceneIds{s}; mIdx=find(strcmp(valIds,currentScene)); cIds={Crows.scene_id}; cIdx=find(strcmp(cIds,currentScene));
        assert(isscalar(mIdx)&&isscalar(cIdx),'CM18Replay:SceneLookup','Scene is not uniquely pinned: %s.',currentScene);
        [sceneResult,eventTable,metricTables{s}]=replay_scene(Mrows(mIdx),Crows(cIdx), ...
            currentScene,models,snapshot,repoRoot,candidateManifestSha);
        eventPath=fullfile(outputDir,['events_' currentScene '.csv']);
        assert(~isfile(eventPath),'CM18Replay:NoOverwrite','Refusing to overwrite %s.',eventPath);
        writetable(eventTable,eventPath); eventInfo=dir(eventPath);
        sceneResult.event_csv=repo_relative(eventPath,repoRoot);
        sceneResult.event_csv_sha256=sha256_file(eventPath); sceneResult.event_csv_bytes=double(eventInfo.bytes);
        completed(end+1)=sceneResult; %#ok<AGROW>
    end
    sceneMetrics=vertcat(metricTables{:}); groups=aggregate_groups(sceneMetrics);
    sceneMetricPath=fullfile(outputDir,'scene_axis_phase_metrics.csv');
    groupMetricPath=fullfile(outputDir,'group_axis_phase_metrics.csv');
    writetable(sceneMetrics,sceneMetricPath); writetable(groups,groupMetricPath);
    sceneMetricInfo=dir(sceneMetricPath); groupMetricInfo=dir(groupMetricPath);
    report=struct('schema','CM18_C5_VAL_STATIC_ACTION_REPLAY_V1','status','PASS', ...
        'source_path',repo_relative(sourcePath,repoRoot),'source_sha256',sha256_file(sourcePath), ...
        'root_release_path',repo_relative(rootReleasePath,repoRoot), ...
        'root_release_sha256',sha256_file(rootReleasePath),'approval_scope',char(release.approval_scope), ...
        'C5_VAL48_manifest_path',repo_relative(valManifestPath,repoRoot), ...
        'C5_VAL48_manifest_sha256',valManifestSha,'candidate_manifest_sha256',candidateManifestSha, ...
        'scene_selection_path',repo_relative(sceneSelectionPath,repoRoot), ...
        'scene_selection_sha256',sceneSelectionSha,'models',model_report(models,repoRoot), ...
        'snapshot_sha256',snapshotSha,'scene_count',numel(completed), ...
        'event_count_total',sum([completed.event_count]),'scene_results',completed, ...
        'scene_metrics_csv',repo_relative(sceneMetricPath,repoRoot), ...
        'scene_metrics_csv_sha256',sha256_file(sceneMetricPath),'scene_metrics_csv_bytes',double(sceneMetricInfo.bytes), ...
        'group_metrics_csv',repo_relative(groupMetricPath,repoRoot), ...
        'group_metrics_csv_sha256',sha256_file(groupMetricPath),'group_metrics_csv_bytes',double(groupMetricInfo.bytes), ...
        'scope',struct('static_same_state_action_replay',true,'closed_loop_trajectories',0, ...
            'Plant_calls',0,'engine_calls',0,'optimizer_steps',0,'TEST_accessed',false, ...
            'C5_or_model_sources_modified',false,'C5_VAL48_only',true,'events_per_scene',1999, ...
            'action_sequence_hold_or_future_state_simulated',false, ...
            'metrics_target','alpha after clip-beta-allocation-true dynamics minus alphaBS; no old-label RMSE'));
    reportPath=fullfile(outputDir,'CM18_C5_VAL_STATIC_ACTION_REPLAY_v1.json'); write_json_new(reportPath,report);
catch ME
    failure=struct('schema','CM18_C5_VAL_STATIC_ACTION_REPLAY_FAILURE_V1','status','FAIL', ...
        'source_path',repo_relative(sourcePath,repoRoot),'source_sha256',sha256_file(sourcePath), ...
        'root_release_sha256',sha256_file(rootReleasePath),'failed_scene_id',currentScene, ...
        'completed_scene_count',numel(completed),'error_identifier',ME.identifier,'error_message',ME.message, ...
        'scope',struct('Plant_calls',0,'engine_calls',0,'optimizer_steps',0,'TEST_accessed',false));
    write_json_new(fullfile(outputDir,'FAILURE.json'),failure); rethrow(ME);
end
end

function model=load_model_release(d,modelName,repoRoot)
required={'deployment_path','deployment_sha256','deployment_schema','artifact_release_sha256', ...
    'checkpoint_sha256','selected_step','normalizer_sha256'};
assert(isstruct(d)&&all(isfield(d,required)),'CM18Replay:ModelRelease','Incomplete %s identity in Root release.',modelName);
deploymentPath=repo_path(repoRoot,d.deployment_path); deploymentSha=lower(char(d.deployment_sha256));
assert_sha(deploymentPath,deploymentSha); spec=jsondecode(fileread(deploymentPath));
if strcmp(modelName,'A1R'), expectedSchema='CM18_A1R_DEPLOYMENT_PARAMETERS_V1';
else, expectedSchema='CM18_A1T_DEPLOYMENT_PARAMETERS_V1'; end
assert(strcmp(char(d.deployment_schema),expectedSchema)&&strcmp(spec.schema,expectedSchema)&& ...
    isfield(spec,'parameters')&&isfield(spec,'identity'), ...
    'CM18Replay:ModelSchema','%s deployment schema differs from the Root release.',modelName);
id=spec.identity;
if strcmp(modelName,'A1R'), releasePin=id.release_sha256; normPin=id.normalizer_float64_sha256;
else
    releasePin=id.training_release_sha256; normPin=id.canonical_normalizer_float64_sha256;
    assert(strcmp(spec.label_semantics,'direct compensation C*: raw network target is C*/beta; runtime clip then beta is unchanged'), ...
        'CM18Replay:A1TSemantics','A1T deployment does not declare the fixed C*/beta action semantics.');
end
assert(strcmpi(char(releasePin),char(d.artifact_release_sha256))&& ...
    strcmpi(char(id.checkpoint_sha256),char(d.checkpoint_sha256))&& ...
    double(id.selected_step)==double(d.selected_step)&& ...
    strcmpi(char(normPin),char(d.normalizer_sha256)), ...
    'CM18Replay:ModelIdentity','%s checkpoint/release/step/normalizer does not match Root pins.',modelName);
if isfield(id,'deployment_parameters_sha256')
    assert(strcmpi(char(id.deployment_parameters_sha256),deploymentSha), ...
        'CM18Replay:SelfHash','%s embedded deployment SHA mismatch.',modelName);
end
p=spec.parameters; shapes={ [32 18],[32 1],[32 32],[32 1],[24 32],[24 1],[1 18],[1 18],[1 3] };
names={'W1','b1','W2','b2','W3','b3','input_mean','input_std','train_axis_rms_rad_s2'};
for k=1:numel(names)
    assert(isfield(p,names{k}),'CM18Replay:ModelParameter','%s missing %s.',modelName,names{k});
    value=double(p.(names{k}));
    if isvector(value)&&numel(value)==prod(shapes{k}), value=reshape(value,shapes{k}); end
    assert(isequal(size(value),shapes{k})&&all(isfinite(value(:))), ...
        'CM18Replay:ModelParameter','%s parameter %s has invalid shape or values.',modelName,names{k});
    p.(names{k})=value;
end
assert(all(p.input_std(:)>=1e-6)&&all(p.train_axis_rms_rad_s2(:)>0), ...
    'CM18Replay:ModelScale','%s normalization scales are invalid.',modelName);
model=struct('name',modelName,'parameters',p,'deployment_path',deploymentPath, ...
    'deployment_sha256',deploymentSha,'deployment_schema',expectedSchema, ...
    'artifact_release_sha256',lower(char(d.artifact_release_sha256)), ...
    'checkpoint_sha256',lower(char(d.checkpoint_sha256)), ...
    'selected_step',double(d.selected_step),'normalizer_sha256',lower(char(d.normalizer_sha256)));
end

function validate_stage_release(release,sceneIds,screen4Ids,valIds,repoRoot,valSha,models)
assert(isfield(release,'approval_scope'),'CM18Replay:Scope','Root release has no approval scope.');
scope=char(release.approval_scope);
if strcmp(scope,'SCREEN4_ONLY')
    expected=screen4Ids;
elseif strcmp(scope,'REMAINING44_AFTER_SCREEN4_REVIEW')
    expected=valIds(~ismember(valIds,screen4Ids));
    assert(numel(expected)==44&&numel(sceneIds)==44, ...
        'CM18Replay:Scope','Remainder stage must contain exactly the other 44 VAL scenes.');
    assert(isfield(release,'prior_screen4_review_path')&&isfield(release,'prior_screen4_review_sha256'), ...
        'CM18Replay:PriorReview','Remainder release must pin its Screen4 review.');
    reviewPath=repo_path(repoRoot,release.prior_screen4_review_path);
    assert_sha(reviewPath,release.prior_screen4_review_sha256); review=jsondecode(fileread(reviewPath));
    assert(isfield(review,'status')&&strcmp(review.status,'PASS')&& ...
        strcmpi(review.C5_VAL48_manifest_sha256,valSha)&& ...
        isequal(text_cells(review.scene_ids),screen4Ids), ...
        'CM18Replay:PriorReview','Screen4 review does not pass for these scenes and C5 VAL48 identity.');
    for k=1:2
        nm=models(k).name; field=[nm '_deployment_sha256'];
        assert(isfield(review,field)&&strcmpi(char(review.(field)),models(k).deployment_sha256), ...
            'CM18Replay:PriorReview','Screen4 review model identity differs for %s.',nm);
    end
else
    error('CM18Replay:Scope','Unsupported approval_scope: %s.',scope);
end
assert(isequal(sceneIds,expected),'CM18Replay:SceneGate', ...
    'Explicit scenes must match the approved stage and canonical VAL manifest order.');
end

function verify_manifest_source_pins(M)
assert(isfield(M,'source_pin_checks')&&~isempty(M.source_pin_checks), ...
    'CM18Replay:SourcePins','C5 VAL manifest lacks its source pins.');
pins=json_records(M.source_pin_checks);
for k=1:numel(pins)
    p=pins(k); assert(isfield(p,'path')&&isfield(p,'expected_sha256')&&isfield(p,'actual_sha256')&& ...
        isfield(p,'pass')&&logical(p.pass)&&strcmpi(char(p.expected_sha256),char(p.actual_sha256)), ...
        'CM18Replay:SourcePinRow','C5 source pin check %d is not PASS.',k);
    assert_sha(char(p.path),char(p.expected_sha256));
end
end

function rows=json_records(value)
if isstruct(value), rows=value;
elseif iscell(value)
    allNames={};
    for k=1:numel(value)
        assert(isstruct(value{k})&&isscalar(value{k}),'CM18Replay:ManifestRows','Malformed manifest row %d.',k);
        allNames=union(allNames,fieldnames(value{k}),'stable');
    end
    template=struct(); for k=1:numel(allNames), template.(allNames{k})=[]; end
    rows=repmat(template,1,numel(value));
    for k=1:numel(value)
        names=fieldnames(value{k}); for j=1:numel(names), rows(k).(names{j})=value{k}.(names{j}); end
    end
elseif isempty(value), rows=struct([]);
else, error('CM18Replay:ManifestRows','Manifest rows must be JSON objects.');
end
end

function values=text_cells(value)
if ischar(value)&&size(value,1)>1, values=cellstr(value).';
elseif ischar(value), values={value};
elseif isstring(value), values=cellstr(value(:)).';
elseif iscell(value)
    values=cell(1,numel(value));
    for k=1:numel(value), values{k}=char(string(value{k})); end
elseif isempty(value), values={};
else, error('CM18Replay:TextList','Expected a text list.'); end
end

function path=repo_path(repoRoot,value)
value=char(string(value)); root=char(java.io.File(repoRoot).getCanonicalPath());
if ~isempty(regexp(value,'^[A-Za-z]:[\\/]','once'))||startsWith(value,'\\')||startsWith(value,'/')
    candidate=value;
else
    assert(~contains(value,'..')&&~startsWith(value,'/'),'CM18Replay:UnsafePath','Unsafe relative path: %s.',value);
    candidate=fullfile(root,strrep(value,'/',filesep));
end
path=char(java.io.File(candidate).getCanonicalPath());
assert(startsWith(lower(path),[lower(root) filesep])||strcmpi(path,root), ...
    'CM18Replay:UnsafePath','Path escapes the repository: %s.',value);
end

function path=pinned_source_path(repoRoot,value)
value=char(string(value));
if ~isempty(regexp(value,'^[A-Za-z]:[\\/]','once'))||startsWith(value,'\\')||startsWith(value,'/')
    path=char(java.io.File(value).getCanonicalPath());
else
    path=repo_path(repoRoot,value);
end
end

function tf=path_is_within(path,parent)
path=char(java.io.File(path).getCanonicalPath()); parent=char(java.io.File(parent).getCanonicalPath());
tf=startsWith(lower(path),[lower(parent) filesep]);
end

function tf=same_path(a,b)
tf=strcmpi(char(java.io.File(char(a)).getCanonicalPath()),char(java.io.File(char(b)).getCanonicalPath()));
end

function value=repo_relative(path,repoRoot)
root=char(java.io.File(repoRoot).getCanonicalPath()); path=char(java.io.File(path).getCanonicalPath());
assert(startsWith(lower(path),[lower(root) filesep]),'CM18Replay:RelativePath','Path is outside repository.');
value=strrep(path,[root filesep],''); value=strrep(value,'\\','/');
end

function assert_sha(path,expected)
assert(isfile(path)&&strcmpi(sha256_file(path),char(expected)), ...
    'CM18Replay:SHA','Missing file or SHA-256 mismatch: %s.',path);
end

function digest=sha256_file(path)
fid=fopen(path,'rb'); assert(fid>=0,'CM18Replay:HashOpen','Cannot open %s.',path);
closer=onCleanup(@()fclose(fid)); md=java.security.MessageDigest.getInstance('SHA-256');
while true
    bytes=fread(fid,1024*1024,'*uint8'); if isempty(bytes), break; end
    md.update(typecast(bytes(:),'int8'));
end
digest=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[])); clear closer
end

function write_json_new(path,value)
assert(~isfile(path),'CM18Replay:NoOverwrite','Refusing to overwrite %s.',path);
bytes=unicode2native(jsonencode(value),'UTF-8'); fid=fopen(path,'wb');
assert(fid>=0,'CM18Replay:OutputOpen','Cannot create %s.',path); closer=onCleanup(@()fclose(fid));
assert(fwrite(fid,bytes,'uint8')==numel(bytes),'CM18Replay:OutputWrite','Incomplete JSON write.'); clear closer
end

function [result,eventTable,metrics]=replay_scene(M,C,sid,models,snapshot,repoRoot,candidateManifestSha)
assert(strcmp(M.scene_id,sid)&&strcmp(C.scene_id,sid)&&strcmp(C.split,'VAL')&& ...
    strcmp(M.status,'PASS')&&logical(M.cache_available)&& ...
    logical(C.C5_candidate.raw_exists)&&strcmp(M.candidate_scene_id_alias,'EXACT_CANONICAL_ID')&& ...
    isempty(M.candidate_scene_differing_fields), ...
    'CM18Replay:SceneManifest','Pinned C5 scene/cache identity failed for %s.',sid);
rawInfo=C.C5_candidate; sourceInfo=C.C5_physical_B_source;
rawPath=repo_path(repoRoot,rawInfo.raw_path); startPath=repo_path(repoRoot,rawInfo.run_start_path);
statusPath=repo_path(repoRoot,rawInfo.run_status_path); physicalPath=pinned_source_path(repoRoot,sourceInfo.path);
cachePath=repo_path(repoRoot,M.cache_path_relative);
assert(strcmpi(rawInfo.raw_sha256,M.candidate_raw_sha256)&& ...
    strcmpi(rawInfo.run_start_sha256,M.candidate_run_start_sha256)&& ...
    strcmpi(rawInfo.run_status_sha256,M.candidate_run_status_sha256)&& ...
    strcmpi(sourceInfo.sha256,M.physical_B_source_sha256), ...
    'CM18Replay:ScenePins','Candidate and certified manifest raw/start/status/source pins differ for %s.',sid);
assert_sha(rawPath,M.candidate_raw_sha256); assert_sha(startPath,M.candidate_run_start_sha256);
assert_sha(statusPath,M.candidate_run_status_sha256); assert_sha(physicalPath,M.physical_B_source_sha256);
assert_sha(cachePath,M.cache_sha256); fi=dir(cachePath);
assert(double(fi.bytes)==double(M.cache_bytes), ...
    'CM18Replay:CacheBytes','C5 cache size differs for %s.',sid);
status=jsondecode(fileread(statusPath)); startLoad=load(startPath);
runStart=extract_run_start(startLoad); raw=load(rawPath,'log','scene');
assert(isfield(raw,'log')&&isfield(raw,'scene')&&isfield(runStart,'cfg')&&isfield(runStart,'opts')&& ...
    strcmp(char(runStart.scene_id),sid)&&strcmp(char(raw.scene.scene_id),sid), ...
    'CM18Replay:RawSchema','Raw/run_start schemas or scene identity differ for %s.',sid);
assert(same_path(status.raw_path,rawPath)&&same_path(status.run_start_path,startPath)&& ...
    strcmpi(status.raw_sha256,M.candidate_raw_sha256)&& ...
    strcmpi(status.run_start_sha256,M.candidate_run_start_sha256)&& ...
    strcmp(char(status.scene_id),sid)&&any(strcmp(char(status.status), ...
    {'RUN_COMPLETE_RAW_PENDING_AUDIT','RUN_COMPLETE_STABLE'}))&& ...
    strcmp(char(status.log_status),'STABLE')&&double(status.transitions)==20000&& ...
    double(status.state_samples)==20001&&double(status.plant_calls)==1&& ...
    double(status.training_steps)==0&&double(status.optimizer_steps)==0&&~logical(status.TEST_accessed)&& ...
    isempty(char(status.safety_stop_reason)), ...
    'CM18Replay:RunStatus','C5 source run is not a stable, complete, non-TEST episode for %s.',sid);
if isfield(status,'physical_B_source_sha256')
    assert(strcmpi(char(status.physical_B_source_sha256),char(sourceInfo.sha256)), ...
        'CM18Replay:PhysicalSource','C5 run status physical-source SHA mismatch for %s.',sid);
else
    assert(strcmp(sid,'DL1018_VAL_T2_C00_W10')&&logical(M.reused_screen)&& ...
        isfield(runStart,'schema')&&strcmp(char(runStart.schema),'C5_AXIS_COORDINATE_RUN_START_V1')&& ...
        isfield(runStart,'scene_raw_sha256')&&strcmpi(char(runStart.scene_raw_sha256),char(sourceInfo.sha256)), ...
        'CM18Replay:LegacyPhysicalSource','Missing physical-source hash is only allowed for exact legacy T2_C00_W10 lineage.');
end
assert(isequaln(runStart.cfg,snapshot.cfg),'CM18Replay:Config','C5 run cfg differs from frozen snapshot for %s.',sid);
sharedOpts={'formal_rbf_baseline','attitude_rbf_frequency_hz','rbf_phase_start','rbf_full_phase_start', ...
    'rbf_attitude_gamma_scale','rbf_attitude_enabled','rbf_attitude_output_enabled', ...
    'rbf_attitude_update_enabled','v1_adaptive'};
for k=1:numel(sharedOpts)
    name=sharedOpts{k};
    assert(isfield(runStart.opts,name)&&isfield(snapshot.opts,name)&& ...
        isequaln(runStart.opts.(name),snapshot.opts.(name)), ...
        'CM18Replay:AttitudeOpts','C5 shared attitude option %s differs from snapshot for %s.',name,sid);
end
assert(strcmpi(char(M.runtime_source_identity_type),char(string(runStart_source_type(runStart)))), ...
    'CM18Replay:RuntimeSourceType','C5 runtime source branch differs from manifest for %s.',sid);
verify_runtime_source(runStart,M,snapshot,repoRoot);
physical=load(physicalPath,'scene');
assert(isfield(physical,'scene')&&same_scene_after_id_alias(raw.scene,physical.scene,sid, ...
    char(M.physical_scene_id_alias)),'CM18Replay:PhysicalScene','Embedded physical scene differs for %s.',sid);

cacheLoad=load(cachePath,'cache'); cache=cacheLoad.cache;
assert(strcmp(cache.schema,'CM18_VAL_C5_EVENT_CACHE_V2')&& ...
    strcmp(cache.identity.schema,'CM18_VAL_C5_EVENT_CACHE_IDENTITY_V2')&& ...
    strcmp(cache.identity.scene_id,sid)&&strcmp(cache.identity.split,'VAL')&& ...
    ~logical(cache.identity.training_eligible)&& ...
    strcmpi(cache.identity.candidate_manifest_sha256,candidateManifestSha)&& ...
    strcmpi(cache.identity.candidate_raw_sha256,M.candidate_raw_sha256)&& ...
    strcmpi(cache.identity.candidate_run_start_sha256,M.candidate_run_start_sha256)&& ...
    strcmpi(cache.identity.candidate_run_status_sha256,M.candidate_run_status_sha256)&& ...
    strcmpi(cache.identity.physical_B_source_sha256,M.physical_B_source_sha256), ...
    'CM18Replay:CacheIdentity','Embedded C5 cache identity differs for %s.',sid);
events=extract_cm18_events_v1(runStart.cfg,raw.scene,raw.log); ce=cache.events;
assert(strcmp(ce.schema,'CM18_RECONSTRUCTED_EVENTS_V1')&&strcmp(ce.scene_id,sid)&& ...
    isequal(size(ce.X18),[1999 18])&&isequal(size(ce.target_raw),[1999 3])&& ...
    isequal(ce.plant_index,(11:10:19991).')&& ...
    max(abs(double(ce.X18(:))-double(events.X18(:))))<=1e-12&& ...
    max(abs(double(ce.target_raw(:))-double(events.target_raw(:))))<=1e-12&& ...
    isequal(double(ce.plant_index(:)),double(events.plant_index(:)))&& ...
    max(abs(double(ce.event_time_s(:))-double(events.event_time_s(:))))<=1e-12&& ...
    isequal(double(ce.phase_code(:)),double(events.phase_code(:))), ...
    'CM18Replay:CacheEventParity','Extracted events do not exactly match the pinned cache for %s.',sid);

cfg=runStart.cfg; log=raw.log; scene=raw.scene; idx=double(events.plant_index(:)); N=numel(idx);
assert(N==1999&&double(cfg.plant.dt)==0.001&& ...
    strcmpi(char(cfg.controller_morphology_mode),'fixed')&& ...
    strcmpi(char(cfg.controller_inertia_derivative_mode),'full')&& ...
    max(abs(double(cfg.rbf.attitude.dmax(:))-[45;45;4.7124]))<=1e-12&& ...
    abs(double(cfg.rbf.attitude.beta_rise_time)-2.2)<=1e-12, ...
    'CM18Replay:RuntimeContract','C5 fixed-controller/clip/beta contract differs for %s.',sid);
if isfield(runStart.opts,'rbf_attitude_output_delay_events')
    assert(double(runStart.opts.rbf_attitude_output_delay_events)==0, ...
        'CM18Replay:RBFLag','C5 original RBF output delay is nonzero for %s.',sid);
end
P0=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
Pc=controller_parameters(cfg,P0,'fixed'); J0=double(P0.inertia); Jdot0=double(P0.inertia_dot);
assert(isequal(size(J0),[3 3])&&isequal(size(Jdot0),[3 3])&& ...
    isequal(size(Pc.allocation.C),[4 4])&&max(abs(double(Pc.inertia)-J0),[],'all')<=1e-14, ...
    'CM18Replay:NominalModel','Fixed nominal J0/C0 identity invalid for %s.',sid);

time=double(log.time(:)); transitionTime=double(log.transition_time(:)); state=double(log.state);
eventFlag=logical(log.attitude_event_flag(:)); tauNom=double(log.attitude_bs_nominal_torque_Nm);
tauOld=double(log.attitude_compensation_applied_torque_Nm); requestOld=double(log.requested_generalized);
realizedOld=double(log.realized_generalized); wind=double(log.wind_torque_B);
rho=double(scene.arms.rho_true); rhoDot=double(scene.arms.rhoDot_true);
assert(numel(time)==20001&&numel(transitionTime)==20000&&isequal(size(state),[20001 12])&& ...
    isequal(size(tauNom),[20000 3])&&isequal(size(tauOld),[20000 3])&& ...
    isequal(size(requestOld),[20000 4])&&isequal(size(realizedOld),[20000 4])&& ...
    isequal(size(wind),[20000 3])&&isequal(size(rho),[20001 4])&&isequal(size(rhoDot),[20001 4])&& ...
    isequal(find(eventFlag),idx)&&max(abs(time-(0:0.001:20).'))<=1e-10&& ...
    max(abs(transitionTime-time(1:20000)))<=1e-12, ...
    'CM18Replay:RawTiming','Raw schedule, state arrays, or transition index differs for %s.',sid);
motorTc=double(log.motor_time_constant_s);
assert(isscalar(motorTc)&&isfinite(motorTc)&&abs(motorTc)<=1e-12, ...
    'CM18Replay:MotorLag','Static replay requires the certified zero motor time constant for %s.',sid);
assert(isfield(log,'rbf_event_count')&&double(log.rbf_event_count)==1999&& ...
    isfield(log,'rbf_event_audit')&&isfield(log.rbf_event_audit,'weight_before')&& ...
    isfield(log.rbf_event_audit,'time'), ...
    'CM18Replay:RBFInitialAudit','Raw lacks the full RBF audit for %s.',sid);
weightBefore=double(log.rbf_event_audit.weight_before); auditTime=double(log.rbf_event_audit.time(:));
assert(size(weightBefore,1)==81&&size(weightBefore,2)==3&&size(weightBefore,3)>=1&& ...
    abs(auditTime(1)-transitionTime(idx(1)))<=1e-12&&all(weightBefore(:,:,1)==0,'all')&& ...
    logical(M.initial_attitude_rbf_weight_zero), ...
    'CM18Replay:RBFInitialWeight','First actual RBF weights were not exact zero for %s.',sid);

rbfRaw=double(log.rbf_output_raw); rbfUnclipped=double(log.rbf_output_unclipped);
rbfBeta=double(log.attitude_event_beta(:)); rbfApplied=double(log.attitude_rbf_estimate_acceleration_rads2);
rbfTorque=double(log.attitude_compensation_applied_torque_Nm);
assert(isequal(size(rbfRaw),[20000 3])&&isequal(size(rbfUnclipped),[20000 3])&& ...
    isequal(size(rbfApplied),[20000 3]),'CM18Replay:RBFShape','RBF action logs malformed for %s.',sid);
dmax=double(cfg.rbf.attitude.dmax(:)).'; beta=zeros(N,1); alphaBS=zeros(N,3);
rawByStrategy=zeros(N,3,3); appliedByStrategy=zeros(N,3,3); compensation=zeros(N,3,3);
requestByStrategy=zeros(N,4,3); realizedByStrategy=zeros(N,4,3); alphaByStrategy=zeros(N,3,3);
errorByStrategy=zeros(N,3,3); outputClip=false(N,3,3); allocClip=false(N,4,3); motorSat=false(N,4,3);
rawByStrategy(:,:,1)=rbfUnclipped(idx,:); appliedByStrategy(:,:,1)=rbfApplied(idx,:);
compensation(:,:,1)=tauOld(idx,:);
maxRbfClip=0; maxRbfBeta=0; maxRbfApplied=0; maxRbfTorque=0; maxCurrentRequest=0; maxCurrentRealized=0;
for q=1:N
    k=idx(q); beta(q)=min(k*double(cfg.plant.dt)/double(cfg.rbf.attitude.beta_rise_time),1);
    w=state(k,10:12).'; tn=tauNom(k,:).'; tau=realizedOld(k,:).'; windNow=wind(k,:).';
    alphaBS(q,:)=(J0\(tn-cross(w,J0*w)-Jdot0*w)).';
    maxRbfClip=max(maxRbfClip,max(abs(min(max(rbfUnclipped(k,:),-dmax),dmax)-rbfRaw(k,:))));
    maxRbfBeta=max(maxRbfBeta,abs(rbfBeta(k)-beta(q)));
    maxRbfApplied=max(maxRbfApplied,max(abs(rbfApplied(k,:)-beta(q)*rbfRaw(k,:))));
    maxRbfTorque=max(maxRbfTorque,max(abs(tauOld(k,:).'-J0*rbfApplied(k,:).')));
    reconstructed=[requestOld(k,1);tn-tauOld(k,:).'];
    maxCurrentRequest=max(maxCurrentRequest,max(abs(reconstructed-requestOld(k,:).')));
    Ptrue=simulation_parameters(cfg,rho(k,:).',rhoDot(k,:).');
    [~,currentRealized,currentInfo]=allocate_control(reconstructed,Pc,Ptrue,[]);
    maxCurrentRealized=max(maxCurrentRealized,max(abs(currentRealized-realizedOld(k,:).')));
    assert(isequal(logical(currentInfo.generalized_command_clipped(:)).',logical(log.generalized_clipped(k,:)))&& ...
        isequal(logical(currentInfo.motor_saturated(:)).',logical(log.motor_saturated(k,:))), ...
        'CM18Replay:CurrentAllocatorFlags','RBF/current allocator flags differ from raw for %s event %d.',sid,k);
    rawByStrategy(q,:,2)=cm18_a1_forward_v1(events.X18(q,:),models(1).parameters);
    rawByStrategy(q,:,3)=cm18_a1_forward_v1(events.X18(q,:),models(2).parameters);
    for m=1:3
        clipped=min(max(rawByStrategy(q,:,m),-dmax),dmax);
        outputClip(q,:,m)=abs(clipped-rawByStrategy(q,:,m))>1e-12;
        if m==1, applied=rbfApplied(k,:); comp=tauOld(k,:).';
        else
            applied=beta(q)*clipped; comp=J0*applied(:);
        end
        appliedByStrategy(q,:,m)=applied; compensation(q,:,m)=comp(:).';
        cmd=[requestOld(k,1);tn-comp(:)]; requestByStrategy(q,:,m)=cmd.';
        [~,realizedNow,info]=allocate_control(cmd,Pc,Ptrue,[]);
        realizedByStrategy(q,:,m)=realizedNow(:).';
        allocClip(q,:,m)=logical(info.generalized_command_clipped(:)).';
        motorSat(q,:,m)=logical(info.motor_saturated(:)).';
        alpha=double(Ptrue.inertia)\(realizedNow(2:4)+windNow- ...
            cross(w,double(Ptrue.inertia)*w)-double(Ptrue.inertia_dot)*w);
        alphaByStrategy(q,:,m)=alpha(:).'; errorByStrategy(q,:,m)=alpha(:).'-alphaBS(q,:);
    end
    assert(max(abs(requestByStrategy(q,:,1)-requestOld(k,:)))<=1e-8&& ...
        max(abs(realizedByStrategy(q,:,1)-realizedOld(k,:)))<=1e-8, ...
        'CM18Replay:RBFActionClosure','Recreated same-state RBF action differs from raw for %s event %d.',sid,k);
end
assert(maxRbfClip<=1e-10&&maxRbfBeta<=1e-12&&maxRbfApplied<=1e-10&&maxRbfTorque<=1e-8&& ...
    maxCurrentRequest<=1e-8&&maxCurrentRealized<=1e-8, ...
    'CM18Replay:RBFClosure','RBF clip/beta/torque/current-action closure failed for %s.',sid);
eventTable=make_event_table(sid,events,beta,rawByStrategy,appliedByStrategy,compensation, ...
    requestByStrategy,realizedByStrategy,alphaBS,alphaByStrategy,errorByStrategy,outputClip,allocClip,motorSat);
metrics=make_scene_metrics(eventTable,sid);
tags=scene_tags(sid); clipCounts=squeeze(sum(outputClip,1)); allocatorCounts=squeeze(sum(allocClip,1)); satCounts=squeeze(sum(motorSat,1));
strategySummary=repmat(struct('strategy','','axis_rmse_rad_s2',[],'axis_signed_mean_rad_s2',[], ...
    'vector_rmse_rad_s2',0, ...
    'output_clip_count_by_axis',[],'generalized_clip_count_by_channel',[],'motor_saturation_count_by_motor',[]),1,3);
names={'RBF','A1R','A1T'};
for m=1:3
    strategySummary(m).strategy=names{m};
    strategySummary(m).axis_rmse_rad_s2=sqrt(mean(errorByStrategy(:,:,m).^2,1));
    strategySummary(m).vector_rmse_rad_s2=sqrt(mean(sum(errorByStrategy(:,:,m).^2,2)));
    strategySummary(m).axis_signed_mean_rad_s2=mean(errorByStrategy(:,:,m),1);
    strategySummary(m).output_clip_count_by_axis=clipCounts(:,m).';
    strategySummary(m).generalized_clip_count_by_channel=allocatorCounts(:,m).';
    strategySummary(m).motor_saturation_count_by_motor=satCounts(:,m).';
end
result=struct('scene_id',sid,'split','VAL','task',tags.task,'condition',tags.condition,'wind',tags.wind, ...
    'source_classification',char(M.source_classification),'reused_screen',logical(M.reused_screen), ...
    'runtime_source_identity_type',char(M.runtime_source_identity_type), ...
    'runtime_source_core_sha256',char(M.runtime_source_core_sha256), ...
    'raw_sha256',char(M.candidate_raw_sha256),'run_start_sha256',char(M.candidate_run_start_sha256), ...
    'run_status_sha256',char(M.candidate_run_status_sha256),'physical_B_source_sha256',char(M.physical_B_source_sha256), ...
    'cache_sha256',char(M.cache_sha256),'cache_bytes',double(M.cache_bytes), ...
    'historical_raw_plant_calls',double(status.plant_calls),'event_count',N, ...
    'plant_index_first_last',[idx(1),idx(end)],'event_time_first_last_s',[events.event_time_s(1),events.event_time_s(end)], ...
    'phase_event_counts',phase_counts(events.phase_code),'max_abs_RBF_clip_beta_applied_torque_closure', ...
      [maxRbfClip,maxRbfBeta,maxRbfApplied,maxRbfTorque],'max_abs_RBF_request_realized_allocator_closure', ...
      [maxCurrentRequest,maxCurrentRealized],'strategy_summary',strategySummary, ...
    'generalized_clip_count_by_strategy_channel',allocatorCounts.','motor_saturation_count_by_strategy_motor',satCounts.');
end

function rs=extract_run_start(S)
if isfield(S,'runStart')&&isstruct(S.runStart), rs=S.runStart;
elseif all(isfield(S,{'cfg','opts','scene_id'})), rs=S;
else, error('CM18Replay:RunStartSchema','MAT run_start has no recognized runStart/cfg schema.'); end
end

function name=runStart_source_type(rs)
if isfield(rs,'source_identity')&&isfield(rs.source_identity,'active_paths')
    name='REUSED_SCREEN_RUN_START_SOURCE_IDENTITY';
elseif isfield(rs,'source_paths')&&isfield(rs,'source_sha256')
    name='DEV72_SOURCE_PATHS_SHA256';
else
    name='UNRECOGNIZED_SOURCE_IDENTITY';
end
end

function verify_runtime_source(rs,M,snapshot,repoRoot)
if isfield(rs,'source_identity')&&isfield(rs.source_identity,'active_paths')&& ...
        isfield(rs.source_identity,'active_sha256')
    identity=rs.source_identity; paths=text_cells(identity.active_paths); hashes=text_cells(identity.active_sha256);
    assert(numel(paths)==numel(hashes)&&numel(paths)==double(M.runtime_source_active_count), ...
        'CM18Replay:RuntimeSourceCount','Reused C5 source inventory count differs from its certification.');
    for k=1:numel(paths), assert_sha(repo_path(repoRoot,paths{k}),hashes{k}); end
    assert(isfield(identity,'c5_core_path')&&isfield(identity,'c5_core_sha256')&& ...
        same_path(identity.c5_core_path,M.runtime_source_core_path)&& ...
        strcmpi(char(identity.c5_core_sha256),char(M.runtime_source_core_sha256)), ...
        'CM18Replay:RuntimeCore','Reused C5 core path/SHA differs from pinned runtime identity.');
    assert_sha(repo_path(repoRoot,identity.c5_core_path),identity.c5_core_sha256);
elseif isfield(rs,'source_paths')&&isfield(rs,'source_sha256')
    paths=text_cells(rs.source_paths); hashes=text_cells(rs.source_sha256);
    snapPaths=text_cells(snapshot.sourceIdentity.active_paths); snapHashes=text_cells(snapshot.sourceIdentity.active_sha256);
    assert(numel(paths)==numel(hashes)&&numel(paths)==numel(snapPaths)&& ...
        numel(hashes)==numel(snapHashes),'CM18Replay:RuntimeSourceCount','DEV72 source inventory count differs from C5 snapshot.');
    for k=1:numel(paths)
        assert(same_path(repo_path(repoRoot,paths{k}),repo_path(repoRoot,snapPaths{k}))&& ...
            strcmpi(hashes{k},snapHashes{k}),'CM18Replay:RuntimeSourceBinding', ...
            'DEV72 run_start source inventory differs from the C5 snapshot.');
        assert_sha(repo_path(repoRoot,paths{k}),hashes{k});
    end
else
    error('CM18Replay:RuntimeSourceIdentity','C5 run_start has an unsupported source identity schema.');
end
if ~isempty(M.runtime_source_core_path)
    assert(strcmpi(char(M.runtime_source_core_sha256),sha256_file(repo_path(repoRoot,M.runtime_source_core_path))), ...
        'CM18Replay:RuntimeCore','Pinned C5 runtime core SHA does not match disk.');
end
end

function tf=same_scene_after_id_alias(a,b,sid,alias)
try
    aId=char(string(a.scene_id)); bId=char(string(b.scene_id));
    if strcmp(alias,'EXACT_CANONICAL_ID')
        tf=strcmp(aId,sid)&&strcmp(bId,sid);
    elseif strcmp(alias,'EXPLICIT_ACC_FIX_V1_SUFFIX_ALIAS')
        tf=strcmp(canonical_accfix_id(aId),sid)&&strcmp(canonical_accfix_id(bId),sid);
    else, tf=false; return
    end
    a.scene_id=sid; b.scene_id=sid; tf=tf&&isequaln(a,b);
catch
    tf=false;
end
end

function sid=canonical_accfix_id(sid)
sid=regexprep(char(sid),'_ACC_FIX_V1(_B)?$','');
end

function tags=scene_tags(sid)
t=regexp(char(sid),'_T(\d+)_C(\d+)_W(\d{2})$','tokens','once');
assert(~isempty(t),'CM18Replay:SceneTags','Canonical task/condition/wind tags missing in %s.',sid);
tags=struct('task',['T' t{1}],'condition',['C' t{2}],'wind',['W' t{3}]);
end

function rows=phase_counts(code)
names={'STATIC','PRE','EXTEND','HOLD','RETRACT','RECOVERY'};
rows=repmat(struct('phase_code',0,'phase_name','','event_count',0),1,numel(names));
for k=1:numel(names), rows(k)=struct('phase_code',k-1,'phase_name',names{k},'event_count',nnz(double(code(:))==k-1)); end
end

function T=make_event_table(sid,E,beta,raw,applied,comp,request,realized,alphaBS,alpha,error,clip,allocClip,motorSat)
N=numel(beta); tags=scene_tags(sid); phaseNames={'STATIC','PRE','EXTEND','HOLD','RETRACT','RECOVERY'};
phase=double(E.phase_code(:)); phaseText=cell(N,1);
for k=1:N, phaseText{k}=phaseNames{phase(k)+1}; end
T=table(repmat(string(sid),N,1),repmat(string(tags.task),N,1), ...
    repmat(string(tags.condition),N,1),repmat(string(tags.wind),N,1), ...
    double(E.event_index(:)),double(E.plant_index(:)),double(E.event_time_s(:)),phase, ...
    string(phaseText),beta(:),'VariableNames',{'scene_id','task','condition','wind','event_ordinal', ...
    'plant_index','event_time_s','phase_code','phase_name','beta'});
strategy={'RBF','A1R','A1T'}; axes={'roll','pitch','yaw'}; channels={'thrust','roll','pitch','yaw'};
for m=1:3
    prefix=strategy{m};
    for a=1:3
        T.([prefix '_raw_' axes{a} '_rad_s2'])=raw(:,a,m);
        T.([prefix '_output_clip_' axes{a}])=clip(:,a,m);
        T.([prefix '_applied_' axes{a} '_rad_s2'])=applied(:,a,m);
        T.([prefix '_comp_torque_' axes{a} '_Nm'])=comp(:,a,m);
        T.([prefix '_alpha_true_' axes{a} '_rad_s2'])=alpha(:,a,m);
        T.([prefix '_error_' axes{a} '_rad_s2'])=error(:,a,m);
    end
    for c=1:4
        T.([prefix '_requested_' channels{c}])=request(:,c,m);
        T.([prefix '_realized_' channels{c}])=realized(:,c,m);
        T.([prefix '_allocator_clip_' channels{c}])=allocClip(:,c,m);
        T.([prefix '_motor_saturated_' num2str(c)])=motorSat(:,c,m);
    end
end
for a=1:3, T.(['alpha_BS_' axes{a} '_rad_s2'])=alphaBS(:,a); end
end

function T=make_scene_metrics(E,sid)
tags=scene_tags(sid); strategy={'RBF','A1R','A1T'}; axes={'roll','pitch','yaw'};
template=struct('scene_id','','task','','condition','','wind','','task_wind','','phase_code',0, ...
    'phase_name','','strategy','','axis','','event_count',0,'rms_error_rad_s2',0, ...
    'signed_mean_error_rad_s2',0,'p95_abs_error_rad_s2',0,'p99_abs_error_rad_s2',0, ...
    'max_abs_error_rad_s2',0,'output_clip_events',0,'same_axis_allocator_clip_events',0, ...
    'any_allocator_clip_events',0,'any_motor_saturation_events',0);
rows=repmat(template,0,1); phaseValues=[-1 0 1 2 3 4 5];
phaseNames={'STATIC','PRE','EXTEND','HOLD','RETRACT','RECOVERY'};
for phaseCode=phaseValues
    if phaseCode<0, mask=true(height(E),1); phaseName='ALL';
    else, mask=double(E.phase_code)==phaseCode; phaseName=phaseNames{phaseCode+1}; end
    n=nnz(mask); if n==0, continue; end
    for m=1:3
        prefix=strategy{m}; allocNames={[prefix '_allocator_clip_thrust'], ...
            [prefix '_allocator_clip_roll'],[prefix '_allocator_clip_pitch'],[prefix '_allocator_clip_yaw']};
        satNames={[prefix '_motor_saturated_1'],[prefix '_motor_saturated_2'], ...
            [prefix '_motor_saturated_3'],[prefix '_motor_saturated_4']};
        anyAlloc=any(E{mask,allocNames},2); anySat=any(E{mask,satNames},2);
        for a=1:3
            err=double(E{mask,[prefix '_error_' axes{a} '_rad_s2']}); sorted=sort(abs(err));
            row=template; row.scene_id=sid; row.task=tags.task; row.condition=tags.condition;
            row.wind=tags.wind; row.task_wind=[tags.task '_' tags.wind]; row.phase_code=phaseCode;
            row.phase_name=phaseName; row.strategy=prefix; row.axis=axes{a}; row.event_count=n;
            row.rms_error_rad_s2=sqrt(mean(err.^2)); row.signed_mean_error_rad_s2=mean(err);
            row.p95_abs_error_rad_s2=sorted(max(1,ceil(.95*n)));
            row.p99_abs_error_rad_s2=sorted(max(1,ceil(.99*n)));
            row.max_abs_error_rad_s2=max(abs(err));
            row.output_clip_events=nnz(E{mask,[prefix '_output_clip_' axes{a}]});
            channel=axes{a}; row.same_axis_allocator_clip_events=nnz(E{mask,[prefix '_allocator_clip_' channel]});
            row.any_allocator_clip_events=nnz(anyAlloc); row.any_motor_saturation_events=nnz(anySat);
            rows(end+1,1)=row; %#ok<AGROW>
        end
    end
end
T=struct2table(rows);
end

function G=aggregate_groups(T)
template=struct('group_type','','group_key','','phase_code',0,'phase_name','','strategy','','axis','', ...
    'scene_count',0,'event_count',0,'pooled_rms_error_rad_s2',0,'pooled_signed_mean_error_rad_s2',0, ...
    'scene_macro_rms_error_rad_s2',0,'output_clip_events',0,'same_axis_allocator_clip_events',0, ...
    'any_allocator_clip_events',0,'any_motor_saturation_events',0);
rows=repmat(template,0,1); groupFields={'task','condition','wind','task_wind'};
for g=1:numel(groupFields)
    groupField=groupFields{g}; keys=unique(string(T.(groupField)),'stable');
    for keyIndex=1:numel(keys)
        key=keys(keyIndex); groupMask=string(T.(groupField))==key;
        phases=unique(double(T.phase_code(groupMask)),'stable');
        for phaseCode=phases(:).'
            phaseMask=groupMask&double(T.phase_code)==phaseCode;
            strategies=unique(string(T.strategy(phaseMask)),'stable');
            for s=1:numel(strategies)
                axes=unique(string(T.axis(phaseMask&string(T.strategy)==strategies(s))),'stable');
                for a=1:numel(axes)
                    m=phaseMask&string(T.strategy)==strategies(s)&string(T.axis)==axes(a);
                    part=T(m,:); n=sum(part.event_count); row=template;
                    row.group_type=groupField; row.group_key=char(key); row.phase_code=phaseCode;
                    row.phase_name=char(part.phase_name(1)); row.strategy=char(strategies(s)); row.axis=char(axes(a));
                    row.scene_count=height(part); row.event_count=n;
                    row.pooled_rms_error_rad_s2=sqrt(sum(part.event_count.*part.rms_error_rad_s2.^2)/n);
                    row.pooled_signed_mean_error_rad_s2=sum(part.event_count.*part.signed_mean_error_rad_s2)/n;
                    row.scene_macro_rms_error_rad_s2=mean(part.rms_error_rad_s2);
                    row.output_clip_events=sum(part.output_clip_events);
                    row.same_axis_allocator_clip_events=sum(part.same_axis_allocator_clip_events);
                    row.any_allocator_clip_events=sum(part.any_allocator_clip_events);
                    row.any_motor_saturation_events=sum(part.any_motor_saturation_events);
                    rows(end+1,1)=row; %#ok<AGROW>
                end
            end
        end
    end
end
G=struct2table(rows);
end

function report=model_report(models,repoRoot)
report=repmat(struct('name','','deployment_path','','deployment_sha256','','deployment_schema','', ...
    'artifact_release_sha256','','checkpoint_sha256','','selected_step',0,'normalizer_sha256',''),1,numel(models));
for k=1:numel(models)
    m=models(k); report(k)=struct('name',m.name,'deployment_path',repo_relative(m.deployment_path,repoRoot), ...
        'deployment_sha256',m.deployment_sha256,'deployment_schema',m.deployment_schema, ...
        'artifact_release_sha256',m.artifact_release_sha256,'checkpoint_sha256',m.checkpoint_sha256, ...
        'selected_step',m.selected_step,'normalizer_sha256',m.normalizer_sha256);
end
end

