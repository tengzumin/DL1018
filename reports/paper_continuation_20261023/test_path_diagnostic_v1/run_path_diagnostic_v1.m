function result=run_path_diagnostic_v1()
reportDir=fileparts(mfilename('fullpath'));
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
contractPath=fullfile(root,'experiments','c5_test48_v4','TEST48_RUN_CONTRACT_v4.json');
manifestPath=fullfile(root,'reports','paper_continuation_20261023','test_entry_v4','TEST_METHOD_SOURCE_MANIFEST_v4.json');
provenancePath=fullfile(reportDir,'EXTRACTED_SOURCE_MANIFEST_v1.json');
sourcePath=fullfile(root,'experiments','c5_test48_v4','test48_entry_v4.m');
resultPath=fullfile(reportDir,'PATH_DIAGNOSTIC_RESULT_v1.json');
failurePath=fullfile(reportDir,'PATH_DIAGNOSTIC_FAILURE_v1.json');
assert(~isfile(resultPath)&&~isfile(failurePath),'PATHDIAG:NoRetry','Diagnostic output exists; preserve and do not rerun.');
try
    contract=jsondecode(fileread(contractPath));
    manifest=jsondecode(fileread(manifestPath));
    provenance=jsondecode(fileread(provenancePath));
    assert(strcmpi(sha256_file(sourcePath),char(provenance.v4_entry_sha256))&& ...
        strcmpi(sha256_file(sourcePath),char(contract.entry_sha256)), ...
        'PATHDIAG:EntrySHA','Frozen v4 entry SHA does not match provenance/contract.');
    assert(strcmpi(sha256_file(manifestPath),char(contract.method_source_manifest_sha256))&& ...
        strcmpi(sha256_file(contractPath),char(provenance.contract_sha256)), ...
        'PATHDIAG:LockSHA','Contract/manifest SHA changed.');
    restoredefaultpath;
    addpath(fullfile(root,'matlab','runtime'),'-begin');
    clear init_dl1018;
    rehash;
    initPath=fullfile(root,'matlab','runtime','init_dl1018.m');
    initWhichBefore=which('init_dl1018');
    [cfg,~,resolvedRoot]=init_dl1018();
    initWhichAfter=which('init_dl1018');
    methods=manifest.methods;
    emptyBindings=struct('function_name',{},'expected_path',{},'resolved_first_path',{},'which_all_paths',{});
    emptyRows=empty_path_records();
    methodTemplate=struct('order',0,'method_id','','alias','','snapshot_status','','snapshot_error','', ...
        'snapshot_summary',struct(),'preflight_status','','preflight_error','','preflight_record',struct(), ...
        'method_bind_attempt_status','','method_bind_error','','method_bindings',{emptyBindings}, ...
        'global_diagnostic_error','','global_platform_rows',{emptyRows},'method_core_rows',{emptyRows});
    methodRows=repmat(methodTemplate,numel(methods),1);
    for k=1:numel(methods)
        method=methods(k);
        row=methodTemplate;
        row.order=k; row.method_id=char(method.method_id); row.alias=char(method.alias);
        snap=[];
        try
            snap=build_method_snapshot(root,method,cfg);
            row.snapshot_status='PASS';
            row.snapshot_summary=struct('method_id',snap.method_id,'alias',snap.alias, ...
                'cfg_value_sha256',sha256_bytes(getByteStreamFromArray(snap.cfg)), ...
                'opts_value_sha256',sha256_bytes(getByteStreamFromArray(snap.opts)), ...
                'model_identity',snap.modelIdentity,'model_mat_sha256',snap.model_sha256, ...
                'normalizer_sha256',snap.normalizer_sha256,'runtime_tree_sha256',snap.runtime_tree_sha256, ...
                'cfg_opts_source_sha256',snap.cfg_opts_source_sha256, ...
                'template_run_start_sha256',snap.template_run_start_sha256);
        catch ME
            row.snapshot_status='ERROR';
            row.snapshot_error=struct('identifier',ME.identifier,'message',ME.message);
        end
        methodBindings=emptyBindings;
        if strcmp(row.snapshot_status,'PASS')
            try
                preflight=method_preflight_summary(root,method,snap);
                row.preflight_status='PASS';
                row.preflight_record=preflight;
                methodBindings=preflight.which_bindings;
            catch ME
                row.preflight_status='ERROR';
                row.preflight_error=struct('identifier',ME.identifier,'message',ME.message);
            end
        else
            row.preflight_status='SKIPPED_SNAPSHOT_ERROR';
        end
        if isempty(methodBindings)
            try
                methodBindings=bind_method_path(root,method);
                row.method_bind_attempt_status='PASS_FALLBACK_BIND_ONLY';
            catch ME
                row.method_bind_attempt_status='ERROR';
                row.method_bind_error=struct('identifier',ME.identifier,'message',ME.message);
            end
        else
            row.method_bind_attempt_status='RECORDED_BY_PREFLIGHT';
        end
        row.method_bindings=methodBindings;
        try
            diag=verify_global_platform_which_diagnostic(root,manifest,method,methodBindings);
            row.global_platform_rows=diag.global_platform_rows;
            row.method_core_rows=diag.method_core_rows;
        catch ME
            row.global_diagnostic_error=struct('identifier',ME.identifier,'message',ME.message);
        end
        methodRows(k)=row;
    end
    allGlobal=empty_path_records();
    for k=1:numel(methodRows)
        if ~isempty(methodRows(k).global_platform_rows)
            allGlobal=[allGlobal methodRows(k).global_platform_rows]; %#ok<AGROW>
        end
    end
    mismatchCount=sum(~[allGlobal.same_path]);
    result=struct('schema','TEST48_V4_PATH_DIAGNOSTIC_V1','status','DIAGNOSTIC_COMPLETE', ...
        'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
        'root',root,'matlab_version',version,'matlab_release',version('-release'),'computer',computer, ...
        'initializer_expected_path',initPath,'initializer_which_before',initWhichBefore, ...
        'initializer_which_after',initWhichAfter,'resolved_project_root',resolvedRoot, ...
        'method_order',{cellstr(string({methods.method_id}))},'method_count',numel(methodRows), ...
        'global_ref_count_per_method',numel(allGlobal)/max(1,numel(methodRows)), ...
        'global_rows_total',numel(allGlobal),'global_same_path_mismatch_rows',mismatchCount, ...
        'method_rows',methodRows,'global_platform_rows_all_methods',allGlobal, ...
        'source_provenance',provenance,'source_provenance_file_sha256',sha256_file(provenancePath), ...
        'diagnostic_script_sha256',char(provenance.diagnostic_script_sha256), ...
        'TEST_shared_scene_loaded',false,'TEST_raw_loaded',false,'TEST_outcomes_read',false, ...
        'plant_calls',0,'training_steps',0,'created_utc_completed',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')));
    write_path_json_new(resultPath,result);
catch ME
    failure=struct('schema','TEST48_V4_PATH_DIAGNOSTIC_FAILURE_V1','status','FAILED_DIAGNOSTIC', ...
        'identifier',ME.identifier,'message',ME.message, ...
        'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
        'plant_calls',0,'training_steps',0,'TEST_shared_scene_loaded',false,'TEST_raw_loaded',false);
    if ~isfile(failurePath), write_path_json_new(failurePath,failure); end
    rethrow(ME);
end
end

function rows=empty_path_records()
rows=struct('scope',{},'source_role',{},'reference_raw_path',{},'resolved_repo_path',{}, ...
    'fileparts_name',{},'fileparts_extension',{},'which_actual',{},'which_all_paths',{}, ...
    'which_error',{},'path_add_error',{},'expected_canonical_path',{},'expected_canonical_error',{}, ...
    'which_canonical_path',{},'which_canonical_error',{},'same_path',{},'same_path_error',{}, ...
    'method_binding_recorded_path',{},'method_binding_expected_path',{}, ...
    'method_binding_same_path',{},'method_binding_which_all_paths',{});
end

function diagnostic=verify_global_platform_which_diagnostic(root,manifest,method,methodBindings)
globalRows=empty_path_records();
coreRows=empty_path_records();
refs=manifest.global_platform_refs;
addErrors=containers.Map('KeyType','char','ValueType','char');
for k=1:numel(refs)
    ref=refs(k); if ~any(strcmp(char(ref.role),{'frozen_plant','frozen_runtime'})), continue; end
    p=repo_path(root,char(ref.path)); [~,~,ext]=fileparts(p);
    if strcmpi(ext,'.m')
        try
            addpath(fileparts(p),'-end');
        catch ME
            addErrors(p)=ME.message;
        end
    end
end
rehash;
for k=1:numel(refs)
    ref=refs(k); if ~any(strcmp(char(ref.role),{'frozen_plant','frozen_runtime'})), continue; end
    p=repo_path(root,char(ref.path)); [~,name,ext]=fileparts(p); if ~strcmpi(ext,'.m'), continue; end
    active=''; whichError='';
    try
        active=which(name);
        if isstring(active), active=char(active); end
    catch ME
        whichError=ME.message;
    end
    pathAddError=''; if isKey(addErrors,p), pathAddError=addErrors(p); end
    globalRows(end+1)=make_path_record('global_platform',char(ref.role),char(ref.path),p,name,ext,active, ...
        methodBindings,whichError,pathAddError); %#ok<AGROW>
end
for name={'run_episode_dl1018','run_dl1018_closed_loop'}
    ref=find_function_ref(method,name{1});
    active=''; whichError='';
    try
        active=which(name{1});
        if isstring(active), active=char(active); end
    catch ME
        whichError=ME.message;
    end
    coreRows(end+1)=make_path_record('method_core','method_core',char(ref.path),char(ref.path), ...
        name{1},'.m',active,methodBindings,whichError,''); %#ok<AGROW>
end
diagnostic=struct('global_platform_rows',globalRows,'method_core_rows',coreRows);
end

function row=make_path_record(scope,role,rawPath,resolvedPath,name,extension,active,methodBindings,whichError,pathAddError)
[expectedCanonical,expectedCanonicalError]=canonical_or_error(resolvedPath);
[whichCanonical,whichCanonicalError]=canonical_or_error(active);
same=false; sameError='';
if ~isempty(active)
    try
        same=same_path(active,resolvedPath);
    catch ME
        sameError=ME.message;
    end
end
bindingPath=''; bindingExpected=''; bindingSame=false; bindingAll={};
if isstruct(methodBindings)&&~isempty(methodBindings)
    ix=find(strcmp({methodBindings.function_name},name),1);
    if ~isempty(ix)
        bindingPath=char(methodBindings(ix).resolved_first_path);
        bindingExpected=char(methodBindings(ix).expected_path);
        bindingAll=methodBindings(ix).which_all_paths;
        try
            bindingSame=same_path(bindingPath,resolvedPath);
        catch
            bindingSame=false;
        end
    end
end
whichAll={};
if ~isempty(active)
    try
        allPaths=which(name,'-all');
        if ischar(allPaths)
            if size(allPaths,1)>1, whichAll=cellstr(allPaths); else, whichAll={strtrim(allPaths)}; end
        elseif isstring(allPaths)
            whichAll=cellstr(allPaths(:));
        elseif iscell(allPaths)
            whichAll=allPaths;
        end
    catch
        whichAll={active};
    end
end
row=struct('scope',scope,'source_role',role,'reference_raw_path',rawPath, ...
    'resolved_repo_path',resolvedPath,'fileparts_name',name,'fileparts_extension',extension, ...
    'which_actual',active,'which_all_paths',{whichAll},'which_error',whichError, ...
    'path_add_error',pathAddError,'expected_canonical_path',expectedCanonical, ...
    'expected_canonical_error',expectedCanonicalError,'which_canonical_path',whichCanonical, ...
    'which_canonical_error',whichCanonicalError,'same_path',logical(same), ...
    'same_path_error',sameError,'method_binding_recorded_path',bindingPath, ...
    'method_binding_expected_path',bindingExpected,'method_binding_same_path',logical(bindingSame), ...
    'method_binding_which_all_paths',{bindingAll});
end

function [pathValue,errorValue]=canonical_or_error(path)
pathValue=''; errorValue='';
if isempty(path), return; end
try
    pathValue=char(java.io.File(char(path)).getCanonicalPath());
catch ME
    errorValue=ME.message;
end
end

function write_path_json_new(path,value)
assert(~isfile(path),'PATHDIAG:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'PATHDIAG:Write','Cannot create %s.',path);
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(value) newline],'char');
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


function ref=find_model_ref(method,role)
ix=find(strcmp({method.model_refs.role},role)); assert(numel(ix)==1,'TEST48:ModelRef','Model role is absent/duplicated: %s.',role); ref=method.model_refs(ix);
end

function w=initial_weight_identity(snap)
w='';
if isstruct(snap.modelIdentity)&&isfield(snap.modelIdentity,'W0_sha256'), w=char(snap.modelIdentity.W0_sha256); end
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

function tf=same_path(a,b)
tf=strcmpi(char(java.io.File(a).getCanonicalPath()),char(java.io.File(b).getCanonicalPath()));
end
