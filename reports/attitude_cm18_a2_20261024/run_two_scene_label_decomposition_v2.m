function run_two_scene_label_decomposition_v2()
% Offline, read-only decomposition of two pinned legacy A2 yaw labels.
% No engine, Plant, training, TEST, or label rewrite is performed.
reportDir = fileparts(mfilename('fullpath'));
repoRoot = fileparts(fileparts(reportDir));
manifestRel = 'reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/DATASET_MANIFEST_v1.json';
manifestPath = fullfile(repoRoot,manifestRel);
taskbookRel = 'reports/attitude_cm18_a2_20261024/ROOT_TWO_SCENE_LABEL_DIAGNOSIS_TASKBOOK_v1_ZH.md';
taskbookPath = fullfile(repoRoot,taskbookRel);
outputPath = fullfile(reportDir,'TWO_SCENE_LABEL_DECOMPOSITION_v2.json');
assert(~isfile(outputPath),'CM18:OutputExists','Refusing to overwrite an existing result.');
assert(strcmp(sha256_file(manifestPath),'7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271'), ...
    'CM18:ManifestSHA','ALL816 manifest identity mismatch.');
assert(strcmp(sha256_file(taskbookPath),'65c3f3d0634a6331842d6b59917ce83a040435d27d15f8aec859a48eb376f44b'), ...
    'CM18:TaskbookSHA','Frozen two-scene taskbook identity mismatch.');
M = jsondecode(fileread(manifestPath));
assert(strcmp(M.schema,'CM18_A1_DATASET_MANIFEST_V1')&&strcmp(M.mode,'ALL816')&& ...
    double(M.scene_count)==816&&double(M.qualified_count)==816&&double(M.failed_count)==0&& ...
    strcmpi(M.input_manifest_sha256,'a5f7fea9b0918c1449af6fa83929177d3bf7d5e70cb3b71711c40f6338d210a5')&& ...
    isequal(M.TEST_accessed,false),'CM18:ManifestContract','Dataset manifest gate failed.');

coreDir = fullfile(repoRoot,'matlab','core');
addpath(coreDir,'-begin');
helperNames = {'arm_mass_properties','distributed_mass_properties','arm_directions', ...
    'simulation_parameters','controller_parameters','allocation_matrix'};
helperSHAs = { ...
    '8ec66e107156b5219f7e41aca2464eef1ec8043eb7f67df313c0f23ef4b551f5', ...
    'db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a', ...
    '517bbfcd0df9526b189f64bff067a49551f573ad96e682ee005533ab510e686c', ...
    '962b5434c23d5ac1a9ac568f136635a8ea651a775165d84b7d95250ca88bb9ae', ...
    '4fad5e78c0bd4177461647af167e7c86a7defa628b43d523b0b7da2ef5556398', ...
    '5886c00b3f8800301a324159e534b4c65e857cdd00392a3231af22c6dbba517d'};
helperRows = repmat(struct('path','','sha256',''),numel(helperNames),1);
for i = 1:numel(helperNames)
    helperPath = fullfile(coreDir,[helperNames{i} '.m']);
    assert(strcmpi(which(helperNames{i}),helperPath),'CM18:HelperPath', ...
        'MATLAB resolved a different physical helper: %s',helperNames{i});
    actualSHA = sha256_file(helperPath);
    assert(strcmp(actualSHA,helperSHAs{i}),'CM18:HelperSHA', ...
        'Physical helper source SHA mismatch: %s',helperNames{i});
    helperRows(i).path = strrep(helperPath,[repoRoot filesep],'');
    helperRows(i).sha256 = actualSHA;
end

ids = {'DL1018_TRAIN_T1_C15_W14','DL1018_VAL_T2_C15_W09'};
splits = {'TRAIN','VAL'};
rawRel = { ...
    'data/raw/train/DL1018_TRAIN_T1_C15_W14/B/attempt_01/raw_run.mat', ...
    'data/raw/val/DL1018_VAL_T2_C15_W09/B/attempt_01/raw_run.mat'};
rawSHA = { ...
    '591b0951c906b151ce6db22e53db3ce70d4ceab1d24cfcfd4680dcc1d34be3ff', ...
    'ae0c318a69bc76e0cd64f50a708d8b768f7cc4077fcd2489e972f28e18de4bb2'};
startRel = { ...
    'data/raw/train/DL1018_TRAIN_T1_C15_W14/B/attempt_01/run_start.mat', ...
    'data/raw/val/DL1018_VAL_T2_C15_W09/B/attempt_01/run_start.mat'};
startSHA = { ...
    'aebc46bc1b8d036a4b1af4db7ba9af3c78b5dd5dc3ef42ee1e388c0e958719db', ...
    '75e94f2773ccb61c4c4a1962346a91d7a16953012db522a2a3f564247c2937f2'};
cacheRel = { ...
    'reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/TRAIN_DL1018_TRAIN_T1_C15_W14.mat', ...
    'reports/attitude_cm18_a1_20261024/data_preparation_v1/events_all816_v1/VAL_DL1018_VAL_T2_C15_W09.mat'};
cacheSHA = { ...
    '2d87ad8962a243d24c2cb1845e3031e62e723dfa8a8ee0435a01cd90c4368f81', ...
    '29fe6f08c5a1349797bc2ea83c51efc389aa99893e71b91767e2733ace813a49'};
phaseNames = {'STATIC','PRE','EXTEND','HOLD','RETRACT','RECOVERY'};
componentNames = {'nominal_transfer','old_compensation_transfer','gyro_jdot', ...
    'wind','request_gap','realized_gap'};
sceneResults = cell(1,2);

for s = 1:2
    rows = M.rows;
    rowIndex = find(strcmp({rows.scene_id},ids{s}) & strcmp({rows.split},splits{s}));
    assert(numel(rowIndex)==1,'CM18:SceneRow','Pinned scene row is absent or duplicated.');
    row = rows(rowIndex);
    assert(strcmp(row.cache_path,cacheRel{s})&&strcmpi(row.cache_sha256,cacheSHA{s})&& ...
        strcmpi(row.input_sha256.raw_run,rawSHA{s})&&strcmpi(row.input_sha256.run_start,startSHA{s}), ...
        'CM18:ManifestRow','Pinned row inputs differ from the frozen task.');
    rawPath = fullfile(repoRoot,rawRel{s});
    startPath = fullfile(repoRoot,startRel{s});
    cachePath = fullfile(repoRoot,cacheRel{s});
    assert(isfile(rawPath)&&isfile(startPath)&&isfile(cachePath)&& ...
        strcmp(sha256_file(rawPath),rawSHA{s})&&strcmp(sha256_file(startPath),startSHA{s})&& ...
        strcmp(sha256_file(cachePath),cacheSHA{s}), ...
        'CM18:InputSHA','A raw, run_start, or event cache SHA mismatch.');
    cacheInfo = dir(cachePath);
    assert(cacheInfo.bytes==double(row.cache_bytes),'CM18:CacheSize','Cache byte count mismatch.');

    % Only selected cache variables are loaded; no other scene/cache is opened.
    C = load(cachePath,'X18','target_raw','event_time_s','phase_code','plant_index', ...
        'scene_id','split','input_identity','export_meta');
    assert(strcmp(matlab_text(C.scene_id),ids{s})&&strcmp(matlab_text(C.split),splits{s})&& ...
        strcmp(matlab_text(C.input_identity.input_manifest_sha256),M.input_manifest_sha256)&& ...
        strcmp(matlab_text(C.input_identity.raw_run_sha256),rawSHA{s})&& ...
        strcmp(matlab_text(C.input_identity.run_start_sha256),startSHA{s})&& ...
        strcmp(matlab_text(C.input_identity.event_h5_sha256),row.input_sha256.event_h5)&& ...
        strcmp(matlab_text(C.export_meta.status),'PASS')&&logical(C.export_meta.qualified), ...
        'CM18:CacheIdentity','Cache and manifest identities disagree.');
    assert(isequal(size(C.X18),[1999,18])&&isequal(size(C.target_raw),[1999,3])&& ...
        all(isfinite(C.X18),'all')&&all(isfinite(C.target_raw),'all')&& ...
        numel(C.phase_code)==1999&&numel(C.plant_index)==1999, ...
        'CM18:CacheShape','Pinned event cache dimensions are invalid.');

    Rload = load(startPath,'runStart');
    R = Rload.runStart;
    assert(strcmp(matlab_text(R.model_id),'B')&&strcmp(matlab_text(R.contract_version), ...
        'DL1018_V311_R2E_PAPER_FINAL'),'CM18:RunStartIdentity','run_start identity mismatch.');
    savedRawPath = strrep(matlab_text(R.raw_path),'\','/');
    assert(strcmpi(savedRawPath,rawRel{s}),'CM18:RunStartRawPath', ...
        'run_start does not point at the pinned raw file.');
    cfg = R.cfg;
    assert(strcmpi(matlab_text(cfg.controller_morphology_mode),'fixed')&& ...
        strcmpi(matlab_text(cfg.controller_inertia_derivative_mode),'full'), ...
        'CM18:ControllerMode','Fixed nominal/full-Jdot controller mode is required.');
    if istable(R.scene_spec)&&any(strcmp(R.scene_spec.Properties.VariableNames,'scene_id'))
        assert(strcmp(matlab_text(R.scene_spec.scene_id(1)),ids{s}), ...
            'CM18:SceneSpecIdentity','run_start scene_spec identity mismatch.');
    end

    % HDF5 reads are restricted to fields used by the physical label equation and gates.
    sceneTime = read_vector(rawPath,'/scene/time',20001);
    command = read_rows(rawPath,'/scene/arms/command',20001,4);
    rho = read_rows(rawPath,'/scene/arms/rho_true',20001,4);
    rhoDot = read_rows(rawPath,'/scene/arms/rhoDot_true',20001,4);
    time = read_vector(rawPath,'/log/time',20001);
    transitionTime = read_vector(rawPath,'/log/transition_time',20000);
    state = read_rows(rawPath,'/log/state',20001,12);
    eventFlag = read_vector(rawPath,'/log/attitude_event_flag',20000)~=0;
    tauNom = read_rows(rawPath,'/log/attitude_bs_nominal_torque_Nm',20000,3);
    tauComp = read_rows(rawPath,'/log/attitude_compensation_applied_torque_Nm',20000,3);
    requested = read_rows(rawPath,'/log/requested_generalized',20000,4);
    realized = read_rows(rawPath,'/log/realized_generalized',20000,4);
    windTorque = read_rows(rawPath,'/log/wind_torque_B',20000,3);
    controllerWrench = read_rows(rawPath,'/log/controller_clipped_generalized',20000,4);
    controllerClip = abs(controllerWrench-requested)>1e-9;
    allocatorClip = read_rows(rawPath,'/log/generalized_clipped',20000,4)~=0;
    motorSaturated = read_rows(rawPath,'/log/motor_saturated',20000,4)~=0;
    motorTc = double(h5read(rawPath,'/log/motor_time_constant_s'));
    assert(isscalar(motorTc)&&isfinite(motorTc),'CM18:MotorTimeConstant','Invalid logged motor time constant.');
    if isfield(R.opts,'motor_time_constant_s')
        assert(abs(double(R.opts.motor_time_constant_s)-motorTc)<=1e-12, ...
            'CM18:MotorTimeConstant','run_start and raw motor time constants differ.');
    end
    idx = find(eventFlag);
    expectedIdx = (11:10:19991).';
    assert(numel(idx)==1999&&isequal(idx,expectedIdx)&& ...
        max(abs(sceneTime-time))<=1e-12&&max(abs(transitionTime-time(1:20000)))<=1e-12&& ...
        max(abs(C.plant_index(:)-idx))==0&& ...
        max(abs(C.event_time_s(:)-time(idx)))<=1e-12&&all(diff(sceneTime)>0)&& ...
        max(abs(diff(sceneTime)-0.001))<=1e-12, ...
        'CM18:EventAlignment','Raw/cache event schedule or timebase mismatch.');
    assert(all(isfinite([state(:);tauNom(:);tauComp(:);requested(:);realized(:); ...
        windTorque(:);rho(:);rhoDot(:)])),'CM18:Finite','Required raw arrays contain non-finite values.');
    dt = diff(sceneTime);
    zAll = [zeros(1,4);cumsum(command(1:end-1,:).*repmat(dt,1,4),1)];
    maxShapeReconstruction = max(abs(rho-(0.15+0.05*zAll)),[],'all');
    maxRateReconstruction = max(abs(rhoDot-0.05*command),[],'all');

    P0 = simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
    Pc = controller_parameters(cfg,P0,'fixed');
    J0 = double(P0.inertia);
    Jdot0 = double(P0.inertia_dot);
    J0inv = J0\eye(3);
    nominalYawInverseOffdiag = max(abs(J0inv(3,1:2)));
    nominalJdotYawCross = max(abs(Jdot0(3,1:2)));
    nominalControllerInertiaMismatch = max(abs(double(Pc.inertia)-J0),[],'all');
    assert(isequal(size(J0),[3,3])&&isequal(size(Jdot0),[3,3])&&nominalControllerInertiaMismatch<=1e-14, ...
        'CM18:NominalInertia','Nominal inertia dimensions or controller identity invalid.');
    N = numel(idx);
    comp = zeros(N,numel(componentNames));
    alphaBS = zeros(N,3);
    cOld = zeros(N,3);
    gzz = zeros(N,1);
    windZOverJzz = zeros(N,1);
    oldActionSimple = zeros(N,1);
    simpleCandidate = zeros(N,1);
    targetDirect = zeros(N,1);
    yawRowMismatch = zeros(N,1);
    yawInverseRowOffdiag = zeros(N,1);
    jDotYawCross = zeros(N,1);
    requestGapYaw = zeros(N,1);
    realizedGapYaw = zeros(N,1);
    perEventTemplate = struct('plant_index',0,'event_time_s',0,'phase_code',0, ...
        'target_raw_yaw',0,'decomposed_yaw',0,'closure_error',0,'alpha_BS_z',0, ...
        'c_old_z',0,'g_zz',0,'wind_torque_z_over_Jzz',0, ...
        'old_action_simple_term',0,'simple_formula_candidate',0, ...
        'yaw_inverse_row_offdiag_max',0,'jdot_w_yaw',0,'request_gap_yaw',0, ...
        'realized_gap_yaw',0,'components',struct());
    perEvent = repmat(perEventTemplate,N,1);

    for q = 1:N
        k = idx(q);
        w = state(k,10:12).';
        tn = tauNom(k,:).';
        tc = tauComp(k,:).';
        trq = requested(k,2:4).';
        treal = realized(k,2:4).';
        wt = windTorque(k,:).';
        [Ptrue,~] = make_true_plant(cfg,rho(k,:).',rhoDot(k,:).');
        J = double(Ptrue.inertia);
        Jdot = double(Ptrue.inertia_dot);
        gyro0 = cross(w,J0*w);
        gyroTrue = cross(w,J*w);
        alpha = J0\(tn-gyro0-Jdot0*w);
        c = J0\tc;
        dRequest = trq-(tn-tc);
        dRealized = treal-trq;
        invYaw = J\eye(3);
        terms = zeros(1,6);
        vNom = J\(J0*alpha);
        terms(1) = vNom(3)-alpha(3);
        vAction = (J0\tc)-(J\tc);
        terms(2) = vAction(3);
        vGyroJdot = J\(gyro0+Jdot0*w-gyroTrue-Jdot*w);
        terms(3) = vGyroJdot(3);
        vWind = J\wt;
        terms(4) = vWind(3);
        vRequest = J\dRequest;
        terms(5) = vRequest(3);
        vRealized = J\dRealized;
        terms(6) = vRealized(3);
        alphaVirtual = J0\(tn-tc-gyro0-Jdot0*w);
        alphaTrue = J\(treal+wt-gyroTrue-Jdot*w);
        targetDirect(q) = alphaTrue(3)-alphaVirtual(3);
        comp(q,:) = terms;
        alphaBS(q,:) = alpha.';
        cOld(q,:) = c.';
        gzz(q) = J0(3,3)/J(3,3);
        windZOverJzz(q) = wt(3)/J(3,3);
        oldActionSimple(q) = -(gzz(q)-1)*c(3);
        vJdot = Jdot*w;
        jDotYawCross(q) = vJdot(3);
        simpleCandidate(q) = (gzz(q)-1)*(alpha(3)-c(3))+ ...
            (gyro0(3)-gyroTrue(3)-vJdot(3)+wt(3))/J(3,3);
        yawInverseRowOffdiag(q) = max(abs(invYaw(3,1:2)));
        yawRowMismatch(q) = max(abs(Pc.allocation.C(4,:)-Ptrue.allocation.C(4,:)));
        requestGapYaw(q) = vRequest(3);
        realizedGapYaw(q) = vRealized(3);
        perEvent(q).plant_index = k;
        perEvent(q).event_time_s = time(k);
        perEvent(q).phase_code = C.phase_code(q);
        perEvent(q).target_raw_yaw = C.target_raw(q,3);
        perEvent(q).decomposed_yaw = sum(terms);
        perEvent(q).closure_error = sum(terms)-C.target_raw(q,3);
        perEvent(q).alpha_BS_z = alpha(3);
        perEvent(q).c_old_z = c(3);
        perEvent(q).g_zz = gzz(q);
        perEvent(q).wind_torque_z_over_Jzz = windZOverJzz(q);
        perEvent(q).old_action_simple_term = oldActionSimple(q);
        perEvent(q).simple_formula_candidate = simpleCandidate(q);
        perEvent(q).yaw_inverse_row_offdiag_max = yawInverseRowOffdiag(q);
        perEvent(q).jdot_w_yaw = jDotYawCross(q);
        perEvent(q).request_gap_yaw = requestGapYaw(q);
        perEvent(q).realized_gap_yaw = realizedGapYaw(q);
        for j = 1:numel(componentNames),perEvent(q).components.(componentNames{j})=terms(j);end
    end

    cacheYaw = double(C.target_raw(:,3));
    closure = comp*ones(numel(componentNames),1)-cacheYaw;
    directClosure = targetDirect-cacheYaw;
    requestClosure = requested(idx,2:4)-(tauNom(idx,:)-tauComp(idx,:));
    realizedClosure = realized(idx,2:4)-requested(idx,2:4);
    maxLabelClosure = max(abs(closure));
    maxDirectClosure = max(abs(directClosure));
    maxAlphaFeature = max(abs(alphaBS-C.X18(:,4:6)),[],'all');
    maxRequestClosure = max(abs(requestClosure),[],'all');
    maxRealizedGap = max(abs(realizedClosure),[],'all');
    maxRequestYawGap = max(abs(requestGapYaw));
    maxRealizedYawGap = max(abs(realizedGapYaw));
    maxJdot0 = max(abs(Jdot0),[],'all');
    noControllerClip = ~any(controllerClip(idx,:),'all');
    controllerAllocatorClipCrosscheck = struct(...
        'event_component_count',numel(idx)*4, ...
        'inferred_controller_clip_count',nnz(controllerClip(idx,:)), ...
        'allocator_boolean_clip_count',nnz(allocatorClip(idx,:)), ...
        'both_clip_count',nnz(controllerClip(idx,:)&allocatorClip(idx,:)), ...
        'controller_only_count',nnz(controllerClip(idx,:)&~allocatorClip(idx,:)), ...
        'allocator_only_count',nnz(~controllerClip(idx,:)&allocatorClip(idx,:)));
    noYawControllerClip = ~any(controllerClip(idx,4));
    noYawAllocatorClip = ~any(allocatorClip(idx,4));
    noAllocatorClip = ~any(allocatorClip(idx,:),'all');
    noMotorSaturation = ~any(motorSaturated(idx,:),'all');
    motorTcZero = abs(motorTc)<=1e-12;
    nominalJdotZero = maxJdot0<=1e-14;
    yawRowSame = max(yawRowMismatch)<=1e-12;
    yawInverseDecoupled = max(yawInverseRowOffdiag)<=1e-12;
    nominalYawInverseDecoupled = nominalYawInverseOffdiag<=1e-12;
    noRequestGap = maxRequestClosure<=1e-8;
    noRealizedGap = maxRealizedGap<=1e-8;
    noRequestYawGap = maxRequestYawGap<=1e-8;
    noRealizedYawGap = maxRealizedYawGap<=1e-8;
    simpleApplicable = nominalJdotZero&&nominalYawInverseDecoupled&&yawInverseDecoupled&&yawRowSame&& ...
        noYawControllerClip&&noYawAllocatorClip&&motorTcZero&&noRequestYawGap&&noRealizedYawGap;
    maxSimpleClosure = max(abs(simpleCandidate-cacheYaw));
    if simpleApplicable
        assert(maxSimpleClosure<=1e-8,'CM18:SimpleFormulaClosure', ...
            'Simple yaw formula preconditions passed but its cache closure failed.');
    end
    assert(maxLabelClosure<=1e-8&&maxDirectClosure<=1e-8&&maxAlphaFeature<=1e-7, ...
        'CM18:LabelClosure','Full-matrix decomposition/direct physics/cache closure failed.');
    assert(all(C.phase_code(:)>=0&C.phase_code(:)<=5),'CM18:Phase','Invalid cache phase code.');
    for q = 1:N,perEvent(q).closure_error = closure(q);end

    preconditions = struct('nominal_jdot_zero',nominalJdotZero, ...
        'max_abs_nominal_jdot',maxJdot0,'nominal_jdot_yaw_xy_max_abs',nominalJdotYawCross, ...
        'nominal_controller_inertia_matches_nominal_plant',nominalControllerInertiaMismatch<=1e-14, ...
        'nominal_inverse_yaw_row_decoupled_from_xy',nominalYawInverseDecoupled, ...
        'max_abs_nominal_inverse_yaw_xy_entry',nominalYawInverseOffdiag, ...
        'controller_allocator_yaw_row_matches_true_plant',yawRowSame, ...
        'max_abs_yaw_row_difference',max(yawRowMismatch), ...
        'true_inverse_yaw_row_decoupled_from_xy',yawInverseDecoupled, ...
        'max_abs_true_inverse_yaw_xy_entry',max(yawInverseRowOffdiag), ...
        'yaw_controller_clipping_inferred_from_wrench_gap_absent',noYawControllerClip, ...
        'yaw_allocator_clipping_absent',noYawAllocatorClip, ...
        'controller_clipping_inferred_from_wrench_gap_absent',noControllerClip, ...
        'controller_vs_allocator_clip_crosscheck',controllerAllocatorClipCrosscheck, ...
        'allocator_generalized_clipping_absent',noAllocatorClip, ...
        'motor_saturation_absent',noMotorSaturation,'motor_time_constant_zero',motorTcZero, ...
        'motor_time_constant_s',motorTc,'requested_equals_nominal_minus_compensation',noRequestGap, ...
        'max_abs_request_closure_Nm',maxRequestClosure, ...
        'max_abs_request_yaw_gap_rad_s2',maxRequestYawGap, ...
        'max_abs_realized_yaw_gap_rad_s2',maxRealizedYawGap, ...
        'realized_equals_requested',noRealizedGap,'max_abs_realized_request_gap_Nm',maxRealizedGap, ...
        'simple_formula_applicable',simpleApplicable, ...
        'simple_formula_candidate_max_abs_cache_error_rad_s2',maxSimpleClosure, ...
        'general_full_matrix_equation_used',true);
    phaseSummary = summarize_phases(C.phase_code,comp,cacheYaw,closure,phaseNames,componentNames);
    overallSummary = summarize_group('ALL',-1,true(size(cacheYaw)),comp,cacheYaw,closure,componentNames);
    for q = 1:N
        perEvent(q).decomposed_yaw = sum(comp(q,:));
    end
    sceneResult = struct('scene_id',ids{s},'split',splits{s}, ...
        'raw_path',rawRel{s},'raw_sha256',rawSHA{s},'run_start_path',startRel{s}, ...
        'run_start_sha256',startSHA{s},'cache_path',cacheRel{s},'cache_sha256',cacheSHA{s}, ...
        'event_count',N,'plant_index_first_last',[idx(1),idx(end)], ...
        'motor_time_constant_s',motorTc,'nominal_inertia_kg_m2',J0, ...
        'nominal_inertia_dot_max_abs_kg_m2_s',maxJdot0, ...
        'max_abs_shape_reconstruction_m',maxShapeReconstruction, ...
        'max_abs_rate_reconstruction_mps',maxRateReconstruction, ...
        'max_abs_request_closure_Nm',maxRequestClosure, ...
        'max_abs_realized_request_gap_Nm',maxRealizedGap, ...
        'max_abs_label_closure_rad_s2',maxLabelClosure, ...
        'max_abs_direct_physics_vs_cache_rad_s2',maxDirectClosure, ...
        'preconditions',preconditions,'component_names',{componentNames}, ...
        'overall_summary',overallSummary,'phase_summary',phaseSummary, ...
        'event_records',perEvent);
    sceneResults{s} = sceneResult;
end

report = struct('schema','CM18_TWO_SCENE_LABEL_DECOMPOSITION_V2', ...
    'status','PASS','taskbook_path',taskbookRel, ...
    'taskbook_sha256','65c3f3d0634a6331842d6b59917ce83a040435d27d15f8aec859a48eb376f44b', ...
    'dataset_manifest_path',manifestRel, ...
    'dataset_manifest_sha256','7dd3e1f786f6095ecc2ba56473e5cf0fab6b92cdd42e38a184d6ad1223f36271', ...
    'source_path',strrep(mfilename('fullpath'),[repoRoot filesep],''), ...
    'source_sha256',sha256_file([mfilename('fullpath') '.m']), ...
    'physical_helper_sources',helperRows, ...
    'scope',struct('scene_ids',{ids},'training_steps',0,'optimizer_steps',0, ...
        'plant_calls',0,'engine_calls',0,'TEST_accessed',false, ...
        'reads_only_pinned_raw_fields',true, ...
        'label_interpretation','target_raw is alphaTrue-alphaVirtual; tauComp is the applied legacy behavior action, not a defective implementation.'), ...
    'method',struct('decomposition','Exact full-matrix equation with separately logged request and realized-torque gaps.', ...
        'component_order',{componentNames},'simple_diagonal_formula_used_only_if_all_gates_pass',true, ...
        'controller_clipping_inference','abs(controller_clipped_generalized-requested_generalized)>1e-9; cross-tabulated against generalized_clipped allocator booleans.', ...
        'controller_field_semantics_limit','Raw files do not embed field provenance. V2 follows runtime assignment of a.clipped_generalized as numeric clipped wrench and infers clipping from its gap to requested_generalized. V1 misread the numeric wrench as a boolean flag; this was a diagnostic interpretation error, not evidence of a controller defect.', ...
        'rms_rule','RMS values are not additive; per-component second moments and all pairwise mean products are reported.', ...
        'causal_limit','Nonzero wind/action terms show contributions to this label only; they do not show alphaXY encodes them or caused A2 offline VAL degradation.'), ...
    'scenes',{sceneResults});
jsonText = jsonencode(report,'PrettyPrint',true);
fid = fopen(outputPath,'w');
assert(fid>=0,'CM18:OutputOpen','Could not create new report file.');
closer = onCleanup(@()fclose(fid));
fwrite(fid,jsonText,'char');
clear closer
end

function [P,Jdot] = make_true_plant(cfg,rho,rhoDot)
P = simulation_parameters(cfg,rho,rhoDot);
Jdot = P.inertia_dot;
end

function value = read_vector(filePath,datasetPath,expectedLength)
value = double(h5read(filePath,datasetPath));
value = value(:);
assert(numel(value)==expectedLength&&all(isfinite(value)), ...
    'CM18:H5Vector','Unexpected HDF5 vector size or non-finite value: %s',datasetPath);
end

function value = read_rows(filePath,datasetPath,nRows,nCols)
value = double(h5read(filePath,datasetPath));
if isequal(size(value),[nCols,nRows]),value=value.';end
assert(isequal(size(value),[nRows,nCols])&&all(isfinite(value),'all'), ...
    'CM18:H5Rows','Unexpected HDF5 row matrix or non-finite value: %s',datasetPath);
end

function text = matlab_text(value)
if ischar(value)
    text = strtrim(value);
elseif isstring(value)
    assert(isscalar(value),'CM18:Text','Expected scalar MATLAB text.');
    text = char(value);
elseif iscell(value)&&numel(value)==1
    text = matlab_text(value{1});
elseif isnumeric(value)&&isvector(value)
    text = char(value(:).');
else
    error('CM18:Text','Unsupported MATLAB text representation.');
end
text = strtrim(text);
end

function summary = summarize_phases(phase,components,target,residual,phaseNames,componentNames)
summary = summarize_group(phaseNames{1},0,phase(:)==0,components,target,residual,componentNames);
for p = 1:numel(phaseNames)-1
    summary(p+1) = summarize_group(phaseNames{p+1},p,phase(:)==p,components,target,residual,componentNames);
end
end

function summary = summarize_group(name,phaseCode,mask,components,target,residual,componentNames)
mask = mask(:);
values = components(mask,:);
y = target(mask);
r = residual(mask);
n = numel(y);
stats = repmat(struct('name','','mean',[],'second_moment',[],'rms',[]),1,numel(componentNames));
for j = 1:numel(componentNames)
    stats(j).name = componentNames{j};
    if n>0
        stats(j).mean = mean(values(:,j));
        stats(j).second_moment = mean(values(:,j).^2);
        stats(j).rms = sqrt(stats(j).second_moment);
    end
end
pairs = struct('first','','second','','mean_product',[]);
pairs = repmat(pairs,0,1);
expandedSecondMoment = [];
if n>0
    expandedSecondMoment = sum(mean(values.^2,1));
    for i = 1:size(values,2)
        for j = i+1:size(values,2)
            p = struct('first',componentNames{i},'second',componentNames{j}, ...
                'mean_product',mean(values(:,i).*values(:,j)));
            pairs(end+1,1) = p; %#ok<AGROW>
            expandedSecondMoment = expandedSecondMoment+2*p.mean_product;
        end
    end
end
if n>0
    targetMean = mean(y);
    targetSecondMoment = mean(y.^2);
    targetRMS = sqrt(targetSecondMoment);
    residualMax = max(abs(r));
    secondMomentError = expandedSecondMoment-targetSecondMoment;
else
    targetMean = [];targetSecondMoment = [];targetRMS = [];residualMax = [];secondMomentError = [];
end
summary = struct('phase',name,'phase_code',phaseCode,'event_count',n, ...
    'components',stats,'pairwise_mean_products',pairs, ...
    'expanded_sum_second_moment',expandedSecondMoment, ...
    'target_mean',targetMean,'target_second_moment',targetSecondMoment, ...
    'target_rms',targetRMS,'second_moment_expansion_error',secondMomentError, ...
    'max_abs_closure_residual',residualMax);
end

function digest = sha256_file(path)
fid = fopen(path,'rb');
assert(fid>=0,'CM18:HashOpen','Cannot open file for SHA256: %s',path);
closer = onCleanup(@()fclose(fid));
md = java.security.MessageDigest.getInstance('SHA-256');
while true
    bytes = fread(fid,1024*1024,'*uint8');
    if isempty(bytes),break;end
    md.update(typecast(bytes,'int8'));
end
raw = typecast(md.digest(),'uint8');
digest = lower(reshape(dec2hex(raw,2).',1,[]));
clear closer
end


