function report = offline_smoke_c2_beta()
% Offline-only smoke for the one-line beta-clock candidate. Never calls an episode.
here = fileparts(mfilename('fullpath'));
repoRoot = fileparts(fileparts(here));
lockPath = fullfile(here,'C2_SOURCE_LOCK.json');
assert(isfile(lockPath),'C2:LockMissing','Missing C2 source lock.');
lock = jsondecode(fileread(lockPath));
assert(strcmp(lock.schema,'C2_BETA_CLOCK_ALIGNMENT_SOURCE_LOCK_V1') && ...
    strcmp(lock.state,'PREPARED_NO_PLANT') && ~logical(lock.plant_authorized) && ...
    ~logical(lock.new_closed_loop_authorized) && double(lock.optimizer_steps)==0 && ...
    double(lock.gpu_jobs)==0 && ~logical(lock.test_accessed), ...
    'C2:Scope','C2 source lock does not describe a no-Plant preparation.');
verify_file(lock.taskbook.path,lock.taskbook.sha256);
verify_file(lock.c1_source_lock.path,lock.c1_source_lock.sha256);
verify_file(lock.parent_same_state_quantification.path,lock.parent_same_state_quantification.sha256);
verify_file(lock.offline_smoke.path,lock.offline_smoke.sha256);
c1 = jsondecode(fileread(lock.c1_source_lock.path));
assert(strcmpi(sha256_file(lock.c1_source_lock.path),lock.c1_source_lock.sha256) && ...
    strcmp(c1.schema,'C1_PRIOR_SCALE_SCREEN_V1'),'C2:C1Lock','C1 source lock identity failed.');
for k = 1:numel(lock.unchanged_locked_sources)
    verify_file(lock.unchanged_locked_sources(k).path,lock.unchanged_locked_sources(k).sha256);
end
verify_file(lock.shared_c1_inputs.model_mat_path,lock.shared_c1_inputs.model_mat_sha256);
verify_file(lock.shared_c1_inputs.normalizer_npz_path,lock.shared_c1_inputs.normalizer_npz_sha256);
verify_file(lock.shared_c1_inputs.effective_config_path,lock.shared_c1_inputs.effective_config_sha256);
verify_file(lock.shared_c1_inputs.scene_list_path,lock.shared_c1_inputs.scene_list_sha256);
verify_file(lock.shared_c1_inputs.scene_payload_identity_path,lock.shared_c1_inputs.scene_payload_identity_sha256);

runtimeDir = fullfile(here,'runtime');
candidateCore = fullfile(runtimeDir,'run_dl1018_closed_loop.m');
candidateWrapper = fullfile(runtimeDir,'run_episode_dl1018.m');
verify_file(candidateCore,lock.runtime_change.candidate_core_sha256);
verify_file(candidateWrapper,lock.runtime_change.wrapper_sha256);
verify_file(lock.runtime_change.original_core_path,lock.runtime_change.original_core_sha256);
verify_file(lock.runtime_change.wrapper_original_path,lock.runtime_change.wrapper_sha256);
assert_one_expression_diff(lock.runtime_change.original_core_path,candidateCore, ...
    lock.runtime_change.original_expression,lock.runtime_change.candidate_expression);

initPath = locked_source_path(c1,'init_dl1018.m');
candidateRuntimeSources = locked_source_path(c1,'position_only_search_options.m');
helperRuntimeDir = fileparts(candidateRuntimeSources);
addpath(fileparts(initPath),'-begin');
clear init_dl1018;
rehash;
assert(same_path(which('init_dl1018'),initPath),'C2:InitPath','init_dl1018 resolved outside its frozen source.');
[cfg,~,resolvedRoot] = init_dl1018();
assert(same_path(resolvedRoot,repoRoot),'C2:ProjectRoot','init_dl1018 resolved an unexpected project root.');
addpath(helperRuntimeDir,'-begin');
addpath(runtimeDir,'-begin');
clear run_dl1018_closed_loop run_episode_dl1018 position_only_search_options ...
    position_only_search_head_step controller_options_dl1018 simulation_parameters ...
    controller_parameters arm_mass_properties;
rehash;
assert(same_path(which('run_dl1018_closed_loop'),candidateCore) && ...
    same_path(which('run_episode_dl1018'),candidateWrapper) && ...
    same_path(which('position_only_search_options'),candidateRuntimeSources), ...
    'C2:ResolvedRuntime','A runtime or candidate helper resolved outside its locked path.');

modelPack = load(lock.shared_c1_inputs.model_mat_path,'model');
assert(isfield(modelPack,'model') && isstruct(modelPack.model),'C2:Model','Locked model variable is absent.');
model = modelPack.model;
W0 = double(model.output_W);
assert(isequal(size(W0),[33,3]) && all(isfinite(W0(:))) && ...
    strcmpi(hash_bytes(typecast(W0(:),'uint8')),lock.shared_c1_inputs.w0_output_W_double_f_order_sha256), ...
    'C2:W0','Locked W0 identity failed.');
normalizerHash = hash_normalizer_arrays(model);
assert(strcmpi(normalizerHash,lock.shared_c1_inputs.normalizer_arrays_sha256), ...
    'C2:Normalizer','Loaded model X14 normalizer identity failed.');
assert(strcmp(char(model.model_id),'DSSM14') && double(model.seed)==2026102001 && ...
    double(model.selected_step)==60000 && double(model.input_dim)==14 && ...
    double(model.window)==32 && double(model.context_length)==32, ...
    'C2:ModelIdentity','Unexpected frozen model identity.');

opts = position_only_search_options(cfg,model,'FEATURE',12,1);
p = opts.stage1_position_runtime;
h = p.position_only_search_head;
assert(logical(p.enabled) && logical(p.update_enabled) && ...
    logical(p.command_filter_coordination_v3_5.enabled) && logical(h.enabled) && ...
    strcmpi(char(h.head_type),'FEATURE') && double(h.gamma)==12 && double(h.kappa)==1 && ...
    isequal(double(p.weight),W0) && isequal(double(p.model.output_W),W0) && ...
    isequal(double(h.W0),W0) && double(p.beta_scale)==1, ...
    'C2:CandidateOptions','The candidate is not the fixed original ON1 c=1 contract.');
assert(abs(double(cfg.plant.dt)-0.001)<=1e-12 && ...
    double(cfg.rbf.position.beta_rise_time)==1.8 && ...
    double(cfg.rbf.runtime.position_update_hz)==100, ...
    'C2:Clocks','Unexpected locked Plant / beta / event clock values.');

% Check the two clock formulas at every fixed-step index and at saturation.
dt = double(cfg.plant.dt);
riseTime = double(cfg.rbf.position.beta_rise_time);
k = (1:20000).';
betaOld = min(max(((k-1).*dt)./riseTime,0),1);
betaNew = min(max((k.*dt)./riseTime,0),1);
assert(all(betaNew>=betaOld) && betaNew(1800)==1 && betaOld(1800)<1 && ...
    all(betaNew(1801:end)==betaOld(1801:end)), ...
    'C2:BetaClock','The candidate beta equation or saturation boundary is incorrect.');

% Exercise the frozen pure Head helper on fixed input; no runtime/Plant is called.
headStepPath = locked_source_path(c1,'position_only_search_head_step.m');
assert(same_path(which('position_only_search_head_step'),headStepPath), ...
    'C2:HeadPath','The frozen pure Head helper resolved from an unexpected path.');
phi = linspace(-0.2,0.2,33).';
state = W0;
sEff = [0.17;-0.09;0.04];
eventDt = 0.01;
dmax = [3;3;3];
kSmoke = 250;
bOld = min(max((kSmoke-1)*dt/riseTime,0),1);
bNew = min(max(kSmoke*dt/riseTime,0),1);
[rawOld,appliedOld,stateOld] = position_only_search_head_step( ...
    phi,W0,state,'FEATURE',12,1,sEff,eventDt,bOld,dmax);
[rawNew,appliedNew,stateNew] = position_only_search_head_step( ...
    phi,W0,state,'FEATURE',12,1,sEff,eventDt,bNew,dmax);
expectedRaw = state.'*phi;
expectedClipped = max(min(expectedRaw,dmax),-dmax);
expectedOld = max(min(state+eventDt*(-12*bOld*phi*sEff.'-0.002*state),60),-60);
expectedNew = max(min(state+eventDt*(-12*bNew*phi*sEff.'-0.002*state),60),-60);
headRawError = max(abs([rawOld(:)-expectedRaw(:);rawNew(:)-expectedRaw(:)]));
headAppliedError = max(abs([appliedOld(:)-bOld*expectedClipped(:); ...
    appliedNew(:)-bNew*expectedClipped(:)]));
headUpdateError = max(abs([stateOld(:)-expectedOld(:);stateNew(:)-expectedNew(:)]));
assert(headRawError<=1e-14 && headAppliedError<=1e-14 && headUpdateError<=1e-14 && ...
    isequal(rawOld,rawNew) && norm(stateOld-stateNew,'fro')>0, ...
    'C2:HeadContract','The Head did not produce raw output before the beta-scaled update.');

% Reconstruct fixed-controller nominal properties from frozen source, not cfg.plant.inertia.
Pplant = simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
Pcontroller = controller_parameters(cfg,Pplant,'fixed');
assert(strcmp(Pcontroller.role,'controller') && strcmpi(Pcontroller.morphology_mode,'fixed') && ...
    isscalar(Pcontroller.mass) && isfinite(Pcontroller.mass) && ...
    isequal(size(Pcontroller.inertia),[3,3]) && all(isfinite(Pcontroller.inertia(:))) && ...
    all(eig((Pcontroller.inertia+Pcontroller.inertia.')/2)>0) && ...
    isequal(size(Pcontroller.allocation.C),[4,4]) && all(isfinite(Pcontroller.allocation.C(:))) && ...
    numel(Pcontroller.cog)==3 && all(isfinite(Pcontroller.cog(:))), ...
    'C2:NominalSnapshot','Frozen fixed-controller nominal parameters are invalid.');

analyzer = struct();
analyzer.core = summarize_checkcode(checkcode(candidateCore,'-id'));
analyzer.wrapper = summarize_checkcode(checkcode(candidateWrapper,'-id'));
analyzer.smoke = summarize_checkcode(checkcode([mfilename('fullpath') '.m'],'-id'));

report = struct();
report.status = 'PASS_NO_PLANT_SMOKE';
report.created_utc = char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
report.source_lock_sha256 = sha256_file(lockPath);
report.c1_source_lock_sha256 = sha256_file(lock.c1_source_lock.path);
report.candidate_core_sha256 = sha256_file(candidateCore);
report.candidate_wrapper_sha256 = sha256_file(candidateWrapper);
report.taskbook_sha256 = lock.taskbook.sha256;
report.parent_same_state_quantification_sha256 = lock.parent_same_state_quantification.sha256;
quant = jsondecode(fileread(lock.parent_same_state_quantification.path));
assert(strcmp(quant.status,'PASS_CONFIRMED_CLOCK_DIFFERENCE_ALL12') && numel(quant.rows)==12 && ...
    all([quant.rows.valid_events]==1968) && all([quant.rows.different_beta_events]==148), ...
    'C2:ParentQuantification','The independently frozen 12-scene beta summary failed its identity gate.');
report.parent_quantification_summary = struct('scene_count',numel(quant.rows), ...
    'valid_events_per_scene',1968,'different_beta_events_per_scene',148, ...
    'max_same_state_applied_delta_mps2',max([quant.rows.same_state_applied_delta_max_abs_mps2]), ...
    'plant_called',false);
report.candidate_model_id = char(model.model_id);
report.candidate_initial_W_sha256 = lock.shared_c1_inputs.w0_output_W_double_f_order_sha256;
report.normalizer_arrays_sha256 = normalizerHash;
report.resolved_paths = struct('init_dl1018',which('init_dl1018'), ...
    'run_dl1018_closed_loop',which('run_dl1018_closed_loop'), ...
    'run_episode_dl1018',which('run_episode_dl1018'), ...
    'position_only_search_options',which('position_only_search_options'), ...
    'position_only_search_head_step',which('position_only_search_head_step'));
report.beta_check = struct('dt_s',dt,'rise_time_s',riseTime,'tested_fixed_steps',numel(k), ...
    'old_expression',lock.runtime_change.original_expression, ...
    'candidate_expression',lock.runtime_change.candidate_expression, ...
    'step_1800_old',betaOld(1800),'step_1800_candidate',betaNew(1800), ...
    'step_1801_both',betaNew(1801));
report.head_check = struct('raw_output_before_update_max_abs_error',headRawError, ...
    'beta_scaled_applied_output_max_abs_error',headAppliedError, ...
    'weight_update_max_abs_error',headUpdateError,'beta_old',bOld,'beta_candidate',bNew, ...
    'state_next_fro_difference',norm(stateOld-stateNew,'fro'));
report.fixed_controller_parameters_reconstructed = struct( ...
    'source', 'simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1)) -> controller_parameters(...,''fixed'')', ...
    'is_historical_runtime_snapshot',false,'plant_dynamics_called',false, ...
    'mass_kg',double(Pcontroller.mass),'J0_kg_m2',double(Pcontroller.inertia), ...
    'C0_allocation_matrix',double(Pcontroller.allocation.C), ...
    'cog_m',double(Pcontroller.cog(:).'), ...
    'cfg_declared_inertia_not_used_as_actual',double(cfg.plant.inertia));
report.checkcode = analyzer;
report.execution_scope = struct('run_episode_called',false,'Plant_dynamics_called',false, ...
    'optimizer_steps',0,'gpu_jobs',0,'TEST_accessed',false,'new_closed_loop_authorized',false);
outDir = fullfile(here,'reports');
if ~isfolder(outDir), mkdir(outDir); end
outPath = fullfile(outDir,'OFFLINE_SMOKE_NO_PLANT.json');
write_json(outPath,report);
fprintf('C2 beta offline smoke PASS; result=%s\n',outPath);
end

function assert_one_expression_diff(originalPath,candidatePath,oldExpression,newExpression)
oldBytes = read_bytes(originalPath);
newBytes = read_bytes(candidatePath);
oldNeedle = uint8(oldExpression);
newNeedle = uint8(newExpression);
oldText = char(oldBytes(:).');
newText = char(newBytes(:).');
oldHits = strfind(oldText,char(oldNeedle));
newHits = strfind(newText,char(newNeedle));
assert(numel(oldHits)==1 && numel(newHits)==1 && numel(oldNeedle)==numel(newNeedle), ...
    'C2:ExpressionCount','Expected exactly one equal-length beta-expression replacement.');
expectedBytes = [oldBytes(1:oldHits(1)-1); newNeedle(:); ...
    oldBytes(oldHits(1)+numel(oldNeedle):end)];
assert(isequal(newBytes(:),expectedBytes(:)), ...
    'C2:SourceDiff','Candidate core differs from original outside the one beta expression.');
end

function path = locked_source_path(lock,name)
ix = find(arrayfun(@(x) endsWith(x.path,[filesep name],'IgnoreCase',true),lock.frozen_runtime_files));
assert(numel(ix)==1,'C2:SourceInventory','Expected one locked source named %s.',name);
path = lock.frozen_runtime_files(ix).path;
verify_file(path,lock.frozen_runtime_files(ix).sha256);
end

function verify_file(path,expected)
assert(isfile(path),'C2:MissingInput','Missing locked input: %s',path);
actual = sha256_file(path);
assert(strcmpi(actual,expected),'C2:InputSHA','SHA mismatch for %s: %s',path,actual);
end

function h = sha256_file(path)
bytes = read_bytes(path);
h = hash_bytes(bytes);
end

function bytes = read_bytes(path)
fid = fopen(path,'rb');
assert(fid>=0,'C2:Read','Cannot open %s',path);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes = fread(fid,Inf,'*uint8');
end

function h = hash_bytes(bytes)
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(uint8(bytes(:)),'int8'));
h = lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function h = hash_normalizer_arrays(model)
md = java.security.MessageDigest.getInstance('SHA-256');
for name = {'input_mu','input_sigma'}
    field = name{1};
    a = reshape(double(model.(field)),1,[]);
    assert(numel(a)==14 && all(isfinite(a)),'C2:NormalizerShape','Invalid %s.',field);
    header = [field char(0) '((1, 14), ''float64'')' char(0)];
    md.update(typecast(uint8(unicode2native(header,'UTF-8')),'int8'));
    md.update(typecast(a(:),'int8'));
end
h = lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function tf = same_path(a,b)
if isempty(a) || isempty(b), tf = false; return; end
tf = strcmpi(char(java.io.File(a).getCanonicalPath()),char(java.io.File(b).getCanonicalPath()));
end

function s = summarize_checkcode(messages)
items = repmat(struct('id','','line',0,'severity','','message',''),numel(messages),1);
for k = 1:numel(messages)
    if isfield(messages,'id'), items(k).id = char(messages(k).id); end
    if isfield(messages,'line'), items(k).line = double(messages(k).line); end
    if isfield(messages,'severity'), items(k).severity = char(messages(k).severity); end
    if isfield(messages,'message'), items(k).message = char(messages(k).message); end
end
s = struct('message_count',numel(messages),'messages',items);
end

function write_json(path,value)
assert(~isfile(path),'C2:NoOverwrite','Refusing to overwrite an existing smoke result: %s',path);
text = jsonencode(value,'PrettyPrint',true);
fid = fopen(path,'w','n','UTF-8');
assert(fid>=0,'C2:Write','Cannot create %s',path);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid,[text newline],'char');
end
