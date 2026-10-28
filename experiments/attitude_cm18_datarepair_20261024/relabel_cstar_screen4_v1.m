function outputPath = relabel_cstar_screen4_v1()
% Create same-state c* targets for exactly four pinned B scenes; no rollout/training.
sourceRel = 'reports/attitude_cm18_datarepair_20261024/B_REF_REPAIRED_SOURCE_MANIFEST_v1.json';
sourceSha = '0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5';
manifestRel = 'reports/attitude_cm18_datarepair_20261024/repaired_all816_v1/DATASET_MANIFEST_v1.json';
manifestSha = '3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0';
extractorRel = 'experiments/attitude_cm18_datarepair_20261024/extract_cm18_events_v1.m';
extractorSha = '15d8fb369b93e3a251d70c7eb7a590f732da839d35a5bebfb2011f25123e37c1';
modelRel = 'experiments/attitude_cm18_a1_20261024/model_cm18_v1.py';
modelSha = 'ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6';
deploymentRel = 'experiments/attitude_cm18_a1_20261024/deployment_v1/deployment_parameters_v1.json';
deploymentSha = 'ee00c46af42cbce83a630ae9b03eaf1a86bfc6047910ed68bc4e7b8b020aa6ae';
here = fileparts(mfilename('fullpath')); repoRoot = fileparts(fileparts(here));
reportDir = fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024','cstar_screen4_v1');
outputPath = fullfile(reportDir,'CSTAR_RELABEL_SCREEN4_v1.json');
assert(~isfolder(reportDir)&&~isfile(outputPath),'CStar4:NoOverwrite', ...
    'Refusing to overwrite an existing Screen4 relabel attempt.');
stage = 'manifest_preflight'; activeScene = ''; cacheFilesWritten = 0;
try
    sourcePath = fullfile(repoRoot,strrep(sourceRel,'/',filesep));
    manifestPath = fullfile(repoRoot,strrep(manifestRel,'/',filesep));
    assert_sha(sourcePath,sourceSha); assert_sha(manifestPath,manifestSha);
    S = jsondecode(fileread(sourcePath)); M = jsondecode(fileread(manifestPath));
    assert(strcmp(S.schema,'CM18_REFERENCE_REPAIRED_SOURCE_MANIFEST_V1')&& ...
        S.counts.all_scenes==816&&S.counts.reuse_a1_t1_t3_cache==544&& ...
        S.counts.rebuild_corrected_t2==272&&S.counts.t2_train_g3_b==256&& ...
        S.counts.t2_val_physical_b==16&&S.counts.screen4_fixed==4&& ...
        strcmp(M.schema,'CM18_B_REF_REPAIRED_ALL816_DATASET_MANIFEST_V1')&& ...
        strcmp(M.status,'PASS')&&M.scene_count==816&&M.qualified_count==816&& ...
        M.failed_count==0&&M.training_eligible&&~M.TEST_accessed&& ...
        strcmpi(M.source_manifest_sha256,sourceSha)&& ...
        M.split_counts.TRAIN==768&&M.split_counts.VAL==48, ...
        'CStar4:Manifest','Pinned ALL816/source manifest schema, status, or counts changed.');
    assert_sha(fullfile(repoRoot,strrep(extractorRel,'/',filesep)),extractorSha);
    assert_sha(fullfile(repoRoot,strrep(modelRel,'/',filesep)),modelSha);
    assert_sha(fullfile(repoRoot,strrep(deploymentRel,'/',filesep)),deploymentSha);
    coreDir = fullfile(repoRoot,'matlab','core');
    helperNames = {'allocate_control','simulation_parameters','controller_parameters', ...
        'allocation_matrix','arm_mass_properties','distributed_mass_properties','arm_directions'};
    helperShas = { ...
        '5ac26d8c5ba6243f755bcf6ad3a07e98e503c213e4c95edbee7dd2c2627f3d53', ...
        '962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae', ...
        '4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398', ...
        '5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d', ...
        '8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5', ...
        'db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a', ...
        '517bbfcd0df9526b189f64bff067a49551f573ad96e682ee005533ab510e686c'};
    for h=1:numel(helperNames)
        hp=fullfile(coreDir,[helperNames{h} '.m']); assert_sha(hp,helperShas{h});
    end
    addpath(coreDir,'-begin'); addpath(here,'-begin'); rehash;
    for h=1:numel(helperNames)
        assert(same_path(which(helperNames{h}),fullfile(coreDir,[helperNames{h} '.m'])), ...
            'CStar4:HelperPath','Unexpected helper resolution: %s.',helperNames{h});
    end
    assert(same_path(which('extract_cm18_events_v1'),fullfile(here,'extract_cm18_events_v1.m')), ...
        'CStar4:ExtractorPath','MATLAB resolved a different CM18 event extractor.');

    stage = 'four_scene_source_preflight';
    ids = {'DL1018_TRAIN_T1_C15_W14','DL1018_TRAIN_T2_C15_W14', ...
        'DL1018_TRAIN_T3_C15_W14','DL1018_VAL_T2_C00_W10'};
    splits = {'TRAIN','TRAIN','TRAIN','VAL'};
    sourceRows=json_rows(S.scenes,'source scenes'); manifestRows=json_rows(M.rows,'ALL816 rows');
    assert(numel(sourceRows)==816&&numel(manifestRows)==816, ...
        'CStar4:ManifestRows','Source or final manifest row count changed.');
    sourceIds=cellfun(@(r) char(string(r.scene_id)),sourceRows,'UniformOutput',false);
    manifestIds=cellfun(@(r) char(string(r.scene_id)),manifestRows,'UniformOutput',false);
    inputs = cell(4,1);
    for q=1:4
        activeScene=ids{q}; si=find(strcmp(sourceIds,ids{q}),1); mi=find(strcmp(manifestIds,ids{q}),1);
        assert(~isempty(si)&&~isempty(mi),'CStar4:SceneMissing','Scene absent from a pinned manifest: %s.',ids{q});
        src=sourceRows{si}; row=manifestRows{mi};
        assert(strcmp(src.split,splits{q})&&strcmp(row.split,splits{q})&& ...
            src.ordinal==row.ordinal&&row.qualified&&strcmp(row.status,'PASS')&& ...
            strcmp(src.source_action,row.source_action), ...
            'CStar4:SceneIdentity','Scene order/split/status/source action mismatch: %s.',ids{q});
        if strcmp(src.source_action,'REUSE_A1_CERTIFIED_CACHE')
            assert(any(strcmp(ids{q},{'DL1018_TRAIN_T1_C15_W14','DL1018_TRAIN_T3_C15_W14'}))&& ...
                strcmp(row.cache_schema,'CM18_A1_EVENT_CACHE_V1'), ...
                'CStar4:SourceClass','Unexpected A1 reuse scene: %s.',ids{q});
            rawRef=src.original_a1_source.raw_run; startRef=src.original_a1_source.run_start;
            assert(strcmpi(row.original_a1_input_sha256.raw_run,char(rawRef.sha256))&& ...
                strcmpi(row.original_a1_input_sha256.run_start,char(startRef.sha256)), ...
                'CStar4:A1SourceBinding','Original A1 raw/start hashes differ from final manifest: %s.',ids{q});
            runtimeId=ids{q};
        else
            assert(strcmp(src.source_action,'REBUILD_FROM_CORRECTED_T2_B_RAW')&& ...
                strcmp(row.cache_schema,'CM18_REPAIRED_EVENT_CACHE_V1'), ...
                'CStar4:SourceClass','Unexpected corrected-source schema: %s.',ids{q});
            rawRef=src.corrected_source.raw; startRef=src.corrected_source.run_start;
            assert(strcmpi(row.corrected_raw_sha256,char(rawRef.sha256))&& ...
                strcmpi(row.corrected_run_start_sha256,char(startRef.sha256)), ...
                'CStar4:CorrectedSourceBinding','Corrected raw/start hashes differ from final manifest: %s.',ids{q});
            runtimeId=char(src.corrected_source.runtime_scene_id);
            if q==2
                assert(strcmp(src.corrected_source.class,'CORRECTED_T2_TRAIN_B_G3'), ...
                    'CStar4:T2TrainSource','T2 TRAIN must use corrected B G3 raw.');
            elseif q==4
                assert(strcmp(src.corrected_source.class,'CORRECTED_T2_VAL_PHYSICAL_B'), ...
                    'CStar4:T2ValSource','T2 VAL must use corrected physical-B raw.');
            else
                error('CStar4:UnexpectedRepair','Only the pinned T2 sources may be rebuilt.');
            end
        end
        rawPath=source_path(repoRoot,char(rawRef.path)); startPath=source_path(repoRoot,char(startRef.path));
        cachePath=repo_cache_path(repoRoot,char(row.cache_path));
        assert_file_identity(rawPath,char(rawRef.sha256),double(rawRef.size_bytes));
        assert_file_identity(startPath,char(startRef.sha256),double(startRef.size_bytes));
        assert_file_identity(cachePath,char(row.cache_sha256),double(row.cache_bytes));
        inputs{q}=struct('scene_id',ids{q},'split',splits{q},'runtime_scene_id',runtimeId, ...
            'source_action',char(src.source_action),'cache_schema',char(row.cache_schema), ...
            'raw_path',rawPath,'raw_path_manifest',char(rawRef.path),'raw_sha256',char(rawRef.sha256), ...
            'run_start_path',startPath,'run_start_path_manifest',char(startRef.path), ...
            'run_start_sha256',char(startRef.sha256),'cache_path',cachePath, ...
            'cache_path_manifest',char(row.cache_path),'cache_sha256',char(row.cache_sha256), ...
            'cache_bytes',double(row.cache_bytes));
    end

    stage = 'extractor_parity_and_physics';
    sceneResults = cell(4,1); cacheData = cell(4,1);
    commonJ0=[]; commonC0=[]; commonDmax=[]; commonBeta=[];
    for q=1:4
        activeScene=ids{q};
        [sceneResults{q},cacheData{q},commonJ0,commonC0,commonDmax,commonBeta] = ...
            inspect_scene(inputs{q},commonJ0,commonC0,commonDmax,commonBeta);
    end

    stage = 'publish_new_label_caches';
    mkdir(reportDir);
    for q=1:4
        cachePath=fullfile(reportDir,[splits{q} '_' ids{q} '_CSTAR_V1.mat']);
        assert(~isfile(cachePath),'CStar4:CacheExists','Refusing cache overwrite: %s.',cachePath);
        save_label_cache(cachePath,cacheData{q});
        d=dir(cachePath); cacheFilesWritten=cacheFilesWritten+1;
        sceneResults{q}.new_cache_path=repo_relative(cachePath,repoRoot);
        sceneResults{q}.new_cache_sha256=sha256_file(cachePath);
        sceneResults{q}.new_cache_bytes=d.bytes;
    end
    sceneResultsOut=[sceneResults{:}];
    report=struct('schema','CM18_A1_CSTAR_RELABEL_SCREEN4_V1','status','PASS', ...
        'source_manifest_path',sourceRel,'source_manifest_sha256',sourceSha, ...
        'dataset_manifest_path',manifestRel,'dataset_manifest_sha256',manifestSha, ...
        'extractor_path',extractorRel,'extractor_sha256',extractorSha, ...
        'model_source_path',modelRel,'model_source_sha256',modelSha, ...
        'deployment_path',deploymentRel,'deployment_sha256',deploymentSha, ...
        'target_contract','target_applied_acceleration is c*=G\E0 after beta; target_raw_output is c*/beta before output clip; target_after_clip_beta records the runtime-applied value.', ...
        'G_storage','Each cache stores reshape(G,1,9), MATLAB column-major order, under G_column_major.', ...
        'scope',struct('scene_count',4,'events_per_scene',1999,'plant_calls',0, ...
            'engine_calls',0,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false, ...
            'full816_relabel',false,'X18_copied_to_new_cache',false), ...
        'nominal_inertia_J0_kg_m2',commonJ0,'nominal_allocation_C0',commonC0, ...
        'zero_morphology_basis_definition','Model output is A*[z/2;u], so exact X18 columns 8:15 zero force exact zero physical output.', ...
        'dmax_rad_s2',commonDmax,'beta_rise_time_s',commonBeta,'scenes',sceneResultsOut);
    encoded=jsonencode(report,'PrettyPrint',true); bytes=unicode2native(encoded,'UTF-8');
    files=dir(fullfile(reportDir,'*.mat')); totalBytes=numel(bytes)+sum([files.bytes]);
    assert(totalBytes<=16*1024^2,'CStar4:OutputBudget','Screen4 outputs exceed 16 MiB.');
    write_new_bytes(outputPath,bytes);
catch ME
    if ~isfolder(reportDir), mkdir(reportDir); end
    failure=struct('schema','CM18_A1_CSTAR_RELABEL_SCREEN4_V1','status','FAIL', ...
        'source_manifest_sha256',sourceSha,'dataset_manifest_sha256',manifestSha, ...
        'failed_stage',stage,'failed_scene_id',activeScene,'error_identifier',ME.identifier, ...
        'error_message',ME.message,'new_cache_files_written',cacheFilesWritten, ...
        'scope',struct('scene_count_requested',4,'full816_relabel',false,'Plant_calls',0, ...
            'training_steps',0,'optimizer_steps',0,'TEST_accessed',false));
    if ~isfile(outputPath)
        try
            write_new_bytes(outputPath,unicode2native(jsonencode(failure,'PrettyPrint',true),'UTF-8'));
        catch
        end
    end
    rethrow(ME);
end
end

function [result,C,J0,C0,dmax,betaRise]=inspect_scene(input,J0,C0,dmax,betaRise)
R=load(input.run_start_path); D=load(input.raw_path,'log','scene');
assert(isfield(D,'log')&&isfield(D,'scene'), ...
    'CStar4:RawSchema','Pinned raw MAT schema is incomplete: %s.',input.scene_id);
cfg=run_start_cfg(R,input);
assert(strcmp(char(string(D.scene.scene_id)),input.runtime_scene_id), ...
    'CStar4:RuntimeScene','Raw runtime scene identity mismatch: %s.',input.scene_id);
E=extract_cm18_events_v1(cfg,D.scene,D.log);
old=load(input.cache_path,'X18','target_raw','event_time_s','phase_code','plant_index','scene_id','split');
required={'X18','target_raw','event_time_s','phase_code','plant_index','scene_id','split'};
assert(all(isfield(old,required))&&strcmp(char(string(old.scene_id)),input.scene_id)&& ...
    strcmp(char(string(old.split)),input.split), ...
    'CStar4:CacheSchema','Old cache lacks required arrays or canonical scene identity: %s.',input.scene_id);
assert(isequal(size(E.X18),[1999,18])&&isequal(size(E.target_raw),[1999,3])&& ...
    isequal(size(old.X18),[1999,18])&&isequal(size(old.target_raw),[1999,3])&& ...
    isequal(double(E.plant_index(:)),double(old.plant_index(:)))&& ...
    isequal(double(E.phase_code(:)),double(old.phase_code(:)))&& ...
    max(abs(double(E.event_time_s(:))-double(old.event_time_s(:))))<=1e-12, ...
    'CStar4:CacheTiming','Extractor/cache dimensions, indices, phase, or time differ: %s.',input.scene_id);
cacheXDelta=max(abs(double(E.X18)-double(old.X18)),[],'all');
cacheYDelta=max(abs(double(E.target_raw)-double(old.target_raw)),[],'all');
assert(cacheXDelta<=1e-10&&cacheYDelta<=1e-10, ...
    'CStar4:CacheParity','Frozen extractor differs from old cache: %s.',input.scene_id);

assert(strcmp(char(string(cfg.controller_morphology_mode)),'fixed')&& ...
    strcmp(char(string(cfg.controller_inertia_derivative_mode)),'full'), ...
    'CStar4:ControllerMode','Expected fixed nominal controller and full Jdot.');
thisDmax=double(cfg.rbf.attitude.dmax(:)); thisBeta=double(cfg.rbf.attitude.beta_rise_time);
assert(isequal(size(thisDmax),[3,1])&&all(isfinite(thisDmax))&&all(thisDmax>0)&& ...
    isfinite(thisBeta)&&thisBeta>0,'CStar4:ClipBeta','Invalid runtime clip/beta values.');
if isempty(dmax)
    dmax=thisDmax; betaRise=thisBeta;
else
    assert(max(abs(dmax-thisDmax))<=1e-14&&abs(betaRise-thisBeta)<=1e-14, ...
        'CStar4:ClipBetaPair','The four sources do not share clip/beta.');
end

P0=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
Pc=controller_parameters(cfg,P0,'fixed'); J0Now=double(P0.inertia);
Jdot0=double(P0.inertia_dot); C0Now=double(Pc.allocation.C);
assert(isequal(size(J0Now),[3,3])&&isequal(size(Jdot0),[3,3])&& ...
    isequal(size(C0Now),[4,4]),'CStar4:NominalModel','Invalid J0/Jdot0/C0.');
if isempty(J0)
    J0=J0Now; C0=C0Now;
else
    assert(max(abs(J0-J0Now),[],'all')<=1e-14&&max(abs(C0-C0Now),[],'all')<=1e-14, ...
        'CStar4:NominalPair','Fixed nominal controller differs across scenes.');
end

log=D.log; scene=D.scene; idx=double(E.plant_index(:)); n=1999;
assert(isfield(log,'motor_time_constant_s')&&all(abs(double(log.motor_time_constant_s(:)))<=1e-12), ...
    'CStar4:MotorLag','Matrix target assumes ideal actuator timing; raw motor time constant is nonzero/missing.');
assert(all(isfield(log,{'state','attitude_event_flag','attitude_bs_nominal_torque_Nm', ...
    'attitude_compensation_applied_torque_Nm','requested_generalized','realized_generalized', ...
    'wind_torque_B','generalized_clipped','motor_saturated'})), ...
    'CStar4:RequiredLog','Raw log misses a required dynamics/allocator field.');
state=double(log.state); flags=logical(log.attitude_event_flag(:));
tauNom=double(log.attitude_bs_nominal_torque_Nm); tauComp=double(log.attitude_compensation_applied_torque_Nm);
requested=double(log.requested_generalized); realized=double(log.realized_generalized);
wind=double(log.wind_torque_B); rho=double(scene.arms.rho_true); rhoDot=double(scene.arms.rhoDot_true);
assert(isequal(size(state),[20001,12])&&isequal(size(tauNom),[20000,3])&& ...
    isequal(size(tauComp),[20000,3])&&isequal(size(requested),[20000,4])&& ...
    isequal(size(realized),[20000,4])&&isequal(size(wind),[20000,3])&& ...
    isequal(size(rho),[20001,4])&&isequal(size(rhoDot),[20001,4])&& ...
    isequal(find(flags),idx),'CStar4:RawShapes','Raw transition/state arrays or event flags changed.');

X=double(E.X18); dOld=double(E.target_raw); cStar=zeros(n,3); cOld=zeros(n,3);
beta=zeros(n,1); GColumn=zeros(n,9); afterClipBeta=zeros(n,3); rawOutput=zeros(n,3);
rawReachable=true(n,3); rawClip=false(n,3); betaZeroUnreachable=false(n,3);
oldDeployError=zeros(n,3); oldClip=false(n,3); starLinearError=zeros(n,3); starBetaOneError=zeros(n,3);
starDeployError=zeros(n,3); starBetaOneClip=false(n,3); starAllocClip=false(n,4); starMotorSat=false(n,4);
starBetaOneAllocClip=false(n,4); starBetaOneMotorSat=false(n,4);
currentAllocClip=false(n,4); currentMotorSat=false(n,4); nominalAllocClip=false(n,4); nominalMotorSat=false(n,4);
zeroBasis=all(X(:,8:15)==0,2); maxRequestClosure=0; maxAllocatorClosure=0;
maxBehaviorClosure=0; maxE0Identity=0; maxMatrixClosure=0; maxSolveClosure=0; maxBaseAllocatorDelta=0;
maxTargetDirectClosure=0; GCondition=zeros(n,1); GRcond=zeros(n,1); GRank=zeros(n,1);
for q=1:n
    k=idx(q); w=state(k,10:12).'; T=requested(k,1); tn=tauNom(k,:).'; tc=tauComp(k,:).'; wt=wind(k,:).';
    Ptrue=simulation_parameters(cfg,rho(k,:).',rhoDot(k,:).');
    J=double(Ptrue.inertia); Jdot=double(Ptrue.inertia_dot); Ct=double(Ptrue.allocation.C);
    gyro0=cross(w,J0*w); gyroTrue=cross(w,J*w);
    alphaBS=J0\(tn-gyro0-Jdot0*w); cOld(q,:)=(J0\tc).';
    rawRequest=requested(k,:).'; requestFromController=[T;tn-tc];
    maxRequestClosure=max(maxRequestClosure,max(abs(rawRequest-requestFromController)));
    [~,currentRealized,currentInfo]=allocate_control(requestFromController,Pc,Ptrue,[]);
    currentAllocClip(q,:)=logical(currentInfo.generalized_command_clipped(:)).';
    currentMotorSat(q,:)=logical(currentInfo.motor_saturated(:)).';
    maxAllocatorClosure=max(maxAllocatorClosure,max(abs(currentRealized-realized(k,:).')));
    assert(isequal(currentAllocClip(q,:),logical(log.generalized_clipped(k,:)))&& ...
        isequal(currentMotorSat(q,:),logical(log.motor_saturated(k,:))), ...
        'CStar4:RawAllocatorFlags','Pure allocator flags differ from raw at %s event %d.',input.scene_id,k);
    alphaActual=J\(realized(k,2:4).'+wt-gyroTrue-Jdot*w);
    alphaVirtual=J0\(tn-tc-gyro0-Jdot0*w);
    physicalResidual=alphaActual-alphaVirtual;
    maxBehaviorClosure=max(maxBehaviorClosure,max(abs(physicalResidual-dOld(q,:).')));
    L=[zeros(1,3);J0]; transfer=Ct*(C0\L); G=J\transfer(2:4,:); GColumn(q,:)=reshape(G,1,9);
    baseRequest=[T;tn]; [~,baseRealized,baseInfo]=allocate_control(baseRequest,Pc,Ptrue,[]);
    nominalAllocClip(q,:)=logical(baseInfo.generalized_command_clipped(:)).';
    nominalMotorSat(q,:)=logical(baseInfo.motor_saturated(:)).';
    wrench0=Ct*(C0\baseRequest);
    maxBaseAllocatorDelta=max(maxBaseAllocatorDelta,max(abs(baseRealized-wrench0)));
    E0=J\(wrench0(2:4)+wt-gyroTrue-Jdot*w)-alphaBS;
    dMatrix=E0+(eye(3)-G)*cOld(q,:).';
    maxMatrixClosure=max(maxMatrixClosure,max(abs(dMatrix-dOld(q,:).')));
    maxE0Identity=max(maxE0Identity,max(abs(E0-(dOld(q,:).'-((eye(3)-G)*cOld(q,:).')))));
    maxTargetDirectClosure=max(maxTargetDirectClosure,max(abs(physicalResidual-dOld(q,:).')));
    GCondition(q)=cond(G); GRcond(q)=rcond(G); GRank(q)=rank(G);
    assert(all(isfinite([G(:);E0(:);GCondition(q);GRcond(q)]))&&GRank(q)==3&&GRcond(q)>1e-12, ...
        'CStar4:SingularG','G is singular/ill-conditioned at %s event %d; no regularization.',input.scene_id,k);
    cStar(q,:)=(G\E0).'; starLinearError(q,:)=(E0-G*cStar(q,:).').';
    maxSolveClosure=max(maxSolveClosure,max(abs(starLinearError(q,:))));
    beta(q)=min(k*double(cfg.plant.dt)/thisBeta,1);
    oldClip(q,:)=abs(dOld(q,:)-min(max(dOld(q,:),-thisDmax.'),thisDmax.'))>1e-12;
    [alphaOld,~,~]=alpha_for_applied(T,tn,beta(q)*min(max(dOld(q,:).',-thisDmax),thisDmax), ...
        J0,Pc,Ptrue,wt,w,J,Jdot);
    oldDeployError(q,:)=(alphaOld-alphaBS).';
    fullStarClip=min(max(cStar(q,:).',-thisDmax),thisDmax);
    starBetaOneClip(q,:)=abs(cStar(q,:).'-fullStarClip.')>1e-12;
    [alphaStarOne,~,oneInfo]=alpha_for_applied(T,tn,fullStarClip,J0,Pc,Ptrue,wt,w,J,Jdot);
    starBetaOneError(q,:)=(alphaStarOne-alphaBS).';
    starBetaOneAllocClip(q,:)=logical(oneInfo.generalized_command_clipped(:)).';
    starBetaOneMotorSat(q,:)=logical(oneInfo.motor_saturated(:)).';
    if beta(q)>0
        rawOutput(q,:)=(cStar(q,:).'/beta(q)).';
        clipped=min(max(rawOutput(q,:).',-thisDmax),thisDmax);
        rawClip(q,:)=abs(rawOutput(q,:).'-clipped.')>1e-12;
        applied=beta(q)*clipped;
    else
        rawReachable(q,:)=abs(cStar(q,:))<=1e-10;
        betaZeroUnreachable(q,:)=~rawReachable(q,:);
        rawOutput(q,~rawReachable(q,:))=NaN;
        applied=zeros(3,1);
    end
    afterClipBeta(q,:)=applied.';
    [alphaStar,~,starInfo]=alpha_for_applied(T,tn,applied,J0,Pc,Ptrue,wt,w,J,Jdot);
    starDeployError(q,:)=(alphaStar-alphaBS).';
    starAllocClip(q,:)=logical(starInfo.generalized_command_clipped(:)).';
    starMotorSat(q,:)=logical(starInfo.motor_saturated(:)).';
end
assert(maxRequestClosure<=1e-8&&maxAllocatorClosure<=1e-8&&maxBehaviorClosure<=1e-8&& ...
    maxMatrixClosure<=1e-8&&maxE0Identity<=1e-8&&maxTargetDirectClosure<=1e-8&&maxSolveClosure<=1e-8, ...
    'CStar4:PhysicalClosure','Request/allocator/behavior/E0/G/c* closure failed: %s.',input.scene_id);

phaseNames={'STATIC','PRE','EXTEND','HOLD','RETRACT','RECOVERY'};
phaseCounts=struct(); for p=0:5, phaseCounts.(phaseNames{p+1})=nnz(double(E.phase_code(:))==p); end
assert(sum([phaseCounts.STATIC,phaseCounts.PRE,phaseCounts.EXTEND,phaseCounts.HOLD,phaseCounts.RETRACT,phaseCounts.RECOVERY])==n,'CStar4:PhaseCount','Phase counts do not cover all events.');
axisNames={'roll','pitch','yaw'}; axes=repmat(struct('axis','','old_label_minus_cstar_rms',0, ...
    'old_label_exact_deployed_error_rms',0,'cstar_linear_error_rms',0,'cstar_beta1_allocator_error_rms',0, ...
    'cstar_actual_beta_allocator_error_rms',0,'old_label_clip_count',0,'cstar_beta1_clip_count',0, ...
    'cstar_raw_output_clip_count',0,'beta_zero_unreachable_count',0),1,3);
for a=1:3
    axes(a).axis=axisNames{a}; axes(a).old_label_minus_cstar_rms=rms_value(dOld(:,a)-cStar(:,a));
    axes(a).old_label_exact_deployed_error_rms=rms_value(oldDeployError(:,a));
    axes(a).cstar_linear_error_rms=rms_value(starLinearError(:,a));
    axes(a).cstar_beta1_allocator_error_rms=rms_value(starBetaOneError(:,a));
    axes(a).cstar_actual_beta_allocator_error_rms=rms_value(starDeployError(:,a));
    axes(a).old_label_clip_count=nnz(oldClip(:,a)); axes(a).cstar_beta1_clip_count=nnz(starBetaOneClip(:,a));
    axes(a).cstar_raw_output_clip_count=nnz(rawClip(:,a));
    axes(a).beta_zero_unreachable_count=nnz(betaZeroUnreachable(:,a));
end
zeroCount=nnz(zeroBasis); zeroTarget=cStar(zeroBasis,:); if isempty(zeroTarget), zeroTargetMax=0; zeroTargetNonzero=0;
else, zeroTargetMax=max(abs(zeroTarget),[],'all'); zeroTargetNonzero=nnz(any(abs(zeroTarget)>1e-8,2)); end
result=struct('flight_id',input.scene_id,'scene_id',input.scene_id,'split',input.split, ...
    'source_action',input.source_action,'cache_schema',input.cache_schema, ...
    'raw_path',input.raw_path_manifest,'raw_sha256',input.raw_sha256, ...
    'run_start_path',input.run_start_path_manifest,'run_start_sha256',input.run_start_sha256, ...
    'old_cache_path',input.cache_path_manifest,'old_cache_sha256',input.cache_sha256, ...
    'event_count',n,'extractor_cache_max_abs_X18_delta',cacheXDelta, ...
    'extractor_cache_max_abs_behavior_target_delta_rad_s2',cacheYDelta, ...
    'max_abs_request_closure_mixed_units',maxRequestClosure, ...
    'max_abs_allocator_vs_raw_realized_mixed_units',maxAllocatorClosure, ...
    'max_abs_no_comp_allocator_vs_linear_wrench_mixed_units',maxBaseAllocatorDelta, ...
    'max_abs_behavior_target_vs_raw_physics_rad_s2',maxBehaviorClosure, ...
    'max_abs_behavior_target_vs_E0_matrix_relation_rad_s2',maxMatrixClosure, ...
    'max_abs_E0_identity_rad_s2',maxE0Identity,'max_abs_cstar_linear_solve_rad_s2',maxSolveClosure, ...
    'max_G_condition_number',max(GCondition),'min_G_reciprocal_condition',min(GRcond), ...
    'minimum_rank_G',min(GRank),'current_generalized_clip_count_by_channel',sum(currentAllocClip,1), ...
    'current_motor_saturation_count_by_motor',sum(currentMotorSat,1), ...
    'zero_comp_nominal_generalized_clip_count_by_channel',sum(nominalAllocClip,1), ...
    'zero_comp_nominal_motor_saturation_count_by_motor',sum(nominalMotorSat,1), ...
    'cstar_beta1_allocator_clip_count_by_channel',sum(starBetaOneAllocClip,1), ...
    'cstar_beta1_motor_saturation_count_by_motor',sum(starBetaOneMotorSat,1), ...
    'cstar_actual_beta_allocator_clip_count_by_channel',sum(starAllocClip,1), ...
    'cstar_actual_beta_motor_saturation_count_by_motor',sum(starMotorSat,1), ...
    'linear_matrix_preconditions_satisfied',~any(nominalAllocClip(:))&&~any(nominalMotorSat(:))&& ...
        ~any(currentAllocClip(:))&&~any(currentMotorSat(:)), ...
    'beta_first_last',[beta(1),beta(end)],'beta_zero_count',nnz(beta==0), ...
    'beta_below_one_count',nnz(beta<1),'phase_event_count',phaseCounts, ...
    'zero_morphology_basis_event_count',zeroCount, ...
    'zero_basis_nonzero_applied_target_count_gt_1e_8',zeroTargetNonzero, ...
    'zero_basis_target_applied_max_abs_rad_s2',zeroTargetMax,'axis_summary',axes);
C=struct('scene_id',input.scene_id,'split',input.split,'source_action',input.source_action, ...
    'source_manifest_sha256','0f86b47d01940e7b556b78a9664470531572809aa6857a59fc77d88a33681ec5', ...
    'dataset_manifest_sha256','3f51a1cd0e2e8c3eae79a16df363f2f8d47b0d5dbd876ecd95f1571d9e70a5e0', ...
    'raw_path',input.raw_path_manifest,'raw_sha256',input.raw_sha256, ...
    'run_start_path',input.run_start_path_manifest,'run_start_sha256',input.run_start_sha256, ...
    'old_cache_path',input.cache_path_manifest,'old_cache_sha256',input.cache_sha256, ...
    'old_cache_schema',input.cache_schema,'event_index',uint16(E.event_index(:)), ...
    'plant_index',uint32(E.plant_index(:)),'event_time_s',double(E.event_time_s(:)), ...
    'phase_code',uint8(E.phase_code(:)),'target_applied_acceleration_rad_s2',cStar, ...
    'target_raw_output_rad_s2',rawOutput,'target_raw_output_reachable',rawReachable, ...
    'target_after_clip_beta_rad_s2',afterClipBeta,'beta',beta, ...
    'G_column_major',GColumn,'output_clip_mask',rawClip, ...
    'beta_zero_unreachable_mask',betaZeroUnreachable,'allocator_clip_mask',starAllocClip, ...
    'motor_saturation_mask',starMotorSat, ...
    'target_contract','Applied target is c*=G\E0; raw network target is c*/beta before runtime clip; target_after_clip_beta records the actual applied request. NaN plus reachability=false marks a beta=0 unreachable axis.', ...
    'G_layout','Each G is reshaped to one row in MATLAB column-major order.');
end

function rows=json_rows(value,label)
if iscell(value)
    rows=value(:);
elseif isstruct(value)
    rows=num2cell(value(:));
else
    error('CStar4:ManifestRows','%s must decode as a struct array or cell array.',label);
end
assert(all(cellfun(@(r) isstruct(r)&&isscalar(r)&&isfield(r,'scene_id'),rows)), ...
    'CStar4:ManifestRows','%s contains a non-scalar or unidentified row.',label);
end

function cfg=run_start_cfg(R,input)
if isfield(R,'runStart')
    assert(isstruct(R.runStart)&&isscalar(R.runStart)&&isfield(R.runStart,'cfg'), ...
        'CStar4:RunStartSchema','Nested runStart schema is incomplete: %s.',input.scene_id);
    runStart=R.runStart; cfg=runStart.cfg;
    if isfield(runStart,'scene')&&isfield(runStart.scene,'scene_id')
        assert(strcmp(char(string(runStart.scene.scene_id)),input.runtime_scene_id), ...
            'CStar4:RunStartIdentity','Nested run_start scene identity mismatch: %s.',input.scene_id);
    end
elseif all(isfield(R,{'cfg','opts','meta','scene','sceneMeta'}))&& ...
        all(isfield(R.meta,{'runtime_scene_id','source_scene_id'}))&&isfield(R.scene,'scene_id')
    assert(strcmp(char(string(R.meta.runtime_scene_id)),input.runtime_scene_id)&& ...
        strcmp(char(string(R.meta.source_scene_id)),input.scene_id)&& ...
        strcmp(char(string(R.scene.scene_id)),input.runtime_scene_id), ...
        'CStar4:RunStartIdentity','Top-level run_start scene identity mismatch: %s.',input.scene_id);
    cfg=R.cfg;
else
    error('CStar4:RunStartSchema','Unsupported pinned run_start MAT schema: %s.',input.scene_id);
end
assert(isstruct(cfg)&&isscalar(cfg),'CStar4:RunStartConfig','run_start cfg is not a scalar struct: %s.',input.scene_id);
end

function [alpha,realized,info]=alpha_for_applied(T,tauNom,comp,J0,Pc,Ptrue,wind,w,J,Jdot)
[~,realized,info]=allocate_control([T;tauNom-J0*comp],Pc,Ptrue,[]);
alpha=J\(realized(2:4)+wind-cross(w,J*w)-Jdot*w);
end

function save_label_cache(path,C)
scene_id=C.scene_id; split=C.split; source_action=C.source_action;
source_manifest_sha256=C.source_manifest_sha256; dataset_manifest_sha256=C.dataset_manifest_sha256;
raw_path=C.raw_path; raw_sha256=C.raw_sha256; run_start_path=C.run_start_path; run_start_sha256=C.run_start_sha256;
old_cache_path=C.old_cache_path; old_cache_sha256=C.old_cache_sha256; old_cache_schema=C.old_cache_schema;
event_index=C.event_index; plant_index=C.plant_index; event_time_s=C.event_time_s; phase_code=C.phase_code;
target_applied_acceleration_rad_s2=C.target_applied_acceleration_rad_s2;
target_raw_output_rad_s2=C.target_raw_output_rad_s2; target_raw_output_reachable=C.target_raw_output_reachable;
target_after_clip_beta_rad_s2=C.target_after_clip_beta_rad_s2; beta=C.beta; G_column_major=C.G_column_major;
output_clip_mask=C.output_clip_mask; beta_zero_unreachable_mask=C.beta_zero_unreachable_mask;
allocator_clip_mask=C.allocator_clip_mask; motor_saturation_mask=C.motor_saturation_mask;
target_contract=C.target_contract; G_layout=C.G_layout;
save(path,'scene_id','split','source_action','source_manifest_sha256','dataset_manifest_sha256', ...
    'raw_path','raw_sha256','run_start_path','run_start_sha256','old_cache_path','old_cache_sha256', ...
    'old_cache_schema','event_index','plant_index','event_time_s','phase_code', ...
    'target_applied_acceleration_rad_s2','target_raw_output_rad_s2','target_raw_output_reachable', ...
    'target_after_clip_beta_rad_s2','beta','G_column_major','output_clip_mask', ...
    'beta_zero_unreachable_mask','allocator_clip_mask','motor_saturation_mask', ...
    'target_contract','G_layout','-v7');
end

function path=source_path(repoRoot,manifestPath)
manifestPath=char(manifestPath);
if ~isempty(regexp(manifestPath,'^[A-Za-z]:[\\/]|^\\\\','once'))
    path=manifestPath;
else
    path=fullfile(repoRoot,strrep(manifestPath,'/',filesep));
end
assert(isfile(path),'CStar4:SourceMissing','Manifest-pinned source missing: %s.',manifestPath);
end

function path=repo_cache_path(repoRoot,relativePath)
relativePath=char(relativePath);
assert(isempty(regexp(relativePath,'^[A-Za-z]:|^[\\/]','once')),'CStar4:CachePath', ...
    'Cache path must be repository-relative: %s.',relativePath);
path=fullfile(repoRoot,strrep(relativePath,'/',filesep)); root=char(java.io.File(repoRoot).getCanonicalPath());
resolved=char(java.io.File(path).getCanonicalPath()); prefix=[root filesep];
assert(startsWith(resolved,prefix,'IgnoreCase',true),'CStar4:CacheEscape','Cache path escaped repo.');
end

function assert_file_identity(path,sha,bytes)
assert(isfile(path),'CStar4:MissingFile','Pinned input missing: %s.',path);
d=dir(path); assert(d.bytes==bytes,'CStar4:Size','Pinned byte size mismatch: %s.',path);
assert(strcmpi(sha256_file(path),sha),'CStar4:SHA','Pinned SHA256 mismatch: %s.',path);
end

function assert_sha(path,expected)
assert(isfile(path)&&strcmpi(sha256_file(path),expected),'CStar4:SHA','Pinned file changed: %s.',path);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'rb');
assert(fid>=0,'CStar4:Open','Cannot read %s.',path); closer=onCleanup(@()fclose(fid));
while true
    b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end
    md.update(typecast(b(:),'int8'));
end
clear closer; h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function tf=same_path(a,b)
tf=strcmpi(char(java.io.File(a).getCanonicalPath()),char(java.io.File(b).getCanonicalPath()));
end

function s=repo_relative(path,repoRoot)
root=char(java.io.File(repoRoot).getCanonicalPath()); resolved=char(java.io.File(path).getCanonicalPath());
assert(startsWith(resolved,[root filesep],'IgnoreCase',true),'CStar4:RelativePath','Path is not in repo.');
s=resolved(numel(root)+2:end);
end

function write_new_bytes(path,bytes)
assert(~isfile(path),'CStar4:NoOverwrite','Refusing output overwrite: %s.',path);
fid=fopen(path,'wb'); assert(fid>=0,'CStar4:OutputOpen','Cannot create %s.',path);
closer=onCleanup(@()fclose(fid)); assert(fwrite(fid,bytes,'uint8')==numel(bytes), ...
    'CStar4:OutputWrite','Incomplete write: %s.',path); clear closer;
end

function value=rms_value(x)
x=double(x(:)); value=sqrt(mean(x.^2));
end







