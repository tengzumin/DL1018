function out = test48_entry_v1(mode,methodId)
% Independent TEST48 stage/runner entry. Every stage needs its own parent release.
if nargin < 1, error('TEST48:Mode','An exact TEST48 mode is required.'); end
if nargin < 2, methodId=''; end
mode=char(mode); methodId=char(methodId);
allowed={'DEV_INPUT_EQUIVALENCE_ONLY','TEST_INPUT_FREEZE_ONLY','LOCKED_TEST48_PARENT_APPROVED'};
assert(any(strcmp(mode,allowed)),'TEST48:Mode','Unsupported TEST48 mode.');
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(here));
reportDir=fullfile(root,'reports','paper_continuation_20261023','test_entry_v1');
contractPath=fullfile(here,'TEST48_RUN_CONTRACT_v1.json');
manifestPath=fullfile(reportDir,'TEST_METHOD_SOURCE_MANIFEST_v1.json');
assert(isfile(contractPath)&&isfile(manifestPath),'TEST48:Inputs','Code contract or source manifest is missing.');
contract=jsondecode(fileread(contractPath)); manifest=jsondecode(fileread(manifestPath));
verify_code_contract(contract,manifest,root,contractPath,manifestPath);

switch mode
    case 'DEV_INPUT_EQUIVALENCE_ONLY'
        releasePath=fullfile(reportDir,'DEV_INPUT_EQUIVALENCE_PARENT_RELEASE_v1.json');
        release=verify_stage_release(releasePath,'TEST48_DEV_INPUT_EQUIVALENCE_RELEASE_V1', ...
            'APPROVED_DEV_INPUT_EQUIVALENCE_ONLY',contractPath,manifestPath,false,false,false);
        assert(isfield(release,'dev_input_equivalence_authorized')&&logical(release.dev_input_equivalence_authorized), ...
            'TEST48:Release','DEV equivalence permission is absent.');
        out=run_dev_equivalence(root,reportDir,manifest);
    case 'TEST_INPUT_FREEZE_ONLY'
        releasePath=fullfile(reportDir,'TEST_INPUT_FREEZE_PARENT_RELEASE_v1.json');
        release=verify_stage_release(releasePath,'TEST48_INPUT_FREEZE_RELEASE_V1', ...
            'APPROVED_TEST_INPUT_FREEZE_ONLY',contractPath,manifestPath,false,true,true);
        sceneSpecsPath=fullfile(root,'configs','scene_specs.csv');
        assert(isfield(release,'scene_specs_sha256')&&strcmpi(release.scene_specs_sha256,sha256_file(sceneSpecsPath)), ...
            'TEST48:SceneSpecRelease','TEST input freeze release does not bind the original scene_specs.csv.');
        verify_dev_precondition(reportDir,release);
        try
            out=freeze_test_inputs(root,here,reportDir,contract,manifest,release);
        catch ME
            failurePath=fullfile(reportDir,'TEST_INPUT_FREEZE_FAILURE_v1.json');
            if ~isfile(failurePath)
                write_json_new(failurePath,struct('schema','TEST48_INPUT_FREEZE_FAILURE_V1', ...
                    'status','FAILED_NO_RETRY','identifier',ME.identifier,'message',ME.message, ...
                    'TEST_accessed',true,'plant_calls',0,'failed_utc',utc_now()));
            end
            rethrow(ME);
        end
    case 'LOCKED_TEST48_PARENT_APPROVED'
        if isempty(methodId), error('TEST48:Method','A fixed method id is required for the Plant mode.'); end
        releasePath=fullfile(reportDir,'LOCKED_TEST48_PARENT_RELEASE_v1.json');
        release=verify_stage_release(releasePath,'TEST48_LOCKED_RUN_RELEASE_V1', ...
            'APPROVED_LOCKED_TEST48_PARENT_V1',contractPath,manifestPath,true,false,true);
        out=run_one_method(root,here,reportDir,contract,manifest,release,methodId);
end
end

function verify_code_contract(c,m,root,contractPath,manifestPath)
assert(strcmp(c.schema,'TEST48_RUN_CONTRACT_V1')&& ...
    strcmp(c.state,'CODE_ONLY_WAITING_FOR_SEPARATE_STAGE_RELEASES')&& ...
    strcmp(m.schema,'TEST48_METHOD_SOURCE_MANIFEST_V1')&&~logical(m.test_accessed)&&~logical(m.plant_started), ...
    'TEST48:CodeContract','The TEST code/manifest is outside the authorized code-only state.');
assert(strcmpi(sha256_file(manifestPath),c.method_source_manifest_sha256), ...
    'TEST48:ManifestSHA','The run contract does not bind the actual source manifest.');
assert(strcmpi(m.taskbook_sha256,'e0b58545fda8d779f2672afa50de976596ac510f82f6aa83493ed7583216130b')&& ...
    strcmpi(m.code_only_release_sha256,'75f32b259ab3fe901b52ac1f4162f0ea04ee3bb1145c9b958fb5e311a24f1b58'), ...
    'TEST48:Taskbook','The source manifest has another taskbook/release identity.');
taskbookPath=fullfile(root,'reports','paper_continuation_20261023','TEST_ENTRY_CODE_ONLY_TASKBOOK_ZH.md');
codeReleasePath=fullfile(root,'reports','paper_continuation_20261023','TEST_ENTRY_CODE_ONLY_PARENT_RELEASE_v1.json');
verify_file(taskbookPath,c.taskbook_sha256); verify_file(codeReleasePath,c.code_only_release_sha256);
resourcePath=repo_path(root,char(c.limits.prior_creation_observation_path));
verify_file(resourcePath,char(c.limits.prior_creation_observation_sha256));
resourceObservation=jsondecode(fileread(resourcePath));
assert(double(resourceObservation.observed_created_bytes)==double(c.limits.prior_created_bytes)&& ...
    logical(resourceObservation.TEST_started)==false&&isempty(resourceObservation.stat_errors), ...
    'TEST48:ResourceBaseline','The fixed pre-existing artifact baseline or its no-TEST observation changed.');
codeRelease=jsondecode(fileread(codeReleasePath));
assert(strcmp(codeRelease.status,'APPROVED_CODE_IMPLEMENTATION_ONLY')&& ...
    ~logical(codeRelease.MATLAB_authorized)&&~logical(codeRelease.Plant_authorized)&& ...
    ~logical(codeRelease.TEST_generation_authorized)&&~logical(codeRelease.TEST_unsealed)&& ...
    ~logical(codeRelease.training_authorized), ...
    'TEST48:CodeOnlyRelease','The parent release authorizes code only; no execution mode is permitted by it.');
assert(numel(c.method_order)==6&&numel(m.methods)==6&&c.execution.max_unique_plant_calls==288&& ...
    c.execution.scene_count==48&&c.execution.test_accessed_flag_for_TEST_freeze_and_run, ...
    'TEST48:MethodCount','The frozen six-method/48-scene contract changed.');
for k=1:6
    assert(strcmp(c.method_order(k).id,m.methods(k).method_id)&& ...
        strcmp(c.method_order(k).alias,m.methods(k).alias)&&double(m.methods(k).order)==k, ...
        'TEST48:MethodOrder','Method identity/order mismatch at row %d.',k);
    method=m.methods(k);
    if isfield(method,'input_lock_path')&&~isempty(char(method.input_lock_path))
        verify_file(repo_path(root,char(method.input_lock_path)),char(method.input_lock_sha256));
    end
    if isfield(method,'run_contract_path')&&~isempty(char(method.run_contract_path))
        verify_file(repo_path(root,char(method.run_contract_path)),char(method.run_contract_sha256));
    end
    if isfield(method,'cfg_opts_snapshot_path')&&~isempty(char(method.cfg_opts_snapshot_path))
        verify_file(repo_path(root,char(method.cfg_opts_snapshot_path)),char(method.cfg_opts_snapshot_sha256));
    end
    refs=method.source_refs;
    for j=1:numel(refs), verify_file(char(refs(j).path),char(refs(j).sha256)); end
    if isfield(method,'model_refs')
        for j=1:numel(method.model_refs), verify_file(char(method.model_refs(j).path),char(method.model_refs(j).sha256)); end
    end
    if isfield(m.methods(k),'runtime_tree_path')&&~isempty(char(m.methods(k).runtime_tree_path))
        assert(strcmpi(sha256_tree(char(m.methods(k).runtime_tree_path)),char(m.methods(k).runtime_tree_sha256)), ...
            'TEST48:RuntimeTree','Corrected runtime tree identity changed for %s.',m.methods(k).method_id);
    end
end
for j=1:numel(m.shared_source_refs), verify_file(char(m.shared_source_refs(j).path),char(m.shared_source_refs(j).sha256)); end
erratumRef=find_shared(m,'dev_input_equivalence_metadata_erratum');
statsRef=find_shared(m,'test48_score_statistics_contract');
generatorRef=find_shared(m,'current_scene_generator');
assert(strcmpi(char(c.source_contract.dev_input_equivalence_metadata_erratum_sha256),char(erratumRef.sha256))&& ...
    strcmpi(char(c.source_contract.statistics_contract_sha256),char(statsRef.sha256))&& ...
    strcmpi(char(c.source_contract.expected_scene_generator_sha256),char(generatorRef.sha256))&& ...
    strcmp(char(c.source_contract.generator_reference_contract_id),'DL1018_SCENE_REF_FIG8_A2_V2'), ...
    'TEST48:SharedContract','Manifest shared sources differ from the exact generator/statistics/error-note contract.');
% All new path lengths are checked before any scene generation or Plant call.
assert_short(fullfile(root,'experiments','c5_test48_v1','input','TEST_SCENES_SHARED_v1.mat'));
assert_short(fullfile(root,'experiments','c5_test48_v1','input','TEST_METHOD_CFG_OPTS_v1.mat'));
assert_short(fullfile(root,'experiments','c5_test48_v1','input','TEST_INPUT_INDEX_v1.json'));
end

function release=verify_stage_release(path,schema,status,contractPath,manifestPath,plant,sceneGeneration,testAccess)
assert(isfile(path),'TEST48:ParentRelease','The separate parent stage release is missing: %s.',path);
release=jsondecode(fileread(path));
assert(isfield(release,'schema')&&strcmp(release.schema,schema)&&isfield(release,'status')&&strcmp(release.status,status), ...
    'TEST48:ParentRelease','Parent release schema/status mismatch.');
assert(isfield(release,'taskbook_sha256')&&strcmpi(release.taskbook_sha256, ...
    sha256_file(fullfile(fileparts(fileparts(fileparts(mfilename('fullpath')))),'reports','paper_continuation_20261023','TEST_ENTRY_CODE_ONLY_TASKBOOK_ZH.md')))&& ...
    isfield(release,'contract_sha256')&&strcmpi(release.contract_sha256,sha256_file(contractPath))&& ...
    isfield(release,'method_source_manifest_sha256')&&strcmpi(release.method_source_manifest_sha256,sha256_file(manifestPath))&& ...
    isfield(release,'entry_sha256')&&strcmpi(release.entry_sha256,sha256_file([mfilename('fullpath') '.m']))&& ...
    isfield(release,'launcher_sha256')&&strcmpi(release.launcher_sha256,sha256_file(fullfile(fileparts(mfilename('fullpath')),'RUN_TEST48_EXACT_v1.ps1'))), ...
    'TEST48:ParentReleaseBinding','Parent release does not bind the exact taskbook, contract and source manifest.');
assert(isfield(release,'plant_authorized')&&logical(release.plant_authorized)==plant&& ...
    isfield(release,'scene_generation_authorized')&&logical(release.scene_generation_authorized)==sceneGeneration&& ...
    isfield(release,'TEST_accessed')&&logical(release.TEST_accessed)==testAccess&& ...
    isfield(release,'training_authorized')&&~logical(release.training_authorized), ...
    'TEST48:ParentReleaseFlags','Parent release permission flags are not exact.');
end

function verify_dev_precondition(reportDir,release)
resultPath=fullfile(reportDir,'DEV_INPUT_EQUIVALENCE_RESULT_v1.json');
exitPath=fullfile(reportDir,'DEV_INPUT_EQUIVALENCE_MATLAB_OS_EXIT_v1.json');
assert(isfile(resultPath)&&isfile(exitPath),'TEST48:DEVPrecondition','A completed DEV equivalence result and OS receipt are required.');
result=jsondecode(fileread(resultPath)); os=jsondecode(fileread(exitPath));
assert(strcmp(result.status,'PASS_DEV_ALL72_GENERATOR_EQUIVALENCE')&&~logical(result.TEST_accessed)&& ...
    double(result.plant_calls)==0&&double(os.matlab_os_exit_code)==0, ...
    'TEST48:DEVPrecondition','DEV equivalence did not naturally complete OS0.');
assert(isfield(release,'dev_result_sha256')&&strcmpi(release.dev_result_sha256,sha256_file(resultPath))&& ...
    isfield(release,'dev_os_exit_sha256')&&strcmpi(release.dev_os_exit_sha256,sha256_file(exitPath)), ...
    'TEST48:DEVBinding','TEST freeze release does not bind the passed DEV evidence.');
end

function result=run_dev_equivalence(root,reportDir,manifest)
resultPath=fullfile(reportDir,'DEV_INPUT_EQUIVALENCE_RESULT_v1.json');
failurePath=fullfile(reportDir,'DEV_INPUT_EQUIVALENCE_FAILURE_v1.json');
assert(~isfile(resultPath)&&~isfile(failurePath),'TEST48:NoRetry','DEV output exists; preserve it and do not retry.');
c5=find_method(manifest,'C5_M110');
lockPath=char(c5.input_lock_path); lock=jsondecode(fileread(lockPath)); ids=cellstr(string(lock.scene_ids_all_72(:)));
assert(numel(ids)==72&&numel(unique(string(ids)))==72,'TEST48:DEVIds','Expected the locked 72 existing development scene IDs.');
isDev=startsWith(string(ids),'DL1018_DEV_'); isVal=startsWith(string(ids),'DL1018_VAL_');
assert(all(isDev|isVal)&&~any(contains(string(ids),'TEST')),'TEST48:DEVOnlyIds', ...
    'DEV equivalence may read only the locked DEV/VAL IDs and must contain no TEST ID.');
currentRef=find_shared(manifest,'current_scene_generator'); correctedRef=find_shared(manifest,'corrected_fixed_scene_generator');
restoredefaultpath; addpath(fullfile(root,'matlab','runtime'),'-begin'); clear init_dl1018; rehash;
initPath=fullfile(root,'matlab','runtime','init_dl1018.m');
assert(same_path(which('init_dl1018'),initPath),'TEST48:DEVInitPath','Project initializer is not active for six-method preflight.');
[cfg,~,resolvedRoot]=init_dl1018(); assert(same_path(resolvedRoot,root),'TEST48:DEVProjectRoot','DEV preflight resolved another project root.');
methodPreflight=cell(6,1);
for k=1:6
    method=manifest.methods(k); snap=build_method_snapshot(root,method,cfg);
    methodPreflight{k}=method_preflight_summary(root,method,snap);
end
records=cell(72,1);
try
    for k=1:72
        id=ids{k}; row=scene_row(lock,id); verify_file(char(row.B_source.path),char(row.B_source.sha256));
        old=load(char(row.B_source.path),'scene'); assert(isfield(old,'scene'),'TEST48:DEVSource','B_source lacks a scene variable: %s.',id);
        a=call_generator(root,char(currentRef.path),id); b=call_generator(root,char(correctedRef.path),id);
        valid_scene(a.scene,id); valid_scene(b.scene,id);
        oldScene=normalize_scene_id(old.scene,id); a=normalize_pack_alias(a,id); b=normalize_pack_alias(b,id);
        [currentSceneForB,noteB]=remove_current_scene_contract_note(a.scene,oldScene,id,'B_source_vs_current');
        [d1,e1]=compare_tree(oldScene,currentSceneForB,[id '.B_source_vs_current']);
        [aForCorrected,noteC]=remove_current_pack_contract_note(a,b,id);
        [d2,e2]=compare_pack(aForCorrected,b,[id '.current_vs_corrected_fixed']);
        fieldAudit=[fieldwise_compare(oldScene,currentSceneForB,id,'B_source_vs_current','scene'), ...
            fieldwise_compare_pack(aForCorrected,b,id,'current_vs_corrected_fixed')];
        records{k}=struct('scene_id',id,'B_source_path',char(row.B_source.path), ...
            'B_source_sha256',char(row.B_source.sha256),'current_vs_B_max_abs',d1, ...
            'corrected_vs_current_max_abs',d2,'current_vs_B_bit_equal',e1, ...
            'corrected_vs_current_bit_equal',e2,'reference_contract_note_normalizations',[noteB(:);noteC(:)], ...
            'field_audits',fieldAudit);
    end
    result=struct('schema','TEST48_DEV_INPUT_EQUIVALENCE_RESULT_V1', ...
        'status','PASS_DEV_ALL72_GENERATOR_EQUIVALENCE','scope','Existing 72 DEV/VAL scene inputs only; no TEST rows read.', ...
        'scene_count',72,'scene_ids',{ids},'records',{records},'max_abs_limit',1e-12, ...
        'six_method_cfg_opts_model_preflight',{methodPreflight}, ...
        'current_generator_sha256',char(currentRef.sha256),'corrected_fixed_generator_sha256',char(correctedRef.sha256), ...
        'C5_DEV72_input_lock_sha256',sha256_file(lockPath),'TEST_accessed',false,'plant_calls',0, ...
        'training_steps',0,'created_utc',utc_now());
    write_json_new(resultPath,result);
catch ME
    failure=struct('schema','TEST48_DEV_INPUT_EQUIVALENCE_FAILURE_V1','status','FAILED_NO_RETRY', ...
        'identifier',ME.identifier,'message',ME.message,'completed_scenes',k-1,'created_utc',utc_now(), ...
        'TEST_accessed',false,'plant_calls',0);
    write_json_new(failurePath,failure); rethrow(ME);
end
end

function result=freeze_test_inputs(root,here,reportDir,contract,manifest,release)
machine=machine_info();
assert(strcmp(machine.matlab_release,'2025b'),'TEST48:MatlabRelease','The locked entry requires MATLAB R2025b.');
inputDir=fullfile(here,'input');
outputs={fullfile(inputDir,'TEST_SCENES_SHARED_v1.mat'),fullfile(inputDir,'TEST_METHOD_CFG_OPTS_v1.mat'), ...
    fullfile(inputDir,'TEST_INPUT_INDEX_v1.json'),fullfile(reportDir,'TEST_INPUT_FREEZE_RESULT_v1.json'), ...
    fullfile(reportDir,'TEST_INPUT_FREEZE_FAILURE_v1.json')};
assert(all(~cellfun(@isfile,outputs))&&~isfolder(inputDir),'TEST48:NoRetry','TEST input freeze outputs exist; do not overwrite or regenerate.');
assert(isfile(fullfile(root,'reports','G01_SCENES.json'))&&isfile(fullfile(root,'configs','dataset_plan.json')), ...
    'TEST48:SealFiles','G01 or dataset plan is missing.');
g01=jsondecode(fileread(fullfile(root,'reports','G01_SCENES.json')));
plan=jsondecode(fileread(fullfile(root,'configs','dataset_plan.json')));
assert(strcmp(g01.status,'PASS')&&logical(g01.checks.test_sealed)&&double(g01.actual_counts.test)==48&& ...
    strcmp(plan.test_status,'SEALED')&&double(plan.split_counts.TEST)==48, ...
    'TEST48:Sealed','G01/dataset plan no longer report the original sealed 48 TEST scenes.');
specPath=fullfile(root,'configs','scene_specs.csv'); M=readtable(specPath,'TextType','string','VariableNamingRule','preserve');
assert(all(ismember({'scene_id','split'},M.Properties.VariableNames)),'TEST48:SpecSchema','scene_specs schema changed.');
testRows=M(M.split=="TEST",:); sceneIds=sort(string(testRows.scene_id));
assert(height(testRows)==48&&numel(unique(sceneIds))==48&&all(startsWith(sceneIds,"DL1018_TEST_")), ...
    'TEST48:TestSpec','Sealed TEST metadata does not contain exactly 48 unique IDs.');
currentRef=find_shared(manifest,'current_scene_generator'); scenePacks=cell(48,1); digests=cell(48,1);
for k=1:48
    id=char(sceneIds(k)); p=call_generator(root,char(currentRef.path),id);
    valid_scene(p.scene,id);
    assert(strcmp(string(p.spec.scene_id),sceneIds(k)),'TEST48:SceneSpecIdentity','Generated TEST scene/spec mismatch: %s.',id);
    scenePacks{k}=p; digests{k}=sha256_bytes(getByteStreamFromArray(p));
end
% Rebuild each method's actual cfg/opts from locked TEST sources and freeze once per method.
restoredefaultpath; addpath(fullfile(root,'matlab','runtime'),'-begin'); clear init_dl1018; rehash;
assert(same_path(which('init_dl1018'),fullfile(root,'matlab','runtime','init_dl1018.m')), ...
    'TEST48:InitPath','Current project initializer is not active before cfg rebuild.');
[cfg,~,resolvedRoot]=init_dl1018();
assert(same_path(resolvedRoot,root),'TEST48:ProjectRoot','init_dl1018 resolved another project root.');
methodSnapshots=cell(6,1);
for k=1:6
    method=manifest.methods(k); methodSnapshots{k}=build_method_snapshot(root,method,cfg);
end
sceneSetSha=sha256_bytes(uint8(unicode2native(strjoin(cellstr(sceneIds),newline),'UTF-8')));
sceneFieldArrays=cell(48,1);
for k=1:48, sceneFieldArrays{k}=collect_array_inventory(scenePacks{k},char(sceneIds(k)),'pack'); end
if ~isfolder(inputDir), mkdir(inputDir); end
sharedPath=fullfile(inputDir,'TEST_SCENES_SHARED_v1.mat'); cfgPath=fullfile(inputDir,'TEST_METHOD_CFG_OPTS_v1.mat');
save(sharedPath,'scenePacks','sceneIds','digests','sceneSetSha','-v7.3');
save(cfgPath,'methodSnapshots','sceneSetSha','-v7.3');
sharedSha=sha256_file(sharedPath); cfgSha=sha256_file(cfgPath);
index=struct('schema','TEST48_INPUT_INDEX_V1','status','FROZEN_SHARED_TEST_INPUTS', ...
    'scene_ids',{cellstr(sceneIds)},'scene_count',48,'scene_order','sorted scene_id', ...
    'scene_digests',{cellfun(@(s)sha256_bytes(getByteStreamFromArray(s)),scenePacks,'UniformOutput',false)}, ...
    'scene_field_arrays',{sceneFieldArrays}, ...
    'scene_set_sha256',sceneSetSha,'scene_digest_format','MATLAB_GETBYTESTREAM_V1', ...
    'shared_scenes_mat_path',sharedPath,'shared_scenes_mat_sha256',sharedSha, ...
    'method_cfg_opts_path',cfgPath,'method_cfg_opts_sha256',cfgSha, ...
    'scene_specs_path',specPath,'scene_specs_sha256',sha256_file(specPath), ...
    'effective_config_path',fullfile(root,'configs','effective_config.mat'), ...
    'effective_config_sha256',sha256_file(fullfile(root,'configs','effective_config.mat')), ...
    'method_source_manifest_sha256',sha256_file(fullfile(reportDir,'TEST_METHOD_SOURCE_MANIFEST_v1.json')), ...
    'DEV_input_equivalence_result_sha256',sha256_file(fullfile(reportDir,'DEV_INPUT_EQUIVALENCE_RESULT_v1.json')), ...
    'freeze_release_sha256',sha256_file(fullfile(reportDir,'TEST_INPUT_FREEZE_PARENT_RELEASE_v1.json')), ...
    'machine_info',machine, ...
    'TEST_accessed',true,'plant_calls',0,'training_steps',0,'created_utc',utc_now());
write_json_new(fullfile(inputDir,'TEST_INPUT_INDEX_v1.json'),index);
result=struct('schema','TEST48_INPUT_FREEZE_RESULT_V1','status','PREPARED_TEST48_INPUTS_NO_PLANT', ...
    'scene_count',48,'scene_set_sha256',sceneSetSha,'shared_scenes_mat_sha256',sharedSha, ...
    'method_cfg_opts_sha256',cfgSha,'input_index_sha256',sha256_file(fullfile(inputDir,'TEST_INPUT_INDEX_v1.json')), ...
    'freeze_release_sha256',sha256_file(fullfile(reportDir,'TEST_INPUT_FREEZE_PARENT_RELEASE_v1.json')), ...
    'TEST_accessed',true,'plant_calls',0,'training_steps',0,'created_utc',utc_now());
write_json_new(fullfile(reportDir,'TEST_INPUT_FREEZE_RESULT_v1.json'),result);
end

function snap=build_method_snapshot(root,m,cfgNow)
snap=struct('method_id',char(m.method_id),'alias',char(m.alias),'cfg',cfgNow,'opts',[], ...
    'modelIdentity',[],'model_sha256','','normalizer_sha256','','cfg_opts_source_sha256', ...
    char(m.cfg_opts_snapshot_sha256),'template_run_start_sha256','','runtime_tree_sha256',char(m.runtime_tree_sha256));
id=char(m.method_id);
if strcmp(id,'B_TRACEABLE')
    p=load(char(m.cfg_opts_snapshot_path),'cfg','opts');
    assert(isequaln(cfgNow,p.cfg),'TEST48:BConfig','Fresh cfg differs from B prepared snapshot.');
        bind_method_path(root,m);
    opts=controller_options_dl1018(cfgNow,'B');
    assert(isequaln(opts,p.opts),'TEST48:BOptions','Fresh controller_options_dl1018(cfg,''B'') differs from locked B opts.');
    snap.opts=opts;
elseif startsWith(id,'CORRECTED_')
    templatePath=char(m.cfg_opts_snapshot_path);
    templateVars=whos('-file',templatePath); names={templateVars.name};
    required={'cfg','opts','meta','scene','sceneMeta','spec'};
    assert(all(ismember(required,names))&&~ismember('runStart',names), ...
        'TEST48:OldRunStartSchema','Historical corrected run_start must expose top-level cfg/opts/meta/scene/sceneMeta/spec.');
    old=load(templatePath,'cfg','opts');
    assert(isequaln(cfgNow,old.cfg),'TEST48:OldConfig','Historical corrected cfg differs from effective TEST cfg.');
        bind_method_path(root,m);
    modelPath=char(find_model_ref(m,'model_mat').path); modelPack=load(modelPath,'model'); model=modelPack.model;
    expectedId=char(m.model_identity.model_id);
    arch=expectedId(1:end-2);
    contextExpected=32; if strcmp(expectedId,'KAN14'), contextExpected=1; end
    assert(isstruct(model)&&isfield(model,'model_id')&&strcmp(char(model.model_id),expectedId)&& ...
        isfield(model,'architecture')&&strcmpi(char(model.architecture),arch)&& ...
        isfield(model,'input_dim')&&double(model.input_dim)==14&&isfield(model,'window')&&double(model.window)==32&& ...
        isfield(model,'context_length')&&double(model.context_length)==contextExpected&& ...
        isfield(model,'seed')&&double(model.seed)==2026102001&&isfield(model,'selected_step')&&double(model.selected_step)==60000&& ...
        isfield(model,'output_W')&&isequal(size(model.output_W),[33 3])&& ...
        numel(fieldnames(model))==double(m.model_identity.model_field_count), ...
        'TEST48:OldModelSchema','Corrected model identity/shape differs from the actual locked model schema.');
    modelW0Sha=sha256_bytes(typecast(double(model.output_W(:)),'uint8'));
    if isfield(m.model_identity,'W0_sha256')
        assert(strcmpi(modelW0Sha,char(m.model_identity.W0_sha256)), ...
            'TEST48:OldW0','Corrected model output_W differs from its locked W0 SHA.');
    end
    opts=old.opts;
    assert(isfield(opts,'stage1_position_runtime')&&isstruct(opts.stage1_position_runtime), ...
        'TEST48:OldOptsSchema','Historical corrected opts lack stage1_position_runtime.');
    opts.stage1_position_runtime.model=model; opts.stage1_position_runtime.weight=model.output_W;
    if isfield(opts.stage1_position_runtime,'position_only_search_head')&&isstruct(opts.stage1_position_runtime.position_only_search_head)
        opts.stage1_position_runtime.position_only_search_head.W0=model.output_W;
    end
    if isfield(opts,'r2e_first_plant_step_marker'), opts.r2e_first_plant_step_marker=''; end
    snap.opts=opts; snap.modelIdentity=struct('model_id',char(model.model_id),'seed',double(model.seed), ...
        'selected_step',double(model.selected_step),'input_dim',double(model.input_dim),'window',double(model.window), ...
        'W0_sha256',modelW0Sha, ...
        'normalizer_arrays_sha256',hash_normalizer_arrays(model));
    snap.model_sha256=char(find_model_ref(m,'model_mat').sha256);
    snap.normalizer_sha256=char(find_model_ref(m,'normalizer').sha256);
    snap.template_run_start_sha256=sha256_file(templatePath);
else
    snapPath=char(m.cfg_opts_snapshot_path); p=load(snapPath,'cfg','opts','W0','modelIdentity');
    assert(all(isfield(p,{'cfg','opts','W0','modelIdentity'}))&&isequaln(cfgNow,p.cfg), ...
        'TEST48:C5Config','C5 cfg or snapshot schema changed.');
    required={'W0_sha256','input_dim','model_id','normalizer_arrays_sha256','selected_step','window'};
    assert(isstruct(p.modelIdentity)&&isequal(sort(fieldnames(p.modelIdentity)),sort(required(:))), ...
        'TEST48:C5ModelIdentitySchema','Actual C5 modelIdentity is not the locked six-field schema.');
    modelPath=char(find_model_ref(m,'model_mat').path); modelPack=load(modelPath,'model'); model=modelPack.model;
    modelContract=jsondecode(fileread(char(m.run_contract_path)));
    expectedModel=modelContract.model;
    modelW0=double(model.output_W);
    assert(strcmp(char(model.model_id),char(expectedModel.id))&&double(model.seed)==double(expectedModel.seed)&& ...
        double(model.selected_step)==double(expectedModel.selected_step)&&double(model.input_dim)==14&&double(model.window)==32&& ...
        isequal(size(modelW0),[33 3])&&isequal(modelW0,double(p.W0))&& ...
        strcmpi(sha256_bytes(typecast(modelW0(:),'uint8')),char(p.modelIdentity.W0_sha256))&& ...
        strcmpi(hash_normalizer_arrays(model),char(p.modelIdentity.normalizer_arrays_sha256)), ...
        'TEST48:C5ModelArrays','Actual model/W0/normalizer arrays differ from the frozen C5 identity.');
    bind_method_path(root,m);
    if ~isempty(p.opts.position_coordinate_mask)
        assert(isequal(double(p.opts.position_coordinate_mask(:)),[1;1;0]),'TEST48:C5Mask','C5 coordinate mask changed.');
    end
    assert(isequal(double(p.opts.stage1_position_runtime.position_only_search_head.W0),double(p.W0)), ...
        'TEST48:C5W0','C5 initial W0 differs from its snapshot.');
    snap.opts=p.opts; snap.modelIdentity=p.modelIdentity; snap.model_sha256=char(find_model_ref(m,'model_mat').sha256);
    snap.normalizer_sha256=char(find_model_ref(m,'normalizer').sha256);
end
if isfield(snap.opts,'r2e_first_plant_step_marker'), snap.opts=rmfield(snap.opts,'r2e_first_plant_step_marker'); end
end
function record=method_preflight_summary(root,m,snap)
bindings=bind_method_path(root,m);
record=struct('method_id',char(m.method_id),'alias',char(m.alias), ...
    'snapshot_file_sha256',char(m.cfg_opts_snapshot_sha256), ...
    'cfg_value_sha256',sha256_bytes(getByteStreamFromArray(snap.cfg)), ...
    'opts_value_sha256',sha256_bytes(getByteStreamFromArray(snap.opts)), ...
    'model_identity',snap.modelIdentity,'model_mat_sha256',snap.model_sha256, ...
    'normalizer_sha256',snap.normalizer_sha256,'initial_weight_identity',initial_weight_identity(snap), ...
    'which_bindings',bindings,'TEST_accessed',false,'plant_calls',0,'training_steps',0);
end

function out=run_one_method(root,here,reportDir,contract,manifest,release,methodId)
machine=machine_info();
assert(strcmp(machine.matlab_release,'2025b'),'TEST48:MatlabRelease','The locked entry requires MATLAB R2025b.');
ix=find(strcmp({manifest.methods.method_id},methodId));
assert(numel(ix)==1,'TEST48:MethodId','Method id is not one of the six fixed entries: %s.',methodId);
method=manifest.methods(ix); alias=char(method.alias);
inputDir=fullfile(here,'input'); sharedPath=fullfile(inputDir,'TEST_SCENES_SHARED_v1.mat');
cfgPath=fullfile(inputDir,'TEST_METHOD_CFG_OPTS_v1.mat'); indexPath=fullfile(inputDir,'TEST_INPUT_INDEX_v1.json');
freezeResultPath=fullfile(reportDir,'TEST_INPUT_FREEZE_RESULT_v1.json'); freezeExitPath=fullfile(reportDir,'TEST_INPUT_FREEZE_MATLAB_OS_EXIT_v1.json');
assert(isfile(sharedPath)&&isfile(cfgPath)&&isfile(indexPath)&&isfile(freezeResultPath)&&isfile(freezeExitPath), ...
    'TEST48:FrozenInputMissing','TEST scene package/snapshots/natural OS receipt is incomplete.');
idx=jsondecode(fileread(indexPath)); freeze=jsondecode(fileread(freezeResultPath)); freezeOS=jsondecode(fileread(freezeExitPath));
assert(strcmp(freeze.status,'PREPARED_TEST48_INPUTS_NO_PLANT')&&logical(freeze.TEST_accessed)&& ...
    double(freeze.plant_calls)==0&&double(freezeOS.matlab_os_exit_code)==0&& ...
    strcmpi(idx.shared_scenes_mat_sha256,sha256_file(sharedPath))&& ...
    strcmpi(idx.method_cfg_opts_sha256,sha256_file(cfgPath))&& ...
    strcmpi(release.input_index_sha256,sha256_file(indexPath))&& ...
    strcmpi(release.shared_scenes_mat_sha256,sha256_file(sharedPath))&& ...
    strcmpi(release.method_cfg_opts_sha256,sha256_file(cfgPath))&& ...
    strcmpi(release.freeze_result_sha256,sha256_file(freezeResultPath))&& ...
    strcmpi(release.freeze_os_exit_sha256,sha256_file(freezeExitPath)), ...
    'TEST48:InputReleaseBinding','The separate Plant release does not bind the natural-OS0 frozen input package.');
assert(double(release.scene_count)==48&&double(release.max_plant_calls)==288&&logical(idx.TEST_accessed), ...
    'TEST48:RunReleaseScope','Plant release is not exactly 48 shared scenes/288 max calls.');
assert(isfield(release,'scene_set_sha256')&&strcmpi(release.scene_set_sha256,char(idx.scene_set_sha256)), ...
    'TEST48:RunReleaseSceneSet','Plant release does not bind the exact ordered TEST scene set.');
expectedIds=cellstr(string({contract.method_order.id}));
assert(isequal(string(release.method_ids(:)),string(expectedIds(:)))&& ...
    isequal(string(idx.scene_ids(:)),string(sort(string(idx.scene_ids(:))))), ...
    'TEST48:RunReleaseOrder','Release method order or frozen scene ordering changed.');
assert(~isfile(fullfile(reportDir,[alias '_MATLAB_OS_EXIT_v1.json']))&& ...
    ~isfolder(fullfile(here,'runs',alias)),'TEST48:NoRetry','This method already has output; no retry is permitted.');
pack=load(sharedPath,'scenePacks','sceneIds','digests','sceneSetSha'); snapshots=load(cfgPath,'methodSnapshots','sceneSetSha');
assert(numel(pack.scenePacks)==48&&numel(pack.sceneIds)==48&&numel(pack.digests)==48&& ...
    numel(snapshots.methodSnapshots)==6&&isequal(pack.sceneSetSha,snapshots.sceneSetSha)&& ...
    isequal(pack.sceneSetSha,idx.scene_set_sha256), ...
    'TEST48:FrozenPackageSchema','Scene/config snapshot package schema or set hash changed.');
snap=snapshots.methodSnapshots{ix};
assert(strcmp(snap.method_id,methodId)&&strcmp(snap.alias,alias)&&isstruct(snap.cfg)&&isstruct(snap.opts), ...
    'TEST48:MethodSnapshot','Method cfg/opts snapshot identity is wrong.');
whichBindings=bind_method_path(root,method);
methodContract=read_method_contract(method);
candidate=method_candidate(methodContract,methodId);
runRoot=fullfile(here,'runs',alias);
for k=1:48
    id=char(pack.sceneIds(k)); attempt=fullfile(runRoot,id,'attempt_01'); assert_short(attempt);
    names={'attempt_started.marker','first_plant_step.marker','run_start.mat','raw_run.mat','run_status.json','FAILURE_NO_RETRY_v1.json'};
    for j=1:numel(names)
        p=fullfile(attempt,names{j}); assert_short(p);
        assert(~isfile(p),'TEST48:NoRetry','An attempt artifact already exists: %s.',p);
    end
    assert(~isfolder(attempt),'TEST48:NoRetry','An attempt directory already exists: %s.',attempt);
end
if ~isfolder(runRoot), mkdir(runRoot); end
batchPath=fullfile(runRoot,'METHOD_BATCH_STATUS_v1.json'); bodyPath=fullfile(runRoot,'METHOD_BODY_COMPLETE_v1.json');
assert(~isfile(batchPath)&&~isfile(bodyPath),'TEST48:NoRetry','Method batch/body output exists; do not retry.');
batch=struct('schema','TEST48_METHOD_BATCH_STATUS_V1','status','RUNNING', ...
    'method_id',methodId,'alias',alias,'phase','LOCKED_TEST48_PARENT_APPROVED', ...
    'TEST_accessed',true,'plant_calls',0,'training_steps',0,'optimizer_steps',0, ...
    'parent_release_sha256',sha256_file(fullfile(reportDir,'LOCKED_TEST48_PARENT_RELEASE_v1.json')), ...
    'input_index_sha256',sha256_file(indexPath),'shared_scenes_mat_sha256',sha256_file(sharedPath), ...
        'method_cfg_opts_sha256',sha256_file(cfgPath),'method_source_manifest_sha256',sha256_file(fullfile(reportDir,'TEST_METHOD_SOURCE_MANIFEST_v1.json')), ...
        'runner_sha256',sha256_file([mfilename('fullpath') '.m']), ...
    'machine_info',machine,'thread_argument','-singleCompThread', ...
    'controller_timer_boundary','Frozen controller_call_time_s source unchanged; ends before allocator/Plant/MAT save.', ...
        'runtime_tree_sha256',char(method.runtime_tree_sha256),'scene_count',48,'completed_scenes',0, ...
    'records',empty_records(),'created_utc',utc_now());
write_json_new(batchPath,batch); records=empty_records(); plantStartedUnrecorded=0;
try
    for k=1:48
        plantStartedUnrecorded=0;
        remainingSceneCalls=(49-k)+(6-ix)*48;
        remainingProcesses=7-ix;
        assert_budget(here,reportDir,contract,remainingSceneCalls,remainingProcesses);
        scenePack=pack.scenePacks{k};
        assert(strcmp(char(scenePack.scene.scene_id),char(pack.sceneIds(k)))&& ...
            strcmpi(sha256_bytes(getByteStreamFromArray(scenePack)),char(idx.scene_digests(k))), ...
            'TEST48:SceneDigest','Shared scene digest/order mismatch at %d.',k);
        id=char(pack.sceneIds(k)); valid_scene(scenePack.scene,id);
        attemptDir=fullfile(runRoot,id,'attempt_01'); assert_short(attemptDir);
        paths=struct('attempt',fullfile(attemptDir,'attempt_started.marker'), ...
            'plant',fullfile(attemptDir,'first_plant_step.marker'), ...
            'run_start',fullfile(attemptDir,'run_start.mat'), ...
            'raw',fullfile(attemptDir,'raw_run.mat'), ...
            'status',fullfile(attemptDir,'run_status.json'), ...
            'failure',fullfile(attemptDir,'FAILURE_NO_RETRY_v1.json'));
        for p=struct2cell(paths).', assert_short(char(p{1})); end
        assert(~isfolder(attemptDir)&&~any(cellfun(@isfile,struct2cell(paths))), ...
            'TEST48:NoRetry','Attempt artifacts exist for %s.',id);
        if ~isfolder(attemptDir), mkdir(attemptDir); end
        started=utc_now(); scene=scenePack.scene; sceneMeta=scenePack.metadata; spec=scenePack.spec;
        cfg=snap.cfg; opts=snap.opts;
        if strcmp(methodId,'B_TRACEABLE')
            opts=controller_options_dl1018(cfg,'B');
            assert(isequaln(opts,snap.opts),'TEST48:BReset','Fresh per-scene B constructor differs from frozen opts.');
        end
        opts.r2e_first_plant_step_marker=paths.plant;
        identity=struct('schema','TEST48_RUN_IDENTITY_V1','method_id',methodId,'alias',alias, ...
            'scene_id',id,'scene_digest_sha256',char(idx.scene_digests(k)), ...
            'method_source_manifest_sha256',sha256_file(fullfile(reportDir,'TEST_METHOD_SOURCE_MANIFEST_v1.json')), ...
            'method_cfg_opts_snapshot_sha256',sha256_file(cfgPath),'model_identity',snap.modelIdentity, ...
            'model_mat_sha256',snap.model_sha256,'normalizer_sha256',snap.normalizer_sha256, ...
            'runner_path',[mfilename('fullpath') '.m'],'runner_sha256',sha256_file([mfilename('fullpath') '.m']), ...
            'parent_release_sha256',sha256_file(fullfile(reportDir,'LOCKED_TEST48_PARENT_RELEASE_v1.json')), ...
            'input_index_sha256',sha256_file(indexPath),'initial_weight_identity',initial_weight_identity(snap), ...
            'which_bindings',whichBindings, ...
            'machine_info',machine,'method_block_order',ix,'thread_argument','-singleCompThread', ...
            'TEST_accessed',true,'plant_calls',1,'training_steps',0,'optimizer_steps',0, ...
            'parameter_or_seed_search',false,'started_utc',started);
        meta=struct('schema','TEST48_RUN_START_METADATA_V1','method_id',methodId,'alias',alias, ...
            'scene_id',id,'candidate',candidate,'collector_tag',collector_tag(methodContract,methodId), ...
            'batch_index',k,'batch_total',48,'controller_constructor',char(contract.method_order(ix).source), ...
            'coordinate_mask',field_or_empty(snap.opts,'position_coordinate_mask'), ...
            'modelIdentity',snap.modelIdentity,'scene_digest_sha256',char(idx.scene_digests(k)), ...
            'method_source_manifest_sha256',identity.method_source_manifest_sha256, ...
            'method_cfg_opts_snapshot_sha256',identity.method_cfg_opts_snapshot_sha256, ...
            'input_index_sha256',identity.input_index_sha256,'parent_release_sha256',identity.parent_release_sha256, ...
            'which_bindings',whichBindings, ...
            'machine_info',machine,'method_block_order',ix,'thread_argument','-singleCompThread', ...
            'attempt_started_marker_path',paths.attempt,'first_plant_step_marker_path',paths.plant, ...
            'raw_path',paths.raw,'run_status_path',paths.status,'plant_calls_before_invocation',0, ...
            'TEST_accessed',true,'training_steps',0,'optimizer_steps',0,'created_utc',started);
        save(paths.run_start,'scene','sceneMeta','spec','cfg','opts','meta','-v7.3');
        write_text_new(paths.attempt,sprintf('ABOUT_TO_CALL_EPISODE\nTEST_accessed=true\n%s\n',started));
        status=struct('schema','TEST48_RUN_STATUS_V1','status','RUNNING_PREPLANT', ...
            'method_id',methodId,'alias',alias,'scene_id',id,'batch_index',k, ...
            'TEST_accessed',true,'plant_calls',0,'training_steps',0,'optimizer_steps',0, ...
            'raw_path',paths.raw,'run_start_path',paths.run_start, ...
            'attempt_started_marker_path',paths.attempt,'first_plant_step_marker_path',paths.plant, ...
            'started_utc',started,'method_source_manifest_sha256',identity.method_source_manifest_sha256, ...
            'method_cfg_opts_snapshot_sha256',identity.method_cfg_opts_snapshot_sha256, ...
            'parent_release_sha256',identity.parent_release_sha256,'input_index_sha256',identity.input_index_sha256);
        write_json_new(paths.status,status);
        runIdentity=identity;
        try
            clear run_episode_dl1018 run_dl1018_closed_loop delayed_prediction_step_candidate;
            log=run_episode_dl1018(scene,collector_tag(methodContract,methodId),cfg,opts,paths.raw);
            assert(isfile(paths.raw)&&isfile(paths.plant),'TEST48:PlantEvidence','Returned episode lacks raw/first-Plant marker.');
            save(paths.raw,'sceneMeta','spec','runIdentity','-append');
        catch ME
            plantStartedUnrecorded=double(isfile(paths.plant));
            fail=struct('schema','TEST48_SCENE_FAILURE_V1','status','FAILED_NO_RETRY', ...
                'method_id',methodId,'scene_id',id,'batch_index',k,'identifier',ME.identifier, ...
                'message',ME.message,'plant_start_confirmed',isfile(paths.plant), ...
                'partial_raw_preserved',isfile(paths.raw),'partial_raw_sha256',file_sha_if_exists(paths.raw), ...
                'TEST_accessed',true,'failed_utc',utc_now());
            write_json_new(paths.failure,fail); status.status='FAILED_NO_RETRY'; status.failure=fail;
            status.plant_calls=double(isfile(paths.plant)); status.updated_utc=utc_now(); write_json_replace(paths.status,status);
            rethrow(ME);
        end
        plantStartedUnrecorded=double(isfile(paths.plant));
        complete=isfield(log,'status')&&strcmpi(char(log.status),'STABLE')&& ...
            isfield(log,'time')&&numel(log.time)==20001&&isfield(log,'transition_time')&& ...
            numel(log.transition_time)==20000&&isfield(log,'last_transition')&&double(log.last_transition)==20000&& ...
            all(isfinite(log.state(:)))&&all(isfinite(log.reference.position(:)));
        assert(complete,'TEST48:IncompleteRun','Raw episode is incomplete/nonfinite for %s; preserve and stop.',id);
        runIdentity=identity; runIdentity.pre_identity_append_sha256=sha256_file(paths.raw);
        runIdentity.run_start_sha256=sha256_file(paths.run_start);
        runIdentity.first_plant_step_marker_sha256=sha256_file(paths.plant);
        save(paths.raw,'runIdentity','-append'); rawSha=sha256_file(paths.raw);
        status.status='RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT'; status.plant_calls=1;
        status.last_transition=double(log.last_transition); status.transition_count=numel(log.transition_time);
        status.state_sample_count=numel(log.time); status.log_status=char(log.status);
        status.raw_sha256=rawSha; status.run_start_sha256=sha256_file(paths.run_start);
        status.attempt_started_marker_sha256=sha256_file(paths.attempt);
        status.first_plant_step_marker_sha256=sha256_file(paths.plant); status.completed_utc=utc_now();
        write_json_replace(paths.status,status);
        rec=struct('batch_index',k,'scene_id',id,'status',status.status, ...
            'raw_path',paths.raw,'raw_sha256',rawSha,'run_start_path',paths.run_start, ...
            'run_start_sha256',status.run_start_sha256,'run_status_path',paths.status, ...
            'run_status_sha256',sha256_file(paths.status),'attempt_started_marker_path',paths.attempt, ...
            'attempt_started_marker_sha256',status.attempt_started_marker_sha256, ...
            'first_plant_step_marker_path',paths.plant,'first_plant_step_marker_sha256',status.first_plant_step_marker_sha256, ...
            'plant_calls',1,'TEST_accessed',true,'created_utc',utc_now());
        records(end+1)=rec; plantStartedUnrecorded=0; batch.records=records; batch.completed_scenes=k; batch.plant_calls=k; batch.updated_utc=utc_now();
        write_json_replace(batchPath,batch);
    end
    batch.status='COMPLETE_RAW_PENDING_PARENT_AUDIT'; batch.completed_scenes=48; batch.plant_calls=48; batch.records=records; batch.completed_utc=utc_now();
    write_json_replace(batchPath,batch);
    body=struct('schema','TEST48_METHOD_BODY_COMPLETE_V1','status','RUN_COMPLETE_RAW_PENDING_PARENT_AUDIT', ...
        'method_id',methodId,'alias',alias,'scene_count',48,'completed_scenes',48, ...
        'scene_ids',{cellstr(string(idx.scene_ids(:)))},'records',records, ...
        'parent_release_sha256',batch.parent_release_sha256,'input_index_sha256',batch.input_index_sha256, ...
        'shared_scenes_mat_sha256',batch.shared_scenes_mat_sha256,'method_cfg_opts_sha256',batch.method_cfg_opts_sha256, ...
        'method_source_manifest_sha256',batch.method_source_manifest_sha256,'runner_sha256',batch.runner_sha256, ...
        'TEST_accessed',true,'plant_calls',48,'training_steps',0,'optimizer_steps',0,'completed_utc',utc_now());
    write_json_new(bodyPath,body);
    out=body;
catch ME
    batch.status='FAILED_STOP_NO_RETRY'; batch.completed_scenes=numel(records); batch.plant_calls=numel(records)+plantStartedUnrecorded;
    batch.records=records; batch.failure=struct('identifier',ME.identifier,'message',ME.message,'failed_utc',utc_now());
    write_json_replace(batchPath,batch); rethrow(ME);
end
end

function methodContract=read_method_contract(m)
if isempty(char(m.run_contract_path))
    assert(startsWith(char(m.method_id),'CORRECTED_')&&isfile(char(m.cfg_opts_snapshot_path)), ...
        'TEST48:MissingMethodContract','Only the two historical corrected methods may use their locked run_start metadata.');
    old=load(char(m.cfg_opts_snapshot_path),'meta');
    assert(isfield(old,'meta')&&isstruct(old.meta)&&isfield(old.meta,'method_id')&&~isempty(old.meta.method_id), ...
        'TEST48:HistoricalRunStartMetadata','Historical corrected run_start lacks its actual meta.method_id.');
    actual=char(old.meta.method_id);
    if strcmp(char(m.method_id),'CORRECTED_DSSM14_G12_R32')
        expected='DSSM14_G12_R32';
    else
        expected='NEW_KAN14_G12_R32';
    end
    assert(strcmp(actual,expected),'TEST48:HistoricalMethodId','Historical run_start method id differs from the locked identity.');
    methodContract=struct('candidate',actual,'collector_tag',actual);
    return
end
assert(isfile(char(m.run_contract_path))&&strcmpi(sha256_file(char(m.run_contract_path)),char(m.run_contract_sha256)), ...
    'TEST48:MethodContract','Locked method run contract missing or changed.');
methodContract=jsondecode(fileread(char(m.run_contract_path)));
end
function c=method_candidate(contract,methodId)
if isfield(contract,'candidate')&&~isempty(contract.candidate), c=char(contract.candidate);
elseif isfield(contract,'method')&&~isempty(contract.method), c=char(contract.method);
else, c=char(methodId); end
end
function c=collector_tag(contract,methodId)
if isfield(contract,'collector_tag')&&~isempty(contract.collector_tag), c=char(contract.collector_tag); else, c=char(methodId); end
end
function w=initial_weight_identity(snap)
w='';
if isstruct(snap.modelIdentity)&&isfield(snap.modelIdentity,'W0_sha256'), w=char(snap.modelIdentity.W0_sha256); end
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
seen=containers.Map('KeyType','char','ValueType','char'); refs=m.source_refs;
for k=1:numel(refs)
    p=char(refs(k).path); [~,name,ext]=fileparts(p); if ~strcmpi(ext,'.m'), continue; end
    if isKey(seen,name)
        assert(same_path(seen(name),p),'TEST48:AmbiguousSource','Two locked .m sources share basename %s.',name);
        continue
    end
    seen(name)=p; first=which(name);
    assert(~isempty(first)&&same_path(first,p),'TEST48:WhichBinding','%s resolved to another source.',name);
    allPaths=which(name,'-all');
    if ischar(allPaths), allPaths=cellstr(allPaths); elseif isstring(allPaths), allPaths=cellstr(allPaths); end
    if isempty(allPaths), allPaths={first}; end
    bindings(end+1)=struct('function_name',name,'expected_path',p, ...
        'resolved_first_path',first,'which_all_paths',{allPaths}); %#ok<AGROW>
end
for name={'run_episode_dl1018','run_dl1018_closed_loop'}
    ref=find_function_ref(m,name{1});
    assert(isKey(seen,name{1})&&same_path(seen(name{1}),char(ref.path)), ...
        'TEST48:RequiredFunction','Required wrapper/core source is not bound: %s.',name{1});
end
wrapperHandle=functions(@run_episode_dl1018); coreHandle=functions(@run_dl1018_closed_loop);
wrapperRef=find_function_ref(m,'run_episode_dl1018'); coreRef=find_function_ref(m,'run_dl1018_closed_loop');
assert(same_path(wrapperHandle.file,char(wrapperRef.path))&&same_path(coreHandle.file,char(coreRef.path)), ...
    'TEST48:FunctionHandle','Wrapper/core function handles differ from frozen source paths.');
end
function ref=find_function_ref(m,name)
ref=find_function_ref_optional(m,name); assert(~isempty(ref),'TEST48:FunctionRef','Locked method source does not include %s.',name);
end
function ref=find_function_ref_optional(m,name)
ref=[]; refs=m.source_refs;
for k=1:numel(refs)
    [~,n,e]=fileparts(char(refs(k).path));
    if strcmpi([n e],[name '.m'])
        if isempty(ref), ref=refs(k); else, assert(same_path(char(ref.path),char(refs(k).path)), ...
                'TEST48:AmbiguousSource','Multiple locked copies of %s have different paths.',name); end
    end
end
end

function pack=call_generator(root,generatorPath,id)
restoredefaultpath;
runtime=fullfile(root,'matlab','runtime'); addpath(runtime,'-begin'); addpath(fileparts(generatorPath),'-begin');
clear make_scenes_dl1018 init_dl1018; rehash;
assert(same_path(which('make_scenes_dl1018'),generatorPath),'TEST48:GeneratorPath','Scene generator path mismatch.');
initPath=fullfile(root,'matlab','runtime','init_dl1018.m');
assert(same_path(which('init_dl1018'),initPath),'TEST48:GeneratorInitPath','Generator initializer path mismatch.');
raw=make_scenes_dl1018('GET',root,id);
assert(all(isfield(raw,{'scene','metadata','spec'})),'TEST48:GeneratorSchema','GET result lacks scene/metadata/spec.');
pack=struct('scene',raw.scene,'metadata',raw.metadata,'spec',raw.spec);
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
    'TEST48:SceneSchema','Scene schema/time dimensions differ for %s.',id);
numeric={scene.time,scene.initial_state,scene.environment_wind_I,scene.reference.position, ...
    scene.reference.velocity,scene.reference.acceleration,scene.reference.yaw,scene.reference.yaw_rate, ...
    scene.reference.yaw_acceleration,scene.arms.command,scene.arms.rhoDot_hat,scene.arms.rhoDot_true, ...
    scene.arms.rho_hat,scene.arms.rho_true};
for k=1:numel(numeric), assert(all(isfinite(double(numeric{k}(:)))),'TEST48:SceneFinite','Nonfinite scene field for %s.',id); end
assert(all(ismember(unique(scene.arms.command(:)),[-1 0 1]))&&all(scene.arms.rho_true(:)>=.15-1e-12)&& ...
    all(scene.arms.rho_true(:)<=.25+1e-12),'TEST48:SceneActuation','Arm command/morphology contract failed for %s.',id);
end
function scene=normalize_scene_id(scene,id)
if isstruct(scene)&&isfield(scene,'scene_id')&&strcmp(char(scene.scene_id),[id '_ACC_FIX_V1'])
    scene.scene_id=id;
end
assert(isstruct(scene)&&isfield(scene,'scene_id')&&strcmp(char(scene.scene_id),id), ...
    'TEST48:Alias','Only the explicitly allowed ACC_FIX_V1 scene alias may be normalized.');
end
function pack=normalize_pack_alias(pack,id)
pack.scene=normalize_scene_id(pack.scene,id);
for name={'metadata','spec'}
    key=name{1}; pack.(key)=replace_alias_value(pack.(key),id);
end
end
function value=replace_alias_value(value,id)
alias=[id '_ACC_FIX_V1'];
if ischar(value)
    if isrow(value)&&strcmp(value,alias), value=id; end
elseif isstring(value)
    value(value==string(alias))=string(id);
elseif isstruct(value)
    names=fieldnames(value);
    for i=1:numel(value), for k=1:numel(names), value(i).(names{k})=replace_alias_value(value(i).(names{k}),id); end, end
elseif iscell(value)
    for k=1:numel(value), value{k}=replace_alias_value(value{k},id); end
elseif istable(value)
    for k=1:width(value), name=value.Properties.VariableNames{k}; value.(name)=replace_alias_value(value.(name),id); end
end
end
function [current,note]=remove_current_scene_contract_note(current,peer,id,relation)
field='reference_contract_id'; expected='DL1018_SCENE_REF_FIG8_A2_V2';
assert(isstruct(current)&&isfield(current,field)&&~isfield(peer,field)&&strcmp(char(current.(field)),expected), ...
    'TEST48:ReferenceContractNote','Expected only the current scene to carry the exact documented reference_contract_id.');
note=struct('scene_id',id,'relation',relation,'field_path',['scene.' field], ...
    'historical_field_absent',true,'current_value',expected);
current=rmfield(current,field);
end
function [current,note]=remove_current_pack_contract_note(current,peer,id)
field='reference_contract_id'; expected='DL1018_SCENE_REF_FIG8_A2_V2'; parts={'scene','metadata'};
note=repmat(struct('scene_id','','relation','','field_path','','historical_field_absent',false,'current_value',''),0,1);
for k=1:numel(parts)
    part=parts{k}; a=current.(part); b=peer.(part);
    assert(isstruct(a)&&isstruct(b)&&isfield(a,field)&&~isfield(b,field)&&strcmp(char(a.(field)),expected), ...
        'TEST48:ReferenceContractNote','Expected only the current %s to carry the exact documented reference_contract_id.',part);
    note(end+1)=struct('scene_id',id,'relation','current_vs_corrected_fixed', ...
        'field_path',[part '.' field],'historical_field_absent',true,'current_value',expected); %#ok<AGROW>
    current.(part)=rmfield(a,field);
end
end

function [maxAbs,bitEqual]=compare_pack(a,b,where)
[d1,e1]=compare_tree(a.scene,b.scene,[where '.scene']);
[d2,e2]=compare_tree(a.metadata,b.metadata,[where '.metadata']);
[d3,e3]=compare_tree(a.spec,b.spec,[where '.spec']);
maxAbs=max([d1 d2 d3]); bitEqual=e1&&e2&&e3;
end
function rows=fieldwise_compare_pack(a,b,id,relation)
rows=empty_field_audits();
for part={'scene','metadata','spec'}
    name=part{1}; rows=[rows;fieldwise_compare(a.(name),b.(name),id,relation,name)]; %#ok<AGROW>
end
end
function rows=fieldwise_compare(a,b,id,relation,path)
rows=empty_field_audits();
if isstruct(a)
    assert(isstruct(b)&&isequal(size(a),size(b))&&isequal(sort(fieldnames(a)),sort(fieldnames(b))), ...
        'TEST48:CompareStruct','Struct schema differs at %s.',path);
    names=fieldnames(a);
    for i=1:numel(a), for k=1:numel(names)
        rows=[rows;fieldwise_compare(a(i).(names{k}),b(i).(names{k}),id,relation,[path '.' names{k}])]; %#ok<AGROW>
    end, end
elseif iscell(a)
    assert(iscell(b)&&isequal(size(a),size(b)),'TEST48:CompareCell','Cell shape differs at %s.',path);
    for k=1:numel(a), rows=[rows;fieldwise_compare(a{k},b{k},id,relation,sprintf('%s{%d}',path,k))]; %#ok<AGROW>
    end
elseif istable(a)
    assert(istable(b)&&height(a)==height(b)&&isequal(a.Properties.VariableNames,b.Properties.VariableNames), ...
        'TEST48:CompareTable','Table schema differs at %s.',path);
    for k=1:width(a), name=a.Properties.VariableNames{k}; rows=[rows;fieldwise_compare(a.(name),b.(name),id,relation,[path '.' name])]; %#ok<AGROW>
    end
else
    bitEqual=isequaln(a,b); maxAbs=0;
    if isnumeric(a)||islogical(a)
        assert((isnumeric(b)||islogical(b))&&isequal(size(a),size(b)), ...
            'TEST48:CompareShape','Numeric field shape/type mismatch at %s.',path);
        if contains(path,'.arms.command')||islogical(a)||isinteger(a)
            assert(bitEqual,'TEST48:StrictField','Discrete field differs at %s.',path);
        else
            af=double(a(:)); bf=double(b(:)); finiteA=isfinite(af); finiteB=isfinite(bf);
            if any(~finiteA)||any(~finiteB)
                assert(contains(path,'.metadata')&&isequal(finiteA,finiteB)&& ...
                    all(~isnan(af))&&all(~isnan(bf))&&isequaln(af(~finiteA),bf(~finiteB)), ...
                    'TEST48:MetadataNonfinite','Only exactly matching non-NaN metadata infinities may pass at %s.',path);
            end
            finiteMask=finiteA&finiteB;
            if any(finiteMask), maxAbs=max(abs(af(finiteMask)-bf(finiteMask))); end
            assert(maxAbs<=1e-12,'TEST48:CompareTolerance','Field differs by %.17g at %s.',maxAbs,path);
        end
    else
        assert(bitEqual,'TEST48:CompareExact','Non-numeric scene field differs at %s.',path);
    end
    rows=field_audit_row(id,relation,path,a,b,maxAbs,bitEqual);
end
end
function rows=collect_array_inventory(value,id,path)
rows=empty_inventory_rows();
if isstruct(value)
    names=fieldnames(value);
    for i=1:numel(value), for k=1:numel(names)
        rows=[rows;collect_array_inventory(value(i).(names{k}),id,[path '.' names{k}])]; %#ok<AGROW>
    end, end
elseif iscell(value)
    for k=1:numel(value), rows=[rows;collect_array_inventory(value{k},id,sprintf('%s{%d}',path,k))]; %#ok<AGROW>
    end
elseif istable(value)
    for k=1:width(value), name=value.Properties.VariableNames{k}; rows=[rows;collect_array_inventory(value.(name),id,[path '.' name])]; %#ok<AGROW>
    end
else
    rows=struct('scene_id',id,'field_path',path,'shape',mat2str(size(value)), ...
        'matlab_class',class(value),'array_sha256',hash_array_value(value));
end
end
function row=field_audit_row(id,relation,path,a,b,maxAbs,bitEqual)
row=struct('scene_id',id,'relation',relation,'field_path',path, ...
    'shape_a',mat2str(size(a)),'class_a',class(a),'sha256_a',hash_array_value(a), ...
    'shape_b',mat2str(size(b)),'class_b',class(b),'sha256_b',hash_array_value(b), ...
    'max_abs_diff',maxAbs,'bit_equal',logical(bitEqual));
end
function rows=empty_field_audits()
rows=repmat(struct('scene_id','','relation','','field_path','','shape_a','','class_a','','sha256_a','', ...
    'shape_b','','class_b','','sha256_b','','max_abs_diff',0,'bit_equal',false),0,1);
end
function rows=empty_inventory_rows()
rows=repmat(struct('scene_id','','field_path','','shape','','matlab_class','','array_sha256',''),0,1);
end
function h=hash_array_value(value)
header=uint8(unicode2native([class(value) '|' mat2str(size(value)) '|'],'UTF-8'));
if islogical(value)
    raw=uint8(value(:));
elseif isnumeric(value)&&isreal(value)
    raw=typecast(value(:),'uint8');
elseif ischar(value)
    raw=typecast(uint16(value(:)),'uint8');
else
    raw=uint8(getByteStreamFromArray(value));
end
h=sha256_bytes([header(:);uint8(raw(:))]);
end
function [maxAbs,bitEqual]=compare_tree(a,b,where)
maxAbs=0; bitEqual=isequaln(a,b); if bitEqual, return; end
if isnumeric(a)||islogical(a)
    assert((isnumeric(b)||islogical(b))&&isequal(size(a),size(b)), ...
        'TEST48:CompareShape','Numeric scene field shape/type mismatch at %s.',where);
    if contains(where,'.arms.command')
        assert(isequaln(a,b),'TEST48:CommandStrict','Discrete arm command differs at %s.',where); return
    end
    af=double(a(:)); bf=double(b(:)); finiteA=isfinite(af); finiteB=isfinite(bf);
    if any(~finiteA)||any(~finiteB)
        assert(contains(where,'.metadata')&&isequal(finiteA,finiteB)&& ...
            all(~isnan(af))&&all(~isnan(bf))&&isequaln(af(~finiteA),bf(~finiteB)), ...
            'TEST48:CompareNonfinite','Only exactly matching non-NaN metadata infinities may pass at %s.',where);
    end
    finiteMask=finiteA&finiteB;
    if any(finiteMask), maxAbs=max(abs(af(finiteMask)-bf(finiteMask))); end
    assert(maxAbs<=1e-12,'TEST48:CompareTolerance','Scene field differs by %.17g at %s.',maxAbs,where); return
elseif isstruct(a)
    assert(isstruct(b)&&isequal(size(a),size(b))&&isequal(sort(fieldnames(a)),sort(fieldnames(b))), ...
        'TEST48:CompareStruct','Struct schema differs at %s.',where);
    names=fieldnames(a); for i=1:numel(a), for k=1:numel(names)
        [d,e]=compare_tree(a(i).(names{k}),b(i).(names{k}),[where '.' names{k}]); maxAbs=max(maxAbs,d); bitEqual=bitEqual&&e;
    end, end
elseif istable(a)
    assert(istable(b)&&height(a)==height(b)&&isequal(a.Properties.VariableNames,b.Properties.VariableNames), ...
        'TEST48:CompareTable','Table schema differs at %s.',where);
    for k=1:width(a), [d,e]=compare_tree(a.(k),b.(k),[where '.' a.Properties.VariableNames{k}]); maxAbs=max(maxAbs,d); bitEqual=bitEqual&&e; end
elseif iscell(a)
    assert(iscell(b)&&isequal(size(a),size(b)),'TEST48:CompareCell','Cell shape differs at %s.',where);
    for k=1:numel(a), [d,e]=compare_tree(a{k},b{k},sprintf('%s{%d}',where,k)); maxAbs=max(maxAbs,d); bitEqual=bitEqual&&e; end
else
    error('TEST48:CompareExact','Non-numeric scene field differs at %s.',where);
end
end

function assert_budget(outputRoot,reportRoot,contract,remainingSceneCalls,remainingProcesses)
limits=contract.limits; deadline=datetime(char(limits.hard_deadline_utc),'InputFormat',"yyyy-MM-dd'T'HH:mm:ss'Z'",'TimeZone','UTC');
reserve=double(remainingSceneCalls)*double(limits.per_scene_output_reserve_bytes);
drive=java.io.File(outputRoot); free=double(drive.getUsableSpace());
assert(free-reserve>=double(limits.minimum_free_bytes_after_reserve), ...
    'TEST48:DiskReserve','Reserve-adjusted free-space floor failed; do not delete data.');
assert(double(limits.prior_created_bytes)+directory_bytes(outputRoot)+directory_bytes(reportRoot)+reserve<=double(limits.max_output_bytes), ...
    'TEST48:OutputCap','Cycle-wide creation baseline plus TEST output/reserve exceeds the cap.');
required=double(remainingSceneCalls)*double(limits.per_scene_seconds_guard)+ ...
    double(remainingProcesses)*double(limits.process_exit_buffer_seconds);
assert(seconds(deadline-datetime('now','TimeZone','UTC'))>=required, ...
    'TEST48:Deadline','Conservative remaining-time guard failed.');
end
function n=directory_bytes(path)
n=0; if ~isfolder(path), return; end; d=dir(fullfile(path,'**','*'));
for k=1:numel(d), if ~d(k).isdir, n=n+double(d(k).bytes); end, end
end
function row=scene_row(lock,id)
ix=find(strcmp(string({lock.scenes.scene_id}),string(id)));
assert(numel(ix)==1,'TEST48:SceneLock','Development scene is absent/duplicated: %s.',id); row=lock.scenes(ix);
end
function method=find_method(manifest,id)
ix=find(strcmp({manifest.methods.method_id},id)); assert(numel(ix)==1,'TEST48:MethodManifest','Method missing from source manifest.'); method=manifest.methods(ix);
end
function ref=find_shared(manifest,role)
ix=find(strcmp({manifest.shared_source_refs.role},role)); assert(numel(ix)==1,'TEST48:SharedRef','Shared source role is absent/duplicated: %s.',role); ref=manifest.shared_source_refs(ix);
end
function ref=find_model_ref(method,role)
ix=find(strcmp({method.model_refs.role},role)); assert(numel(ix)==1,'TEST48:ModelRef','Model role is absent/duplicated: %s.',role); ref=method.model_refs(ix);
end
function v=field_or_empty(s,name)
if isstruct(s)&&isfield(s,name), v=s.(name); else, v=[]; end
end
function h=sha256_tree(path)
files=dir(fullfile(path,'**','*.m')); [~,ord]=sort(string({files.name})); files=files(ord); parts=cell(numel(files),1);
for k=1:numel(files), p=fullfile(files(k).folder,files(k).name); parts{k}=[p ':' sha256_file(p) newline]; end
h=sha256_bytes(uint8(unicode2native([parts{:}],'UTF-8')));
end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0,'TEST48:Read','Cannot read %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(typecast(b(:),'int8')); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function p=repo_path(root,path)
p=char(path);
isWindowsRoot=numel(p)>=3&&p(2)==':'&&(p(3)=='/'||p(3)=='\');
if ~isWindowsRoot&&~startsWith(p,filesep)&&~startsWith(p,'\\')
    p=fullfile(root,p);
end
end
function h=sha256_bytes(bytes)
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(typecast(uint8(bytes(:)),'int8'));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=hash_normalizer_arrays(model)
md=java.security.MessageDigest.getInstance('SHA-256');
for name={'input_mu','input_sigma'}
    field=name{1}; a=reshape(double(model.(field)),1,[]);
    assert(numel(a)==14&&all(isfinite(a)),'TEST48:NormalizerShape','Invalid model normalizer field %s.',field);
    header=[field char(0) '((1, 14), ''float64'')' char(0)];
    md.update(typecast(uint8(unicode2native(header,'UTF-8')),'int8')); md.update(typecast(a(:),'int8'));
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function info=machine_info()
info=struct('matlab_version',version,'matlab_release',version('-release'),'computer',computer, ...
    'thread_argument','-singleCompThread','cpu_core_count',[],'memory_snapshot',struct());
try, info.cpu_core_count=feature('numcores'); catch, end
try, info.memory_snapshot=memory; catch, end
end
function verify_file(path,expected)
assert(isfile(path),'TEST48:MissingFile','Missing frozen file: %s.',path);
assert(strcmpi(sha256_file(path),expected),'TEST48:SHA','SHA mismatch: %s.',path);
end
function t=utc_now()
t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end
function assert_short(path)
p=char(java.io.File(path).getCanonicalPath()); assert(numel(p)<240,'TEST48:PathLength','New path is too long (%d): %s.',numel(p),p);
end
function tf=same_path(a,b)
tf=strcmpi(char(java.io.File(a).getCanonicalPath()),char(java.io.File(b).getCanonicalPath()));
end
function write_json_new(path,value)
assert(~isfile(path),'TEST48:NoOverwrite','Refusing to overwrite %s.',path);
folder=fileparts(path); if ~isfolder(folder), mkdir(folder); end
fid=fopen(path,'w'); assert(fid>=0,'TEST48:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(value) newline],'char');
end
function write_json_replace(path,value)
fid=fopen(path,'w'); assert(fid>=0,'TEST48:Write','Cannot update %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(value) newline],'char');
end
function write_text_new(path,value)
assert(~isfile(path),'TEST48:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'TEST48:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,value,'char');
end
function records=empty_records()
records=struct('batch_index',{},'scene_id',{},'status',{},'raw_path',{},'raw_sha256',{}, ...
    'run_start_path',{},'run_start_sha256',{},'run_status_path',{},'run_status_sha256',{}, ...
    'attempt_started_marker_path',{},'attempt_started_marker_sha256',{}, ...
    'first_plant_step_marker_path',{},'first_plant_step_marker_sha256',{},'plant_calls',{},'TEST_accessed',{},'created_utc',{});
end
function h=file_sha_if_exists(path)
if isfile(path), h=sha256_file(path); else, h=''; end
end
