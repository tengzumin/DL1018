function log=run_mlp15_dev72_closed_loop(s,cfg,opts)
    % FUNCTION:
    %   run_gate_holdout_closed_loop
    % PURPOSE:
    %   按选定基线、场景和选项执行闭环仿真，并记录状态、参考、控制输入及诊断信号。
    % INPUT:
    %   s: DL1018_GATE_INSPECTION_HOLDOUT_V1 scene payload.
    %   cfg: Plant/configuration bound to the selected geometry arm.
    %   opts: Exact C5 options plus gate arm and identity lock.
    %   log: Full closed-loop state, control, safety, and observer trace.
    % OUTPUT:
    %   log: 闭环时序与诊断日志。
    %RUN_GATE_HOLDOUT_CLOSED_LOOP Derived shared C5 loop; Plant advances here.
    if nargin<3,opts=struct;end
    assert(isstruct(opts)&&all(isfield(opts,{'gate_attitude_arm','gate_geometry_arm','gate_identity_lock'})), ...
        'GATE:Options','Missing gate arm, geometry arm, or identity lock.');
    gateAttitudeArm=upper(char(opts.gate_attitude_arm));
    gateGeometryArm=upper(char(opts.gate_geometry_arm));
    isolatedRoot=fileparts(fileparts(fileparts(mfilename('fullpath'))));
    folders={'core','models','runtime','scenes'};
    for folder=folders
        sourceDir=fullfile(isolatedRoot,'matlab',folder{1});
        entries=dir(fullfile(sourceDir,'*.m'));
        for entry=entries.'
            [~,name]=fileparts(entry.name);
            assert(strcmpi(which(name),fullfile(sourceDir,entry.name)), ...
                'PAIRED:SourcePath','An isolated function resolves outside paired_runner: %s.',name);
        end
    end
    gateArmSpec=gate_attitude_arm_spec(gateAttitudeArm);
    assert(ismember(gateGeometryArm,{'ACTIVE','FIXED_MIN','FIXED_BOUND15'}), ...
        'GATE:GeometryArm','Unknown geometry arm.');
    gateFeedforwardEnabled=gateArmSpec.feedforward_enabled;
    gateObserverEnabled=gateArmSpec.observer_enabled;
    rbfAttitudeArm=gateArmSpec.rbf_enabled;
    physCandidate=~rbfAttitudeArm;
    physicsHelperActive=gateArmSpec.physics_helper_enabled;
    tcnCandidate=strcmp(gateAttitudeArm,'DL_TCN');
    mlpCandidate=strcmp(gateAttitudeArm,'DL_MLP15');
    learnedCandidate=tcnCandidate||mlpCandidate;
    assert(~physicsHelperActive&&(~learnedCandidate||physCandidate), ...
        'GATE:NoInertiaModel','A learned release cannot enable the inertia-reconstruction helper.');
    method='B2-RBF-Full-SPLIT';
    sceneAudit=gate_holdout_validate_dev72_scene(s,cfg,gateGeometryArm);
    positionDelayedPredictionFlag=field_or(opts,'position_delayed_prediction_enabled',false);
    assert((islogical(positionDelayedPredictionFlag)&&isscalar(positionDelayedPredictionFlag))|| ...
        (isnumeric(positionDelayedPredictionFlag)&&isreal(positionDelayedPredictionFlag)&& ...
        isscalar(positionDelayedPredictionFlag)&&isfinite(double(positionDelayedPredictionFlag))&& ...
        ismember(double(positionDelayedPredictionFlag),[0,1])), ...
        'DelayedPrediction:Flag','position_delayed_prediction_enabled must be logical or numeric scalar 0/1.');
    positionDelayedPredictionEnabled=logical(positionDelayedPredictionFlag);
    % Legacy baselines retain M=I semantics; the delayed C5 candidate must set M110 explicitly.
    positionCoordinateMaskFlag=field_or(opts,'position_coordinate_mask',[1;1;1]);
    assert((islogical(positionCoordinateMaskFlag)&&numel(positionCoordinateMaskFlag)==3)|| ...
        (isnumeric(positionCoordinateMaskFlag)&&isreal(positionCoordinateMaskFlag)&& ...
        numel(positionCoordinateMaskFlag)==3&&all(isfinite(double(positionCoordinateMaskFlag(:))))&& ...
        all(ismember(double(positionCoordinateMaskFlag(:)),[0,1]))), ...
        'C5Coordinate:Mask','position_coordinate_mask must be a finite three-element binary vector.');
    positionCoordinateMask=double(positionCoordinateMaskFlag(:));
    assert(positionDelayedPredictionEnabled&&isequal(positionCoordinateMask,[1;1;0]), ...
        'PAIRED:C5','Both arms require C5 delayed prediction and M110.');
    if positionDelayedPredictionEnabled
        assert(isfield(opts,'position_coordinate_mask'),'C5Coordinate:Required', ...
            'C5 delayed prediction requires an explicit three-element coordinate mask.');
    end
    assert(strcmp(method,'B2-RBF-Full-SPLIT')&&abs(cfg.plant.dt-.001)<1e-12, ...
        'RBFBS:A1Only','This standalone package only runs 1-kHz-plant A1-Full-100Hz backstepping.');
    arm=char(field_or(opts,'paired_arm',''));
    assert(strcmp(arm,gateArmSpec.paired_arm)&& ...
        strcmp(char(field_or(opts,'paired_position_method_id','')), ...
        'C5_AXIS_MIXED_COORDINATE_M110'), ...
        'GATE:C5Method','Expected the frozen C5 M110 options for this attitude arm.');
    assert(isfield(opts,'stage1_position_runtime')&& ...
        isfield(opts.stage1_position_runtime,'model'), ...
        'GATE:C5Model','Missing frozen C5 position model.');
    [expectedBaseline,expectedCandidate]=make_paired_c5_options( ...
        cfg,opts.stage1_position_runtime.model);
    if tcnCandidate
        assert(all(isfield(opts,{'tcn_attitude_model','tcn_attitude_model_sha256'})), ...
            'GATE:TCNOptions','DL_TCN requires a frozen model and model SHA.');
        expected=make_gate_holdout_options(cfg,opts.stage1_position_runtime.model, ...
            gateAttitudeArm,gateGeometryArm,struct,opts.tcn_attitude_model, ...
            opts.tcn_attitude_model_sha256);
        expected=rmfield(expected,{'gate_attitude_arm','gate_geometry_arm','gate_identity_lock'});
    elseif mlpCandidate
        assert(all(isfield(opts,{'mlp15_attitude_model','mlp15_attitude_model_sha256'})), ...
            'GATE:MLP15Options','DL_MLP15 requires a frozen model and model SHA.');
        expected=make_gate_holdout_options(cfg,opts.stage1_position_runtime.model, ...
            gateAttitudeArm,gateGeometryArm,struct,opts.mlp15_attitude_model, ...
            opts.mlp15_attitude_model_sha256);
        expected=rmfield(expected,{'gate_attitude_arm','gate_geometry_arm','gate_identity_lock'});
    elseif physCandidate
        expected=expectedCandidate;
    else
        expected=expectedBaseline;
    end
    effectiveOptions=rmfield(opts,{'gate_attitude_arm','gate_geometry_arm','gate_identity_lock'});
    assert(isequaln(effectiveOptions,expected),'GATE:ExactOptions', ...
        'Effective C5 options differ from the frozen paired C5 builder.');
    gateIdentityHashes=gate_holdout_identity_hashes( ...
        cfg,opts.stage1_position_runtime.model,opts);
    assert(isequaln(opts.gate_identity_lock,gateIdentityHashes), ...
        'GATE:IdentityLock','Gate identity lock does not match recomputed C5/geometry hashes.');
    formalRbfBaseline=logical(field_or(opts,'formal_rbf_baseline',false));
    assert(isscalar(formalRbfBaseline),'RBFBS0:FormalBaselineFlag','formal_rbf_baseline must be scalar.');
    attitudeFusion=field_or(opts,'attitude_fusion_v3_6',struct);
    attitudeFusionActive=isstruct(attitudeFusion)&&logical(field_or(attitudeFusion,'enabled',false));
    attitudeFusionLambda=0;attitudeFusionModel=struct;attitudeFusionInputDim=0;
    attitudeHeadCfg=field_or(opts,'attitude_head_v39',struct);
    attitudeHeadEnabled=isstruct(attitudeHeadCfg)&&logical(field_or(attitudeHeadCfg,'enabled',false));
    attitudeHeadDeltaW=zeros(33,3);attitudeHeadAuditCount=0;
    if isfield(opts,'attitude_head_v39')
        assert(isequal(double(field_or(attitudeHeadCfg,'gamma',NaN)),0.002)&& ...
            isequal(double(field_or(attitudeHeadCfg,'sigma_per_s',NaN)),0.02)&& ...
            isequal(double(field_or(attitudeHeadCfg,'projection_fro',NaN)),0.20), ...
            'X23V38:HeadConfiguration','Only the preregistered fixed Head parameters are allowed.');
    end
    if attitudeFusionActive
        assert(isfield(attitudeFusion,'model')&&isstruct(attitudeFusion.model)&& ...
            all(isfield(attitudeFusion.model,{'architecture','input_dim','input_mu','input_sigma','dmax','knots','params'})), ...
            'PCF36:FusionModel','The frozen attitude model is incomplete.');
        attitudeFusionModel=attitudeFusion.model;
        attitudeFusionLambda=double(field_or(attitudeFusion,'lambda',NaN));
        attitudeFusionInputDim=double(attitudeFusionModel.input_dim);
        assert(ismember(attitudeFusionLambda,[0 1])&&ismember(attitudeFusionInputDim,[23 29 33])&& ...
            isequal(size(attitudeFusionModel.input_mu),[attitudeFusionInputDim 1])&& ...
            isequal(size(attitudeFusionModel.input_sigma),[attitudeFusionInputDim 1])&&numel(attitudeFusionModel.dmax)==3, ...
            'PCF36:FusionContract','Fusion lambda or legal input dimensions violate the V3.6 contract.');
    end
    stage1PositionRuntime=field_or(opts,'stage1_position_runtime',struct);
    stage1PositionActive=isstruct(stage1PositionRuntime)&&logical(field_or(stage1PositionRuntime,'enabled',false));
    pcfCoordination=field_or(stage1PositionRuntime,'command_filter_coordination_v3_5',struct);
    pcfCoordinationEnabled=isstruct(pcfCoordination)&&logical(field_or(pcfCoordination,'enabled',false));
    if pcfCoordinationEnabled
        assert(stage1PositionActive, ...
            'PCF35:RuntimeContract','PCF coordination requires an active position KAN; the Head may be frozen.');
    end
    if attitudeFusionActive
        if attitudeFusionLambda==1
            rbfAllowed=~logical(field_or(opts,'rbf_attitude_enabled',true))&& ...
                ~logical(field_or(opts,'rbf_attitude_output_enabled',true))&& ...
                ~logical(field_or(opts,'rbf_attitude_update_enabled',true));
        else
            rbfAllowed=logical(field_or(opts,'rbf_attitude_enabled',true))&& ...
                logical(field_or(opts,'rbf_attitude_output_enabled',true))&& ...
                logical(field_or(opts,'rbf_attitude_update_enabled',true));
        end
        assert(formalRbfBaseline&&rbfAllowed&&(~stage1PositionActive||pcfCoordinationEnabled), ...
            'PCF36:FusionIsolation','V3.11 fusion requires fixed BS/RBF isolation and the original PCF when its position Head is active.');
    end
    fixedController=[];
    if formalRbfBaseline
        fixedPlant=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
        fixedController=controller_parameters(cfg,fixedPlant,'fixed');
        assert(strcmp(fixedController.morphology_mode,'fixed')&& ...
            max(abs(fixedController.arm_lengths-cfg.plant.arm_initial))<1e-12&& ...
            all(isfinite(fixedController.allocation.C),'all')&&all(isfinite(fixedController.inertia),'all'), ...
            'RBFBS0:FixedControllerModel','Formal BS/RBF requires finite fixed initial-arm C0/J0.');
    end
    assert(formalRbfBaseline&&isfield(cfg,'attitude_replacement')&& ...
        isfield(cfg.attitude_replacement,'J0_controller_fixed_kgm2')&& ...
        isfield(cfg.attitude_replacement,'J0_controller_fixed_sha256'), ...
        'PAIRED:J0Config','Missing explicit frozen controller J0 identity.');
    J0frozen=double(cfg.attitude_replacement.J0_controller_fixed_kgm2);
    J0sha=char(cfg.attitude_replacement.J0_controller_fixed_sha256);
    assert(isequal(size(J0frozen),[3,3])&&isequal(J0frozen,double(fixedController.inertia))&& ...
        strcmpi(J0sha,paired_sha256_double(J0frozen))&& ...
        strcmpi(J0sha,paired_sha256_double(double(fixedController.inertia))), ...
        'PAIRED:J0Identity','Frozen helper J0 differs from fixed controller J0 or SHA.');
    rlGapRuntime=field_or(opts,'rl_gap_runtime',struct);
    rlGapRuntimeEnabled=isstruct(rlGapRuntime)&&logical(field_or(rlGapRuntime,'enabled',false));
    rlGapRuntimeStepFn=[];
    if rlGapRuntimeEnabled
        assert(isfield(rlGapRuntime,'step_fn')&&isa(rlGapRuntime.step_fn,'function_handle'), ...
            'RLV023:RuntimeHook','Enabled RL gap runtime requires a step_fn function handle.');
        rlGapRuntimeStepFn=rlGapRuntime.step_fn;
    end
    dt=cfg.plant.dt;
    positionNdo=field_or(opts,'position_ndo',struct);
    positionNdoEnabled=isstruct(positionNdo)&&logical(field_or(positionNdo,'enabled',false));
    positionNdoMode='off';
    positionNdoInputMode='requested';
    positionNdoReconstructionEnabled=false;
    positionNdoDecomposition=field_or(positionNdo,'decomposition',struct);
    positionNdoDecompositionEnabled=isstruct(positionNdoDecomposition)&&logical(field_or(positionNdoDecomposition,'enabled',false));
    positionNdoSlowTau=double(field_or(positionNdoDecomposition,'slow_time_constant_s',.5));
    positionNdoLambda=NaN;
    positionNdoFrequency=1/dt;
    positionNdoOutputLimit=Inf;
    positionNdoZeroOutputInitialization=false;
    if positionNdoEnabled
        positionNdoMode=lower(char(field_or(positionNdo,'mode','')));
        positionNdoInputMode=lower(char(field_or(positionNdo,'input_mode','requested')));
        positionNdoReconstructionEnabled=ismember(positionNdoInputMode, ...
            {'nominal_reconstructed','mode_reconstructed'});
        positionNdoLambda=double(field_or(positionNdo,'lambda_s_inv',NaN));
        positionNdoFrequency=double(field_or(positionNdo,'frequency_hz',1/dt));
        positionNdoOutputLimit=double(field_or(positionNdo,'output_limit_N',Inf));
        positionNdoZeroOutputInitialization=logical(field_or(positionNdo,'initialize_zero_output',false));
        assert(ismember(positionNdoMode,{'ndo_only','rbf_residual'})&& ...
            ismember(positionNdoInputMode,{'requested','realized','nominal_reconstructed','mode_reconstructed'})&& ...
            isscalar(positionNdoLambda)&&isfinite(positionNdoLambda)&&positionNdoLambda>0&& ...
            isscalar(positionNdoFrequency)&&isfinite(positionNdoFrequency)&&positionNdoFrequency>0&&positionNdoFrequency<=1/dt, ...
            'RBFBS:PositionNdoConfig','Enabled Position NDO requires a valid mode, positive gain, and frequency in (0,1/dt].');
        assert(isscalar(positionNdoOutputLimit)&& ...
            (isinf(positionNdoOutputLimit)||isfinite(positionNdoOutputLimit))&&positionNdoOutputLimit>0, ...
            'RBFBS:PositionNdoOutputLimit','Position NDO output limit must be positive or Inf.');
        assert(positionNdoLambda/positionNdoFrequency<2,'RBFBS:PositionNdoEulerPole', ...
            'Forward-Euler NDO requires lambda/frequency_hz<2.');
    end
    positionSmcEnabled=logical(field_or(opts,'position_smc_enabled',false));
    positionSmc=field_or(opts,'position_smc',struct);
    positionSmcLambda=double(field_or(positionSmc,'lambda_s_inv',NaN));
    positionSmcGain=double(field_or(positionSmc,'gain_N',NaN));
    positionSmcBoundary=double(field_or(positionSmc,'boundary_layer_mps',NaN));
    if positionSmcEnabled
        assert(positionNdoEnabled&&strcmp(positionNdoMode,'ndo_only')&& ...
            isscalar(positionSmcLambda)&&isfinite(positionSmcLambda)&&positionSmcLambda>0&& ...
            isscalar(positionSmcGain)&&isfinite(positionSmcGain)&&positionSmcGain>0&& ...
            isscalar(positionSmcBoundary)&&isfinite(positionSmcBoundary)&&positionSmcBoundary>0, ...
            'RBFBS:PositionSmcConfig','Position SMC requires Position NDO-only and positive finite Lambda, gain, and boundary layer.');
    end
    assert(~positionNdoEnabled&&~positionSmcEnabled, ...
        'RBFBS0:ExtraCompensation','RBF-BS0 禁止启用 NDO 或 SMC。');
    if strcmp(positionNdoInputMode,'realized')||positionNdoReconstructionEnabled
        assert(positionNdoEnabled&&strcmp(positionNdoMode,'ndo_only')&&~positionNdoDecompositionEnabled&& ...
            (~positionSmcEnabled||strcmp(positionNdoInputMode,'nominal_reconstructed')), ...
            'RBFBS:PositionNdoRealizedMode','Only nominal-reconstructed NDO may be paired with Position SMC; decomposition remains isolated.');
    end
    if positionNdoDecompositionEnabled
        assert(positionNdoEnabled&&strcmp(positionNdoMode,'ndo_only')&&strcmp(positionNdoInputMode,'requested')&& ...
            ~positionSmcEnabled&&isscalar(positionNdoSlowTau)&&isfinite(positionNdoSlowTau)&&positionNdoSlowTau>0, ...
            'RBFBS:PositionNdoDecomposition','Decomposition requires requested-input NDO-only, no SMC, and a positive slow time constant.');
    end
    adaptiveBasisCollect=logical(field_or(opts,'adaptive_basis_collect',false));
    adaptiveBasisInferFn=[];
    if isfield(opts,'adaptive_basis_inference_fn'),adaptiveBasisInferFn=opts.adaptive_basis_inference_fn;end
    tcnResidualInferFn=[];
    if isfield(opts,'tcn_residual_inference_fn'),tcnResidualInferFn=opts.tcn_residual_inference_fn;end
    tcnResidualActive=~isempty(tcnResidualInferFn);
    assert(~(tcnResidualActive&&(adaptiveBasisCollect||~isempty(adaptiveBasisInferFn))), ...
        'TCN0924:TcnResidualMode','Direct TCN residual inference cannot share the adaptive-basis callback path.');
    motorTimeConstant=double(field_or(opts,'motor_time_constant_s',0));
    assert(isscalar(motorTimeConstant)&&isfinite(motorTimeConstant)&&motorTimeConstant>=0&&motorTimeConstant<=.2, ...
        'TCN0924:MotorTimeConstant','Motor time constant must be finite and between 0 and 0.2 seconds.');
    adaptiveBasisActive=adaptiveBasisCollect||~isempty(adaptiveBasisInferFn)||tcnResidualActive;
    adaptiveTorqueInferFn=[];
    if isfield(opts,'adaptive_torque_inference_fn'),adaptiveTorqueInferFn=opts.adaptive_torque_inference_fn;end
    adaptiveTorqueActive=~isempty(adaptiveTorqueInferFn);
    adaptiveBasisHead=struct;
    if adaptiveBasisActive
        collectorMethod=adaptiveBasisCollect&&strcmp(method,'B2-RBF-Full-SPLIT');
        tcnResidualMethod=tcnResidualActive&&strcmp(method,'B2-RBF-Full-SPLIT');
        assert((strcmp(method,'B2-RBF-Att')||collectorMethod||tcnResidualMethod)&&abs(dt-.001)<1e-12, ...
            'TCN0924:AdaptiveBasisRuntime','Adaptive features require A0, A1 collection, or direct A1 TCN residual inference on the 1-kHz Plant.');
        assert(isempty(adaptiveBasisInferFn)||isa(adaptiveBasisInferFn,'function_handle'), ...
            'TCN0924:AdaptiveBasisInference','Inference must be a function handle.');
        if tcnResidualActive
            assert(isa(tcnResidualInferFn,'function_handle')&&ismember(method,{'B2-RBF-Full-SPLIT'}), ...
                'TCN0924:TcnResidualInference','Direct TCN residual inference requires A1-Full-100 and a function handle.');
        elseif ~adaptiveBasisCollect&&~isempty(adaptiveBasisInferFn)
            assert(isfield(opts,'adaptive_basis_head')&&isequal(size(opts.adaptive_basis_head.weight),[17,3]), ...
                'TCN0924:AdaptiveBasisHead','Learned inference requires the shared 17x3 adaptive head.');
            adaptiveBasisHead=opts.adaptive_basis_head;
        end
    end
    adaptiveTorqueHead=struct;
    if adaptiveTorqueActive
        assert(adaptiveBasisActive&&~adaptiveBasisCollect&&strcmp(method,'B2-RBF-Att')&& ...
            isa(adaptiveTorqueInferFn,'function_handle')&&isfield(opts,'adaptive_torque_head')&& ...
            isequal(size(opts.adaptive_torque_head.weight),[17,3]), ...
            'TCN0924:AdaptiveTorqueRuntime','Dual learned Force/Torque requires independent inference functions and 17x3 heads on A0-100.');
        adaptiveTorqueHead=opts.adaptive_torque_head;
    end
    widthScaleFn=[];
    if isfield(opts,'rbf_position_width_scale_fn')
        widthScaleFn=opts.rbf_position_width_scale_fn;
        assert(isa(widthScaleFn,'function_handle') && ...
            (strcmp(method,'B2-RBF-Full') || ismember(method,{'B2-RBF-Full-250','B2-RBF-Full-200','B2-RBF-Full-400','B2-RBF-Full-SPLIT'})), ...
            'TCN0916:RbfWidthHook','Position width hook is only supported by Formal A1 full/scheduled variants.');
    end
    positionDeepBasisFn=[];
    positionBasisMode=lower(char(field_or(opts,'rbf_position_basis_mode','gaussian')));
    positionDeepDim=double(field_or(opts,'rbf_position_deep_dim',8));
    positionBasisBeta=double(field_or(opts,'rbf_position_basis_beta',0));
    positionDeepGammaScale=double(field_or(opts,'rbf_position_deep_gamma_scale',1));
    if isfield(opts,'rbf_position_deep_basis_fn')
        positionDeepBasisFn=opts.rbf_position_deep_basis_fn;
        assert(isa(positionDeepBasisFn,'function_handle')&&ismember(positionBasisMode, ...
            {'gaussian','tcn_only','hybrid','current_only','attention','static_attention','gain'}), ...
            'TCN0916:DeepBasisHook','Invalid Position deep-basis hook or mode.');
        assert(ismember(method,{'B2-RBF-Full-250'}),'TCN0916:DeepBasisRate', ...
            'Deep-basis pilot requires the 250-Hz Formal A1 scheduler.');
        assert(ismember(positionDeepDim,[8 32])&&isfinite(positionBasisBeta)&& ...
            positionBasisBeta>=0&&isfinite(positionDeepGammaScale)&&positionDeepGammaScale>0, ...
            'TCN0916:DeepBasisShape','Invalid deep-basis dimension, beta, or GammaD.');
        assert((strcmp(positionBasisMode,'current_only')&&positionDeepDim==32)|| ...
            (~strcmp(positionBasisMode,'current_only')&&positionDeepDim==8), ...
            'TCN0916:DeepBasisModeDim','short8 modes require 8 features; current-only requires 32.');
    end
    attitudeModFn=[];
    if isfield(opts,'rbf_attitude_modulation_fn')
        attitudeModFn=opts.rbf_attitude_modulation_fn;
        assert(isa(attitudeModFn,'function_handle') && ismember(method,{'B2-RBF-Full-250','B2-RBF-Full-200','B2-RBF-Full-400','B2-RBF-Full-SPLIT'}), ...
            'TCN0916:RbfAttitudeModHook','Attitude modulation hook requires a scheduled Formal A1 variant.');
    end
    positionGammaScale=double(field_or(opts,'rbf_position_gamma_scale',ones(3,1)));
    attitudeGammaScale=double(field_or(opts,'rbf_attitude_gamma_scale',ones(3,1)));
    assert((isscalar(positionGammaScale)||numel(positionGammaScale)==3)&&all(isfinite(positionGammaScale(:))&positionGammaScale(:)>0), ...
        'TCN0916:RbfPositionGammaScale','Position gamma scale must be positive.');
    assert((isscalar(attitudeGammaScale)||numel(attitudeGammaScale)==3)&&all(isfinite(attitudeGammaScale(:))&attitudeGammaScale(:)>0), ...
        'TCN0916:RbfAttitudeGammaScale','Attitude gamma scale must be positive.');
    positionGammaScale=positionGammaScale(:); if isscalar(positionGammaScale),positionGammaScale=repmat(positionGammaScale,3,1);end
    attitudeGammaScale=attitudeGammaScale(:); if isscalar(attitudeGammaScale),attitudeGammaScale=repmat(attitudeGammaScale,3,1);end
    isNetwork=(startsWith(method,'MLP-') || startsWith(method,'TCN-')) && isfield(opts,'network');
    oracleEnabled=isfield(opts,'oracle_force_rate_hz') && isfinite(opts.oracle_force_rate_hz) && opts.oracle_force_rate_hz>0;
    oracleForceRate=field_or(opts,'oracle_force_rate_hz',NaN);
    oracleStartTime=field_or(opts,'oracle_force_start_time_s',0);
    assert(isfinite(oracleStartTime)&&isscalar(oracleStartTime)&&oracleStartTime>=0,'TCN0916:OracleStart','Invalid oracle start time.');
    if oracleEnabled, assert(oracleForceRate<=1/dt+1e-12&&abs((1/dt)/oracleForceRate-round((1/dt)/oracleForceRate))<1e-9,'TCN0916:OracleRate','Oracle rate must divide the plant rate.');end
    truthOracleEnabled=isfield(opts,'truth_wind_oracle')&&isstruct(opts.truth_wind_oracle);
    truthOracleMode=''; truthOracleRate=NaN; truthOracleHorizonSamples=NaN; truthOracleStartTime=0; truthOracleStride=NaN;
    if truthOracleEnabled
        truthOracleMode=lower(char(field_or(opts.truth_wind_oracle,'mode','')));
        truthOracleRate=field_or(opts.truth_wind_oracle,'rate_hz',50);
        truthOracleHorizonSamples=field_or(opts.truth_wind_oracle,'horizon_samples',20);
        truthOracleStartTime=field_or(opts.truth_wind_oracle,'start_time_s',0);
        assert(ismember(truthOracleMode,{'current50','future_point20','next_hold_avg20'}),'TCN0916:TruthOracleMode','Unknown truth wind oracle mode.');
        assert(isfinite(truthOracleRate)&&truthOracleRate>0&&truthOracleRate<=1/dt+1e-12&&abs((1/dt)/truthOracleRate-round((1/dt)/truthOracleRate))<1e-9,'TCN0916:TruthOracleRate','Truth oracle rate must divide the plant rate.');
        assert(isscalar(truthOracleHorizonSamples)&&truthOracleHorizonSamples>=1&&truthOracleHorizonSamples==round(truthOracleHorizonSamples),'TCN0916:TruthOracleHorizon','Truth oracle horizon must be a positive integer.');
        assert(isfinite(truthOracleStartTime)&&isscalar(truthOracleStartTime)&&truthOracleStartTime>=0,'TCN0916:TruthOracleStart','Invalid truth oracle start time.');
        truthOracleStride=max(1,round((1/dt)/truthOracleRate));
    end
    learnedForceLambda=field_or(opts,'learned_force_lambda',1);
    assert(isfinite(learnedForceLambda)&&isscalar(learnedForceLambda)&&learnedForceLambda>=0&&learnedForceLambda<=1,'TCN0916:LearnedForceLambda','learned_force_lambda must be in [0,1].');
    isM0RFrozen=strcmp(method,'B2-M0R-Frozen');
    isV2Seed=strcmp(method,'B2-V2-SeedForce');
    isFullHistoryForce=isM0RFrozen||isV2Seed;
    isLearnedForce=ismember(method,{'B1-PMForce','B2-ResponseForce','B2-M0R-Frozen','B2-V2-SeedForce'}) && isfield(opts,'network') && ~oracleEnabled;
    a3sV2Adaptive=isLearnedForce && isfield(opts,'a3s_v2_head') && isstruct(opts.a3s_v2_head) && logical(field_or(opts.a3s_v2_head,'adaptation_enabled',true));
    a3sV2FastAdaptive=a3sV2Adaptive && logical(field_or(opts.a3s_v2_head,'fast_update',false));
    v1Adaptive=isLearnedForce && logical(field_or(opts,'v1_adaptive',false));
    contextErrorAdaptive=isfield(opts,'context_error_head')&&isstruct(opts.context_error_head);
    contextMode=''; contextBaseA0=false; contextUsesM2=false; contextUsesLSTM=false; contextUsesNetwork=false; contextBasis='linear'; contextIncludePrior=false; contextHead=struct;
    if contextErrorAdaptive
        contextHead=opts.context_error_head;
        contextMode=lower(char(field_or(contextHead,'mode','')));
        contextBasis=lower(char(field_or(contextHead,'basis_kind','linear')));
        contextBaseA0=strcmp(method,'B2-RBF-Att');
        contextUsesNetwork=strcmp(method,'B2-V2-SeedForce');
        contextUsesM2=contextUsesNetwork&&isfield(opts,'network')&&strcmp(char(field_or(opts.network,'kind','')),'multiscale_force_v2');
        contextUsesLSTM=contextUsesNetwork&&isfield(opts,'network')&&strcmp(char(field_or(opts.network,'kind','')),'lstm_force_v1');
        contextIncludePrior=logical(field_or(contextHead,'include_prior',contextUsesM2));
        assert(contextBaseA0||contextUsesNetwork,'TCN0916:ContextMethod','Context head requires A0 or a frozen temporal network.');
        assert(ismember(contextMode,{'phi','error','hybrid','rbf_prior','rbf_tcn','rbf_tcn_error','rbf_lstm'}),'TCN0916:ContextMode','Unknown context head mode.');
        assert(~v1Adaptive&&~a3sV2Adaptive,'TCN0916:ContextExclusive','Context head cannot be combined with another adaptive head.');
        if strcmp(contextBasis,'linear'), expectedDim=struct('phi',32,'error',6,'hybrid',38); else, expectedDim=struct('rbf_prior',125,'rbf_tcn',157,'rbf_tcn_error',163,'rbf_lstm',157); end
        assert(isfield(expectedDim,contextMode)&&double(contextHead.feature_dim)==expectedDim.(contextMode), ...
            'TCN0916:ContextFeatureDim','Context feature dimension does not match mode.');
        if contextUsesNetwork, assert(contextUsesM2||contextUsesLSTM, ...
                'TCN0916:ContextNetworkContract','Context network must be frozen M2 or standard LSTM32.'); end
        assert(isequal(size(contextHead.weight),[double(contextHead.feature_dim)+1,3])&& ...
            norm(contextHead.initial_weight,'fro')==0,'TCN0916:ContextHead','Context head must be zero-initialized.');
    end
    assert(~(a3sV2Adaptive&&v1Adaptive),'TCN0916:A3SV2Exclusive','A3S-V2 and legacy V1 adaptive heads are mutually exclusive.');
    v1Kind=char(field_or(opts,'v1_kind',''));
    v1FeatureKind=char(field_or(opts,'v1_feature_kind',v1Kind));
    v1Rbf=strcmp(v1Kind,'ResponseRBF');
    v1Law=char(field_or(opts,'v1_law','raw'));
    debugEnabled=isLearnedForce && logical(field_or(opts,'debug_capture',false));
    if isNetwork, assert(ismember(method,{'MLP-Pos','MLP-Att','MLP-Full','TCN-Pos','TCN-Att','TCN-Full'}),'TCN0901:NetworkMethod','Unknown network branch.');
    end
    if isLearnedForce, assert(isfield(opts.network,'kind')&&ismember(char(opts.network.kind),{'frozen_v2_force','multiscale_force_v2','ablation_force_v1','m2_knockout_v1','lstm_force_v1'}),'TCN0901:FrozenForceNetwork','Missing frozen V2 Force network.');
    end
    if v1Adaptive
        assert(isfield(opts,'v1_head')&&isstruct(opts.v1_head),'TCN0910:AdaptiveHead','V1 adaptive head is required.');
        assert(ismember(v1Kind,{'PM','Response','ResponseRBF'}),'TCN0910:AdaptiveKind','Unknown V1 head kind.');
        if v1Rbf, assert(strcmp(v1FeatureKind,'Response'),'TCN0910:RbfFeatureKind','A3R requires Response features.');
        end
        assert(ismember(v1Law,{'raw','normalized','bounded'}),'TCN0910:AdaptiveLaw','v1_law must be raw, normalized, or bounded.');
    end
    if a3sV2Adaptive
        assert(isFullHistoryForce&&strcmp(char(field_or(opts.network,'kind','')),'multiscale_force_v2'), ...
            'TCN0916:A3SV2Contract','A3S-V2 requires the frozen full-history MultiScaleForceTCN prior.');
        assert(isequal(size(opts.a3s_v2_head.weight),[33,3])&&norm(opts.a3s_v2_head.initial_weight,'fro')==0, ...
            'TCN0916:A3SV2Head','A3S-V2 head must be zero-initialized 33x3.');
        if a3sV2FastAdaptive
            assert(abs(dt-.001)<1e-12,'TCN0916:A3SV2FastDt','Fast A3S-V2 requires a 1-kHz plant.');
            assert(isfield(opts.a3s_v2_head,'leakage_rate_s_inv'),'TCN0916:A3SV2FastLeakage','Fast head must carry an explicit continuous leakage rate.');
        end
    end
    t=s.time(:);
    N=numel(t);
    n=N-1;
    assert(N>=2&&max(abs(diff(t)-dt))<1e-12);
    wrenchDiagnostic=field_or(opts,'rbf_disturbance_diagnostic',struct);
    wrenchDiagnosticEnabled=isstruct(wrenchDiagnostic)&&logical(field_or(wrenchDiagnostic,'enabled',false));
    physicalImpulse=field_or(opts,'physical_impulse_force_I',struct);
    physicalImpulseEnabled=isstruct(physicalImpulse)&&logical(field_or(physicalImpulse,'enabled',false));
    physicalImpulseForceI=zeros(n,3);
    if physicalImpulseEnabled
        physicalImpulseForceI=double(field_or(physicalImpulse,'force_I',nan(n,3)));
        assert(isequal(size(physicalImpulseForceI),[n,3])&&all(isfinite(physicalImpulseForceI),'all'), ...
            'RBFBS:PhysicalImpulseForceShape','Enabled physical_impulse_force_I must be a finite (N-1)-by-3 inertial-force array in N.');
    end
    if wrenchDiagnosticEnabled
        diagnosticForce=double(field_or(wrenchDiagnostic,'external_force_I',zeros(n,3)));
        diagnosticTorque=double(field_or(wrenchDiagnostic,'external_torque_B',zeros(n,3)));
        diagnosticOracle=logical(field_or(wrenchDiagnostic,'oracle_enabled',false));
        assert(isequal(size(diagnosticForce),[n,3])&&isequal(size(diagnosticTorque),[n,3])&& ...
            all(isfinite(diagnosticForce),'all')&&all(isfinite(diagnosticTorque),'all'), ...
            'RBFBS:DiagnosticWrenchShape','Diagnostic wrench must contain finite (N-1)-by-3 arrays.');
        assert(isscalar(diagnosticOracle),'RBFBS:DiagnosticOracle','oracle_enabled must be scalar.');
        diagnosticControllerResidual=zeros(n,6);
        diagnosticModelResidual=zeros(n,6);
        diagnosticAeroResidual=zeros(n,6);
        diagnosticInjectedResidual=zeros(n,6);
        diagnosticClosure=zeros(n,6);
        diagnosticRbfForce=zeros(n,3);
        diagnosticRbfTorque=zeros(n,3);
        diagnosticOracleForce=zeros(n,3);
        diagnosticOracleTorque=zeros(n,3);
        diagnosticPositionSurface=zeros(n,3);
        diagnosticAttitudeSurface=zeros(n,3);
    end
    % R2D observation-only logging: allow diagnostics with exactly zero injected wrench.
    wrenchDiagnosticZeroExternal=wrenchDiagnosticEnabled&&~diagnosticOracle&& ...
        all(diagnosticForce==0,'all')&&all(diagnosticTorque==0,'all');
    x=zeros(N,12);
    x(1,:)=s.initial_state(:).';
    statePerturbation=field_or(opts,'state_perturbation',struct);
    statePerturbationEnabled=isstruct(statePerturbation)&&logical(field_or(statePerturbation,'enabled',false));
    statePerturbationTime=NaN;
    statePerturbationDelta=zeros(12,1);
    statePerturbationApplied=false;
    statePerturbationAppliedTime=NaN;
    statePerturbationAppliedFlag=false(N,1);
    if statePerturbationEnabled
        statePerturbationTime=double(field_or(statePerturbation,'time_s',NaN));
        statePerturbationDelta=double(field_or(statePerturbation,'delta_state',nan(12,1)));
        assert(isscalar(statePerturbationTime)&&isfinite(statePerturbationTime)&& ...
            statePerturbationTime>t(1)&&statePerturbationTime<t(end)&& ...
            min(abs(t-statePerturbationTime))<1e-12&&isequal(size(statePerturbationDelta),[12,1])&& ...
            all(isfinite(statePerturbationDelta)), ...
            'RBFBS:StatePerturbationContract','State perturbation must be a finite 12-state delta at an interior Plant time knot.');
    end
    previousMotor=[];
    last=0;
    status='STABLE';
    divergenceTime=NaN;
    safetyStopReason='';
    safetyPositionErrorTime=0;
    safetyTiltTime=0;
    safetyRateTime=0;
    filter=command_filter_init(x(1,7:9).');
    positionBasisRows=size(cfg.rbf.position.centers,2);
    if ~isempty(positionDeepBasisFn)
        switch positionBasisMode
            case 'tcn_only',positionBasisRows=positionDeepDim;
            case 'hybrid',positionBasisRows=positionBasisRows+positionDeepDim;
            case 'current_only',positionBasisRows=32;
        end
    end
    rbfPos.W=zeros(positionBasisRows,3);
    rbfAtt.W=zeros(size(cfg.rbf.attitude.centers,2),3);
    if isfield(opts,'rbf_position_initial_weight')
        assert(isequal(size(opts.rbf_position_initial_weight),size(rbfPos.W)),'TCN0916:RbfInitialPositionWeight','Invalid audit Position RBF initial weight shape.');
        rbfPos.W=double(opts.rbf_position_initial_weight);
    end
    if isfield(opts,'rbf_attitude_initial_weight')
        assert(isequal(size(opts.rbf_attitude_initial_weight),size(rbfAtt.W)),'TCN0916:RbfInitialAttitudeWeight','Invalid audit Attitude RBF initial weight shape.');
        rbfAtt.W=double(opts.rbf_attitude_initial_weight);
    end
    motor=zeros(n,4);
    motorSetpoint=zeros(n,4);
    motorSquaredRequested=zeros(n,4);
    requested=zeros(n,4);
    realized=zeros(n,4);
    motorSat=false(n,4);
    clipped=false(n,4);
    tiltLimited=false(n,1);
    rawAtt=zeros(n,3);
    internalAtt=zeros(n,3);
    internalRate=zeros(n,3);
    filterTargetLog=nan(n,3);
    filterRequestedAccelerationLog=nan(n,3);
    filterAppliedAccelerationLog=nan(n,3);
    internalPos=zeros(n,3);
    internalPosRate=zeros(n,3);
    forceEstimate=zeros(n,3);
    torqueEstimate=zeros(n,3);
    physicsEstimateTorque=zeros(n,3);
    windForce=zeros(n,3);
    windTorque=zeros(n,3);
    residual=zeros(n,6);
    causalResidual=zeros(n,6);
    causalMotor=zeros(n,4);
    observerZ3=nan(n,6);
    controllerTime=zeros(n,1);
    adaptiveBasisFeature=zeros(n,27);
    adaptiveBasisPhi=zeros(n,16);
    adaptiveBasisForce=zeros(n,3);
    adaptiveBasisEvent=false(n,1);
    adaptiveBasisWeightNorm=zeros(n,1);
    adaptiveBasisProjection=false(n,1);
    tcnResidualPrediction=zeros(n,6);
    tcnResidualApplied=zeros(n,6);
    adaptiveTorqueFeature=zeros(n,27);
    adaptiveTorquePhi=zeros(n,16);
    adaptiveTorqueOutput=zeros(n,3);
    adaptiveTorqueEvent=false(n,1);
    adaptiveTorqueWeightNorm=zeros(n,1);
    adaptiveTorqueProjection=false(n,1);
    windForceScale=double(field_or(opts,'wind_force_scale',1));
    assert(isscalar(windForceScale)&&isfinite(windForceScale)&&windForceScale>0, ...
        'RBFBS0:WindScale','风扰载荷缩放必须为有限正数。');
    wcfg=struct('rho_air',1.225,'CdBody',1,'CdArm',1);
    networkRaw=zeros(n,6);
    networkApplied=zeros(n,6);
    oracleForceLog=zeros(n,3);
    oracleForceUpdate=false(n,1);
    truthOracleCurrent=zeros(n,3);
    truthOracleFuture=zeros(n,3);
    truthOracleHold=zeros(n,3);
    truthOracleCompensation=zeros(n,3);
    truthOracleEvent=false(n,1);
    truthOracleZohStart=nan(n,1);
    truthOracleZohEnd=nan(n,1);
    networkUpdate=false(n,1);
    featureHistory=zeros(28,64,'single');
    featureFill=0;
    networkOutput=zeros(6,1);
    oracleForce=zeros(3,1);
    networkCallTime=zeros(n,1);
    networkGate=zeros(n,1);
    networkRelease=zeros(n,1);
    diagnosticFallbackThreshold=field_or(opts,'diagnostic_force_fallback_threshold_N',inf);
    diagnosticForceBound=field_or(opts,'diagnostic_force_bound_N',inf);
    diagnosticFallbackActive=false;
    diagnosticFallbackTrigger=false(n,1);
    diagnosticFallbackActiveLog=false(n,1);
    diagnosticForceBoundActive=false(n,1);
    diagnosticFallbackTime=NaN;
    guardEnabled=isLearnedForce && isfield(opts,'guard') && isstruct(opts.guard) && logical(field_or(opts.guard,'enabled',true));
    s0GuardEnabled=isLearnedForce && isfield(opts,'s0_guard') && isstruct(opts.s0_guard) && logical(field_or(opts.s0_guard,'enabled',true));
    if s0GuardEnabled
        assert(isFullHistoryForce && ~v1Adaptive,'TCN0916:S0GuardContract','S0 guard requires frozen full-history Seed.');
        for guardField={'force_guard_N','position_error_guard_m','attitude_error_guard_rad'}
            guardValue=field_or(opts.s0_guard,guardField{1},NaN);
            assert(isscalar(guardValue)&&isfinite(guardValue)&&guardValue>0,'TCN0916:S0GuardThreshold','Invalid S0 guard threshold %s.',guardField{1});
        end
    end
    guardLatched=false;
    s0TriggerThisRow=false;
    s0SaturationEvents=0;
    guardPersistence=0;
    guardPreviousForce=zeros(3,1);
    guardHavePreviousForce=false;
    guardGrowthWindow=zeros(3,1);
    guardGrowthWindowCount=0;
    guardPreviousCommand=zeros(8,1);
    guardHavePreviousCommand=false;
    guardMorphologyRecent=0;
    guardTrigger=false(n,1);
    guardActiveLog=false(n,1);
    guardSupportScore=nan(n,1);
    guardSupportParts=nan(n,5);
    guardForceNorm=nan(n,1);
    guardForceGrowth=nan(n,1);
    guardForceGrowthSmooth=nan(n,1);
    guardDynamicSupportScore=nan(n,1);
    guardCommandGrowth=nan(n,1);
    guardMorphologyRecentLog=zeros(n,1);
    guardPersistenceLog=zeros(n,1);
    guardTriggerTime=NaN;
    guardTriggerReason=repmat({''},n,1);
    studentAuthority=false(n,1);
    studentEligible=false(n,1);
    fallbackSource=repmat({''},n,1);
    policyMode=repmat({'A0'},n,1);
    if isLearnedForce,policyMode(:)={'STUDENT'};end
    if s0GuardEnabled,policyMode(:)={'PRE_READY'};end
    if oracleEnabled||truthOracleEnabled,policyMode(:)={'ORACLE'};end
    heldGate=~field_or(opts,'command_active_gate',false);
    learnedHistory=zeros(16,253);
    learnedHistoryState=[];
    assert(isequal(size(learnedHistory),[16,253]),'TCN0910:HistoryShape','V1 history must be 16x253.');
    learnedHistoryFill=0;
    previousInternalAtt=x(1,7:9).';
    previousInternalRate=zeros(3,1);
    attitudeFusionFeatureHistory=zeros(max(attitudeFusionInputDim,1),32);attitudeFusionEventCount=0;
    attitudeFusionPreviousEventSetpoint=zeros(4,1);
    attitudeFusionHeldNnTorque=zeros(3,1);
    attitudeHeadReadyEventCount=zeros(n,1);
    attitudeHeadDeltaNorm=zeros(n,1);attitudeHeadEvent=false(n,1);
    attitudeHeadRawNormalized=zeros(n,3);attitudeHeadAppliedNormalized=zeros(n,3);
    attitudeHeadTorqueNm=zeros(n,3);attitudeHeadUpdateNorm=zeros(n,1);
    attitudeHeadProjection=false(n,1);attitudeHeadSaturated=false(n,1);
    attitudeHeadAuditMax=min(n,ceil(n*dt*110)+2);
    attitudeHeadAudit=struct('time',nan(attitudeHeadAuditMax,1), ...
        'dt_event_s',nan(attitudeHeadAuditMax,1),'weight_before',zeros(33,3,attitudeHeadAuditMax), ...
        'weight_after',zeros(33,3,attitudeHeadAuditMax),'phi',zeros(33,attitudeHeadAuditMax), ...
        'y_raw',zeros(3,attitudeHeadAuditMax),'y_applied',zeros(3,attitudeHeadAuditMax), ...
        'dTau_Nm',zeros(3,attitudeHeadAuditMax),'update_norm',zeros(attitudeHeadAuditMax,1), ...
        'projection',false(attitudeHeadAuditMax,1),'saturated',false(attitudeHeadAuditMax,1));
    learnedFirstValidTime=0;
    if v1Adaptive || isFullHistoryForce, learnedFirstValidTime=5.04; end
    learnedHistoryTimes=nan(1,253);
    closureReset=field_or(opts,'closure_reset',struct);
    closureResetApplied=false;
    closureResetAppliedLog=false(n,1);
    if isfield(closureReset,'enabled')&&logical(closureReset.enabled)
        requiredResetFields={'time_s','state','filter_euler','filter_rate','previous_motor', ...
            'previous_internal_att','previous_internal_rate'};
        assert(all(isfield(closureReset,requiredResetFields)), ...
            'TCN0916:ClosureResetContract','closure_reset is missing a closure-state field.');
        assert(isscalar(closureReset.time_s)&&isfinite(closureReset.time_s)&&closureReset.time_s>=0, ...
            'TCN0916:ClosureResetTime','closure_reset.time_s must be finite and nonnegative.');
        assert(isequal(size(closureReset.state),[12,1])&&isequal(size(closureReset.filter_euler),[3,1])&& ...
            isequal(size(closureReset.filter_rate),[3,1])&&isequal(size(closureReset.previous_motor),[4,1])&& ...
            isequal(size(closureReset.previous_internal_att),[3,1])&&isequal(size(closureReset.previous_internal_rate),[3,1]), ...
            'TCN0916:ClosureResetShape','closure_reset state shapes are invalid.');
    end
    v1HistoryMaturity=nan(n,1);
    v1NReal=zeros(n,1);
    v1Alpha=zeros(n,1);
    debugEvent=0;
    debugCount=0;
    debugModelCalls=0;
    v1EventFlag=false(n,1);
    v1HistoryReady=false(n,1);
    v1EventTime=nan(n,1);
    v1CommandState8=nan(n,8);
    v1PhiNorm=nan(n,1);
    v1Surface=zeros(n,3);
    v1UpdateDt=nan(n,1);
    v1WeightNorm=nan(n,1);
    v1WeightDeltaNorm=nan(n,1);
    v1WeightDerivativeNorm=nan(n,1);
    v1ProjectionActive=false(n,1);
    v1QPhi=nan(n,1);
    v1Z2Norm=nan(n,1);
    v1Phi32Norm=nan(n,1);
    v1BoundedPhiNorm=nan(n,1);
    v1RawForceDiagnostic=nan(n,3);
    v1BoundedForceOutput=nan(n,3);
    v1RawDrivingMagnitude=nan(n,1);
    v1NormalizedDrivingMagnitude=nan(n,1);
    v1RelativeWeightUpdate=nan(n,1);
    v1WeightDeltaMatrix=[];
    if v1Adaptive, v1WeightDeltaMatrix=nan(n,size(opts.v1_head.weight,1),size(opts.v1_head.weight,2));
    end
    v1ForceOffParity=nan(n,1);
    v1FirstAdaptationTime=NaN;
    v1LastLearnerEventTime=NaN;
    v1ReleaseHeld=0;
    a3sPriorForce=zeros(n,3);
    a3sDeltaForce=zeros(n,3);
    a3sTotalForce=zeros(n,3);
    a3sPhiRawNorm=nan(n,1);
    a3sPhiBoundedNorm=nan(n,1);
    a3sFeatureLimiterActive=false(n,1);
    a3sDeltaWNorm=nan(n,1);
    a3sDeltaWExcursion=nan(n,1);
    a3sPerEventDeltaW=nan(n,1);
    a3sProjectionActive=false(n,1);
    a3sZ2=zeros(n,3);
    a3sDrivingNorm=nan(n,1);
    a3sForceOffParity=nan(n,1);
    a3sFastUpdateFlag=false(n,1);
    a3sFastUpdateDt=nan(n,1);
    a3sGamma=NaN; a3sSigma=NaN; a3sFeatureLimit=NaN; a3sProjectionBound=NaN;
    fastHeadReady=false; fastPriorForce=zeros(3,1); fastPhiT=zeros(33,1); fastPhiRawNorm=NaN; fastPhiBoundedNorm=NaN; fastFeatureLimiter=false;
    if isfield(opts,'a3s_v2_head') && isstruct(opts.a3s_v2_head)
        a3sGamma=field_or(opts.a3s_v2_head,'gamma',NaN); a3sSigma=field_or(opts.a3s_v2_head,'sigma',NaN);
        a3sFeatureLimit=field_or(opts.a3s_v2_head,'feature_limit',NaN); a3sProjectionBound=field_or(opts.a3s_v2_head,'projection_bound',NaN);
    end
    contextRateHz=field_or(opts,'context_error_rate_hz',400); assert(isnumeric(contextRateHz)&&isscalar(contextRateHz)&&isfinite(contextRateHz)&&contextRateHz>0&&contextRateHz<=1/dt,'TCN0916:ContextRate','context_error_rate_hz must be in (0,1/dt].');
    contextPhase=0; contextLastEventTime=0; contextGateReady=false; contextEvent=false; contextEventDt=0;
    contextPriorReady=~contextUsesNetwork; contextPriorForce=zeros(3,1); contextPhi32=zeros(32,1); contextHeldDelta=zeros(3,1);
    contextUpdateFlag=false(n,1); contextUpdateDt=nan(n,1); contextPriorForceLog=zeros(n,3); contextDeltaForce=zeros(n,3);
    contextZ1=nan(n,3); contextZ2=nan(n,3); contextZ1Bar=nan(n,3); contextZ2Bar=nan(n,3);
    contextRbfCfg=cfg.rbf.position; contextZ1Scale=double(contextRbfCfg.input_scale(:)); contextZ2Scale=double(contextRbfCfg.s_limit(:));
    assert(numel(contextZ1Scale)==3&&numel(contextZ2Scale)==3&&all(isfinite([contextZ1Scale;contextZ2Scale])&[contextZ1Scale;contextZ2Scale]>0), ...
        'TCN0916:ContextScale','Context error scales must be three positive finite values.');
    contextFeatureNorm=nan(n,1); contextFeatureLimiterActive=false(n,1); contextWeightNorm=nan(n,1);
    contextWeightDerivativeNorm=nan(n,1); contextProjectionActive=false(n,1); contextDeltaWNorm=nan(n,1);
    contextForceSaturation=false(n,1);
    contextRbfContribution=zeros(n,3); contextPhiContribution=zeros(n,3); contextZ1Contribution=zeros(n,3); contextZ2Contribution=zeros(n,3); contextBiasContribution=zeros(n,3);
    contextFirstEventTime=NaN; contextLastEventTimeLog=nan(n,1);
    if debugEnabled, forwardDebug=init_forward_debug(ceil(n/20)+2,opts.network,field_or(opts,'debug_repeat_count',0));
    else, forwardDebug=struct('enabled',false,'count',0);
    end
    isRbfFull400=strcmp(method,'B2-RBF-Full-400');
    isRbfFullSplit=strcmp(method,'B2-RBF-Full-SPLIT');
    isRbfFullScheduled=ismember(method,{'B2-RBF-Full-250','B2-RBF-Full-400','B2-RBF-Full-200','B2-RBF-Full-SPLIT'});
    rbfAtt400=ismember(method,{'B2-RBF-Att','B1-PMForce','B2-ResponseForce','B2-M0R-Frozen','B2-V2-SeedForce','B2-OracleForce','B2-RBF-Full-250','B2-RBF-Full-400','B2-RBF-Full-200','B2-RBF-Full-SPLIT'});
    rbfHz=1000;
    if isRbfFullScheduled && isfield(opts,'lowrate_frequency_hz')
        rbfHz=double(opts.lowrate_frequency_hz);
    elseif rbfAtt400 && isfield(cfg,'rbf') && isfield(cfg.rbf,'runtime') && isfield(cfg.rbf.runtime,'attitude_update_hz')
        rbfHz=cfg.rbf.runtime.attitude_update_hz;
    end
    if rbfAtt400, assert(isnumeric(rbfHz)&&isscalar(rbfHz)&&isfinite(rbfHz)&&rbfHz>0&&rbfHz<=1/dt,'TCN0901:RbfRate','attitude_update_hz must be in (0,1/dt].');
    end
    if isRbfFull400, assert(abs(rbfHz-400)<1e-12,'TCN0910:RbfFullRate','A400 requires the frozen 400-Hz scheduler setting.');
    end
    rbfFullHz=rbfHz;
    if isRbfFullScheduled && isfield(opts,'lowrate_frequency_hz')
        rbfFullHz=double(opts.lowrate_frequency_hz);
    elseif isRbfFullScheduled && isfield(opts,'position_rbf_frequency_hz')
        rbfFullHz=double(opts.position_rbf_frequency_hz);
    elseif isRbfFullScheduled && isfield(cfg.rbf,'runtime') && isfield(cfg.rbf.runtime,'position_update_hz')
        rbfFullHz=cfg.rbf.runtime.position_update_hz;
    end
    if isRbfFullScheduled, assert(isnumeric(rbfFullHz)&&isscalar(rbfFullHz)&&isfinite(rbfFullHz)&&rbfFullHz>0&&rbfFullHz<=1/dt,'TCN0901:RbfPositionRate','position_update_hz must be in (0,1/dt].'); end
    if stage1PositionActive
        assert(formalRbfBaseline&&isRbfFullScheduled&&abs(rbfFullHz-100)<1e-12&& ...
            isfield(stage1PositionRuntime,'model')&&isfield(stage1PositionRuntime,'weight')&& ...
            isequal(size(stage1PositionRuntime.weight),[33,3]), ...
            'POSADV:RuntimeContract','Stage-1 replacement requires the isolated fixed controller, a 100-Hz schedule, and a 33x3 head.');
    end
    rbfPhase=field_or(opts,'rbf_phase_start',0);
    lastRbfEventTime=0;
    heldRbfTorque=zeros(3,1);
    heldRbfPositionAcceleration=zeros(3,1);
    heldRbfAttitudeAcceleration=zeros(3,1);
    rbfEventCount=0;
    rbfAuditMax=8;
    rbfFullPhase=field_or(opts,'rbf_full_phase_start',0);
    if isRbfFullSplit
        if ~isfield(opts,'rbf_phase_start'),rbfPhase=-rbfHz*dt;end
        if ~isfield(opts,'rbf_full_phase_start'),rbfFullPhase=-rbfFullHz*dt;end
    end
    lastRbfFullEventTime=0;
    rbfFullEventCount=0;
    rbfPositionEventCount=0;
    heldRbfForce=zeros(3,1);
    stage1ModelInputDim=14;
    if stage1PositionActive&&isfield(stage1PositionRuntime,'model')&&isfield(stage1PositionRuntime.model,'input_dim')
        stage1ModelInputDim=double(stage1PositionRuntime.model.input_dim);
    end
    assert(ismember(stage1ModelInputDim,[14,20]),'D5:InputDim','Candidate input dimension must be 14 or 20.');
    stage1ModelContextLength=32;
    if stage1PositionActive&&isfield(stage1PositionRuntime.model,'context_length')
        stage1ModelContextLength=double(stage1PositionRuntime.model.context_length);
    elseif stage1PositionActive&&isfield(stage1PositionRuntime.model,'window')
        stage1ModelContextLength=double(stage1PositionRuntime.model.window);
    end
    assert(ismember(stage1ModelContextLength,[1,32,128]),'D5:ContextLength','Candidate context must be 1, 32, or 128 events.');
    stage1ModelReadinessEvents=double(field_or(stage1PositionRuntime,'readiness_events',stage1ModelContextLength));
    assert(ismember(stage1ModelReadinessEvents,[1,32]), ...
        'D5:ReadinessEvents','Experiment readiness must be 1 or 32 real position events.');
    stage1PositionHistory=zeros(stage1ModelInputDim,max(stage1ModelContextLength,stage1ModelReadinessEvents));
    stage1PositionHistoryFill=0;
    stage1PositionWeight=double(field_or(stage1PositionRuntime,'weight',zeros(33,3)));
    stage1PositionWeightInitial=stage1PositionWeight;
    stage1PositionUpdateEnabled=logical(field_or(stage1PositionRuntime,'update_enabled',true));
    stage1PositionUpdateDtScale=double(field_or(stage1PositionRuntime,'update_dt_scale',1));
    stage1PositionBetaScale=double(field_or(stage1PositionRuntime,'beta_scale',1));
    stage1SearchHead=field_or(stage1PositionRuntime,'position_only_search_head',struct);
    stage1SearchEnabled=isstruct(stage1SearchHead)&&logical(field_or(stage1SearchHead,'enabled',false));
    stage1SearchStep=[];if stage1SearchEnabled,stage1SearchStep=@position_only_search_head_step;end
    stage1SearchType='';stage1SearchGamma=NaN;stage1SearchKappa=NaN;
    stage1SearchW0=stage1PositionWeight;stage1PositionBias=zeros(3,1);
    if stage1SearchEnabled
        stage1SearchType=upper(char(field_or(stage1SearchHead,'head_type','')));
        stage1SearchGamma=double(field_or(stage1SearchHead,'gamma',NaN));
        stage1SearchKappa=double(field_or(stage1SearchHead,'kappa',NaN));
        stage1SearchW0=double(field_or(stage1SearchHead,'W0',stage1PositionRuntime.model.output_W));
        assert(ismember(stage1SearchType,{'FEATURE','BIAS'})&&isequal(size(stage1SearchW0),[33,3])&& ...
            isfinite(stage1SearchGamma)&&stage1SearchGamma>0&&isfinite(stage1SearchKappa)&&stage1SearchKappa>=0&& ...
            stage1PositionUpdateDtScale==1&&stage1PositionBetaScale==1, ...
            'POSSEARCH:Runtime','Invalid search Head configuration or non-unit scheduler scales.');
        if strcmp(stage1SearchType,'FEATURE')
            assert(norm(stage1PositionWeight-stage1SearchKappa*stage1SearchW0,'fro')<1e-12, ...
                'POSSEARCH:InitialWeight','FEATURE initial state must equal kappa*W0.');
        else
            assert(norm(stage1PositionWeight-stage1SearchW0,'fro')<1e-12, ...
                'POSSEARCH:BiasWeight','BIAS must preserve the frozen W0.');
        end
    end
    if positionDelayedPredictionEnabled
        model=stage1PositionRuntime.model;
        assert(stage1PositionActive&&pcfCoordinationEnabled&&stage1SearchEnabled&& ...
            strcmp(stage1SearchType,'FEATURE')&&stage1PositionUpdateEnabled&& ...
            stage1ModelInputDim==14&&stage1ModelContextLength==32&&stage1ModelReadinessEvents==32&& ...
            abs(dt-.001)<1e-12&&abs(rbfFullHz-100)<1e-12&&numel(t)>320&& ...
            abs(t(1))<1e-12&&all(abs(diff(t)-dt)<1e-12)&& ...
            abs(rbfFullPhase+rbfFullHz*dt)<1e-12&& ...
            abs(stage1SearchGamma-12)<1e-12&&abs(stage1SearchKappa-1)<1e-12&& ...
            abs(cfg.rbf.position.beta_rise_time-1.8)<1e-12&& ...
            isnumeric(cfg.rbf.position.dmax)&&numel(cfg.rbf.position.dmax)==3&& ...
            all(abs(double(cfg.rbf.position.dmax(:))-3)<1e-12)&& ...
            isequal(positionCoordinateMask,[1;1;0]), ...
            'DelayedPrediction:RuntimeContract','C5 requires frozen X14/32, 1-kHz/100-Hz, gamma-12, full-PCF FEATURE update and exact mask [1;1;0].');
        assert(all(isfield(model,{'input_mu','input_sigma','output_W'}))&& ...
            isnumeric(model.input_mu)&&isnumeric(model.input_sigma)&& ...
            numel(model.input_mu)==14&&numel(model.input_sigma)==14&& ...
            all(isfinite(double(model.input_mu(:))))&& ...
            all(isfinite(double(model.input_sigma(:))))&&all(double(model.input_sigma(:))>0)&& ...
            isnumeric(model.output_W)&&isequal(size(model.output_W),[33,3])&& ...
            all(isfinite(double(model.output_W(:))))&& ...
            norm(stage1SearchW0-double(model.output_W),'fro')<1e-12, ...
            'DelayedPrediction:FrozenModel','Frozen X14 normalizer and 33x3 output_W must be finite, with W0 equal to output_W.');
        helperPath=which('delayed_prediction_step_candidate');
        expectedHelper=fullfile(fileparts(mfilename('fullpath')),'delayed_prediction_step_candidate.m');
        assert(~isempty(helperPath)&&exist(helperPath,'file')==2&&strcmpi(helperPath,expectedHelper), ...
            'DelayedPrediction:Helper','The isolated helper must resolve beside this runtime copy.');
    end
    assert(isscalar(stage1PositionUpdateDtScale)&&stage1PositionUpdateDtScale>=0&&stage1PositionUpdateDtScale<=1&& ...
        isscalar(stage1PositionBetaScale)&&stage1PositionBetaScale>=0&&stage1PositionBetaScale<=1, ...
        'DL1009V2:PositionVariantScale','Position variant update_dt_scale and beta_scale must be in [0,1].');
    stage1PositionHeldForce=zeros(3,1);
    stage1PositionLastEventTime=0;
    stage1PositionEvent=false(n,1);
    stage1PositionFeature14=nan(n,14);
    stage1PositionFeatureInput=nan(n,stage1ModelInputDim);
    stage1PositionPhi=nan(n,33);
    stage1PositionRaw=zeros(n,3);
    stage1PositionApplied=zeros(n,3);
    stage1PositionWeightNorm=zeros(n,1);
    % Event-only values use NaN off event; held values are logged at each 1-ms step.
    stage1PositionEventInferenceValid=false(n,1);
    stage1PositionEventRaw=nan(n,3); stage1PositionEventApplied=nan(n,3);
    stage1PositionEventPhi=nan(n,33);
    maxPositionEvents=max(1,ceil((t(end)-t(1))*rbfFullHz)+2);
    stage1PositionEventWeightBefore=nan(33,3,maxPositionEvents);
    stage1PositionEventWeightAfter=nan(33,3,maxPositionEvents);
    stage1PositionEventBiasBefore=nan(3,maxPositionEvents);
    stage1PositionEventBiasAfter=nan(3,maxPositionEvents);
    stage1PositionEventBiasProjection=nan(n,1);
    stage1PositionInferenceEventCount=0;
    stage1PositionEventWeightDeltaFro=nan(n,1); stage1PositionEffectiveUpdateDt=nan(n,1);
    stage1PositionEventBeta=nan(n,1); stage1PositionEventInferenceTime=nan(n,1);
    stage1PositionEventProjection=nan(n,1);
    stage1PcfAReq=nan(n,3); stage1PcfAF=nan(n,3); stage1PcfRf=nan(n,3);
    stage1PcfPredictionReference=nan(n,3);
    stage1PcfEtaBeforeLog=nan(n,3); stage1PcfEtaAfterLog=nan(n,3);
    stage1PcfSurfaceEvent=nan(n,3); stage1PcfEtaEventBefore=nan(n,3);
    stage1PcfScEvent=nan(n,3); stage1PcfScEffEvent=nan(n,3);
    stage1PcfEta=zeros(3,1);
    stage1DelayedAfIntegral=zeros(3,1); stage1DelayedPreviousPhi=[];
    stage1DelayedPredictionReferenceIntegral=zeros(3,1); stage1DelayedPreviousPredictionReferenceIntegral=[];
    stage1DelayedPreviousVelocity=[]; stage1DelayedPreviousAfIntegral=[];
    stage1DelayedPreviousIndex=[]; stage1DelayedPreviousTime=[];
    stage1DelayedTarget=nan(n,3); stage1DelayedPreviousIndexLog=nan(n,1);
    stage1DelayedTermNorm=nan(n,1); stage1DelayedAfIntegralBeforeLog=nan(n,3);
    stage1DelayedPredictionReferenceIntegralBeforeLog=nan(n,3);
    stage1DelayedEventVelocity=nan(n,3); stage1DelayedEventAfIntegral=nan(n,3);
    stage1DelayedEventPredictionReferenceIntegral=nan(n,3);
    stage1PositionHeldRawCache=zeros(3,1); stage1PositionHeldAppliedCache=zeros(3,1);
    stage1PositionHeldRawLog=zeros(n,3); stage1PositionHeldAppliedLog=zeros(n,3);
    stage1PositionHeldForceLog=zeros(n,3); stage1PositionInjectedForceLog=zeros(n,3);
    stage1PositionWeightNormHeld=nan(n,1); stage1PositionLastPredictionTime=NaN;
    stage1PositionLastEventTimeLog=nan(n,1); stage1PositionHistoryFillHeld=zeros(n,1);
    stage1PositionProjection=false(n,1);
    stage1PositionInferenceTime=zeros(n,1);
    stage1PositionEventDt=zeros(n,1);
    stage1PositionHistoryFillLog=zeros(n,1);
    heldRbfForcePrevious=zeros(3,1);
    heldRbfPositionAccelerationPrevious=zeros(3,1);
    heldRbfAttitudeAccelerationPrevious=zeros(3,1);
    positionNdoZ=zeros(3,1);
    if positionNdoEnabled&&positionNdoZeroOutputInitialization
        positionNdoZ=-positionNdoLambda*cfg.plant.mass*x(1,4:6).';
    end
    positionNdoEstimate=zeros(n,3);
    positionNdoAppliedEstimate=zeros(n,3);
    positionNdoLimitActive=false(n,1);
    positionNdoKnownForce=zeros(n,3);
    positionNdoCombinedCompensation=zeros(n,3);
    positionNdoSlowResidual=zeros(n,3);
    positionNdoSlowInnovation=zeros(n,3);
    positionPlantAccelerationTruth=zeros(n,3);
    positionSmcSurface=zeros(n,3);
    positionSmcForce=zeros(n,3);
    positionBsNominalForce=zeros(n,3);
    positionCommandedForce=zeros(n,3);
    positionRbfAccelerationApplied=zeros(n,3);
    attitudeBsNominalTorque=zeros(n,3);
    attitudeRbfAccelerationApplied=zeros(n,3);
    attitudeRbfTorqueApplied=zeros(n,3);
    attitudeFusionEvent=false(n,1);attitudeFusionReady=false(n,1);
    attitudeFusionLambdaLog=zeros(n,1);attitudeFusionRawNormalized=zeros(n,3);
    attitudeFusionAppliedNormalized=zeros(n,3);attitudeFusionAppliedAcceleration=zeros(n,3);
    attitudeFusionOriginalRbfTorque=zeros(n,3);attitudeFusionNnTorque=zeros(n,3);
    attitudeFusionMixedTorque=zeros(n,3);attitudeFusionNormalizedFeature=zeros(n,max(attitudeFusionInputDim,1));
    attitudeFusionFeatureAbsGt4Count=zeros(n,1);
    allocatedWrench=zeros(n,4);
    controllerClippedWrench=zeros(n,4);
    positionRealizedForce=zeros(n,3);
    positionForceRealizationError=zeros(n,3);
    positionNdoTargetTruth=zeros(n,3);
    positionNdoUpdateFlag=false(n,1);
    positionNdoUpdateDt=zeros(n,1);
    positionNdoPhase=-positionNdoFrequency*dt;
    positionNdoLastEventTime=0;
    positionNdoHeldEstimate=zeros(3,1);
    positionNdoHeldAppliedEstimate=zeros(3,1);
    positionNdoHeldKnownForce=zeros(3,1);
    positionNdoHeldSlowResidual=zeros(3,1);
    positionNdoMotorEstimate=zeros(4,1);
    positionNdoMotorEstimateInitialized=false;
    positionNdoReconstructedMotor=zeros(n,4);
    positionNdoReconstructedGeneralized=zeros(n,4);
    positionNdoEstimatedArmLengths=zeros(n,4);
    positionNdoMorphologyCommand=zeros(n,4);
    adaptiveBasisPhase=0;
    adaptiveBasisLastEventTime=0;
    adaptiveBasisHeldForce=zeros(3,1);
    tcnResidualHeld=zeros(6,1);
    adaptiveTorqueHeld=zeros(3,1);
    heldRbfTorquePrevious=zeros(3,1);
    rbfPositionUpdateEnabled=logical(field_or(opts,'rbf_position_update_enabled',true));
    rbfAttitudeUpdateEnabled=logical(field_or(opts,'rbf_attitude_update_enabled',true));
    rbfAttitudeRuntimeEnabled=logical(field_or(opts,'rbf_attitude_enabled',true));
    rbfPositionOutputEnabled=logical(field_or(opts,'rbf_position_output_enabled',true));
    positionRbfWithNdoEnabled=logical(field_or(opts,'position_rbf_with_ndo',false));
    if positionNdoEnabled&&strcmp(positionNdoMode,'ndo_only')&&~positionRbfWithNdoEnabled
        rbfPositionUpdateEnabled=false;
        rbfPositionOutputEnabled=false;
    end
    assert(~positionRbfWithNdoEnabled||(positionNdoEnabled&&strcmp(positionNdoMode,'ndo_only')&& ...
        rbfPositionUpdateEnabled&&rbfPositionOutputEnabled), ...
        'RBFBS:PositionRbfWithNdo','Position RBF/NDO sharing requires both Position RBF update/output and NDO-only mode.');
    if formalRbfBaseline
        assert(~rlGapRuntimeEnabled&&~positionNdoEnabled&&~positionSmcEnabled&& ...
            ~positionRbfWithNdoEnabled&&~adaptiveBasisActive&&~adaptiveTorqueActive&& ...
            isempty(widthScaleFn)&&isempty(positionDeepBasisFn)&&isempty(attitudeModFn)&& ...
            ~oracleEnabled&&~truthOracleEnabled&&~contextErrorAdaptive&& ...
            (~wrenchDiagnosticEnabled||wrenchDiagnosticZeroExternal)&& ...
            ~physicalImpulseEnabled&&~statePerturbationEnabled&& ...
            (~isNetwork||attitudeFusionActive), ...
            'RBFBS0:FormalPathIsolation','Formal RBF-BS0 cannot enable reconstruction, observers, learned hooks, oracle, or diagnostic injections.');
    end
    rbfAttitudeOutputEnabled=logical(field_or(opts,'rbf_attitude_output_enabled',true));
    assert(formalRbfBaseline&&stage1PositionActive&&pcfCoordinationEnabled&& ...
        ~attitudeFusionActive&&~rbfPositionOutputEnabled&&~rbfPositionUpdateEnabled&& ...
        rbfAttitudeRuntimeEnabled==~physCandidate&& ...
        rbfAttitudeOutputEnabled==~physCandidate&& ...
        rbfAttitudeUpdateEnabled==~physCandidate&& ...
        abs(rbfHz-100)<1e-12&&abs(rbfFullHz-100)<1e-12, ...
        'PAIRED:Options','Paired C5/RBF treatment flags or schedule differ.');
    if stage1PositionActive
        attitudeRbfPathAllowed=(rbfAttitudeRuntimeEnabled&&rbfAttitudeOutputEnabled)|| ...
            (physCandidate&&~rbfAttitudeRuntimeEnabled&& ...
             ~rbfAttitudeOutputEnabled&&~rbfAttitudeUpdateEnabled);
        assert(formalRbfBaseline&&~rbfPositionUpdateEnabled&&~rbfPositionOutputEnabled&& ...
            attitudeRbfPathAllowed, ...
            'POSADV:PositionRbfIsolation','P_CF position must remain frozen; V3.6 lambda=1 disables the replaced attitude-RBF output and update.');
    end
    rbfPositionOutputDelayEvents=double(field_or(opts,'rbf_position_output_delay_events',0));
    rbfAttitudeOutputDelayEvents=double(field_or(opts,'rbf_attitude_output_delay_events',0));
    assert(ismember(rbfPositionOutputDelayEvents,[0 1])&&ismember(rbfAttitudeOutputDelayEvents,[0 1]), ...
        'TCN0916:RbfOutputDelay','Only zero- or one-event audit delay is supported.');
    rbfPositionResetTime=double(field_or(opts,'rbf_position_reset_time_s',NaN));
    rbfAttitudeResetTime=double(field_or(opts,'rbf_attitude_reset_time_s',NaN));
    rbfPositionFreezeTime=double(field_or(opts,'rbf_position_freeze_time_s',NaN));
    rbfAttitudeFreezeTime=double(field_or(opts,'rbf_attitude_freeze_time_s',NaN));
    rbfPositionResetApplied=false; rbfAttitudeResetApplied=false;
    rbfPositionFrozen=false; rbfAttitudeFrozen=false;
    assert(isnan(rbfPositionResetTime)||isscalar(rbfPositionResetTime)&&isfinite(rbfPositionResetTime)&&rbfPositionResetTime>=0, ...
        'TCN0916:RbfPositionResetTime','Invalid Position RBF reset time.');
    assert(isnan(rbfAttitudeResetTime)||isscalar(rbfAttitudeResetTime)&&isfinite(rbfAttitudeResetTime)&&rbfAttitudeResetTime>=0, ...
        'TCN0916:RbfAttitudeResetTime','Invalid Attitude RBF reset time.');
    assert(isnan(rbfPositionFreezeTime)||isscalar(rbfPositionFreezeTime)&&isfinite(rbfPositionFreezeTime)&&rbfPositionFreezeTime>=0, ...
        'TCN0916:RbfPositionFreezeTime','Invalid Position RBF freeze time.');
    assert(isnan(rbfAttitudeFreezeTime)||isscalar(rbfAttitudeFreezeTime)&&isfinite(rbfAttitudeFreezeTime)&&rbfAttitudeFreezeTime>=0, ...
        'TCN0916:RbfAttitudeFreezeTime','Invalid Attitude RBF freeze time.');
    rbfUpdateFlag=false(n,1);
    positionEventLog=false(n,1);
    attitudeEventLog=false(n,1);
    positionEventBetaLog=nan(n,1);
    attitudeEventBetaLog=nan(n,1);
    rbfUpdateDt=zeros(n,1);
    rbfEventDt=zeros(n,1);
    rbfInputSample=zeros(n,6);
    rbfOutputRaw=zeros(n,3);
    rbfOutputUnclipped=nan(n,3);
    rbfOutputHeld=zeros(n,3);
    rbfWeightNorm=zeros(n,1);
    rbfWeightMax=zeros(n,1);
    rbfWeightDerivativeNorm=zeros(n,1);
    rbfBasisNorm=zeros(n,1);
    rbfBasisMax=zeros(n,1);
    rbfPositionUpdateFlag=false(n,1);
    rbfPositionOutputLimitActive=false(n,1);
    rbfAttitudeOutputLimitActive=false(n,1);
    rbfPositionUpdateDt=zeros(n,1);
    rbfPositionOutputRaw=zeros(n,3);
    rbfPositionOutputUnclipped=nan(n,3);
    rbfPositionOutputHeld=zeros(n,3);
    rbfPositionWeightNorm=zeros(n,1);
    rbfPositionWeightDerivativeNorm=zeros(n,1);
    rbfPositionBasisNorm=zeros(n,1);
    rbfPositionSurface=zeros(n,3);
    rbfPositionWidthScale=ones(n,1);
    rbfPositionWidthTarget=ones(n,1);
    rbfPositionWidthStep=zeros(n,1);
    rbfPositionWidthEvent=false(n,1);
    rbfPositionWidthFeature=nan(n,28);
    rbfPositionBasisNormRelativeError=zeros(n,1);
    rbfPositionBasisRelativeChange=zeros(n,1);
    rbfPositionBasisFallback=false(n,1);
    rbfPositionOutputBasisConsistency=zeros(n,1);
    rbfPositionUpdateBasisConsistency=zeros(n,1);
    rbfPositionEventDt=zeros(n,1);
    rbfPositionDeepFeature=zeros(n,32);
    rbfPositionDeepFeatureRaw=zeros(n,32);
    rbfPositionDeepFeatureNorm=zeros(n,1);
    rbfPositionDeepFeatureUpdate=false(n,1);
    rbfPositionDeepHistoryFill=zeros(n,1);
    rbfPositionDeepContributionRatio=zeros(n,1);
    rbfPositionWeightDeltaNorm=zeros(n,1);
    rbfPositionBasisAttention=zeros(n,size(cfg.rbf.position.centers,2));
    rbfPositionBasisGamma=zeros(n,size(cfg.rbf.position.centers,2));
    rbfAttitudeGammaScaleLog=nan(n,3);
    rbfAttitudeSurfaceLambdaLog=nan(n,1);
    rbfAttitudeSurfaceOriginal=nan(n,3);
    rbfAttitudeSurfaceLearn=nan(n,3);
    rbfAttitudeModFeature=nan(n,64);
    rbfAttitudeModEvent=false(n,1);
    rbfAttitudeModHistoryReady=false(n,1);
    rbfAttitudeModHistoryFill=zeros(n,1);
    rbfEventAudit=struct('time',zeros(rbfAuditMax,1),'dt',zeros(rbfAuditMax,1), ...
        'input',zeros(6,rbfAuditMax),'output_raw',zeros(3,rbfAuditMax), ...
        'weight_before',zeros(size(rbfAtt.W,1),3,rbfAuditMax), ...
        'weight_derivative',zeros(size(rbfAtt.W,1),3,rbfAuditMax), ...
        'weight_unprojected',zeros(size(rbfAtt.W,1),3,rbfAuditMax), ...
        'weight_after',zeros(size(rbfAtt.W,1),3,rbfAuditMax), ...
        'phi_norm',zeros(rbfAuditMax,1),'phi_max',zeros(rbfAuditMax,1));
    rbfPositionEventAudit=struct('time',zeros(rbfAuditMax,1),'dt',zeros(rbfAuditMax,1), ...
        'input',zeros(3,rbfAuditMax),'output_raw',zeros(3,rbfAuditMax), ...
        'weight_before',zeros(size(rbfPos.W,1),3,rbfAuditMax), ...
        'weight_derivative',zeros(size(rbfPos.W,1),3,rbfAuditMax), ...
        'weight_unprojected',zeros(size(rbfPos.W,1),3,rbfAuditMax), ...
        'weight_after',zeros(size(rbfPos.W,1),3,rbfAuditMax), ...
        'phi_norm',zeros(rbfAuditMax,1),'phi_max',zeros(rbfAuditMax,1));
    attitudeGammaScale=attitudeGammaScale(:);
    attitudeSurfaceLambda=1;
    tcnTrace=cell(n,1);
    heldTcnTorque=zeros(3,1);
    if tcnCandidate
        [tcnMemory,~]=tcn_attitude_step_v1('init',struct,struct,opts.tcn_attitude_model);
    end
    mlp15Trace=cell(n,1);
    heldMlp15Torque=zeros(3,1);
    if mlpCandidate
        [mlp15Memory,~]=mlp15_attitude_step_v1('init',struct,struct,opts.mlp15_attitude_model);
    end
    for k=1:n
        rbfTorqueForLog=zeros(3,1);
        attitudeHeadDeltaNorm(k)=norm(attitudeHeadDeltaW,'fro');
        attitudeHeadReadyEventCount(k)=attitudeFusionEventCount;
        stage1PcfEtaBeforeLog(k,:)=stage1PcfEta.';
        rbfAttitudeGammaScaleLog(k,:)=attitudeGammaScale(:).';
        rbfAttitudeSurfaceLambdaLog(k)=attitudeSurfaceLambda;
        if isfield(closureReset,'enabled')&&logical(closureReset.enabled)&&~closureResetApplied&& ...
                abs(t(k)-closureReset.time_s)<=1e-12
            % Diagnostic-only full closure reset. Default path is untouched.
            x(k,:)=double(closureReset.state(:)).';
            filter.euler=double(closureReset.filter_euler(:));
            filter.rate=double(closureReset.filter_rate(:));
            previousMotor=double(closureReset.previous_motor(:)).';
            previousInternalAtt=double(closureReset.previous_internal_att(:));
            previousInternalRate=double(closureReset.previous_internal_rate(:));
            closureResetApplied=true;
            closureResetAppliedLog(k)=true;
        end
        s0TriggerThisRow=false;
        if s0GuardEnabled
            if guardLatched
                policyMode{k}='FALLBACK_A0';
                fallbackSource{k}='A0';
                guardActiveLog(k)=true;
            elseif learnedHistoryFill==253
                policyMode{k}='STUDENT';
                studentAuthority(k)=true;
            else
                policyMode{k}='PRE_READY';
            end
        end
        r=reference_row(s.reference,k);
        if any(~isfinite(x(k,:)))
            status='SAFE_STOP_NAN_INF'; safetyStopReason='NAN_INF_STATE'; divergenceTime=t(k); last=k-1; break
        end
        positionErrorNow=norm(r.position-x(k,1:3).');
        actualRotation=rotation_zyx(x(k,7:9).');
        actualThrustTilt=acos(max(min(actualRotation(3,3),1),-1));
        bodyRateNorm=norm(x(k,10:12));
        if positionErrorNow>1, safetyPositionErrorTime=safetyPositionErrorTime+dt; else, safetyPositionErrorTime=0; end
        if actualThrustTilt>pi/3, safetyTiltTime=safetyTiltTime+dt; else, safetyTiltTime=0; end
        if bodyRateNorm>20, safetyRateTime=safetyRateTime+dt; else, safetyRateTime=0; end
        if safetyPositionErrorTime>=.2
            status='SAFE_STOP_POSITION_ERROR'; safetyStopReason='POSITION_ERROR_GT_1M_FOR_0P2S'; divergenceTime=t(k); last=k-1; break
        elseif safetyTiltTime>=.1
            status='SAFE_STOP_THRUST_AXIS_TILT'; safetyStopReason='ACTUAL_THRUST_AXIS_GT_60DEG_FOR_0P1S'; divergenceTime=t(k); last=k-1; break
        elseif safetyRateTime>=.05
            status='SAFE_STOP_BODY_RATE'; safetyStopReason='OMEGA_NORM_GT_20RADPS_FOR_0P05S'; divergenceTime=t(k); last=k-1; break
        end
        if wrenchDiagnosticEnabled
            injectedForceI=diagnosticForce(k,:).';
            injectedTorqueB=diagnosticTorque(k,:).';
        end
        if rlGapRuntimeEnabled
            [r,rlGapRuntime]=rlGapRuntimeStepFn(rlGapRuntime,x(k,:).',r,k,t(k),cfg);
            s.reference.position(k,:)=r.position(:).';
            s.reference.velocity(k,:)=r.velocity(:).';
            s.reference.acceleration(k,:)=r.acceleration(:).';
            s.reference.yaw(k)=r.euler(3);
            s.reference.yaw_rate(k)=r.euler_rate(3);
            s.reference.yaw_acceleration(k)=r.euler_acceleration(3);
            s.arms.command(k,:)=rlGapRuntime.u_rho(:).';
            s.arms.rho_true(k,:)=rlGapRuntime.rho_true(:).';
            s.arms.rho_hat(k,:)=rlGapRuntime.rho_hat(:).';
            s.arms.rhoDot_true(k,:)=rlGapRuntime.rhoDot_true(:).';
            s.arms.rhoDot_hat(k,:)=rlGapRuntime.rhoDot_hat(:).';
        end
        if ~rbfPositionResetApplied && isfinite(rbfPositionResetTime) && t(k)>=rbfPositionResetTime
            rbfPos.W(:)=0; rbfPositionResetApplied=true;
        end
        if ~rbfAttitudeResetApplied && isfinite(rbfAttitudeResetTime) && t(k)>=rbfAttitudeResetTime
            rbfAtt.W(:)=0; rbfAttitudeResetApplied=true;
        end
        if isfinite(rbfPositionFreezeTime) && t(k)>=rbfPositionFreezeTime, rbfPositionFrozen=true; end
        if isfinite(rbfAttitudeFreezeTime) && t(k)>=rbfAttitudeFreezeTime, rbfAttitudeFrozen=true; end
        Ptrue=simulation_parameters(cfg,s.arms.rho_true(k,:).',s.arms.rhoDot_true(k,:).');
        if formalRbfBaseline
            P=fixedController;
        else
            Phat=simulation_parameters(cfg,s.arms.rho_hat(k,:).',s.arms.rhoDot_hat(k,:).');
            P=controller_parameters(cfg,Phat);
        end
        assert(strcmp(P.morphology_mode,'fixed')&& ...
            max(abs(P.arm_lengths-cfg.plant.arm_initial))<1e-12, ...
            'RBFBS0:TrueMorphologyLeak','RBF-BS0 控制器必须只使用固定名义构型。');
        if positionNdoReconstructionEnabled
            if strcmp(positionNdoInputMode,'mode_reconstructed')
                reconstructionC=Phat.allocation.C;
                positionNdoEstimatedArmLengths(k,:)=Phat.arm_lengths(:).';
            else
                reconstructionC=P.allocation.C;
                positionNdoEstimatedArmLengths(k,:)=P.arm_lengths(:).';
            end
            positionNdoReconstructedMotor(k,:)=positionNdoMotorEstimate(:).';
            positionNdoReconstructedGeneralized(k,:)=(reconstructionC*positionNdoMotorEstimate.^2).';
            positionNdoMorphologyCommand(k,:)=s.arms.command(k,:);
        end
        if ~isempty(widthScaleFn)
            previousForWidth=zeros(4,1);
            if ~isempty(previousMotor), previousForWidth=previousMotor(:); end
            [widthScale,widthInfo]=widthScaleFn(t(k),k,x(k,:).',s.arms,previousForWidth,r,previousInternalAtt,previousInternalRate);
            assert(isscalar(widthScale)&&isfinite(widthScale)&&widthScale>=.85&&widthScale<=1.15, ...
                'TCN0916:RbfWidthHookValue','Position width hook returned an invalid width scale.');
            cfg.rbf.position.width_scale=double(widthScale);
            rbfPositionWidthScale(k)=double(widthScale);
            if isfield(widthInfo,'target'),rbfPositionWidthTarget(k)=double(widthInfo.target);end
            if isfield(widthInfo,'step'),rbfPositionWidthStep(k)=double(widthInfo.step);end
            if isfield(widthInfo,'event'),rbfPositionWidthEvent(k)=logical(widthInfo.event);end
            if isfield(widthInfo,'feature')
                q=min(numel(widthInfo.feature),28); rbfPositionWidthFeature(k,1:q)=double(widthInfo.feature(1:q));
            end
        end
        if ~isempty(positionDeepBasisFn)
            previousForDeep=zeros(4,1);if ~isempty(previousMotor),previousForDeep=double(previousMotor(:));end
            [deepFeature,deepInfo]=positionDeepBasisFn(t(k),k,x(k,:).',s.arms,previousForDeep,r,previousInternalAtt,previousInternalRate);
            deepFeature=double(deepFeature(:));
            assert(numel(deepFeature)==positionDeepDim&&all(isfinite(deepFeature)), ...
                'TCN0916:DeepBasisFeature','Position deep feature has invalid size or values.');
            rbfPositionDeepFeature(k,1:positionDeepDim)=deepFeature.';
            rbfPositionDeepFeatureNorm(k)=norm(deepFeature);
            if isfield(deepInfo,'raw_feature'),raw=double(deepInfo.raw_feature(:));rbfPositionDeepFeatureRaw(k,1:min(32,numel(raw)))=raw(1:min(32,numel(raw))).';end
            if isfield(deepInfo,'update'),rbfPositionDeepFeatureUpdate(k)=logical(deepInfo.update);end
            if isfield(deepInfo,'history_fill'),rbfPositionDeepHistoryFill(k)=double(deepInfo.history_fill);end
            if isfield(deepInfo,'basis_attention')
                a=double(deepInfo.basis_attention(:));assert(numel(a)==size(cfg.rbf.position.centers,2)&&all(a>.5&a<1.5), ...
                    'TCN0916:BasisAttention','Position basis attention must be in (0.5,1.5).');
                rbfPositionBasisAttention(k,:)=a.';
            end
            if isfield(deepInfo,'basis_gamma_scale')
                g=double(deepInfo.basis_gamma_scale(:));assert(numel(g)==size(cfg.rbf.position.centers,2)&&all(g>.5&g<2), ...
                    'TCN0916:BasisGamma','Position basis Gamma ratio must be in (0.5,2).');
                rbfPositionBasisGamma(k,:)=g.';
            end
        end
        % Low-rate B-G/B-S hooks receive one causal 50-Hz history tick here.
        % The same callback is called again at the actual Attitude-RBF event
        % below, after the current BS surface is available.
        if ~isempty(attitudeModFn)
            previousForMod=zeros(4,1); if ~isempty(previousMotor),previousForMod=double(previousMotor(:));end
            attitudeModFn(t(k),k,x(k,:).',s.arms,previousForMod,r,[],[],previousInternalAtt,previousInternalRate);
        end
        if ~formalRbfBaseline
            motorForCausal=zeros(4,1);
            if ~isempty(previousMotor),motorForCausal=previousMotor;end
            causalMotor(k,:)=motorForCausal.';
            causalResidual(k,:)=trv1_total_residual_label(x(k,:).',motorForCausal,Ptrue,Phat, ...
                s.environment_wind_I(k,:).',wcfg).';
            if s0GuardEnabled && ~guardLatched && learnedHistoryFill==253
                studentEligible(k)=all(isfinite([x(k,:),causalResidual(k,:)]));
            end
        end
        dF=zeros(3,1);
        dT=zeros(3,1);
        timer=tic;
        debugEvent=0;
        rbfFullEvent=false;
        rbfFullDt=0;
        attitudeEvent=false;
        attitudeEventDt=0;
        if isRbfFullScheduled
            [rbfFullEvent,rbfFullPhase,rbfFullDt,lastRbfFullEventTime]=rbf_event_scheduler_step( ...
                rbfFullPhase,rbfFullHz,dt,t(k),lastRbfFullEventTime);
        end
        if isRbfFullSplit
            [attitudeEvent,rbfPhase,attitudeEventDt,lastRbfEventTime]=rbf_event_scheduler_step( ...
                rbfPhase,rbfHz,dt,t(k),lastRbfEventTime);
            if k==1
                rbfFullEvent=false; rbfFullDt=0; attitudeEvent=false; attitudeEventDt=0;
            end
        end
        positionEventLog(k)=rbfFullEvent;
        attitudeEventLog(k)=attitudeEvent;
        contextEvent=false; contextEventDt=0;
        if contextErrorAdaptive
            if ~contextGateReady && t(k)>=5.04-1e-12 && contextPriorReady
                contextGateReady=true; contextPhase=0; contextLastEventTime=t(k);
            end
            if contextGateReady
                [contextEvent,contextPhase,contextEventDt,contextLastEventTime]=rbf_event_scheduler_step( ...
                    contextPhase,contextRateHz,dt,t(k),contextLastEventTime);
            end
        end
        if isNetwork
            previousForFeature=zeros(4,1);
            if ~isempty(previousMotor),previousForFeature=previousMotor;
            end
            featureRow=trv1_online_feature_row(x(k,:),s.arms.command(k,:),s.arms.rho_hat(k,:),s.arms.rhoDot_hat(k,:),previousForFeature.').';
            if k>1 && mod(k-1,5)==0
                featureHistory=[featureHistory(:,2:end),single(featureRow)];
                featureFill=min(featureFill+1,64);
                networkUpdate(k)=true;
                if field_or(opts,'command_active_gate',false),heldGate=any(abs(s.arms.command(k,:))>0);
                end
                if featureFill==64
                    networkTimer=tic;
                    networkOutput=network_predict_dynamic(opts.network,method,featureHistory);
                    networkCallTime(k)=toc(networkTimer);
                end
            end

            release=0;
            if featureFill==64,release=min(max(((k-1)*dt-.320)/.200,0),1);
            end
            applied=release*heldGate*networkOutput;
            networkRaw(k,:)=networkOutput.';
            networkApplied(k,:)=applied.';
            networkGate(k)=heldGate;
            networkRelease(k)=release;
            if contains(method,'Att'), dF=zeros(3,1);
            else, dF=applied(1:3);
            end
            [~,positionInfo]=position_bs_step(x(k,:).',r,dF,P);
            [thrust,eul,limited]=baseline_force_to_attitude(positionInfo.commanded_acceleration,x(k,9),P);
            target=[eul(1:2);r.euler(3)];
            [ir,filter,filterAccelerationRequest]=command_filter_step(target,filter,P);
            filterTargetLog(k,:)=target(:).';
            filterRequestedAccelerationLog(k,:)=filterAccelerationRequest(:).';
            filterAppliedAccelerationLog(k,:)=ir.euler_acceleration(:).';
            if contains(method,'Pos'),dT=zeros(3,1);
            else,dT=applied(4:6);
            end
            moments=attitude_bs_step(x(k,:).',ir,dT,P);
            command=[thrust;moments];
            raw=target;
            ip=r.position;
            ipr=r.velocity;
            z3=nan(6,1);
        else
            if oracleEnabled
                oracleStride=max(1,round((1/dt)/oracleForceRate));
                if t(k)>=oracleStartTime-1e-12 && mod(k-1,oracleStride)==0
                    motorForOracle=zeros(4,1); if ~isempty(previousMotor),motorForOracle=previousMotor;end
                    oracleResidual=trv1_total_residual_label(x(k,:).',motorForOracle,Ptrue,Phat,s.environment_wind_I(k,:).',wcfg);
                    oracleForce=oracleResidual(1:3);
                    oracleForceUpdate(k)=true;
                    networkUpdate(k)=true;
                end
                networkOutput=[oracleForce;zeros(3,1)];
                dF=oracleForce; dT=zeros(3,1);
            end
            if truthOracleEnabled
                if t(k)>=truthOracleStartTime-1e-12 && mod(k-1,truthOracleStride)==0
                    [truthCurrent,truthFuture,truthHold]=truth_wind_oracle_candidates(s,cfg,k,x(k,:).',Ptrue,wcfg,truthOracleHorizonSamples);
                    truthOracleCurrent(k,:)=truthCurrent.';
                    truthOracleFuture(k,:)=truthFuture.';
                    truthOracleHold(k,:)=truthHold.';
                    switch truthOracleMode
                        case 'current50', oracleForce=truthCurrent;
                        case 'future_point20', oracleForce=truthFuture;
                        case 'next_hold_avg20', oracleForce=truthHold;
                    end
                    truthOracleCompensation(k,:)=-oracleForce.';
                    truthOracleEvent(k)=true;
                    truthOracleZohStart(k)=t(k);
                    truthOracleZohEnd(k)=min(t(k)+truthOracleStride*dt,t(end));
                    oracleForceUpdate(k)=true;
                    networkUpdate(k)=true;
                end
                networkOutput=[oracleForce;zeros(3,1)];
                dF=oracleForce; dT=zeros(3,1);
                networkGate(k)=double(t(k)>=truthOracleStartTime-1e-12);
                networkRelease(k)=double(t(k)>=truthOracleStartTime-1e-12);
            end
            if isLearnedForce
                if mod(k-1,20)==0
                    previousFeature=zeros(4,1,'double');
                    if ~isempty(previousMotor), previousFeature=double(previousMotor);
                    end
                    [Tprev,~]=euler_kinematics(x(k,7:9).',x(k,10:12).');
                    contextRow=[double(r.position)-double(x(k,1:3).'); double(r.velocity)-double(x(k,4:6).'); double(wrap(previousInternalAtt-x(k,7:9).')); double(previousInternalRate-Tprev*x(k,10:12).'); previousFeature.^2];
                    wasEmpty=learnedHistoryFill==0;
                    [learnedHistory,learnedHistoryState,historyInfo]= ...
                        tcn0916_cold_start_update(learnedHistoryState,contextRow);
                    learnedHistoryFill=historyInfo.N_real;
                    if wasEmpty
                        learnedHistoryTimes(:)=t(k);
                    else
                        learnedHistoryTimes=[learnedHistoryTimes(2:end),t(k)];
                    end
                    historyMaturity=historyInfo.history_maturity;
                    historyAlpha=historyInfo.alpha;
                    v1HistoryMaturity(k)=historyMaturity;
                    v1NReal(k)=learnedHistoryFill;
                    v1Alpha(k)=historyAlpha;
                    historyReady=(v1Adaptive || isFullHistoryForce) && learnedHistoryFill==253 || ...
                        (~v1Adaptive && ~isFullHistoryForce && learnedHistoryFill>0);
                    currentFeature=[double(x(k,:)),double(s.arms.command(k,:)),double(s.arms.rho_hat(k,:)),double(s.arms.rhoDot_hat(k,:)),previousFeature.'.^2];
                    if oracleEnabled
                        release=1;
                    elseif v1Adaptive || a3sV2Adaptive
                        v1EventFlag(k)=true;
                        v1EventTime(k)=t(k);
                        v1CommandState8(k,:)=currentFeature(17:24).';
                        previousLearnerEventTime=v1LastLearnerEventTime;
                        v1LastLearnerEventTime=t(k);
                    elseif isFullHistoryForce && historyReady
                        v1EventFlag(k)=true;
                        v1EventTime(k)=t(k);
                        v1CommandState8(k,:)=currentFeature(17:24).';
                    end
                    if debugEnabled
                        debugCount=debugCount+1;
                        debugEvent=debugCount;
                        forwardDebug.time(debugEvent)=t(k);
                        forwardDebug.step(debugEvent)=k;
                        forwardDebug.event_index(debugEvent)=debugEvent;
                        forwardDebug.learner_enabled(debugEvent)=true;
                        forwardDebug.history_ready(debugEvent)=historyReady;
                        forwardDebug.history_valid_count(debugEvent)=learnedHistoryFill;
                        if learnedHistoryFill>0, oldestIdx=253-learnedHistoryFill+1;
                            forwardDebug.oldest_history_time(debugEvent)=learnedHistoryTimes(oldestIdx);
                            forwardDebug.newest_history_time(debugEvent)=learnedHistoryTimes(253);
                        end
                        forwardDebug.append_before_infer(debugEvent)=true;
                        forwardDebug.current_feature_raw(:,debugEvent)=currentFeature(:);
                        forwardDebug.current20_raw(:,debugEvent)=[currentFeature(1:16),currentFeature(25:28)].';
                        forwardDebug.command_state_raw(:,debugEvent)=currentFeature(17:24).';
                        forwardDebug.previous_motor_squared(:,debugEvent)=currentFeature(25:28).';
                        forwardDebug.history_raw(:,:,debugEvent)=learnedHistory;
                    end
                    if historyReady
                        v1HistoryReady(k)=v1Adaptive || isFullHistoryForce;
                        if s0GuardEnabled && ~guardLatched
                            policyMode{k}='STUDENT';
                            studentAuthority(k)=true;
                            studentEligible(k)=all(isfinite([x(k,:),causalResidual(k,:)]));
                        end
                        v1PhiNorm(k)=NaN;
                        currentFeatureBefore=currentFeature;
                        historyBefore=learnedHistory;
                        networkTimer=tic;
                        if v1Adaptive
                            if v1Rbf
                                [~,frozenPhysical,featureDebug]=v1_frozen_force_feature(opts.network,v1FeatureKind,currentFeature,learnedHistory);
                                c8=featureDebug.c8;
                                metricPhi=v1_rbf_force_head('basis',opts.v1_head,c8);
                                networkOutput=[v1_rbf_force_head('predict',opts.v1_head,c8,frozenPhysical(1:3));zeros(3,1)];
                            else
                                [metricPhi,frozenPhysical,~]=v1_frozen_force_feature(opts.network,v1Kind,currentFeature,learnedHistory);
                                phiBar=[metricPhi;1];
                                rawForce=v1_force_head_predict(opts.v1_head,metricPhi);
                                v1Phi32Norm(k)=norm(metricPhi);
                                if strcmp(v1Law,'bounded')
                                    phiBar=phiBar/max(1,norm(phiBar));
                                    v1BoundedPhiNorm(k)=norm(phiBar);
                                    networkOutput=[(phiBar.'*opts.v1_head.weight).';zeros(3,1)];
                                    v1RawForceDiagnostic(k,:)=rawForce.';
                                    v1BoundedForceOutput(k,:)=networkOutput(1:3).';
                                else
                                    networkOutput=[rawForce;zeros(3,1)];
                                end
                            end
                            networkCallTime(k)=toc(networkTimer);
                            networkUpdate(k)=true;
                            v1PhiNorm(k)=norm([metricPhi;1]);
                            v1ForceOffParity(k)=max(abs(networkOutput(1:3)-frozenPhysical(1:3)));
                            [~,positionInfoAtEvent]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                            dtUpdate=t(k)-previousLearnerEventTime;
                            if isnan(dtUpdate), error('TCN0910:AdaptiveDt','First adaptive event cannot update without a prior learner event.'); end
                            weightBefore=opts.v1_head.weight;
                            if v1Rbf
                                [opts.v1_head,headInfo]=v1_rbf_force_head('update',opts.v1_head,c8,positionInfoAtEvent.surface,dtUpdate);
                            elseif any(strcmp(v1Law,{'normalized','bounded'}))
                                [opts.v1_head,headInfo]=v1_force_head_update_normalized(opts.v1_head,metricPhi,positionInfoAtEvent.surface,dtUpdate);
                            else
                                [opts.v1_head,headInfo]=v1_force_head_update(opts.v1_head,metricPhi,positionInfoAtEvent.surface,dtUpdate);
                            end
                            v1Surface(k,:)=positionInfoAtEvent.surface.';
                            v1UpdateDt(k)=dtUpdate;
                            v1WeightDeltaNorm(k)=headInfo.weight_delta_fro;
                            v1WeightDerivativeNorm(k)=headInfo.weight_derivative_fro;
                            v1ProjectionActive(k)=headInfo.projection_active;
                            phiBar=[metricPhi;1];
                            qPhi=norm(phiBar)^2;
                            gammaValue=double(opts.v1_head.gamma);
                            if ~isscalar(gammaValue),gammaValue=norm(gammaValue,2);
                            end
                            v1QPhi(k)=qPhi;
                            v1Z2Norm(k)=norm(positionInfoAtEvent.surface);
                            v1RawDrivingMagnitude(k)=dtUpdate*gammaValue*sqrt(qPhi)*v1Z2Norm(k);
                            v1NormalizedDrivingMagnitude(k)=dtUpdate*gammaValue*sqrt(qPhi)/max(1,sqrt(qPhi))*v1Z2Norm(k);
                            v1RelativeWeightUpdate(k)=headInfo.weight_delta_fro/(norm(weightBefore,'fro')+eps);
                            v1WeightDeltaMatrix(k,:,:)=opts.v1_head.weight-weightBefore;
                            if ~isnan(dtUpdate) && isnan(v1FirstAdaptationTime), v1FirstAdaptationTime=t(k);
                            end
                        elseif a3sV2Adaptive
                            [~,guardForward]=network_predict_frozen(opts.network,method,currentFeature,learnedHistory);
                            priorForce=double(guardForward.physical_output(1:3));
                            phi32=double(guardForward.phi32(:));
                            [phiT,featureInfo]=v2_feature_norm_limit(phi32,opts.a3s_v2_head.feature_limit);
                            if a3sV2FastAdaptive
                                fastPriorForce=priorForce; fastPhiT=phiT; fastPhiRawNorm=featureInfo.raw_norm;
                                fastPhiBoundedNorm=featureInfo.bounded_norm; fastFeatureLimiter=featureInfo.limiter_active; fastHeadReady=true;
                            end
                            deltaForce=v2_delta_force_head_predict(opts.a3s_v2_head,phiT);
                            networkOutput=[priorForce+deltaForce;zeros(3,1)];
                            networkCallTime(k)=toc(networkTimer);
                            networkUpdate(k)=true;
                            a3sPriorForce(k,:)=priorForce.';
                            a3sDeltaForce(k,:)=deltaForce.';
                            a3sTotalForce(k,:)=networkOutput(1:3).';
                            a3sPhiRawNorm(k)=featureInfo.raw_norm;
                            a3sPhiBoundedNorm(k)=featureInfo.bounded_norm;
                            a3sFeatureLimiterActive(k)=featureInfo.limiter_active;
                            a3sForceOffParity(k)=max(abs(networkOutput(1:3)-priorForce));
                            [~,positionInfoAtEvent]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                            z2Now=double(positionInfoAtEvent.surface(:));
                            if ~a3sV2FastAdaptive
                                dtUpdate=t(k)-previousLearnerEventTime;
                                if isnan(dtUpdate),error('TCN0916:A3SV2Dt','First adaptive event cannot update without a prior learner event.');end
                                weightBefore=opts.a3s_v2_head.weight;
                                [opts.a3s_v2_head,headInfo]=v2_delta_force_head_update(opts.a3s_v2_head,phiT,z2Now,dtUpdate);
                                a3sZ2(k,:)=z2Now.';
                                a3sDrivingNorm(k)=double(opts.a3s_v2_head.gamma)*norm(phiT)*norm(z2Now);
                                a3sPerEventDeltaW(k)=headInfo.weight_delta_fro;
                                a3sProjectionActive(k)=headInfo.projection_active;
                                a3sDeltaWNorm(k)=norm(opts.a3s_v2_head.weight,'fro');
                                a3sDeltaWExcursion(k)=a3sDeltaWNorm(k);
                            else
                                dtUpdate=dt; weightBefore=opts.a3s_v2_head.weight;
                                headInfo=struct('weight_delta_fro',0,'weight_derivative_fro',0,'projection_active',false);
                            end
                            v1Phi32Norm(k)=featureInfo.raw_norm;
                            v1BoundedPhiNorm(k)=featureInfo.bounded_norm;
                            v1Surface(k,:)=z2Now.';
                            v1UpdateDt(k)=dtUpdate;
                            v1WeightDeltaNorm(k)=headInfo.weight_delta_fro;
                            v1WeightDerivativeNorm(k)=headInfo.weight_derivative_fro;
                            v1ProjectionActive(k)=headInfo.projection_active;
                            v1QPhi(k)=featureInfo.bounded_norm^2;
                            v1Z2Norm(k)=norm(z2Now);
                            v1RawDrivingMagnitude(k)=dtUpdate*double(opts.a3s_v2_head.gamma)*featureInfo.raw_norm*norm(z2Now);
                            v1NormalizedDrivingMagnitude(k)=dtUpdate*double(opts.a3s_v2_head.gamma)*featureInfo.bounded_norm*norm(z2Now);
                            v1RelativeWeightUpdate(k)=headInfo.weight_delta_fro/(norm(weightBefore,'fro')+eps);
                            if isnan(v1FirstAdaptationTime),v1FirstAdaptationTime=t(k);end
                        else
                            [networkOutput,guardForward]=network_predict_frozen(opts.network,method,currentFeature,learnedHistory);
                            if isfield(opts,'predictive_force_head') && isstruct(opts.predictive_force_head)
                                [futureForce,predictiveInfo]=predictive_short_force_predict(opts.predictive_force_head,currentFeature,guardForward.c8);
                                networkOutput=[futureForce;zeros(3,1)];
                                guardForward.physical_output=networkOutput;
                                guardForward.predictive_force=true;
                                guardForward.predictive_horizon_ms=predictiveInfo.horizon_ms;
                            end
                            networkCallTime(k)=toc(networkTimer);
                            networkUpdate(k)=true;
                            if contextErrorAdaptive && contextUsesNetwork
                                if contextIncludePrior, contextPriorForce=double(guardForward.physical_output(1:3)); else, contextPriorForce=zeros(3,1); end
                                if contextUsesM2, contextPhi32=double(guardForward.phi32(:)); else, contextPhi32=double(guardForward.context32(:)); end
                                contextPriorReady=true;
                            end
                            if s0GuardEnabled
                                nonfiniteLearner=any(~isfinite(networkOutput));
                                positionErrorNorm=norm(currentFeature(1:3).'-double(r.position(:)));
                                attitudeErrorNorm=norm(wrap(previousInternalAtt-x(k,7:9).'));
                                forceViolation=~nonfiniteLearner && norm(networkOutput(1:3))>double(opts.s0_guard.force_guard_N);
                                positionViolation=positionErrorNorm>double(opts.s0_guard.position_error_guard_m);
                                attitudeViolation=attitudeErrorNorm>double(opts.s0_guard.attitude_error_guard_rad);
                                if ~guardLatched && (nonfiniteLearner || forceViolation || positionViolation || attitudeViolation)
                                    guardLatched=true;
                                    guardTrigger(k)=true;
                                    guardTriggerTime=t(k);
                                    s0TriggerThisRow=true;
                                    if nonfiniteLearner,guardTriggerReason{k}='NONFINITE_LEARNER_OUTPUT';
                                    elseif forceViolation,guardTriggerReason{k}='FORCE_GUARD';
                                    elseif positionViolation,guardTriggerReason{k}='POSITION_ERROR_GUARD';
                                    else,guardTriggerReason{k}='ATTITUDE_ERROR_GUARD';
                                    end
                                    networkOutput(~isfinite(networkOutput))=0;
                                end
                            end
                            if ~diagnosticFallbackActive && isfinite(diagnosticFallbackThreshold) && ...
                                    norm(networkOutput(1:3))>diagnosticFallbackThreshold
                                diagnosticFallbackActive=true;
                                diagnosticFallbackTrigger(k)=true;
                                diagnosticFallbackTime=t(k);
                            end
                            if guardEnabled
                                [guardSupportScore(k),guardSupportParts(k,:)]=guard_support(guardForward,opts.guard);
                                guardDynamicSupportScore(k)=guardSupportScore(k);
                                guardForceNorm(k)=norm(networkOutput(1:3));
                                if guardHavePreviousForce
                                    guardForceGrowth(k)=norm(networkOutput(1:3)-guardPreviousForce);
                                    guardGrowthWindowCount=min(guardGrowthWindowCount+1,numel(guardGrowthWindow));
                                    guardGrowthWindow=[guardGrowthWindow(2:end);guardForceGrowth(k)];
                                    guardForceGrowthSmooth(k)=mean(guardGrowthWindow(end-guardGrowthWindowCount+1:end));
                                else
                                    guardForceGrowth(k)=0;
                                    guardForceGrowthSmooth(k)=0;
                                end
                                limits=double(opts.guard.support_limits(:)).';
                                if guardHavePreviousCommand
                                    guardCommandGrowth(k)=norm(guardForward.command_norm(:)-guardPreviousCommand);
                                end
                                if guardHavePreviousCommand && guardCommandGrowth(k)>double(field_or(opts.guard,'command_shift_threshold',.5))
                                    guardMorphologyRecent=4;
                                elseif guardMorphologyRecent>0
                                    guardMorphologyRecent=guardMorphologyRecent-1;
                                end
                                guardPreviousCommand=guardForward.command_norm(:);
                                guardHavePreviousCommand=true;
                                guardMorphologyRecentLog(k)=guardMorphologyRecent;
                                % command/morphology are diagnostic only; the trigger uses
                                % dynamic support groups A/B/C = history/current/motor^2.
                                dynamicGroups=double(field_or(opts.guard,'dynamic_group_indices',[1 2 4]));
                                requireAll=strcmp(char(field_or(opts.guard,'dynamic_support_rule','all')),'all');
                                requiredGroups=numel(dynamicGroups); if ~requireAll,requiredGroups=2;end
                                supportAbnormal=sum(guardSupportParts(k,dynamicGroups)>limits(dynamicGroups))>=requiredGroups;
                                forceAbnormal=guardForceNorm(k)>double(opts.guard.force_threshold_N) || ...
                                    guardForceGrowthSmooth(k)>double(field_or(opts.guard,'growth_threshold_N',inf));
                                if supportAbnormal && forceAbnormal && historyMaturity>=double(field_or(opts.guard,'min_history_maturity',.60))
                                    guardPersistence=guardPersistence+1;
                                else
                                    guardPersistence=0;
                                end
                                guardPersistenceLog(k)=guardPersistence;
                                guardPreviousForce=networkOutput(1:3);
                                guardHavePreviousForce=true;
                                if ~guardLatched && guardPersistence>=double(opts.guard.persistence_events)
                                    guardLatched=true;
                                    guardTrigger(k)=true;
                                    guardTriggerTime=t(k);
                                end
                            end
                        end
                        if debugEnabled
                            if v1Adaptive
                                [~,forwardCall]=network_predict_frozen(opts.network,method,currentFeature,learnedHistory);
                            else
                                forwardCall=guardForward;
                            end
                            debugModelCalls=debugModelCalls+1;
                            mapperInput=nan(36,1);
                            mapperInput(1:numel(forwardCall.mapper_input_norm))=forwardCall.mapper_input_norm;
                            forwardDebug.model_call(debugEvent)=true;
                            forwardDebug.fast_norm(:,debugEvent)=forwardCall.fast_norm;
                            forwardDebug.command_norm(:,debugEvent)=forwardCall.command_norm;
                            forwardDebug.mapper_input_norm(:,debugEvent)=mapperInput;
                            forwardDebug.history_norm(:,:,debugEvent)=field_or(forwardCall,'history_norm',nan(16,253));
                            forwardDebug.c8(:,debugEvent)=field_or(forwardCall,'c8',nan(size(forwardDebug.c8,1),1));
                            forwardDebug.phi32(:,debugEvent)=field_or(forwardCall,'phi32',nan(32,1));
                            forwardDebug.std_output(:,debugEvent)=forwardCall.std_output;
                            forwardDebug.physical_output(:,debugEvent)=forwardCall.physical_output;
                            forwardDebug.input_mutation_max(debugEvent)=max(abs(currentFeature(:)-currentFeatureBefore(:)));
                            forwardDebug.history_input_mutation_max(debugEvent)=max(abs(learnedHistory(:)-historyBefore(:)));
                            forwardDebug.network_call_time_s(debugEvent)=networkCallTime(k);
                            repeatCount=field_or(opts,'debug_repeat_count',0);
                            repeatEvents=field_or(opts,'debug_repeat_model_calls',3);
                            if repeatCount>0 && debugModelCalls<=repeatEvents
                                for repeatIndex=1:repeatCount, repeatOutput=network_predict_frozen(opts.network,method,currentFeature,learnedHistory);
                                    forwardDebug.repeat_physical(:,repeatIndex,debugEvent)=repeatOutput;
                                end
                            end
                        end
                    end
                end
                if a3sV2FastAdaptive && fastHeadReady
                    deltaForce=v2_delta_force_head_predict(opts.a3s_v2_head,fastPhiT);
                    networkOutput=[fastPriorForce+deltaForce;zeros(3,1)];
                    a3sPriorForce(k,:)=fastPriorForce.'; a3sDeltaForce(k,:)=deltaForce.'; a3sTotalForce(k,:)=networkOutput(1:3).';
                    a3sPhiRawNorm(k)=fastPhiRawNorm; a3sPhiBoundedNorm(k)=fastPhiBoundedNorm; a3sFeatureLimiterActive(k)=fastFeatureLimiter;
                    a3sForceOffParity(k)=max(abs(networkOutput(1:3)-fastPriorForce));
                    v1Phi32Norm(k)=fastPhiRawNorm; v1BoundedPhiNorm(k)=fastPhiBoundedNorm; v1QPhi(k)=fastPhiBoundedNorm^2;
                end
                    if contextErrorAdaptive
                        if contextUsesNetwork && ~contextIncludePrior && (~contextGateReady || ~logical(contextHead.adaptation_enabled))
                            networkOutput=zeros(6,1);
                        end
                        if contextGateReady
                            [~,contextPositionInfo]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                            z1Now=double(contextPositionInfo.error(:)); z2Now=double(contextPositionInfo.surface(:));
                            z1Bar=z1Now./contextZ1Scale; z2Bar=z2Now./contextZ2Scale;
                            contextPriorForceLog(k,:)=contextPriorForce.'; contextDeltaForce(k,:)=contextHeldDelta.';
                            contextZ1(k,:)=z1Now.'; contextZ2(k,:)=z2Now.'; contextZ1Bar(k,:)=z1Bar.'; contextZ2Bar(k,:)=z2Bar.';
                            contextWeightNorm(k)=norm(contextHead.weight,'fro'); contextLastEventTimeLog(k)=contextLastEventTime;
                            if contextEvent && contextPriorReady
                                [psi,featureInfo]=context_regressor(contextMode,contextPhi32,z1Now,z2Now,contextHead.feature_limit,contextZ1Scale,contextZ2Scale,contextRbfCfg);
                                weightBefore=contextHead.weight;
                                if strcmp(contextBasis,'rbf')
                                    [contextHeldDelta,contextHead,headInfo]=rbf_context_update(contextHead,psi,z2Now,contextEventDt,P.mass,min(t(k)/contextRbfCfg.beta_rise_time,1),contextRbfCfg);
                                    contextForceSaturation(k)=headInfo.output_clipped;
                                else
                                    rawDelta=psi.'*double(weightBefore); if isfield(contextHead,'force_limit_N'), contextForceSaturation(k)=norm(rawDelta)>double(contextHead.force_limit_N); end
                                    contextHeldDelta=v2_delta_force_head_predict(contextHead,psi);
                                    [contextHead,headInfo]=v2_delta_force_head_update(contextHead,psi,z2Now,contextEventDt);
                                end
                                contextUpdateFlag(k)=true; contextUpdateDt(k)=contextEventDt;
                                if isnan(contextFirstEventTime),contextFirstEventTime=t(k);end
                                contextPriorForceLog(k,:)=contextPriorForce.'; contextDeltaForce(k,:)=contextHeldDelta.';
                                contextFeatureNorm(k)=featureInfo.bounded_norm; contextFeatureLimiterActive(k)=featureInfo.limiter_active;
                                contextWeightDerivativeNorm(k)=headInfo.weight_derivative_fro; contextProjectionActive(k)=headInfo.projection_active;
                                contextDeltaWNorm(k)=norm(contextHead.weight-weightBefore,'fro');
                                contextContributionScale=1; if strcmp(contextBasis,'rbf'),contextContributionScale=P.mass*min(t(k)/contextRbfCfg.beta_rise_time,1);end
                                contextRbfContribution(k,:)=contextContributionScale*block_contribution(featureInfo.rbf_block,featureInfo.rbf_rows,weightBefore);
                                contextPhiContribution(k,:)=contextContributionScale*block_contribution(featureInfo.phi_block,featureInfo.phi_rows,weightBefore);
                                contextZ1Contribution(k,:)=contextContributionScale*block_contribution(featureInfo.z1_block,featureInfo.z1_rows,weightBefore);
                                contextZ2Contribution(k,:)=contextContributionScale*block_contribution(featureInfo.z2_block,featureInfo.z2_rows,weightBefore);
                                contextBiasContribution(k,:)=contextContributionScale*weightBefore(end,:);
                            end
                        end
                        if contextUsesNetwork && logical(contextHead.adaptation_enabled) && contextGateReady && contextPriorReady
                            networkOutput=[contextPriorForce+contextHeldDelta;zeros(3,1)];
                        end
                    end
                    if v1Adaptive
                        if v1EventFlag(k), v1ReleaseHeld=0;
                        if v1HistoryReady(k), v1ReleaseHeld=min(max((t(k)-learnedFirstValidTime)/.200,0),1);
                        end, end
                        release=v1ReleaseHeld;
                    else
                        release=0;
                        if isFullHistoryForce
                            release=double(learnedHistoryFill==253);
                        elseif learnedHistoryFill>0
                            release=historyAlpha;
                        end
                    end
                    networkOutputForApply=networkOutput;
                    if isfinite(diagnosticForceBound)
                        forceNorm=norm(networkOutputForApply(1:3));
                        if forceNorm>diagnosticForceBound
                            networkOutputForApply(1:3)=diagnosticForceBound*networkOutputForApply(1:3)/forceNorm;
                            diagnosticForceBoundActive(k)=true;
                        end
                    end
                    if isLearnedForce,networkOutputForApply(1:3)=learnedForceLambda*networkOutputForApply(1:3);end
                    applied=release*networkOutputForApply;
                    if diagnosticFallbackActive
                        applied(1:3)=0;
                        diagnosticFallbackActiveLog(k)=true;
                    end
                    if guardLatched && ~(s0GuardEnabled && s0TriggerThisRow)
                        applied(1:3)=0;
                        guardActiveLog(k)=true;
                        policyMode{k}='FALLBACK_A0';
                        fallbackSource{k}='A0';
                    end
                    applied(4:6)=0;
                    if a3sV2FastAdaptive && fastHeadReady
                        [~,fastPositionInfo]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                        z2Fast=double(fastPositionInfo.surface(:)); weightBefore=opts.a3s_v2_head.weight;
                        [opts.a3s_v2_head,headInfo]=v2_delta_force_head_update(opts.a3s_v2_head,fastPhiT,z2Fast,dt);
                        a3sFastUpdateFlag(k)=true; a3sFastUpdateDt(k)=dt; a3sZ2(k,:)=z2Fast.';
                        a3sDrivingNorm(k)=double(opts.a3s_v2_head.gamma)*norm(fastPhiT)*norm(z2Fast);
                        a3sPerEventDeltaW(k)=headInfo.weight_delta_fro; a3sProjectionActive(k)=headInfo.projection_active;
                        a3sDeltaWNorm(k)=norm(opts.a3s_v2_head.weight,'fro'); a3sDeltaWExcursion(k)=a3sDeltaWNorm(k);
                        v1Surface(k,:)=z2Fast.'; v1UpdateDt(k)=dt; v1WeightDeltaNorm(k)=headInfo.weight_delta_fro;
                        v1WeightDerivativeNorm(k)=headInfo.weight_derivative_fro; v1ProjectionActive(k)=headInfo.projection_active;
                        v1Z2Norm(k)=norm(z2Fast); v1RawDrivingMagnitude(k)=dt*double(opts.a3s_v2_head.gamma)*fastPhiRawNorm*norm(z2Fast);
                        v1NormalizedDrivingMagnitude(k)=dt*double(opts.a3s_v2_head.gamma)*fastPhiBoundedNorm*norm(z2Fast);
                        v1RelativeWeightUpdate(k)=headInfo.weight_delta_fro/(norm(weightBefore,'fro')+eps);
                    end
                    networkRaw(k,:)=networkOutput.';
                    networkApplied(k,:)=applied.';
                    networkGate(k)=double(oracleEnabled || truthOracleEnabled || (v1Adaptive && learnedHistoryFill==253) || ...
                        (isFullHistoryForce && learnedHistoryFill==253) || ...
                        (~v1Adaptive && ~isFullHistoryForce && learnedHistoryFill>0));
                    networkRelease(k)=release;
                    if debugEnabled && debugEvent>0, forwardDebug.release(debugEvent)=release;
                        forwardDebug.force_selected(:,debugEvent)=networkOutput(1:3);
                        forwardDebug.applied_force(:,debugEvent)=applied(1:3);
                        forwardDebug.zoh_force(:,debugEvent)=applied(1:3);
                    end
                    dF=applied(1:3);
                    dT=zeros(3,1);
                end
                if contextErrorAdaptive && contextBaseA0
                    if contextGateReady
                        [~,contextPositionInfo]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                        z1Now=double(contextPositionInfo.error(:)); z2Now=double(contextPositionInfo.surface(:));
                        z1Bar=z1Now./contextZ1Scale; z2Bar=z2Now./contextZ2Scale;
                        contextPriorForceLog(k,:)=contextPriorForce.'; contextDeltaForce(k,:)=contextHeldDelta.';
                        contextZ1(k,:)=z1Now.'; contextZ2(k,:)=z2Now.'; contextZ1Bar(k,:)=z1Bar.'; contextZ2Bar(k,:)=z2Bar.';
                        contextWeightNorm(k)=norm(contextHead.weight,'fro'); contextLastEventTimeLog(k)=contextLastEventTime;
                        if contextEvent
                            [psi,featureInfo]=context_regressor(contextMode,contextPhi32,z1Now,z2Now,contextHead.feature_limit,contextZ1Scale,contextZ2Scale,contextRbfCfg);
                            weightBefore=contextHead.weight;
                            if strcmp(contextBasis,'rbf')
                                [contextHeldDelta,contextHead,headInfo]=rbf_context_update(contextHead,psi,z2Now,contextEventDt,P.mass,min(t(k)/contextRbfCfg.beta_rise_time,1),contextRbfCfg);
                                contextForceSaturation(k)=headInfo.output_clipped;
                            else
                                rawDelta=psi.'*double(weightBefore); if isfield(contextHead,'force_limit_N'), contextForceSaturation(k)=norm(rawDelta)>double(contextHead.force_limit_N); end
                                contextHeldDelta=v2_delta_force_head_predict(contextHead,psi);
                                [contextHead,headInfo]=v2_delta_force_head_update(contextHead,psi,z2Now,contextEventDt);
                            end
                            contextUpdateFlag(k)=true; contextUpdateDt(k)=contextEventDt;
                            if isnan(contextFirstEventTime),contextFirstEventTime=t(k);end
                            contextPriorForceLog(k,:)=contextPriorForce.'; contextDeltaForce(k,:)=contextHeldDelta.';
                            contextFeatureNorm(k)=featureInfo.bounded_norm; contextFeatureLimiterActive(k)=featureInfo.limiter_active;
                            contextWeightDerivativeNorm(k)=headInfo.weight_derivative_fro; contextProjectionActive(k)=headInfo.projection_active;
                            contextDeltaWNorm(k)=norm(contextHead.weight-weightBefore,'fro');
                            contextContributionScale=1; if strcmp(contextBasis,'rbf'),contextContributionScale=P.mass*min(t(k)/contextRbfCfg.beta_rise_time,1);end
                            contextRbfContribution(k,:)=contextContributionScale*block_contribution(featureInfo.rbf_block,featureInfo.rbf_rows,weightBefore);
                            contextPhiContribution(k,:)=contextContributionScale*block_contribution(featureInfo.phi_block,featureInfo.phi_rows,weightBefore);
                            contextZ1Contribution(k,:)=contextContributionScale*block_contribution(featureInfo.z1_block,featureInfo.z1_rows,weightBefore);
                            contextZ2Contribution(k,:)=contextContributionScale*block_contribution(featureInfo.z2_block,featureInfo.z2_rows,weightBefore);
                            contextBiasContribution(k,:)=contextContributionScale*weightBefore(end,:);
                        end
                    end
                    if contextGateReady, release=1; else, release=0; end
                    networkOutput=[contextHeldDelta;zeros(3,1)]; networkRaw(k,:)=networkOutput.';
                    applied=release*networkOutput; networkApplied(k,:)=applied.'; networkGate(k)=double(contextGateReady); networkRelease(k)=release;
                    dF=applied(1:3);
                end
                switch method
                case {'B1-PMForce','B2-ResponseForce','B2-M0R-Frozen','B2-V2-SeedForce','B2-OracleForce'}
                    [~,positionInfo]=position_bs_step(x(k,:).',r,dF,P);
                    if debugEnabled && debugEvent>0, forwardDebug.requested_force(:,debugEvent)=positionInfo.commanded_force;
                    end
                    [thrust,eul,limited]=baseline_force_to_attitude(positionInfo.commanded_acceleration,x(k,9),P);
                    target=[eul(1:2);r.euler(3)];
                    [ir,filter,filterAccelerationRequest]=command_filter_step(target,filter,P);
                    filterTargetLog(k,:)=target(:).';
                    filterRequestedAccelerationLog(k,:)=filterAccelerationRequest(:).';
                    filterAppliedAccelerationLog(k,:)=ir.euler_acceleration(:).';
                    if rbfAtt400
                        rbfPhase=rbfPhase+rbfHz*dt;
                        if k>1 && rbfPhase>=1-1e-12
                            rbfPhase=rbfPhase-1;
                            dtUpdate=t(k)-lastRbfEventTime;
                            assert(dtUpdate>0,'TCN0901:RbfDt','RBF update dt must be positive.');
                             [~,ai0]=attitude_bs_step(x(k,:).',ir,zeros(3,1),P);
                             zRbf=attitude_input(ai0);
                             surfaceLearn=ai0.surface;
                             if ~isempty(attitudeModFn)
                                 previousForMod=zeros(4,1); if ~isempty(previousMotor),previousForMod=double(previousMotor(:));end
                                 [modInfo]=attitudeModFn(t(k),k,x(k,:).',s.arms,previousForMod,r,ir,ai0,previousInternalAtt,previousInternalRate);
                                 if isfield(modInfo,'gamma_scale'),attitudeGammaScale=double(modInfo.gamma_scale(:));end
                                 if isscalar(attitudeGammaScale),attitudeGammaScale=repmat(attitudeGammaScale,3,1);end
                                 if isfield(modInfo,'surface_lambda'),attitudeSurfaceLambda=double(modInfo.surface_lambda);end
                                 if isfield(modInfo,'surface_learn'),surfaceLearn=double(modInfo.surface_learn(:));end
                                 rbfAttitudeModEvent(k)=logical(field_or(modInfo,'event',false));
                                 rbfAttitudeModHistoryReady(k)=logical(field_or(modInfo,'history_ready',false));
                                 rbfAttitudeModHistoryFill(k)=double(field_or(modInfo,'history_fill',0));
                                 if isfield(modInfo,'feature'),q=min(numel(modInfo.feature),size(rbfAttitudeModFeature,2));rbfAttitudeModFeature(k,1:q)=double(modInfo.feature(1:q));end
                             end
                             rbfAttitudeSurfaceOriginal(k,:)=ai0.surface(:).';
                             rbfAttitudeSurfaceLearn(k,:)=surfaceLearn(:).';
                             rbfAttitudeGammaScaleLog(k,:)=attitudeGammaScale(:).';
                             rbfAttitudeSurfaceLambdaLog(k)=attitudeSurfaceLambda;
                             attitudeRbfCfg=cfg.rbf.attitude;
                             attitudeRbfCfg.gamma=attitudeRbfCfg.gamma(:).*attitudeGammaScale(:);
                             updateDt=0;
                             if rbfAttitudeUpdateEnabled && ~rbfAttitudeFrozen
                                 updateDt=rbf_dt_used(opts,dtUpdate);
                             end
                              [datt,rbfAtt,rbfInfo]=rbf_mimo_update(zRbf,surfaceLearn,rbfAtt,attitudeRbfCfg,updateDt);
                            beta=min(k*dt/cfg.rbf.attitude.beta_rise_time,1);
                            attitudeEventBetaLog(k)=beta;
                            nextHeldRbfTorque=beta*datt;
                            if rbfAttitudeOutputDelayEvents>0
                                heldRbfTorque=heldRbfTorquePrevious;
                                heldRbfTorquePrevious=nextHeldRbfTorque;
                            else
                                heldRbfTorque=nextHeldRbfTorque;
                            end
                            rbfUpdateFlag(k)=updateDt>0;
                             rbfUpdateDt(k)=updateDt;
                             rbfEventDt(k)=dtUpdate;
                            rbfInputSample(k,:)=zRbf.';
                            rbfOutputRaw(k,:)=datt.';
                            rbfOutputUnclipped(k,:)=rbfInfo.output_unclipped(:).';
                            rbfEventCount=rbfEventCount+1;
                            if rbfEventCount<=rbfAuditMax, rbfEventAudit.time(rbfEventCount)=t(k);
                                rbfEventAudit.dt(rbfEventCount)=dtUpdate;
                                rbfEventAudit.input(:,rbfEventCount)=zRbf;
                                rbfEventAudit.output_raw(:,rbfEventCount)=datt;
                                rbfEventAudit.weight_before(:,:,rbfEventCount)=rbfInfo.W_before;
                                rbfEventAudit.weight_derivative(:,:,rbfEventCount)=rbfInfo.W_dot;
                                rbfEventAudit.weight_unprojected(:,:,rbfEventCount)=rbfInfo.W_unprojected;
                                rbfEventAudit.weight_after(:,:,rbfEventCount)=rbfInfo.W_after;
                                rbfEventAudit.phi_norm(rbfEventCount)=norm(rbfInfo.Phi);
                                rbfEventAudit.phi_max(rbfEventCount)=max(abs(rbfInfo.Phi));
                            end
                            rbfWeightDerivativeNorm(k)=norm(rbfInfo.W_dot,'fro');
                            rbfBasisNorm(k)=norm(rbfInfo.Phi);
                            rbfBasisMax(k)=max(abs(rbfInfo.Phi));
                            lastRbfEventTime=t(k);
                        end
                        dT=heldRbfTorque;
                        if ~rbfAttitudeOutputEnabled, dT=zeros(3,1); end
                    end
                    rbfOutputHeld(k,:)=dT.';
                    rbfWeightNorm(k)=norm(rbfAtt.W,'fro');
                    rbfWeightMax(k)=max(abs(rbfAtt.W),[],'all');
                    moments=attitude_bs_step(x(k,:).',ir,dT,P);
                    command=[thrust;moments];
                    raw=target;
                    ip=r.position;
                    ipr=r.velocity;
                    z3=nan(6,1);
                case {'B2-BS','B2-RBF-Att','B2-RBF-Full','B2-RBF-Full-250','B2-RBF-Full-400','B2-RBF-Full-200','B2-RBF-Full-SPLIT'}
                    if strcmp(method,'B2-RBF-Full')
                        [~,pi0]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                        updateDt=0;
                        if rbfPositionUpdateEnabled && ~rbfPositionFrozen
                            updateDt=rbf_dt_used(opts,dt);
                        end
                        positionRbfCfg=cfg.rbf.position;
                        positionRbfCfg.gamma=positionRbfCfg.gamma(:).*positionGammaScale;
                        [dpos,rbfPos,posInfo]=rbf_mimo_update(pi0.surface,pi0.surface,rbfPos,positionRbfCfg,updateDt);
                        if isfield(posInfo,'Phi_by_output')
                            outputFromBasis=sum(posInfo.W_before.*posInfo.Phi_by_output,1).';
                        else
                            outputFromBasis=posInfo.W_before.'*posInfo.Phi;
                        end
                        outputFromBasis=max(min(outputFromBasis,cfg.rbf.position.dmax),-cfg.rbf.position.dmax);
                        rbfPositionOutputBasisConsistency(k)=max(abs(dpos-outputFromBasis));
                        sEff=max(min(pi0.surface,cfg.rbf.position.s_limit),-cfg.rbf.position.s_limit);
                        if isfield(posInfo,'Phi_by_output')
                            rbfPositionUpdateBasisConsistency(k)=posInfo.update_equation_error;
                        else
                            expectedWdot=-posInfo.Phi*(cfg.rbf.position.gamma(:).'.*sEff.')-posInfo.W_before.*cfg.rbf.position.sigma_w(:).';
                            rbfPositionUpdateBasisConsistency(k)=max(abs(posInfo.W_dot-expectedWdot),[],'all');
                        end
                        assert(rbfPositionOutputBasisConsistency(k)<=1e-12&&rbfPositionUpdateBasisConsistency(k)<=1e-12, ...
                            'TCN0916:RbfWidthBasisMismatch','Position RBF output/update did not use the same basis.');
                        rbfPositionBasisNormRelativeError(k)=posInfo.basis_audit.relative_norm_error;
                        rbfPositionBasisRelativeChange(k)=posInfo.basis_audit.relative_feature_change;
                        rbfPositionBasisFallback(k)=posInfo.basis_audit.used_numerical_fallback;
                        rbfPositionUpdateFlag(k)=updateDt>0;
                        rbfPositionUpdateDt(k)=updateDt;
                        rbfPositionOutputRaw(k,:)=dpos.';
                        rbfPositionOutputUnclipped(k,:)=posInfo.output_unclipped(:).';
                        rbfPositionWeightNorm(k)=norm(rbfPos.W,'fro');
                        rbfPositionWeightDerivativeNorm(k)=norm(posInfo.W_dot,'fro');
                        rbfPositionBasisNorm(k)=norm(posInfo.Phi);
                        rbfPositionSurface(k,:)=pi0.surface.';
                        rbfPositionEventCount=rbfPositionEventCount+1;
                        rbfPositionEventDt(k)=dt;
                        if rbfPositionEventCount<=rbfAuditMax
                            rbfPositionEventAudit.time(rbfPositionEventCount)=t(k);
                            rbfPositionEventAudit.dt(rbfPositionEventCount)=dt;
                            rbfPositionEventAudit.input(:,rbfPositionEventCount)=pi0.surface;
                            rbfPositionEventAudit.output_raw(:,rbfPositionEventCount)=dpos;
                            rbfPositionEventAudit.weight_before(:,:,rbfPositionEventCount)=posInfo.W_before;
                            rbfPositionEventAudit.weight_derivative(:,:,rbfPositionEventCount)=posInfo.W_dot;
                            rbfPositionEventAudit.weight_unprojected(:,:,rbfPositionEventCount)=posInfo.W_unprojected;
                            rbfPositionEventAudit.weight_after(:,:,rbfPositionEventCount)=posInfo.W_after;
                            rbfPositionEventAudit.phi_norm(rbfPositionEventCount)=norm(posInfo.Phi);
                            rbfPositionEventAudit.phi_max(rbfPositionEventCount)=max(abs(posInfo.Phi));
                        end
                        beta=min(k*dt/cfg.rbf.position.beta_rise_time,1);
                        positionEventBetaLog(k)=beta;
                        dF=P.mass*beta*dpos;
                        if rbfPositionOutputDelayEvents>0
                            dFPrevious=heldRbfForcePrevious;
                            heldRbfForcePrevious=dF;
                            dF=dFPrevious;
                        end
                        if ~rbfPositionOutputEnabled, dF=zeros(3,1); end
                        rbfPositionOutputHeld(k,:)=dF.';
                    elseif isRbfFullScheduled
                        if rbfFullEvent
                            [~,pi0]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                            updateDt=0;
                            if rbfPositionUpdateEnabled && ~rbfPositionFrozen
                                updateDt=rbf_dt_used(opts,rbfFullDt);
                            end
                            positionRbfCfg=cfg.rbf.position;
                            positionRbfCfg.gamma=positionRbfCfg.gamma(:).*positionGammaScale;
                            if ~isempty(positionDeepBasisFn)&&~strcmp(positionBasisMode,'gaussian')
                                phiR=rbf_mimo_basis(pi0.surface,positionRbfCfg);
                                phiD=rbfPositionDeepFeature(k,1:positionDeepDim).';
                                switch positionBasisMode
                                    case 'tcn_only',Phi=phiD;rowGamma=positionDeepGammaScale*ones(positionDeepDim,1);
                                    case 'hybrid',Phi=[phiR;positionBasisBeta*phiD];rowGamma=[ones(numel(phiR),1);positionDeepGammaScale*ones(positionDeepDim,1)];
                                    case 'current_only',Phi=phiD;rowGamma=positionDeepGammaScale*ones(positionDeepDim,1);
                                    case {'attention','static_attention'},Phi=phiR.*rbfPositionBasisAttention(k,:).';rowGamma=ones(numel(phiR),1);
                                    case 'gain',Phi=phiR;rowGamma=rbfPositionBasisGamma(k,:).';
                                end
                                positionRbfCfg.basis_override=Phi;
                                positionRbfCfg.basis_gamma_scale=rowGamma;
                            end
                            [dpos,rbfPos,posInfo]=rbf_mimo_update(pi0.surface,pi0.surface,rbfPos,positionRbfCfg,updateDt);
                            rbfPositionOutputLimitActive(k)=updateDt>0&&posInfo.output_limit_active;
                            if isfield(posInfo,'Phi_by_output')
                                outputFromBasis=sum(posInfo.W_before.*posInfo.Phi_by_output,1).';
                            else
                                outputFromBasis=posInfo.W_before.'*posInfo.Phi;
                            end
                            outputFromBasis=max(min(outputFromBasis,positionRbfCfg.dmax),-positionRbfCfg.dmax);
                            rbfPositionOutputBasisConsistency(k)=max(abs(dpos-outputFromBasis));
                            sEff=max(min(pi0.surface,positionRbfCfg.s_limit),-positionRbfCfg.s_limit);
                            rowGamma=ones(size(posInfo.Phi));if isfield(positionRbfCfg,'basis_gamma_scale'),rowGamma=positionRbfCfg.basis_gamma_scale(:);end
                            if isfield(posInfo,'Phi_by_output')
                                expectedWdot=posInfo.W_dot;
                                rbfPositionUpdateBasisConsistency(k)=posInfo.update_equation_error;
                            else
                                expectedWdot=-(posInfo.Phi.*rowGamma)*(positionRbfCfg.gamma(:).'.*sEff.')-posInfo.W_before.*positionRbfCfg.sigma_w(:).';
                                rbfPositionUpdateBasisConsistency(k)=max(abs(posInfo.W_dot-expectedWdot),[],'all');
                            end
                            assert(rbfPositionOutputBasisConsistency(k)<=1e-12&&rbfPositionUpdateBasisConsistency(k)<=1e-12, ...
                                'TCN0916:RbfWidthBasisMismatch','Scheduled Position RBF output/update did not use the same basis.');
                            rbfPositionBasisNormRelativeError(k)=posInfo.basis_audit.relative_norm_error;
                            rbfPositionBasisRelativeChange(k)=posInfo.basis_audit.relative_feature_change;
                            rbfPositionBasisFallback(k)=posInfo.basis_audit.used_numerical_fallback;
                            rbfPositionUpdateFlag(k)=updateDt>0;
                            rbfPositionUpdateDt(k)=updateDt;
                            rbfPositionEventDt(k)=rbfFullDt;
                            rbfPositionOutputRaw(k,:)=dpos.';
                            rbfPositionOutputUnclipped(k,:)=posInfo.output_unclipped(:).';
                            rbfPositionWeightDerivativeNorm(k)=norm(posInfo.W_dot,'fro');
                            rbfPositionWeightDeltaNorm(k)=norm(posInfo.W_after-posInfo.W_before,'fro');
                            rbfPositionBasisNorm(k)=norm(posInfo.Phi);
                            if ismember(positionBasisMode,{'tcn_only','hybrid','current_only'})
                                deepStart=1;if strcmp(positionBasisMode,'hybrid'),deepStart=numel(phiR)+1;end
                                deepOut=posInfo.W_before(deepStart:end,:).'*posInfo.Phi(deepStart:end);
                                rbfPositionDeepContributionRatio(k)=norm(deepOut)/max(norm(posInfo.W_before.'*posInfo.Phi),eps);
                            end
                            rbfPositionSurface(k,:)=pi0.surface.';
                            rbfFullEventCount=rbfFullEventCount+1;
                            rbfPositionEventCount=rbfPositionEventCount+1;
                            if rbfPositionEventCount<=rbfAuditMax
                                rbfPositionEventAudit.time(rbfPositionEventCount)=t(k);
                                rbfPositionEventAudit.dt(rbfPositionEventCount)=rbfFullDt;
                                rbfPositionEventAudit.input(:,rbfPositionEventCount)=pi0.surface;
                                rbfPositionEventAudit.output_raw(:,rbfPositionEventCount)=dpos;
                                rbfPositionEventAudit.weight_before(:,:,rbfPositionEventCount)=posInfo.W_before;
                                rbfPositionEventAudit.weight_derivative(:,:,rbfPositionEventCount)=posInfo.W_dot;
                                rbfPositionEventAudit.weight_unprojected(:,:,rbfPositionEventCount)=posInfo.W_unprojected;
                                rbfPositionEventAudit.weight_after(:,:,rbfPositionEventCount)=posInfo.W_after;
                                rbfPositionEventAudit.phi_norm(rbfPositionEventCount)=norm(posInfo.Phi);
                                rbfPositionEventAudit.phi_max(rbfPositionEventCount)=max(abs(posInfo.Phi));
                            end
                            beta=min(k*dt/cfg.rbf.position.beta_rise_time,1);
                            positionEventBetaLog(k)=beta;
                            nextHeldRbfAcceleration=beta*dpos;
                            nextHeldRbfForce=P.mass*nextHeldRbfAcceleration;
                            if rbfPositionOutputDelayEvents>0
                                heldRbfPositionAcceleration=heldRbfPositionAccelerationPrevious;
                                heldRbfPositionAccelerationPrevious=nextHeldRbfAcceleration;
                                heldRbfForce=heldRbfForcePrevious;
                                heldRbfForcePrevious=nextHeldRbfForce;
                            else
                                heldRbfPositionAcceleration=nextHeldRbfAcceleration;
                                heldRbfForce=nextHeldRbfForce;
                            end
                        end
                        dF=heldRbfForce;
                        if ~rbfPositionOutputEnabled, dF=zeros(3,1); end
                        rbfPositionOutputHeld(k,:)=heldRbfForce.';
                        rbfPositionWeightNorm(k)=norm(rbfPos.W,'fro');
                    end
                    if adaptiveBasisActive
                        if k==1
                            adaptiveBasisEvent(k)=true;
                            adaptiveBasisLastEventTime=t(k);
                        else
                            [adaptiveBasisEvent(k),adaptiveBasisPhase,~,adaptiveBasisLastEventTime]= ...
                                rbf_event_scheduler_step(adaptiveBasisPhase,100,dt,t(k),adaptiveBasisLastEventTime);
                        end
                        if adaptiveBasisEvent(k)
                            [~,positionPreview]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                            [previewThrust,previewEuler]=baseline_force_to_attitude( ...
                                positionPreview.commanded_acceleration,x(k,9),P);
                            previewTarget=[previewEuler(1:2);r.euler(3)];
                            [previewIr,~]=command_filter_step(previewTarget,filter,P);
                            previewTorque=heldRbfTorque;
                            if adaptiveTorqueActive,previewTorque=adaptiveTorqueHeld;end
                            if tcnResidualActive,previewTorque=heldRbfTorque+tcnResidualHeld(4:6);end
                            [previewMoment,attitudePreview]=attitude_bs_step(x(k,:).',previewIr,previewTorque,P);
                            previousForFeature=zeros(4,1);
                            if ~isempty(previousMotor),previousForFeature=double(previousMotor(:));end
                            q=[x(k,4:6).';x(k,7:9).';x(k,10:12).';positionPreview.surface(:); ...
                                attitudePreview.surface(:);previewThrust;previewMoment(:);previousForFeature.^2; ...
                                double(s.arms.command(k,:).')];
                            assert(numel(q)==27&&all(isfinite(q)), ...
                                'TCN0924:AdaptiveBasisFeature','Invalid deployable 27D feature.');
                            adaptiveBasisFeature(k,:)=q.';
                            if tcnResidualActive
                                predictedResidual=double(tcnResidualInferFn(q));predictedResidual=predictedResidual(:);
                                assert(numel(predictedResidual)==6&&all(isfinite(predictedResidual)), ...
                                    'TCN0924:TcnResidualOutput','TCN residual inference must return a finite 6D wrench.');
                                tcnResidualHeld=predictedResidual;
                                tcnResidualPrediction(k,:)=predictedResidual.';
                            elseif ~adaptiveBasisCollect&&~isempty(adaptiveBasisInferFn)
                                if adaptiveTorqueActive
                                    phiTau=double(adaptiveTorqueInferFn(q));phiTau=phiTau(:);
                                    assert(numel(phiTau)==16&&all(isfinite(phiTau)), ...
                                        'TCN0924:AdaptiveTorqueBasis','Torque basis inference must return finite 16D phi.');
                                    [phiTauT,~]=v2_feature_norm_limit(phiTau,adaptiveTorqueHead.feature_limit);
                                    adaptiveTorqueHeld=v2_delta_torque_head_predict(adaptiveTorqueHead,phiTauT);
                                    [adaptiveTorqueHead,torqueUpdateInfo]=v2_delta_torque_head_update( ...
                                        adaptiveTorqueHead,phiTauT,attitudePreview.surface,.01);
                                    adaptiveTorqueEvent(k)=true;adaptiveTorqueFeature(k,:)=q.';
                                    adaptiveTorquePhi(k,:)=phiTau.';adaptiveTorqueProjection(k)=torqueUpdateInfo.projection_active;
                                end
                                phi=double(adaptiveBasisInferFn(q));
                                phi=phi(:);
                                assert(numel(phi)==16&&all(isfinite(phi)), ...
                                    'TCN0924:AdaptiveBasisOutput','Basis inference must return finite 16D phi.');
                                [phiT,~]=v2_feature_norm_limit(phi,adaptiveBasisHead.feature_limit);
                                adaptiveBasisHeldForce=v2_delta_force_head_predict(adaptiveBasisHead,phiT);
                                [adaptiveBasisHead,updateInfo]=v2_delta_force_head_update( ...
                                    adaptiveBasisHead,phiT,positionPreview.surface,.01);
                                adaptiveBasisPhi(k,:)=phi.';
                                adaptiveBasisProjection(k)=updateInfo.projection_active;
                            end
                            if ~adaptiveBasisCollect&&~isempty(adaptiveBasisInferFn)
                                dF=adaptiveBasisHeldForce;
                                adaptiveBasisForce(k,:)=adaptiveBasisHeldForce.';
                                adaptiveBasisWeightNorm(k)=norm(adaptiveBasisHead.weight,'fro');
                            end
                        else
                            if ~adaptiveBasisCollect&&~isempty(adaptiveBasisInferFn)
                                dF=adaptiveBasisHeldForce;
                                adaptiveBasisForce(k,:)=adaptiveBasisHeldForce.';
                            end
                        end
                    end
                    if tcnResidualActive
                        dF=heldRbfForce+tcnResidualHeld(1:3);
                        tcnResidualApplied(k,1:3)=tcnResidualHeld(1:3).';
                    end
                    if wrenchDiagnosticEnabled
                        diagnosticRbfForce(k,:)=dF.';
                        if diagnosticOracle
                            dF=dF+injectedForceI;
                            diagnosticOracleForce(k,:)=injectedForceI.';
                        end
                    end
                    if stage1PositionActive
                        dF=stage1PositionHeldForce;
                        if rbfFullEvent
                            [~,stage1Preview]=position_bs_step(x(k,:).',r,zeros(3,1),P);
                            [previewThrust,~,~]=baseline_force_to_attitude( ...
                                stage1Preview.commanded_acceleration,x(k,9),P);
                            feature14=[stage1Preview.error(:);stage1Preview.surface(:); ...
                                x(k,7:9).';previewThrust/P.mass;double(s.arms.command(k,:).')];
                            assert(numel(feature14)==14&&all(isfinite(feature14)), ...
                                'D5:Feature14','The original causal X14 feature must be finite.');
                            if stage1ModelInputDim==20
                                feature=[feature14;x(k,4:6).';stage1Preview.nominal_acceleration(:)];
                            else
                                feature=feature14;
                            end
                            assert(numel(feature)==stage1ModelInputDim&&all(isfinite(feature)), ...
                                'D5:FeatureInput','Candidate runtime feature must be finite and match its model.');
                            stage1PositionHistory=[stage1PositionHistory(:,2:end),feature];
                            stage1PositionHistoryFill=min(stage1PositionHistoryFill+1,size(stage1PositionHistory,2));
                            stage1PositionEvent(k)=true;
                            stage1PositionFeature14(k,:)=feature14.';
                            stage1PositionFeatureInput(k,:)=feature.';
                            stage1PositionEventDt(k)=rbfFullDt;
                            if stage1PositionHistoryFill>=stage1ModelReadinessEvents
                                inferenceTimer=tic;
                                phi=position_stage1_model_forward_v2(stage1PositionRuntime.model,stage1PositionHistory);
                                betaOriginal=min(max(k*dt/cfg.rbf.position.beta_rise_time,0),1);
                                beta=betaOriginal*stage1PositionBetaScale;
                                positionEventBetaLog(k)=beta;
                                weightBefore=stage1PositionWeight;
                                if stage1SearchEnabled&&stage1PositionUpdateEnabled
                                    if pcfCoordinationEnabled
                                        etaBeforeEvent=stage1PcfEta;
                                        stage1PcfSurfaceEvent(k,:)=stage1Preview.surface(:).';
                                        stage1PcfEtaEventBefore(k,:)=etaBeforeEvent.';
                                        stage1PcfScEvent(k,:)=stage1Preview.surface(:).'-positionCoordinateMask.'.*etaBeforeEvent.';
                                        stage1PcfScEffEvent(k,:)=max(min(stage1PcfScEvent(k,:),[7 8 10]),-[7 8 10]);
                                    else
                                        stage1PcfScEvent(k,:)=stage1Preview.surface(:).';
                                        stage1PcfScEffEvent(k,:)=max(min(stage1Preview.surface(:),[7;8;10]),-[7;8;10]).';
                                    end
                                    sEff=stage1PcfScEffEvent(k,:).';
                                    if strcmp(stage1SearchType,'FEATURE')
                                        if positionDelayedPredictionEnabled
                                            nZero=k-1; delayedTarget=nan(3,1); previousIndex=[];
                                            previousPhi=[]; previousTarget=[]; previousTime=[];
                                            if ~isempty(stage1DelayedPreviousIndex)
                                                previousIndex=stage1DelayedPreviousIndex;
                                                assert(nZero-stage1DelayedPreviousIndex==10&& ...
                                                    stage1DelayedPreviousIndex>=320, ...
                                                    'C5Coordinate:PreviousInterval','Delayed target must use the completed j=n-10 interval.');
                                                predictionReferenceIntegral=stage1DelayedPredictionReferenceIntegral;
                                                previousReferenceIntegral=stage1DelayedPreviousPredictionReferenceIntegral;
                                                delayedTarget=((x(k,4:6).'-stage1DelayedPreviousVelocity)- ...
                                                    (predictionReferenceIntegral-previousReferenceIntegral))/0.01;
                                                previousPhi=stage1DelayedPreviousPhi;
                                                previousTarget=delayedTarget;
                                                previousTime=stage1DelayedPreviousTime;
                                            end
                                            assert(abs(rbfFullDt-.01)<1e-12, ...
                                                'DelayedPrediction:EventPeriod','FEATURE event interval must remain 10 ms.');
                                            delayedOut=delayed_prediction_step_candidate(stage1PositionWeight,phi,sEff, ...
                                                nZero,t(k),previousPhi,previousTarget,previousIndex,previousTime);
                                            assert(abs(delayedOut.beta-beta)<1e-12, ...
                                                'DelayedPrediction:BetaClock','Candidate beta must match the C2 event clock.');
                                            raw=delayedOut.raw; applied=delayedOut.applied; weightNext=delayedOut.W_next;
                                            projection=any(weightNext(:)~=delayedOut.preprojection_candidate(:));
                                            searchAudit=struct('bias_before',zeros(3,1),'bias_after',zeros(3,1), ...
                                                'bias_projection',false);
                                            stage1DelayedTarget(k,:)=delayedTarget.';
                                            if ~isempty(previousIndex),stage1DelayedPreviousIndexLog(k)=previousIndex;end
                                            stage1DelayedTermNorm(k)=.01*norm(delayedOut.prediction_gradient,'fro');
                                            stage1DelayedEventVelocity(k,:)=x(k,4:6);
                                            stage1DelayedEventAfIntegral(k,:)=stage1DelayedAfIntegral.';
                                            stage1DelayedEventPredictionReferenceIntegral(k,:)= ...
                                                stage1DelayedPredictionReferenceIntegral.';
                                            stage1DelayedPreviousPhi=phi;
                                            stage1DelayedPreviousVelocity=x(k,4:6).';
                                            stage1DelayedPreviousAfIntegral=stage1DelayedAfIntegral;
                                            stage1DelayedPreviousPredictionReferenceIntegral= ...
                                                stage1DelayedPredictionReferenceIntegral;
                                            stage1DelayedPreviousIndex=nZero;
                                            stage1DelayedPreviousTime=t(k);
                                        else
                                            [raw,applied,weightNext,projection,searchAudit]=stage1SearchStep( ...
                                                phi,stage1SearchW0,stage1PositionWeight,'FEATURE',stage1SearchGamma, ...
                                                stage1SearchKappa,sEff,rbfFullDt,beta,cfg.rbf.position.dmax);
                                        end
                                    else
                                        [raw,applied,biasNext,projection,searchAudit]=stage1SearchStep( ...
                                            phi,stage1SearchW0,stage1PositionBias,'BIAS',stage1SearchGamma, ...
                                            stage1SearchKappa,sEff,rbfFullDt,beta,cfg.rbf.position.dmax);
                                        stage1PositionBias=biasNext;weightNext=stage1PositionWeight;
                                    end
                                    stage1PositionEventBiasBefore(:,stage1PositionInferenceEventCount+1)=searchAudit.bias_before;
                                    stage1PositionEventBiasAfter(:,stage1PositionInferenceEventCount+1)=searchAudit.bias_after;
                                    stage1PositionEventBiasProjection(k)=double(searchAudit.bias_projection);
                                elseif stage1SearchEnabled
                                    if strcmp(stage1SearchType,'FEATURE')
                                        raw=stage1PositionWeight.'*phi;
                                    else
                                        raw=stage1SearchKappa*(stage1SearchW0.'*phi)+stage1PositionBias;
                                    end
                                    headClipped=max(min(raw,cfg.rbf.position.dmax(:)),-cfg.rbf.position.dmax(:));
                                    applied=beta*headClipped;weightNext=stage1PositionWeight;projection=false;
                                    stage1PositionEventBiasBefore(:,stage1PositionInferenceEventCount+1)=stage1PositionBias;
                                    stage1PositionEventBiasAfter(:,stage1PositionInferenceEventCount+1)=stage1PositionBias;
                                    stage1PositionEventBiasProjection(k)=0;
                                elseif stage1PositionUpdateEnabled
                                    if pcfCoordinationEnabled
                                        etaBeforeEvent=stage1PcfEta;
                                        [raw,applied,weightNext,projection,pcfHeadInfo]= ...
                                            position_stage1_update_head_pcf_v3_5(phi,stage1PositionWeight, ...
                                            stage1Preview.surface,rbfFullDt*stage1PositionUpdateDtScale, ...
                                            beta,cfg.rbf.position.dmax,etaBeforeEvent,true);
                                        stage1PcfSurfaceEvent(k,:)=stage1Preview.surface(:).';
                                        stage1PcfEtaEventBefore(k,:)=etaBeforeEvent.';
                                        stage1PcfScEvent(k,:)=pcfHeadInfo.surface.';
                                        stage1PcfScEffEvent(k,:)=pcfHeadInfo.surface_effective.';
                                    else
                                        [raw,applied,weightNext,projection]=position_stage1_update_head( ...
                                            phi,stage1PositionWeight,stage1Preview.surface, ...
                                            rbfFullDt*stage1PositionUpdateDtScale,beta,cfg.rbf.position.dmax);
                                    end
                                else
                                    raw=stage1PositionWeight.'*phi;
                                    headClipped=max(min(raw,cfg.rbf.position.dmax(:)),-cfg.rbf.position.dmax(:));
                                    applied=beta*headClipped;weightNext=stage1PositionWeight;projection=false;
                                end
                                stage1PositionWeight=weightNext;
                                stage1PositionProjection(k)=projection;
                                stage1PositionInferenceTime(k)=toc(inferenceTimer);
                                stage1PositionPhi(k,:)=phi.';
                                stage1PositionRaw(k,:)=raw.';
                                stage1PositionApplied(k,:)=applied.';
                                stage1PositionEventRaw(k,:)=raw.';
                                stage1PositionEventApplied(k,:)=applied.';
                                stage1PositionEventPhi(k,:)=phi.';
                                stage1PositionInferenceEventCount=stage1PositionInferenceEventCount+1;
                                stage1PositionEventWeightBefore(:,:,stage1PositionInferenceEventCount)=weightBefore;
                                stage1PositionEventWeightAfter(:,:,stage1PositionInferenceEventCount)=stage1PositionWeight;
                                stage1PositionEventWeightDeltaFro(k)=norm(stage1PositionWeight-weightBefore,'fro');
                                stage1PositionEffectiveUpdateDt(k)=rbfFullDt*stage1PositionUpdateDtScale;
                                stage1PositionEventBeta(k)=beta;
                                stage1PositionEventProjection(k)=double(projection);
                                stage1PositionEventInferenceValid(k)=true;
                                stage1PositionLastPredictionTime=t(k);
                                stage1PositionHeldRawCache=raw;
                                stage1PositionHeldAppliedCache=applied;
                                stage1PositionHeldForce=P.mass*applied;
                                stage1PositionInferenceTime(k)=toc(inferenceTimer);
                                stage1PositionEventInferenceTime(k)=stage1PositionInferenceTime(k);
                            else
                                stage1PositionHeldRawCache=zeros(3,1);
                                stage1PositionHeldAppliedCache=zeros(3,1);
                                stage1PositionHeldForce=zeros(3,1);
                            end
                            stage1PositionWeightNorm(k)=norm(stage1PositionWeight,'fro');
                            stage1PositionHistoryFillLog(k)=stage1PositionHistoryFill;
                            dF=stage1PositionHeldForce;
                        end
                    end
                    if positionDelayedPredictionEnabled
                        stage1DelayedAfIntegralBeforeLog(k,:)=stage1DelayedAfIntegral.';
                        stage1DelayedPredictionReferenceIntegralBeforeLog(k,:)= ...
                            stage1DelayedPredictionReferenceIntegral.';
                    end
                    if stage1PositionActive
                        stage1PositionHeldRawLog(k,:)=stage1PositionHeldRawCache.';
                        stage1PositionHeldAppliedLog(k,:)=stage1PositionHeldAppliedCache.';
                        stage1PositionHeldForceLog(k,:)=stage1PositionHeldForce.';
                        stage1PositionInjectedForceLog(k,:)=dF.';
                        stage1PositionWeightNormHeld(k)=norm(stage1PositionWeight,'fro');
                        stage1PositionLastEventTimeLog(k)=stage1PositionLastPredictionTime;
                        stage1PositionHistoryFillHeld(k)=stage1PositionHistoryFill;
                    end
                    [~,positionInfo]=position_bs_step(x(k,:).',r,dF,P);
                    if positionNdoEnabled
                        [ndoEvent,positionNdoPhase,ndoDt,positionNdoLastEventTime]= ...
                            rbf_event_scheduler_step(positionNdoPhase,positionNdoFrequency,dt, ...
                            t(k),positionNdoLastEventTime);
                        if ndoEvent
                            if positionNdoDecompositionEnabled&&k>1
                                slowInnovation=P.mass*(x(k,4:6).'-x(k-1,4:6).')/ndoDt-positionCommandedForce(k-1,:).';
                                alpha=-expm1(-ndoDt/positionNdoSlowTau);
                                positionNdoHeldSlowResidual=positionNdoHeldSlowResidual+ ...
                                    alpha*(slowInnovation-positionNdoHeldSlowResidual);
                                positionNdoSlowInnovation(k,:)=slowInnovation.';
                            end
                            if strcmp(positionNdoInputMode,'requested')&&isfinite(positionNdoOutputLimit)
                                positionNdoHeldEstimate=positionNdoZ+ ...
                                    positionNdoLambda*P.mass*x(k,4:6).';
                                positionNdoHeldAppliedEstimate=limit_vector_norm( ...
                                    positionNdoHeldEstimate,positionNdoOutputLimit);
                                positionNdoHeldKnownForce=positionInfo.nominal_force- ...
                                    positionNdoHeldAppliedEstimate;
                                % Match Level0: the controller applies the norm-limited
                                % output, and the observer accounts for raw minus applied.
                                positionNdoZ=positionNdoZ-ndoDt*positionNdoLambda* ...
                                    (positionNdoHeldEstimate+positionNdoHeldKnownForce);
                            elseif strcmp(positionNdoInputMode,'realized')
                                realizedKnownForce=zeros(3,1);
                                if ~isempty(previousMotor)
                                    realizedWrench=Ptrue.allocation.C*double(previousMotor(:)).^2;
                                    realizedKnownForce=rotation_zyx(x(k,7:9).')*[0;0;realizedWrench(1)]- ...
                                        [0;0;P.mass*P.g];
                                end
                                assert(all(isfinite(realizedKnownForce)),'RBFBS:PositionNdoKnownForce', ...
                                    'Realized known force must be finite.');
                                positionNdoHeldEstimate=positionNdoZ+ ...
                                    positionNdoLambda*P.mass*x(k,4:6).';
                                positionNdoHeldKnownForce=realizedKnownForce;
                                positionNdoZ=positionNdoZ-ndoDt*positionNdoLambda* ...
                                    (positionNdoHeldEstimate+positionNdoHeldKnownForce);
                                positionNdoHeldAppliedEstimate=limit_vector_norm( ...
                                    positionNdoHeldEstimate,positionNdoOutputLimit);
                            elseif positionNdoReconstructionEnabled
                                reconstructedKnownForce=zeros(3,1);
                                if positionNdoMotorEstimateInitialized
                                    reconstructedKnownForce=rotation_zyx(x(k,7:9).')* ...
                                        [0;0;positionNdoReconstructedGeneralized(k,1)]- ...
                                        [0;0;P.mass*P.g];
                                end
                                positionNdoHeldEstimate=positionNdoZ+ ...
                                    positionNdoLambda*P.mass*x(k,4:6).';
                                positionNdoHeldKnownForce=reconstructedKnownForce;
                                positionNdoZ=positionNdoZ-ndoDt*positionNdoLambda* ...
                                    (positionNdoHeldEstimate+positionNdoHeldKnownForce);
                                positionNdoHeldAppliedEstimate=limit_vector_norm( ...
                                    positionNdoHeldEstimate,positionNdoOutputLimit);
                            else
                                [positionNdoZ,positionNdoHeldEstimate,positionNdoHeldKnownForce]= ...
                                    position_nonlinear_disturbance_observer_step(positionNdoZ, ...
                                    x(k,4:6).',positionInfo.nominal_force,P.mass, ...
                                    positionNdoLambda,ndoDt);
                                positionNdoHeldAppliedEstimate=limit_vector_norm( ...
                                    positionNdoHeldEstimate,positionNdoOutputLimit);
                            end
                            positionNdoUpdateFlag(k)=true;
                            positionNdoUpdateDt(k)=ndoDt;
                        end
                        positionNdoEstimate(k,:)=positionNdoHeldEstimate.';
                        positionNdoAppliedEstimate(k,:)=positionNdoHeldAppliedEstimate.';
                        positionNdoLimitActive(k)=isfinite(positionNdoOutputLimit)&& ...
                            norm(positionNdoHeldEstimate)>positionNdoOutputLimit;
                        positionNdoKnownForce(k,:)=positionNdoHeldKnownForce.';
                        positionNdoSlowResidual(k,:)=positionNdoHeldSlowResidual.';
                        dF=dF+positionNdoHeldAppliedEstimate+positionNdoHeldSlowResidual;
                        positionNdoCombinedCompensation(k,:)=dF.';
                        if positionSmcEnabled
                            ep=r.position(:)-x(k,1:3).';
                            ev=r.velocity(:)-x(k,4:6).';
                            slidingSurface=ev+positionSmcLambda*ep;
                            smcForce=-positionSmcGain*max(min(slidingSurface/positionSmcBoundary,1),-1);
                            positionSmcSurface(k,:)=slidingSurface.';
                            positionSmcForce(k,:)=smcForce.';
                            dF=dF+smcForce;
                        end
                        [~,positionInfo]=position_bs_step(x(k,:).',r,dF,P);
                        positionBsNominalForce(k,:)=positionInfo.nominal_force.';
                        positionCommandedForce(k,:)=positionInfo.commanded_force.';
                    end
                    if ~positionNdoEnabled
                        positionBsNominalForce(k,:)=positionInfo.nominal_force.';
                        positionCommandedForce(k,:)=positionInfo.commanded_force.';
                    end
                    if wrenchDiagnosticEnabled,diagnosticPositionSurface(k,:)=positionInfo.surface.';end
                    if wrenchDiagnosticEnabled
                        positionBsNominalForce(k,:)=positionInfo.nominal_force.';
                        positionCommandedForce(k,:)=positionInfo.commanded_force.';
                    end
                    [thrust,eul,limited]=baseline_force_to_attitude(positionInfo.commanded_acceleration,x(k,9),P);
                    target=[eul(1:2);r.euler(3)];
                    [ir,filter,filterAccelerationRequest]=command_filter_step(target,filter,P);
                    filterTargetLog(k,:)=target(:).';
                    filterRequestedAccelerationLog(k,:)=filterAccelerationRequest(:).';
                    filterAppliedAccelerationLog(k,:)=ir.euler_acceleration(:).';
                    if pcfCoordinationEnabled
                        [af,rf,etaNext]=position_filter_realization_pcf_step_v3_5( ...
                            thrust,ir.euler,positionInfo.commanded_acceleration,stage1PcfEta, ...
                            P.bs.position.k2,P.mass,P.g,dt,true);
                        stage1PcfAReq(k,:)=positionInfo.commanded_acceleration(:).';
                        stage1PcfAF(k,:)=af.'; stage1PcfRf(k,:)=rf.';
                        stage1PcfEta=etaNext;
                        if positionDelayedPredictionEnabled
                            stage1DelayedAfIntegral=stage1DelayedAfIntegral+af*dt;
                            predictionReference=af;
                            predictionReference(positionCoordinateMask==0)= ...
                                positionInfo.commanded_acceleration(positionCoordinateMask==0);
                            stage1PcfPredictionReference(k,:)=predictionReference(:).';
                            stage1DelayedPredictionReferenceIntegral= ...
                                stage1DelayedPredictionReferenceIntegral+predictionReference*dt;
                        end
                    end
                    stage1PcfEtaAfterLog(k,:)=stage1PcfEta.';
                    if rbfAtt400 && (rbfAttitudeRuntimeEnabled||attitudeFusionActive||physicsHelperActive||learnedCandidate)
                        % Split-rate scheduler sets attitudeEvent before this branch;
                        % preserve it so independent Position/Attitude rates remain causal.
                        dtUpdate=0;
                        if isRbfFullScheduled && ~isRbfFullSplit
                            attitudeEvent=rbfFullEvent;
                            dtUpdate=rbfFullDt;
                        elseif ~isRbfFullSplit
                            rbfPhase=rbfPhase+rbfHz*dt;
                            if k>1 && rbfPhase>=1-1e-12
                                rbfPhase=rbfPhase-1;
                                attitudeEvent=true;
                                dtUpdate=t(k)-lastRbfEventTime;
                            end
                        else
                            dtUpdate=attitudeEventDt;
                        end
                        if tcnCandidate
                            dT=heldTcnTorque;
                            if attitudeEvent
                                [~,ai0]=attitude_bs_step(x(k,:).',ir,zeros(3,1),P);
                                feature=[double(ai0.error(:));double(x(k,10:12)).'; ...
                                    double(ai0.nominal_moment(:)); ...
                                    double(s.arms.command(k,:)).'];
                                assert(numel(feature)==13&&all(isfinite(feature)), ...
                                    'GATE:TCNFeature','DL_TCN runtime feature is invalid.');
                                beta=min(k*dt/cfg.rbf.attitude.beta_rise_time,1);
                                tcnInput=struct('feature',feature, ...
                                    'J0',double(cfg.attitude_replacement.J0_controller_fixed_kgm2), ...
                                    'beta',beta,'dmax',double(cfg.rbf.attitude.dmax(:)));
                                [tcnMemory,tcnOut]=tcn_attitude_step_v1( ...
                                    'step',tcnMemory,tcnInput,opts.tcn_attitude_model);
                                heldTcnTorque=double(tcnOut.estimateTorque_Nm(:));
                                dT=heldTcnTorque;
                                tcnTrace{k}=struct('sample_index',k,'time_s',t(k), ...
                                    'is_attitude_event',true,'event_delta_s',attitudeEventDt, ...
                                    'feature_raw',feature,'feature_normalized',tcnOut.feature_normalized, ...
                                    'raw_residual_rad_s2',tcnOut.raw_residual_rad_s2, ...
                                    'clipped_residual_rad_s2',tcnOut.clipped_residual_rad_s2, ...
                                    'beta',beta,'estimateTorque_Nm',heldTcnTorque, ...
                                    'history_count',tcnOut.history_count, ...
                                    'rbf_output_enabled',false,'rbf_update_enabled',false, ...
                                    'time_varying_inertia_reconstruction_used',false);
                            end
                        elseif mlpCandidate
                            dT=heldMlp15Torque;
                            if attitudeEvent
                                [~,ai0]=attitude_bs_step(x(k,:).',ir,zeros(3,1),P);
                                feature=[double(ai0.error(:));double(x(k,10:12)).'; ...
                                    double(ai0.nominal_moment(:)); ...
                                    double(s.arms.command(k,:)).'];
                                assert(numel(feature)==13&&all(isfinite(feature)), ...
                                    'GATE:MLP15Feature','DL_MLP15 runtime feature is invalid.');
                                beta=min(k*dt/cfg.rbf.attitude.beta_rise_time,1);
                                mlpInput=struct('feature',feature, ...
                                    'J0',double(cfg.attitude_replacement.J0_controller_fixed_kgm2), ...
                                    'beta',beta,'dmax',double(cfg.rbf.attitude.dmax(:)));
                                [mlp15Memory,mlpOut]=mlp15_attitude_step_v1( ...
                                    'step',mlp15Memory,mlpInput,opts.mlp15_attitude_model);
                                heldMlp15Torque=double(mlpOut.estimateTorque_Nm(:));
                                dT=heldMlp15Torque;
                                mlp15Trace{k}=struct('sample_index',k,'time_s',t(k), ...
                                    'is_attitude_event',true,'event_delta_s',attitudeEventDt, ...
                                    'feature_raw',feature,'feature_normalized',mlpOut.feature_normalized, ...
                                    'raw_residual_rad_s2',mlpOut.raw_residual_rad_s2, ...
                                    'clipped_residual_rad_s2',mlpOut.clipped_residual_rad_s2, ...
                                    'beta',beta,'estimateTorque_Nm',heldMlp15Torque, ...
                                    'history_count',mlpOut.history_count, ...
                                    'rbf_output_enabled',false,'rbf_update_enabled',false, ...
                                    'time_varying_inertia_reconstruction_used',false);
                            end
                        elseif attitudeEvent
                            assert(dtUpdate>0,'TCN0901:RbfDt','RBF update dt must be positive.');
                            [~,ai0]=attitude_bs_step(x(k,:).',ir,zeros(3,1),P);
                            zRbf=attitude_input(ai0);
                            surfaceLearn=ai0.surface;
                            if ~isempty(attitudeModFn)
                                previousForMod=zeros(4,1); if ~isempty(previousMotor),previousForMod=double(previousMotor(:));end
                                [modInfo]=attitudeModFn(t(k),k,x(k,:).',s.arms,previousForMod,r,ir,ai0,previousInternalAtt,previousInternalRate);
                                if isfield(modInfo,'gamma_scale'),attitudeGammaScale=double(modInfo.gamma_scale(:));end
                                if isscalar(attitudeGammaScale),attitudeGammaScale=repmat(attitudeGammaScale,3,1);end
                                if isfield(modInfo,'surface_lambda'),attitudeSurfaceLambda=double(modInfo.surface_lambda);end
                                if isfield(modInfo,'surface_learn'),surfaceLearn=double(modInfo.surface_learn(:));end
                                rbfAttitudeModEvent(k)=logical(field_or(modInfo,'event',false));
                                rbfAttitudeModHistoryReady(k)=logical(field_or(modInfo,'history_ready',false));
                                rbfAttitudeModHistoryFill(k)=double(field_or(modInfo,'history_fill',0));
                                if isfield(modInfo,'feature'),q=min(numel(modInfo.feature),size(rbfAttitudeModFeature,2));rbfAttitudeModFeature(k,1:q)=double(modInfo.feature(1:q));end
                            end
                            rbfAttitudeSurfaceOriginal(k,:)=ai0.surface(:).';
                            rbfAttitudeSurfaceLearn(k,:)=surfaceLearn(:).';
                            rbfAttitudeGammaScaleLog(k,:)=attitudeGammaScale(:).';
                            rbfAttitudeSurfaceLambdaLog(k)=attitudeSurfaceLambda;
                            attitudeRbfCfg=cfg.rbf.attitude;
                            attitudeRbfCfg.gamma=attitudeRbfCfg.gamma(:).*attitudeGammaScale(:);
                            updateDt=0;
                            if rbfAttitudeUpdateEnabled && ~rbfAttitudeFrozen
                                updateDt=rbf_dt_used(opts,dtUpdate);
                            end
                            [datt,rbfAtt,rbfInfo]=rbf_mimo_update(zRbf,surfaceLearn,rbfAtt,attitudeRbfCfg,updateDt);
                            rbfAttitudeOutputLimitActive(k)=updateDt>0&&rbfInfo.output_limit_active;
                            nextHeldRbfAttitudeAcceleration=min(k*dt/cfg.rbf.attitude.beta_rise_time,1)*datt;
                            nextHeldRbfTorque=P.inertia*nextHeldRbfAttitudeAcceleration;
                            if rbfAttitudeOutputDelayEvents>0
                                heldRbfAttitudeAcceleration=heldRbfAttitudeAccelerationPrevious;
                                heldRbfAttitudeAccelerationPrevious=nextHeldRbfAttitudeAcceleration;
                                heldRbfTorque=heldRbfTorquePrevious;
                                heldRbfTorquePrevious=nextHeldRbfTorque;
                            else
                                heldRbfAttitudeAcceleration=nextHeldRbfAttitudeAcceleration;
                                heldRbfTorque=nextHeldRbfTorque;
                            end
                            if attitudeFusionActive
                                if attitudeFusionInputDim==23
                                    feature=attitude_feature_row_x23_v37(ai0,x(k,:).',ir,thrust, ...
                                        attitudeFusionPreviousEventSetpoint,cfg.plant.mass,cfg.plant.limits.motor_max);
                                else
                                    currentRawCommand=zeros(0,1);
                                    if attitudeFusionInputDim==33
                                        currentRawCommand=double(s.arms.command(k,:)).';
                                    end
                                    feature=attitude_feature_row_v3_6(ai0,x(k,:).',ir,thrust, ...
                                        attitudeFusionPreviousEventSetpoint,currentRawCommand, ...
                                        cfg.plant.mass,cfg.plant.limits.motor_max,attitudeFusionInputDim);
                                end
                                attitudeFusionFeatureHistory(:,1:end-1)=attitudeFusionFeatureHistory(:,2:end);
                                attitudeFusionFeatureHistory(:,end)=feature;
                                attitudeFusionEventCount=attitudeFusionEventCount+1;
                                ready=attitudeFusionEventCount>=32;
                                z=(feature-double(attitudeFusionModel.input_mu(:)))./ ...
                                    max(double(attitudeFusionModel.input_sigma(:)),1e-6);
                                attitudeFusionEvent(k)=true;attitudeFusionReady(k)=ready;
                                attitudeFusionLambdaLog(k)=attitudeFusionLambda;
                                attitudeFusionNormalizedFeature(k,:)=z.';
                                attitudeFusionFeatureAbsGt4Count(k)=sum(abs(z)>4);
                                if ready
                                    if isfield(opts,'attitude_head_v39')
                                        if isfield(opts,'attitude_head_v39')
                                            [phiHead,W0Head,rawFrozen]=attitude_model_feature_x29_v39( ...
                                                attitudeFusionModel,attitudeFusionFeatureHistory);
                                            aiHead=ai0;aiHead.J0=P.inertia;
                                            beta=min(k*dt/cfg.rbf.attitude.beta_rise_time,1);
                                            attitudeEventBetaLog(k)=beta;
                                            [raw,applied,dTauHead,DeltaWAfter,headDiag]=attitude_kan_head_step_v39( ...
                                                phiHead,W0Head,attitudeHeadDeltaW,aiHead,beta,dtUpdate, ...
                                                attitudeFusionModel.dmax,ready,attitudeHeadEnabled);
                                            if ready
                                                attitudeHeadDeltaW=DeltaWAfter;
                                                attitudeFusionHeldNnTorque=dTauHead;
                                            else
                                                attitudeFusionHeldNnTorque=zeros(3,1);
                                            end
                                            attitudeHeadEvent(k)=true;attitudeHeadRawNormalized(k,:)=raw(:).';
                                            attitudeHeadAppliedNormalized(k,:)=applied(:).';
                                            attitudeHeadTorqueNm(k,:)=dTauHead(:).';
                                            attitudeHeadUpdateNorm(k)=headDiag.update_norm;
                                            attitudeHeadProjection(k)=headDiag.projection_active;
                                            attitudeHeadSaturated(k)=headDiag.saturated;
                                            attitudeHeadDeltaNorm(k)=norm(attitudeHeadDeltaW,'fro');
                                            attitudeFusionRawNormalized(k,:)=raw(:).';
                                            attitudeFusionAppliedNormalized(k,:)=applied(:).';
                                            attitudeFusionAppliedAcceleration(k,:)=(applied(:).*double(attitudeFusionModel.dmax(:))).';
                                            attitudeHeadAuditCount=attitudeHeadAuditCount+1;
                                            if attitudeHeadAuditCount<=attitudeHeadAuditMax
                                                ia=attitudeHeadAuditCount;
                                                attitudeHeadAudit.time(ia)=t(k);attitudeHeadAudit.dt_event_s(ia)=dtUpdate;
                                                attitudeHeadAudit.weight_before(:,:,ia)=headDiag.weight_before;
                                                attitudeHeadAudit.weight_after(:,:,ia)=headDiag.weight_after;
                                                attitudeHeadAudit.phi(:,ia)=phiHead;
                                                attitudeHeadAudit.y_raw(:,ia)=raw(:);attitudeHeadAudit.y_applied(:,ia)=applied(:);
                                                attitudeHeadAudit.dTau_Nm(:,ia)=dTauHead(:);
                                                attitudeHeadAudit.update_norm(ia)=headDiag.update_norm;
                                                attitudeHeadAudit.projection(ia)=headDiag.projection_active;
                                                attitudeHeadAudit.saturated(ia)=headDiag.saturated;
                                            end
                                            attitudeHeadReadyEventCount(k)=attitudeFusionEventCount;
                                            assert(max(abs(rawFrozen-W0Head.'*phiHead))<=1e-12, ...
                                            'X29V39:FrozenOutput','Feature interface differs from frozen normalized readout.');
                                        else
                                            raw=attitude_model_forward_x23_v37(attitudeFusionModel,attitudeFusionFeatureHistory);
                                            applied=min(max(raw(:),-1),1);
                                            dA=applied.*double(attitudeFusionModel.dmax(:));
                                            beta=min(k*dt/cfg.rbf.attitude.beta_rise_time,1);
                                            attitudeFusionHeldNnTorque=P.inertia*(beta*dA);
                                        end
                                    else
                                        raw=attitude_model_forward_b_v3_6a(attitudeFusionModel,attitudeFusionFeatureHistory);
                                        applied=min(max(raw(:),-1),1);
                                        dA=applied.*double(attitudeFusionModel.dmax(:));
                                        beta=min(k*dt/cfg.rbf.attitude.beta_rise_time,1);
                                        attitudeFusionHeldNnTorque=P.inertia*(beta*dA);
                                        attitudeFusionRawNormalized(k,:)=raw(:).';
                                        attitudeFusionAppliedNormalized(k,:)=applied(:).';
                                        attitudeFusionAppliedAcceleration(k,:)=dA(:).';
                                    end
                                else
                                    attitudeFusionHeldNnTorque=zeros(3,1);
                                end
                            end
                            rbfUpdateFlag(k)=updateDt>0;
                            rbfUpdateDt(k)=updateDt;
                            rbfEventDt(k)=dtUpdate;
                            rbfInputSample(k,:)=zRbf.';
                            rbfOutputRaw(k,:)=datt.';
                            rbfOutputUnclipped(k,:)=rbfInfo.output_unclipped(:).';
                            rbfEventCount=rbfEventCount+1;
                            if rbfEventCount<=rbfAuditMax
                                rbfEventAudit.time(rbfEventCount)=t(k);
                                rbfEventAudit.dt(rbfEventCount)=dtUpdate;
                                rbfEventAudit.input(:,rbfEventCount)=zRbf;
                                rbfEventAudit.output_raw(:,rbfEventCount)=datt;
                                rbfEventAudit.weight_before(:,:,rbfEventCount)=rbfInfo.W_before;
                                rbfEventAudit.weight_derivative(:,:,rbfEventCount)=rbfInfo.W_dot;
                                rbfEventAudit.weight_unprojected(:,:,rbfEventCount)=rbfInfo.W_unprojected;
                                rbfEventAudit.weight_after(:,:,rbfEventCount)=rbfInfo.W_after;
                                rbfEventAudit.phi_norm(rbfEventCount)=norm(rbfInfo.Phi);
                                rbfEventAudit.phi_max(rbfEventCount)=max(abs(rbfInfo.Phi));
                            end
                            rbfWeightDerivativeNorm(k)=norm(rbfInfo.W_dot,'fro');
                            rbfBasisNorm(k)=norm(rbfInfo.Phi);
                            rbfBasisMax(k)=max(abs(rbfInfo.Phi));
                            lastRbfEventTime=t(k);
                        end
                        if ~physCandidate
                            dT=heldRbfTorque;
                            if ~rbfAttitudeOutputEnabled, dT=zeros(3,1); end
                            rbfTorqueForLog=dT;
                        end
                        if attitudeFusionActive
                            attitudeFusionLambdaLog(k)=attitudeFusionLambda;
                            attitudeFusionReady(k)=attitudeFusionEventCount>=32;
                            attitudeFusionOriginalRbfTorque(k,:)=dT(:).';
                            attitudeFusionNnTorque(k,:)=attitudeFusionHeldNnTorque(:).';
                            if attitudeFusionLambda==1
                                dT=attitudeFusionHeldNnTorque;
                            else
                                dT=attitude_fusion_mix_v3_6(attitudeFusionLambda,dT,attitudeFusionHeldNnTorque);
                            end
                            attitudeFusionMixedTorque(k,:)=dT(:).';
                        end
                    elseif strcmp(method,'B2-RBF-Full')
                        [~,ai0]=attitude_bs_step(x(k,:).',ir,zeros(3,1),P);
                        zRbf=attitude_input(ai0);
                        updateDt=0;
                        if rbfAttitudeUpdateEnabled && ~rbfAttitudeFrozen
                            updateDt=rbf_dt_used(opts,dt);
                        end
                            [datt,rbfAtt,rbfInfo]=rbf_mimo_update(zRbf,ai0.surface,rbfAtt,cfg.rbf.attitude,updateDt);
                        rbfAttitudeOutputLimitActive(k)=updateDt>0&&rbfInfo.output_limit_active;
                        beta=min(k*dt/cfg.rbf.attitude.beta_rise_time,1);
                        attitudeEventBetaLog(k)=beta;
                        nextHeldRbfTorque=beta*datt;
                        if rbfAttitudeOutputDelayEvents>0
                            dT=heldRbfTorquePrevious;
                            heldRbfTorquePrevious=nextHeldRbfTorque;
                        else
                            dT=nextHeldRbfTorque;
                        end
                        if ~rbfAttitudeOutputEnabled, dT=zeros(3,1); end
                        rbfUpdateFlag(k)=updateDt>0; rbfUpdateDt(k)=updateDt; rbfInputSample(k,:)=zRbf.'; rbfOutputRaw(k,:)=datt.';
                        rbfOutputUnclipped(k,:)=rbfInfo.output_unclipped(:).'; rbfEventCount=rbfEventCount+1;
                        if rbfEventCount<=rbfAuditMax
                            rbfEventAudit.time(rbfEventCount)=t(k); rbfEventAudit.dt(rbfEventCount)=dt; rbfEventAudit.input(:,rbfEventCount)=zRbf;
                            rbfEventAudit.output_raw(:,rbfEventCount)=datt; rbfEventAudit.weight_before(:,:,rbfEventCount)=rbfInfo.W_before;
                            rbfEventAudit.weight_derivative(:,:,rbfEventCount)=rbfInfo.W_dot; rbfEventAudit.weight_unprojected(:,:,rbfEventCount)=rbfInfo.W_unprojected;
                            rbfEventAudit.weight_after(:,:,rbfEventCount)=rbfInfo.W_after; rbfEventAudit.phi_norm(rbfEventCount)=norm(rbfInfo.Phi); rbfEventAudit.phi_max(rbfEventCount)=max(abs(rbfInfo.Phi));
                        end
                        rbfWeightDerivativeNorm(k)=norm(rbfInfo.W_dot,'fro'); rbfBasisNorm(k)=norm(rbfInfo.Phi); rbfBasisMax(k)=max(abs(rbfInfo.Phi));
                    end
                    if adaptiveTorqueActive
                        dT=adaptiveTorqueHeld;
                        adaptiveTorqueOutput(k,:)=adaptiveTorqueHeld.';
                        adaptiveTorqueWeightNorm(k)=norm(adaptiveTorqueHead.weight,'fro');
                    end
                    if tcnResidualActive
                        dT=heldRbfTorque+tcnResidualHeld(4:6);
                        tcnResidualApplied(k,4:6)=tcnResidualHeld(4:6).';
                    end
                    if wrenchDiagnosticEnabled
                        diagnosticRbfTorque(k,:)=dT.';
                        if diagnosticOracle
                            dT=dT+injectedTorqueB;
                            diagnosticOracleTorque(k,:)=injectedTorqueB.';
                        end
                    end
                    if ~physCandidate,rbfOutputHeld(k,:)=rbfTorqueForLog.';end
            if stage1PositionActive
                positionRbfAccelerationApplied(k,:)=0;
            else
                positionRbfAccelerationApplied(k,:)=dF.'/P.mass;
            end
                    if ~physCandidate
                        attitudeRbfAccelerationApplied(k,:)=heldRbfAttitudeAcceleration.';
                        if attitudeFusionActive
                            attitudeRbfTorqueApplied(k,:)=attitudeFusionOriginalRbfTorque(k,:);
                        else
                            attitudeRbfTorqueApplied(k,:)=rbfTorqueForLog.';
                        end
                    end
                    rbfWeightNorm(k)=norm(rbfAtt.W,'fro');
                    rbfWeightMax(k)=max(abs(rbfAtt.W),[],'all');
                    if wrenchDiagnosticEnabled
                        [moments,diagnosticAttInfo]=attitude_bs_step(x(k,:).',ir,dT,P);
                        attitudeInfo=diagnosticAttInfo;
                        diagnosticAttitudeSurface(k,:)=diagnosticAttInfo.surface.';
                    else
                        [moments,attitudeInfo]=attitude_bs_step(x(k,:).',ir,dT,P);
                    end
                    attitudeBsNominalTorque(k,:)=attitudeInfo.nominal_moment.';
                    command=[thrust;moments];
                    raw=target;
                    ip=r.position;
                    ipr=r.velocity;
                    z3=nan(6,1);
                otherwise
                    error('TCN0901:BaselineMethod','Unknown baseline method %s.',method);
                end
            end
            controllerTime(k)=toc(timer);
            [motorSetpointNow,wrenchNow,a]=allocate_control(command,P,Ptrue,previousMotor);
            controllerClippedWrench(k,:)=a.clipped_generalized.';
            motorNow=motorSetpointNow;
            if motorTimeConstant>0&&~isempty(previousMotor)
                alpha=-expm1(-dt/motorTimeConstant);
                motorNow=double(previousMotor(:))+alpha*(motorSetpointNow(:)-double(previousMotor(:)));
                wrenchNow=Ptrue.allocation.C*motorNow.^2;
            end
            % 按控制器名义分配矩阵，由本采样实际电机指令重构分配 wrench。
            allocatedWrench(k,:)=(P.allocation.C*motorNow.^2).';
            if positionNdoReconstructionEnabled
                if motorTimeConstant>0&&positionNdoMotorEstimateInitialized
                    alpha=-expm1(-dt/motorTimeConstant);
                    positionNdoMotorEstimate=positionNdoMotorEstimate+ ...
                        alpha*(motorSetpointNow(:)-positionNdoMotorEstimate);
                else
                    positionNdoMotorEstimate=motorSetpointNow(:);
                end
                positionNdoMotorEstimateInitialized=true;
            end
            if positionNdoEnabled||wrenchDiagnosticEnabled
                positionRealizedForce(k,:)=(rotation_zyx(x(k,7:9).')* ...
                    [0;0;wrenchNow(1)]-[0;0;P.mass*P.g]).';
                positionForceRealizationError(k,:)=positionRealizedForce(k,:)-positionCommandedForce(k,:);
            end
            [fWind,tWind]=morphology_aware_wind_load(x(k,:).',Ptrue,s.environment_wind_I(k,:).',wcfg);
            fWind=windForceScale*fWind;
            tWind=windForceScale*tWind;
            if wrenchDiagnosticEnabled
                forcePlant=fWind+injectedForceI;
                if physicalImpulseEnabled,forcePlant=forcePlant+physicalImpulseForceI(k,:).';end
                torquePlant=tWind+injectedTorqueB;
                next=rk4_vehicle_step(x(k,:).',wrenchNow,forcePlant,torquePlant,Ptrue);
                Pvisible=simulation_parameters(cfg,P.arm_lengths,P.arm_rates);
                wrenchTrue=Ptrue.allocation.C*motorNow.^2;
                wrenchVisible=Pvisible.allocation.C*motorNow.^2;
                zeroWrench=zeros(3,1);
                fNoExternal=vehicle_derivative(x(k,:).',wrenchTrue,zeroWrench,zeroWrench,Ptrue);
                fAero=vehicle_derivative(x(k,:).',wrenchTrue,fWind,tWind,Ptrue);
                fFull=vehicle_derivative(x(k,:).',wrenchTrue,forcePlant,torquePlant,Ptrue);
                positionPlantAccelerationTruth(k,:)=fFull(4:6).';
                fVisible=vehicle_derivative(x(k,:).',wrenchVisible,zeroWrench,zeroWrench,Pvisible);
                % Offline residual target only; it is never passed to the observer.
                positionNdoTargetTruth(k,:)=(P.mass*fFull(4:6)-positionNdoKnownForce(k,:).').';
                diagnosticModelResidual(k,:)=[P.mass*(fNoExternal(4:6)-fVisible(4:6)); ...
                    P.inertia*(fNoExternal(10:12)-fVisible(10:12))].';
                diagnosticAeroResidual(k,:)=[P.mass*(fAero(4:6)-fNoExternal(4:6)); ...
                    P.inertia*(fAero(10:12)-fNoExternal(10:12))].';
                diagnosticInjectedResidual(k,:)=[P.mass*(fFull(4:6)-fAero(4:6)); ...
                    P.inertia*(fFull(10:12)-fAero(10:12))].';
                diagnosticControllerResidual(k,:)=[P.mass*(fFull(4:6)-fVisible(4:6)); ...
                    P.inertia*(fFull(10:12)-fVisible(10:12))].';
                diagnosticClosure(k,:)=diagnosticControllerResidual(k,:)- ...
                    diagnosticModelResidual(k,:)-diagnosticAeroResidual(k,:)-diagnosticInjectedResidual(k,:);
            else
                forcePlant=fWind;
                if physicalImpulseEnabled,forcePlant=forcePlant+physicalImpulseForceI(k,:).';end
                next=rk4_vehicle_step(x(k,:).',wrenchNow,forcePlant,tWind,Ptrue);
            end
            if statePerturbationEnabled&&~statePerturbationApplied&& ...
                    abs(t(k+1)-statePerturbationTime)<1e-12
                next=next+statePerturbationDelta;
                statePerturbationApplied=true;
                statePerturbationAppliedTime=t(k+1);
                statePerturbationAppliedFlag(k+1)=true;
            end
            if ~formalRbfBaseline
                residual(k,:)=trv1_total_residual_label(x(k,:).',motorNow,Ptrue,Phat,s.environment_wind_I(k,:).',wcfg).';
            end
            if k==1&&isfield(opts,'r2e_first_plant_step_marker')
                markerPath=char(opts.r2e_first_plant_step_marker);
                markerFile=fopen(markerPath,'w');
                if markerFile>=0
                    fprintf(markerFile,'first_plant_transition=1\n');fclose(markerFile);
                end
            end
            x(k+1,:)=next.';
            motor(k,:)=motorNow.';
            motorSetpoint(k,:)=motorSetpointNow.';
            requested(k,:)=command.';
            realized(k,:)=wrenchNow.';
            motorSat(k,:)=a.motor_saturated.';
            clipped(k,:)=a.generalized_command_clipped.';
            motorSquaredRequested(k,:)=a.motor_squared_requested.';
            if s0GuardEnabled && ~guardLatched
                if any(a.motor_saturated)||any(a.generalized_command_clipped)
                    s0SaturationEvents=s0SaturationEvents+1;
                else
                    s0SaturationEvents=0;
                end
                if s0SaturationEvents*dt>=0.100
                    guardLatched=true;
                    guardTrigger(k)=true;
                    guardTriggerTime=t(k);
                    guardTriggerReason{k}='SATURATION_OR_GENERALIZED_CLIP_PERSISTENCE';
                end
            end
            rawAtt(k,:)=raw.';
            internalAtt(k,:)=ir.euler.';
            internalRate(k,:)=ir.euler_rate.';
            previousInternalAtt=ir.euler;
            previousInternalRate=ir.euler_rate;
            internalPos(k,:)=ip.';
            internalPosRate(k,:)=ipr.';
            if debugEnabled && debugEvent>0, forwardDebug.saturation(debugEvent)=any(a.motor_saturated);
                forwardDebug.allocation_clip(debugEvent)=any(a.generalized_command_clipped);
                forwardDebug.requested_force_norm(debugEvent)=norm(forwardDebug.requested_force(:,debugEvent));
            end
            forceEstimate(k,:)=dF.';
            oracleForceLog(k,:)=oracleForce.';
            torqueEstimate(k,:)=dT.';
            windForce(k,:)=fWind.';
            windTorque(k,:)=tWind.';
            observerZ3(k,:)=z3.';
            tiltLimited(k)=limited;
            previousMotor=motorNow;
            if attitudeFusionActive
                if attitudeFusionEvent(k),attitudeFusionPreviousEventSetpoint=double(motorSetpointNow(:));end
            end
            last=k;
            if v1Adaptive, v1WeightNorm(k)=norm(opts.v1_head.weight,'fro');
            end
            finiteCheckValues=[x(k,:).';r.position(:);r.velocity(:);command(:);motorNow(:); ...
                motorSetpointNow(:);wrenchNow(:);a.motor_squared_requested(:);dF(:);dT(:); ...
                fWind(:);tWind(:);next(:)];
            if any(~isfinite(finiteCheckValues))|| ...
                    (~formalRbfBaseline&&any(~isfinite(residual(k,:))))|| ...
                    norm(x(k,1:3)-r.position.')>=100||norm(wrap(x(k,7:9)-ir.euler.'))>=pi
                status='DIVERGED';
                divergenceTime=t(k);
                break
            end
        end
        q=1:last;
        qs=1:last+1;
        if rlGapRuntimeEnabled && last>=1
            rlGapRuntime=rl_gap_runtime_finalize(rlGapRuntime,cfg);
            s.reference.position(last+1,:)=[rlGapRuntime.ref.x_ref,rlGapRuntime.ref.y_ref,rlGapRuntime.ref.z_ref];
            s.reference.velocity(last+1,:)=[rlGapRuntime.ref.v_ref,0,0];
            s.reference.acceleration(last+1,:)=[rlGapRuntime.ref.a_ref,0,0];
            s.reference.yaw(last+1)=0;s.reference.yaw_rate(last+1)=0;s.reference.yaw_acceleration(last+1)=0;
            s.arms.command(last+1,:)=rlGapRuntime.u_rho(:).';
            s.arms.rho_true(last+1,:)=rlGapRuntime.rho_true(:).';
            s.arms.rho_hat(last+1,:)=rlGapRuntime.rho_hat(:).';
            s.arms.rhoDot_true(last+1,:)=rlGapRuntime.rhoDot_true(:).';
            s.arms.rhoDot_hat(last+1,:)=rlGapRuntime.rhoDot_hat(:).';
        end
        contextUpdateRate=0; contextFirstIdx=find(contextUpdateFlag(1:last),1,'first');
        if ~isempty(contextFirstIdx), contextUpdateRate=sum(contextUpdateFlag(1:last))/max(t(last)-t(contextFirstIdx),eps); end
        if debugEnabled, forwardDebug.count=debugCount;
            forwardDebug=trim_forward_debug(forwardDebug);
        end
        log=struct('time',t(qs),'transition_time',t(q),'initial_state',s.initial_state(:),'reference',trim_reference(s.reference,qs),'state',x(qs,:), ...
            'adaptive_basis_event',adaptiveBasisEvent(q),'adaptive_basis_feature_27',adaptiveBasisFeature(q,:), ...
            'adaptive_basis_phi_16',adaptiveBasisPhi(q,:),'adaptive_basis_force_N',adaptiveBasisForce(q,:), ...
            'adaptive_basis_weight_norm',adaptiveBasisWeightNorm(q),'adaptive_basis_projection',adaptiveBasisProjection(q), ...
            'tcn_residual_prediction_6',tcnResidualPrediction(q,:),'tcn_residual_applied_6',tcnResidualApplied(q,:), ...
            'adaptive_torque_event',adaptiveTorqueEvent(q),'adaptive_torque_feature_27',adaptiveTorqueFeature(q,:), ...
            'adaptive_torque_phi_16',adaptiveTorquePhi(q,:),'adaptive_torque_output_Nm',adaptiveTorqueOutput(q,:), ...
            'adaptive_torque_weight_norm',adaptiveTorqueWeightNorm(q),'adaptive_torque_projection',adaptiveTorqueProjection(q), ...
            'raw_outer_attitude',rawAtt(q,:),'filtered_attitude_reference',internalAtt(q,:),'filtered_attitude_rate',internalRate(q,:), ...
            'command_filter_target_euler',filterTargetLog(q,:), ...
            'command_filter_acceleration_request_unclamped_rads2',filterRequestedAccelerationLog(q,:), ...
            'command_filter_acceleration_applied_rads2',filterAppliedAccelerationLog(q,:), ...
            'internal_position_reference',internalPos(q,:),'internal_position_rate',internalPosRate(q,:),'observer_z3_native',observerZ3(q,:), ...
            'arms',trim_arms(s.arms,qs),'environment_wind_I',s.environment_wind_I(qs,:),'wind_force_I',windForce(q,:),'wind_torque_B',windTorque(q,:), ...
            'rl_gap_runtime_enabled',rlGapRuntimeEnabled,'rl_gap_runtime_log',field_or(rlGapRuntime,'log',struct), ...
            'rl_gap_mode',field_or(rlGapRuntime,'mode','disabled'),'rl_gap_collision',field_or(rlGapRuntime,'collision',false), ...
            'rl_gap_passage_success',field_or(rlGapRuntime,'passage_success',false),'rl_gap_mission_success',field_or(rlGapRuntime,'mission_success',false), ...
            'rl_gap_auto_recovery',field_or(rlGapRuntime,'auto_recovery',false),'rl_gap_policy_event_count',field_or(rlGapRuntime,'policy_event_count',0), ...
            'residual_force_estimate_N',forceEstimate(q,:),'residual_torque_estimate_Nm',torqueEstimate(q,:), ...
            'diagnostic_total_residual',residual(q,:),'diagnostic_causal_residual_prev_motor',causalResidual(q,:), ...
            'causal_label_motor',causalMotor(q,:),'requested_generalized',requested(q,:), ...
            'controller_clipped_generalized',controllerClippedWrench(q,:), ...
            'allocated_generalized',allocatedWrench(q,:),'realized_generalized',realized(q,:), ...
            'position_nominal_acceleration_mps2',positionBsNominalForce(q,:)/P.mass, ...
            'position_compensation_applied_force_N',forceEstimate(q,:), ...
            'position_compensation_applied_acceleration_mps2',forceEstimate(q,:)/P.mass, ...
            'attitude_nominal_torque_Nm',attitudeBsNominalTorque(q,:), ...
            'attitude_compensation_applied_torque_Nm',torqueEstimate(q,:), ...
            'physics_feedforward_estimate_torque_Nm',physicsEstimateTorque(q,:), ...
            'position_event_flag',positionEventLog(q), ...
            'attitude_event_flag',attitudeEventLog(q), ...
            'position_event_beta',positionEventBetaLog(q), ...
            'attitude_event_beta',attitudeEventBetaLog(q), ...
            'position_head_update_executed',stage1PositionEventInferenceValid(q)&stage1PositionUpdateEnabled, ...
            'attitude_head_update_executed',attitudeHeadEvent(q)&attitudeHeadEnabled, ...
            'position_bs_nominal_force_N',positionBsNominalForce(q,:), ...
            'position_commanded_force_N',positionCommandedForce(q,:), ...
            'position_rbf_estimate_acceleration_mps2',positionRbfAccelerationApplied(q,:), ...
            'position_rbf_compensation_force_N',rbfPositionOutputHeld(q,:), ...
            'attitude_bs_nominal_torque_Nm',attitudeBsNominalTorque(q,:), ...
            'attitude_rbf_estimate_acceleration_rads2',attitudeRbfAccelerationApplied(q,:), ...
            'attitude_rbf_compensation_torque_Nm',attitudeRbfTorqueApplied(q,:), ...
             'attitude_fusion_enabled',attitudeFusionActive,'attitude_fusion_architecture',char(field_or(attitudeFusionModel,'architecture','none')), ...
             'attitude_fusion_input_dim',attitudeFusionInputDim, ...
             'attitude_fusion_rbf_output_enabled',rbfAttitudeOutputEnabled, ...
             'attitude_fusion_rbf_update_enabled',rbfAttitudeUpdateEnabled, ...
             'attitude_fusion_lambda',attitudeFusionLambdaLog(q),'attitude_fusion_event',attitudeFusionEvent(q), ...
             'attitude_fusion_ready',attitudeFusionReady(q),'attitude_fusion_raw_normalized_output',attitudeFusionRawNormalized(q,:), ...
             'attitude_fusion_applied_normalized_output',attitudeFusionAppliedNormalized(q,:), ...
             'attitude_fusion_applied_acceleration_rads2',attitudeFusionAppliedAcceleration(q,:), ...
             'attitude_fusion_original_rbf_torque_Nm',attitudeFusionOriginalRbfTorque(q,:), ...
             'attitude_fusion_nn_torque_Nm',attitudeFusionNnTorque(q,:), ...
                         'attitude_fusion_mixed_torque_Nm',attitudeFusionMixedTorque(q,:), ...
                         'attitude_head_enabled',attitudeHeadEnabled,'attitude_head_event',attitudeHeadEvent(q), ...
                         'attitude_head_ready_event_count',attitudeHeadReadyEventCount(q), ...
                         'attitude_head_raw_normalized',attitudeHeadRawNormalized(q,:), ...
                         'attitude_head_applied_normalized',attitudeHeadAppliedNormalized(q,:), ...
                         'attitude_head_compensation_torque_Nm',attitudeHeadTorqueNm(q,:), ...
                         'attitude_head_deltaW_norm',attitudeHeadDeltaNorm(q), ...
                         'attitude_head_update_norm',attitudeHeadUpdateNorm(q), ...
                         'attitude_head_projection_active',attitudeHeadProjection(q), ...
                         'attitude_head_output_saturated',attitudeHeadSaturated(q), ...
                         'attitude_head_event_audit',trim_head_audit_v39(attitudeHeadAudit,attitudeHeadAuditCount), ...
             'attitude_fusion_normalized_feature',attitudeFusionNormalizedFeature(q,:), ...
             'attitude_fusion_feature_abs_gt4_count',attitudeFusionFeatureAbsGt4Count(q), ...
            'motor_command',motor(q,:),'motor_saturated',motorSat(q,:),'motor_squared_requested',motorSquaredRequested(q,:), ...
            'generalized_clipped',clipped(q,:),'tilt_limited',tiltLimited(q), ...
            'motor_setpoint',motorSetpoint(q,:),'motor_time_constant_s',motorTimeConstant, ...
            'controller_call_time_s',controllerTime(q),'network_raw',networkRaw(q,:),'network_applied',networkApplied(q,:), ...
            'oracle_force_N',oracleForceLog(q,:),'oracle_force_update',oracleForceUpdate(q),'oracle_force_rate_hz',oracleForceRate, ...
            'truth_oracle_enabled',truthOracleEnabled,'truth_oracle_mode',truthOracleMode,'truth_oracle_rate_hz',truthOracleRate, ...
            'truth_oracle_horizon_samples',truthOracleHorizonSamples,'truth_oracle_current_force_N',truthOracleCurrent(q,:), ...
            'truth_oracle_future_point_force_N',truthOracleFuture(q,:),'truth_oracle_hold_average_force_N',truthOracleHold(q,:), ...
            'truth_oracle_compensation_force_N',truthOracleCompensation(q,:),'truth_oracle_event',truthOracleEvent(q), ...
            'truth_oracle_zoh_start_s',truthOracleZohStart(q),'truth_oracle_zoh_end_s',truthOracleZohEnd(q), ...
            'learned_force_lambda',learnedForceLambda, ...
            'closure_reset_enabled',isfield(closureReset,'enabled')&&logical(closureReset.enabled), ...
            'closure_reset_applied',closureResetAppliedLog(q), ...
            'network_update',networkUpdate(q),'network_call_time_s',networkCallTime(q),'network_gate',networkGate(q),'network_release',networkRelease(q), ...
            'a3s_v2_adaptive',a3sV2Adaptive,'a3s_v2_frozen_prior_force',a3sPriorForce(q,:), ...
            'a3s_v2_fast_update',a3sV2FastAdaptive,'a3s_v2_fast_update_flag',a3sFastUpdateFlag(q),'a3s_v2_fast_update_dt',a3sFastUpdateDt(q), ...
            'a3s_v2_adaptive_delta_force',a3sDeltaForce(q,:),'a3s_v2_total_learned_force',a3sTotalForce(q,:), ...
            'a3s_v2_phi_raw_norm',a3sPhiRawNorm(q),'a3s_v2_phi_bounded_norm',a3sPhiBoundedNorm(q), ...
            'a3s_v2_feature_limiter_active',a3sFeatureLimiterActive(q),'a3s_v2_deltaW_norm',a3sDeltaWNorm(q), ...
            'a3s_v2_deltaW_excursion',a3sDeltaWExcursion(q),'a3s_v2_per_event_deltaW',a3sPerEventDeltaW(q), ...
            'a3s_v2_projection_active',a3sProjectionActive(q),'a3s_v2_z2',a3sZ2(q,:), ...
            'a3s_v2_driving_norm',a3sDrivingNorm(q),'a3s_v2_force_off_parity_max_abs',a3sForceOffParity(q), ...
            'a3s_v2_gamma',a3sGamma,'a3s_v2_sigma',a3sSigma, ...
            'a3s_v2_c_phi',a3sFeatureLimit,'a3s_v2_Wmax',a3sProjectionBound, ...
            'context_error_adaptive',contextErrorAdaptive,'context_error_mode',contextMode,'context_error_rate_hz',contextRateHz, ...
            'context_error_head',contextHead,'context_error_feature_dim',field_or(contextHead,'feature_dim',NaN), ...
            'context_error_update_flag',contextUpdateFlag(q),'context_error_update_dt',contextUpdateDt(q), ...
            'context_error_prior_force',contextPriorForceLog(q,:),'context_error_delta_force',contextDeltaForce(q,:), ...
            'context_error_z1',contextZ1(q,:),'context_error_z2',contextZ2(q,:), ...
            'context_error_z1_bar',contextZ1Bar(q,:),'context_error_z2_bar',contextZ2Bar(q,:), ...
            'context_error_feature_norm',contextFeatureNorm(q),'context_error_feature_limiter_active',contextFeatureLimiterActive(q), ...
            'context_error_force_saturation',contextForceSaturation(q), ...
            'context_error_weight_norm',contextWeightNorm(q),'context_error_weight_derivative_norm',contextWeightDerivativeNorm(q), ...
            'context_error_projection_active',contextProjectionActive(q),'context_error_deltaW_norm',contextDeltaWNorm(q), ...
            'context_error_rbf_contribution',contextRbfContribution(q,:),'context_error_phi_contribution',contextPhiContribution(q,:),'context_error_z1_contribution',contextZ1Contribution(q,:), ...
            'context_error_z2_contribution',contextZ2Contribution(q,:),'context_error_bias_contribution',contextBiasContribution(q,:), ...
            'context_error_z1_scale',contextZ1Scale,'context_error_z2_scale',contextZ2Scale, ...
            'context_error_first_event_time_s',contextFirstEventTime,'context_error_actual_update_rate_hz',contextUpdateRate, ...
            'diagnostic_fallback_trigger',diagnosticFallbackTrigger(q),'diagnostic_fallback_active',diagnosticFallbackActiveLog(q), ...
            'diagnostic_fallback_time_s',diagnosticFallbackTime,'diagnostic_force_fallback_threshold_N',diagnosticFallbackThreshold, ...
            'diagnostic_force_bound_N',diagnosticForceBound,'diagnostic_force_bound_active',diagnosticForceBoundActive(q), ...
            'guard_trigger',guardTrigger(q),'guard_active',guardActiveLog(q),'guard_support_score',guardSupportScore(q), ...
            'guard_support_parts',guardSupportParts(q,:),'guard_force_norm_N',guardForceNorm(q), ...
            'guard_force_growth_N',guardForceGrowth(q),'guard_command_growth',guardCommandGrowth(q), ...
            'guard_force_growth_smooth_N',guardForceGrowthSmooth(q),'guard_dynamic_support_score',guardDynamicSupportScore(q), ...
            'guard_morphology_recent',guardMorphologyRecentLog(q),'guard_persistence_count',guardPersistenceLog(q), ...
            'guard_trigger_time_s',guardTriggerTime,'guard_trigger_reason',{guardTriggerReason(q)}, ...
            'policy_mode',{policyMode(q)},'student_authority',studentAuthority(q),'student_eligible',studentEligible(q), ...
            'fallback_source',{fallbackSource(q)}, ...
             'rbf_update_flag',rbfUpdateFlag(q),'rbf_update_dt',rbfUpdateDt(q),'rbf_event_dt',rbfEventDt(q),'rbf_input_sample',rbfInputSample(q,:), ...
             'rbf_attitude_output_limit_active',rbfAttitudeOutputLimitActive(q), ...
              'rbf_output_raw',rbfOutputRaw(q,:), ...
             'rbf_output_unclipped',rbfOutputUnclipped(q,:), ...
             'rbf_output_held',rbfOutputHeld(q,:), ...
             'rbf_weight_norm',rbfWeightNorm(q),'rbf_weight_max',rbfWeightMax(q), ...
              'rbf_weight_derivative_norm',rbfWeightDerivativeNorm(q), ...
             'rbf_basis_norm',rbfBasisNorm(q),'rbf_basis_max',rbfBasisMax(q), ...
             'rbf_attitude_gamma_scale',rbfAttitudeGammaScaleLog(q,:),'rbf_attitude_surface_lambda',rbfAttitudeSurfaceLambdaLog(q), ...
             'rbf_attitude_surface_original',rbfAttitudeSurfaceOriginal(q,:),'rbf_attitude_surface_learn',rbfAttitudeSurfaceLearn(q,:), ...
             'rbf_attitude_mod_feature',rbfAttitudeModFeature(q,:),'rbf_attitude_mod_event',rbfAttitudeModEvent(q), ...
             'rbf_attitude_mod_history_ready',rbfAttitudeModHistoryReady(q),'rbf_attitude_mod_history_fill',rbfAttitudeModHistoryFill(q), ...
             'rbf_event_count',rbfEventCount,'rbf_event_audit',trim_rbf_audit(rbfEventAudit,rbfEventCount,rbfAuditMax), ...
             'rbf_position_update_flag',rbfPositionUpdateFlag(q),'rbf_position_update_dt',rbfPositionUpdateDt(q), ...
            'rbf_position_output_limit_active',rbfPositionOutputLimitActive(q), ...
             'rbf_position_event_dt',rbfPositionEventDt(q), ...
            'rbf_position_output_raw',rbfPositionOutputRaw(q,:), ...
            'rbf_position_output_unclipped',rbfPositionOutputUnclipped(q,:), ...
            'rbf_position_output_held',rbfPositionOutputHeld(q,:), ...
             'rbf_position_weight_norm',rbfPositionWeightNorm(q),'rbf_position_weight_derivative_norm',rbfPositionWeightDerivativeNorm(q), ...
             'rbf_position_basis_norm',rbfPositionBasisNorm(q),'rbf_position_surface',rbfPositionSurface(q,:), ...
             'rbf_position_width_scale',rbfPositionWidthScale(q),'rbf_position_width_target',rbfPositionWidthTarget(q), ...
             'rbf_position_width_step',rbfPositionWidthStep(q),'rbf_position_width_event',rbfPositionWidthEvent(q), ...
             'rbf_position_width_feature',rbfPositionWidthFeature(q,:),'rbf_position_basis_norm_relative_error',rbfPositionBasisNormRelativeError(q), ...
             'rbf_position_basis_relative_change',rbfPositionBasisRelativeChange(q),'rbf_position_basis_fallback',rbfPositionBasisFallback(q), ...
             'rbf_position_output_basis_consistency',rbfPositionOutputBasisConsistency(q), ...
             'rbf_position_update_basis_consistency',rbfPositionUpdateBasisConsistency(q), ...
             'rbf_position_deep_feature',rbfPositionDeepFeature(q,:),'rbf_position_deep_feature_raw',rbfPositionDeepFeatureRaw(q,:), ...
             'rbf_position_deep_feature_norm',rbfPositionDeepFeatureNorm(q),'rbf_position_deep_feature_update',rbfPositionDeepFeatureUpdate(q), ...
             'rbf_position_deep_history_fill',rbfPositionDeepHistoryFill(q),'rbf_position_deep_contribution_ratio',rbfPositionDeepContributionRatio(q), ...
             'rbf_position_basis_attention',rbfPositionBasisAttention(q,:),'rbf_position_basis_gamma_scale',rbfPositionBasisGamma(q,:), ...
             'rbf_position_weight_delta_norm',rbfPositionWeightDeltaNorm(q), ...
            'rbf_position_event_count',rbfPositionEventCount,'rbf_position_event_audit',trim_rbf_audit(rbfPositionEventAudit,rbfPositionEventCount,rbfAuditMax), ...
            'rbf_position_weight_final',rbfPos.W,'learned_forward_debug',forwardDebug, ...
            'stage1_position_replacement_enabled',stage1PositionActive, ...
            'stage1_position_model_context_length',stage1ModelContextLength, ...
            'stage1_position_readiness_events',stage1ModelReadinessEvents, ...
            'stage1_position_event',stage1PositionEvent(q),'stage1_position_feature_14',stage1PositionFeature14(q,:), ...
            'stage1_position_feature_input',stage1PositionFeatureInput(q,:), ...
            'stage1_position_phi_33',stage1PositionPhi(q,:),'stage1_position_raw_acceleration_mps2',stage1PositionRaw(q,:), ...
            'stage1_position_applied_acceleration_mps2',stage1PositionApplied(q,:), ...
            'stage1_position_weight_norm',stage1PositionWeightNorm(q),'stage1_position_weight_projection',stage1PositionProjection(q), ...
            'stage1_position_inference_time_s',stage1PositionInferenceTime(q),'stage1_position_event_dt_s',stage1PositionEventDt(q), ...
            'stage1_position_history_fill',stage1PositionHistoryFillLog(q),'stage1_position_weight_final',stage1PositionWeight, ...
            'stage1_position_event_inference_valid',stage1PositionEventInferenceValid(q), ...
            'stage1_position_event_raw_acceleration_mps2',stage1PositionEventRaw(q,:), ...
            'stage1_position_event_applied_acceleration_mps2',stage1PositionEventApplied(q,:), ...
            'stage1_position_event_phi_33',stage1PositionEventPhi(q,:), ...
            'stage1_position_event_step_index',q(stage1PositionEventInferenceValid(q)), ...
            'stage1_position_event_weight_before_33x3',stage1PositionEventWeightBefore(:,:,1:stage1PositionInferenceEventCount), ...
            'stage1_position_event_weight_after_33x3',stage1PositionEventWeightAfter(:,:,1:stage1PositionInferenceEventCount), ...
             'stage1_position_search_head_enabled',stage1SearchEnabled, ...
             'stage1_position_search_head_type',stage1SearchType, ...
             'stage1_position_search_gamma',stage1SearchGamma,'stage1_position_search_kappa',stage1SearchKappa, ...
             'stage1_position_event_bias_before_mps2',stage1PositionEventBiasBefore(:,1:stage1PositionInferenceEventCount), ...
             'stage1_position_event_bias_after_mps2',stage1PositionEventBiasAfter(:,1:stage1PositionInferenceEventCount), ...
             'stage1_position_event_bias_projection',stage1PositionEventBiasProjection(q), ...
             'stage1_position_search_initial_weight',stage1SearchW0, ...
             'stage1_position_search_final_bias_mps2',stage1PositionBias, ...
            'stage1_position_event_weight_delta_fro',stage1PositionEventWeightDeltaFro(q), ...
            'stage1_position_effective_update_dt_s',stage1PositionEffectiveUpdateDt(q), ...
            'stage1_position_event_beta',stage1PositionEventBeta(q), ...
            'stage1_position_event_inference_time_s',stage1PositionEventInferenceTime(q), ...
            'stage1_position_event_projection',stage1PositionEventProjection(q), ...
            'stage1_position_pcf_coordination_enabled',pcfCoordinationEnabled, ...
            'stage1_position_delayed_prediction_enabled',positionDelayedPredictionEnabled, ...
            'stage1_position_coordinate_mask',positionCoordinateMask(:).', ...
            'stage1_position_pcf_prediction_reference_mps2',stage1PcfPredictionReference(q,:), ...
            'stage1_position_delayed_prediction_target_mps2',stage1DelayedTarget(q,:), ...
            'stage1_position_delayed_prediction_prev_index_zero_based',stage1DelayedPreviousIndexLog(q), ...
            'stage1_position_delayed_prediction_term_norm',stage1DelayedTermNorm(q), ...
            'stage1_position_delayed_prediction_af_integral_before_step_mps',stage1DelayedAfIntegralBeforeLog(q,:), ...
            'stage1_position_delayed_prediction_reference_integral_before_step_mps', ...
                stage1DelayedPredictionReferenceIntegralBeforeLog(q,:), ...
            'stage1_position_delayed_prediction_event_velocity_mps',stage1DelayedEventVelocity(q,:), ...
            'stage1_position_delayed_prediction_event_af_integral_mps',stage1DelayedEventAfIntegral(q,:), ...
            'stage1_position_delayed_prediction_event_reference_integral_mps', ...
                stage1DelayedEventPredictionReferenceIntegral(q,:), ...
            'stage1_position_pcf_a_req_mps2',stage1PcfAReq(q,:), ...
            'stage1_position_pcf_a_f_mps2',stage1PcfAF(q,:), ...
            'stage1_position_pcf_r_f_mps2',stage1PcfRf(q,:), ...
            'stage1_position_pcf_eta_before_mps',stage1PcfEtaBeforeLog(q,:), ...
            'stage1_position_pcf_eta_after_mps',stage1PcfEtaAfterLog(q,:), ...
            'stage1_position_pcf_event_s_original_mps',stage1PcfSurfaceEvent(q,:), ...
            'stage1_position_pcf_event_eta_before_mps',stage1PcfEtaEventBefore(q,:), ...
            'stage1_position_pcf_event_s_coord_mps',stage1PcfScEvent(q,:), ...
            'stage1_position_pcf_event_s_coord_eff_mps',stage1PcfScEffEvent(q,:), ...
            'stage1_position_held_raw_acceleration_mps2',stage1PositionHeldRawLog(q,:), ...
            'stage1_position_held_applied_acceleration_mps2',stage1PositionHeldAppliedLog(q,:), ...
            'stage1_position_held_force_I_N',stage1PositionHeldForceLog(q,:), ...
            'stage1_position_injected_force_I_N',stage1PositionInjectedForceLog(q,:), ...
            'stage1_position_weight_norm_held',stage1PositionWeightNormHeld(q), ...
            'stage1_position_last_event_time_s',stage1PositionLastEventTimeLog(q), ...
            'stage1_position_history_fill_held',stage1PositionHistoryFillHeld(q), ...
            'stage1_position_weight_initial',stage1PositionWeightInitial,'stage1_position_update_enabled',stage1PositionUpdateEnabled, ...
            'stage1_position_update_dt_scale',stage1PositionUpdateDtScale,'stage1_position_beta_scale',stage1PositionBetaScale, ...
            'v1_adaptive',v1Adaptive,'v1_head_kind',v1Kind,'v1_learner_event',v1EventFlag(q),'v1_history_ready',v1HistoryReady(q), ...
            'v1_history_maturity',v1HistoryMaturity(q),'v1_N_real',v1NReal(q),'v1_alpha',v1Alpha(q), ...
            'v1_learner_event_time',v1EventTime(q),'v1_command_state8',v1CommandState8(q,:),'v1_phi_norm',v1PhiNorm(q), ...
            'v1_phi32_norm',v1Phi32Norm(q),'v1_bounded_phi_norm',v1BoundedPhiNorm(q),'v1_raw_force_diagnostic',v1RawForceDiagnostic(q,:), ...
            'v1_bounded_force_output',v1BoundedForceOutput(q,:), ...
            'v1_surface',v1Surface(q,:),'v1_update_dt',v1UpdateDt(q),'v1_weight_norm',v1WeightNorm(q), ...
            'v1_weight_delta_norm',v1WeightDeltaNorm(q),'v1_weight_derivative_norm',v1WeightDerivativeNorm(q), ...
            'v1_q_phi',v1QPhi(q),'v1_z2_norm',v1Z2Norm(q),'v1_raw_driving_magnitude',v1RawDrivingMagnitude(q),'v1_normalized_driving_magnitude',v1NormalizedDrivingMagnitude(q), ...
            'v1_relative_weight_update',v1RelativeWeightUpdate(q),'v1_weight_delta_matrix',v1WeightDeltaMatrix, ...
            'v1_projection_active',v1ProjectionActive(q),'v1_force_off_parity_max_abs',v1ForceOffParity(q), ...
             'v1_first_adaptation_time_s',v1FirstAdaptationTime,'v1_history_shape',[16,253], ...
             'predictive_force_active',isfield(opts,'predictive_force_head')&&isstruct(opts.predictive_force_head), ...
             'predictive_force_horizon_ms',field_or(field_or(opts,'predictive_force_head',struct),'horizon_ms',NaN), ...
            'v1_adaptation_law',v1Law,'v1_feature_kind',v1FeatureKind,'status',status,'divergence_time_s',divergenceTime,'last_transition',last,'controller_method',method,'method',gateAttitudeArm);
     log.safety_stop_reason=safetyStopReason;
     log.paired_arm=arm;
     log.gate_attitude_arm=gateAttitudeArm;
     log.gate_geometry_arm=gateGeometryArm;
     log.gate_feedforward_enabled=gateFeedforwardEnabled;
     log.gate_observer_enabled=gateObserverEnabled;
     log.gate_identity_lock=opts.gate_identity_lock;
     log.gate_identity_recomputed=gateIdentityHashes;
     log.scene_id=sceneAudit.scene_id;
     log.scene_contract_id=char(string(s.reference_contract_id));
     log.scene_payload_sha256=sceneAudit.scene_payload_sha256;
     log.scene_geometry_audit=sceneAudit;
     log.state_is_finite=all(isfinite(x(qs,:)),2);
     log.transition_is_finite=all(isfinite([requested(q,:),controllerClippedWrench(q,:), ...
         allocatedWrench(q,:),realized(q,:),motor(q,:),motorSetpoint(q,:), ...
         windForce(q,:),windTorque(q,:)]),2);
     log.actual_transition_count=last;
     log.actual_state_sample_count=last+1;
     log.complete_transitions=(last==n)&&all(log.state_is_finite)&&all(log.transition_is_finite);
     if isfield(s,'R_task')
         log.R_task=double(s.R_task(:,:,qs));
         log.R_task_sha256=sceneAudit.R_task_sha256;
     end
     if tcnCandidate
         log.tcn_attitude_trace=tcnTrace(q);
         log.tcn_attitude_model_sha256=opts.tcn_attitude_model_sha256;
         log.tcn_variable_inertia_reconstruction_used=false;
     end
     if mlpCandidate
         log.mlp15_attitude_trace=mlp15Trace(q);
         log.mlp15_attitude_model_sha256=opts.mlp15_attitude_model_sha256;
         log.mlp15_variable_inertia_reconstruction_used=false;
     end
     log.safety_position_error_persistence_s=safetyPositionErrorTime;
     log.safety_tilt_persistence_s=safetyTiltTime;
     log.safety_body_rate_persistence_s=safetyRateTime;
     if formalRbfBaseline
         log=rmfield(log,{'residual_force_estimate_N','residual_torque_estimate_Nm', ...
             'diagnostic_total_residual','diagnostic_causal_residual_prev_motor','causal_label_motor'});
         log.formal_rbf_baseline=true;
     end
     log.state_perturbation_enabled=statePerturbationEnabled;
     log.state_perturbation_requested_time_s=statePerturbationTime;
     log.state_perturbation_applied_time_s=statePerturbationAppliedTime;
     log.state_perturbation_delta=statePerturbationDelta;
     log.state_perturbation_applied_flag=statePerturbationAppliedFlag(qs);
     log.physical_impulse_enabled=physicalImpulseEnabled;
     log.physical_impulse_force_I_N=physicalImpulseForceI(q,:);
     log.physical_impulse_truth_visible_to_controller=false;
     assert(~statePerturbationEnabled||statePerturbationApplied, ...
         'RBFBS:StatePerturbationNotApplied','Enabled state perturbation was not applied before simulation stopped.');
     if wrenchDiagnosticEnabled
        log.diagnostic_external_force_I=diagnosticForce(q,:);
        log.diagnostic_external_torque_B=diagnosticTorque(q,:);
        log.diagnostic_oracle_enabled=diagnosticOracle;
        log.diagnostic_rbf_force_compensation_I_N=diagnosticRbfForce(q,:);
        log.diagnostic_rbf_torque_compensation_B_Nm=diagnosticRbfTorque(q,:);
        log.diagnostic_oracle_force_compensation_I_N=diagnosticOracleForce(q,:);
        log.diagnostic_oracle_torque_compensation_B_Nm=diagnosticOracleTorque(q,:);
        log.diagnostic_position_surface=diagnosticPositionSurface(q,:);
        log.diagnostic_attitude_surface=diagnosticAttitudeSurface(q,:);
        log.diagnostic_controller_visible_residual_6=diagnosticControllerResidual(q,:);
        log.diagnostic_model_residual_6=diagnosticModelResidual(q,:);
        log.diagnostic_aero_residual_6=diagnosticAeroResidual(q,:);
        log.diagnostic_injected_residual_6=diagnosticInjectedResidual(q,:);
        log.diagnostic_residual_closure_error_6=diagnosticClosure(q,:);
    end
    if positionNdoEnabled
        log.position_ndo_mode=positionNdoMode;
        log.position_ndo_input_mode=positionNdoInputMode;
        log.position_ndo_decomposition_enabled=positionNdoDecompositionEnabled;
        log.position_ndo_slow_time_constant_s=positionNdoSlowTau;
        log.position_ndo_lambda_s_inv=positionNdoLambda;
        log.position_ndo_frequency_hz=positionNdoFrequency;
        log.position_ndo_sample_period_s=1/positionNdoFrequency;
        log.position_ndo_update_flag=positionNdoUpdateFlag(q);
        log.position_ndo_update_dt_s=positionNdoUpdateDt(q);
        log.position_ndo_estimate_N=positionNdoEstimate(q,:);
        log.position_ndo_applied_N=positionNdoAppliedEstimate(q,:);
        log.position_ndo_output_limit_N=positionNdoOutputLimit;
        log.position_ndo_limit_active=positionNdoLimitActive(q);
        log.position_rbf_with_ndo=positionRbfWithNdoEnabled;
        log.position_ndo_known_force_N=positionNdoKnownForce(q,:);
        log.position_ndo_reconstructed_motor=positionNdoReconstructedMotor(q,:);
        log.position_ndo_reconstructed_generalized=positionNdoReconstructedGeneralized(q,:);
        log.position_ndo_estimated_arm_lengths=positionNdoEstimatedArmLengths(q,:);
        log.position_ndo_morphology_command=positionNdoMorphologyCommand(q,:);
        log.position_ndo_reconstruction_uses_plant_truth=strcmp(positionNdoInputMode,'realized');
        log.position_ndo_combined_compensation_N=positionNdoCombinedCompensation(q,:);
        log.position_ndo_slow_residual_N=positionNdoSlowResidual(q,:);
        log.position_ndo_slow_innovation_N=positionNdoSlowInnovation(q,:);
        log.position_smc_enabled=positionSmcEnabled;
        log.position_smc_lambda_s_inv=positionSmcLambda;
        log.position_smc_gain_N=positionSmcGain;
        log.position_smc_boundary_layer_mps=positionSmcBoundary;
        log.position_smc_surface_mps=positionSmcSurface(q,:);
        log.position_smc_force_N=positionSmcForce(q,:);
        log.position_bs_nominal_force_N=positionBsNominalForce(q,:);
        log.position_commanded_force_N=positionCommandedForce(q,:);
        log.position_realized_force_N=positionRealizedForce(q,:);
        log.position_force_realization_error_N=positionForceRealizationError(q,:);
    end
    if wrenchDiagnosticEnabled
        log.position_ndo_target_truth_N=positionNdoTargetTruth(q,:);
        log.position_plant_acceleration_truth_mps2=positionPlantAccelerationTruth(q,:);
        if ~positionNdoEnabled
            log.position_bs_nominal_force_N=positionBsNominalForce(q,:);
            log.position_commanded_force_N=positionCommandedForce(q,:);
            log.position_realized_force_N=positionRealizedForce(q,:);
            log.position_force_realization_error_N=positionForceRealizationError(q,:);
        end
    end
    end

    function [score,parts]=guard_support(d,g)
        % ponytail: five grouped P95 scores; replace only if calibration proves
        % a lower-cost sufficient statistic is safe for the collection gate.
        parts=[prctile(abs(d.history_norm(:)),95), ...
            prctile(abs(d.fast_norm(1:12)),95),prctile(abs(d.fast_norm(13:16)),95), ...
            prctile(abs(d.fast_norm(17:20)),95),prctile(abs(d.command_norm(:)),95)];
        limits=double(g.support_limits(:)).';
        assert(numel(limits)==5&&all(isfinite(limits)&limits>0),'TCN0916:GuardSupportLimits','Guard support limits must be five positive finite values.');
        groups=double(field_or(g,'dynamic_group_indices',[1 2 4]));
        assert(isequal(sort(groups),[1 2 4]),'TCN0916:GuardDynamicGroups','R2 dynamic guard groups must be history/current/motor^2.');
        score=max(parts(groups)./limits(groups));
    end

    function [force,info]=predictive_short_force_predict(head,currentFeature,short8)
        % Causal forecast head: current/command at t_k plus frozen short8(t_k).
        currentFeature=double(currentFeature(:)); short8=double(short8(:));
        assert(isequal(size(currentFeature),[28,1])&&isequal(size(short8),[16,1])&&double(head.feature_dim)==36, ...
            'TCN0916:PredictiveHeadShape','Predictive short head expects 28 current features and 8 short features.');
        current20=[currentFeature(1:16);currentFeature(25:28)];
        x=[(current20-double(head.current_mean(:)))./double(head.current_scale(:)); ...
            (currentFeature(17:24)-double(head.command_mean(:)))./double(head.command_scale(:)); short8(1:8)];
        xn=(x-double(head.feature_mean(:)))./double(head.feature_scale(:));
        z=[xn;1]; force=(double(head.beta).'*z).*double(head.target_scale(:))+double(head.target_mean(:));
        force=force(:); info=struct('horizon_ms',double(head.horizon_ms));
        assert(all(isfinite(force)),'TCN0916:PredictiveHeadFinite','Predictive head output is nonfinite.');
    end

    function c=block_contribution(block,rows,W)
        if isempty(rows), c=zeros(1,3); else, c=block(:).'*W(rows,:); end
    end

    function [psi,info]=context_regressor(mode,phi,z1,z2,limit,z1Scale,z2Scale,rbfCfg)
        % Position-BS contract: z1=p_d-p, z2=(v_d-v)+K1.*z1, both inertial-frame.
        z1Bar=double(z1(:))./double(z1Scale(:)); z2Bar=double(z2(:))./double(z2Scale(:));
        phiRows=[]; rbfRows=[]; z1Rows=[]; z2Rows=[]; phiBlock=[]; rbfBlock=[]; z1Block=[]; z2Block=[];
        switch lower(char(mode))
            case 'phi'
                [phiT,phiInfo]=v2_feature_norm_limit(phi,limit); psi=phiT; phiRows=1:32;
            case 'error'
                [psi,phiInfo]=v2_feature_norm_limit([z1Bar;z2Bar],limit); z1Rows=1:3; z2Rows=4:6;
            case 'hybrid'
                [phiT,phiInfo]=v2_feature_norm_limit(phi,limit);
                [psi,finalInfo]=v2_feature_norm_limit([phiT(1:32);z1Bar;z2Bar],limit);
                phiRows=1:32; z1Rows=33:35; z2Rows=36:38; phiInfo.limiter_active=phiInfo.limiter_active||finalInfo.limiter_active;
            case {'rbf_prior','rbf_tcn','rbf_tcn_error','rbf_lstm'}
                rbf=rbf_mimo_basis(z2,rbfCfg); rbfRows=1:numel(rbf); phiInfo=struct('raw_norm',norm(phi),'limiter_active',false);
                switch lower(char(mode))
                    case 'rbf_prior'
                        psi=[rbf;1];
                    case 'rbf_tcn'
                        [phiT,phiInfo]=v2_feature_norm_limit(phi,limit); psi=[rbf;phiT(1:32);1]; phiRows=126:157;
                    case 'rbf_tcn_error'
                        [phiT,phiInfo]=v2_feature_norm_limit(phi,limit); psi=[rbf;phiT(1:32);z1Bar;z2Bar;1]; phiRows=126:157; z1Rows=158:160; z2Rows=161:163;
                    case 'rbf_lstm'
                        [phiT,phiInfo]=v2_feature_norm_limit(phi,limit); psi=[rbf;phiT(1:32);1]; phiRows=126:157;
                end
            otherwise
                error('TCN0916:ContextRegressor','Unknown context mode %s.',mode);
        end
        if isempty(rbfRows), rbfBlock=zeros(0,1); else, rbfBlock=psi(rbfRows); end
        if isempty(phiRows), phiBlock=zeros(0,1); else, phiBlock=psi(phiRows); end
        if isempty(z1Rows), z1Block=zeros(0,1); else, z1Block=psi(z1Rows); end
        if isempty(z2Rows), z2Block=zeros(0,1); else, z2Block=psi(z2Rows); end
        info=struct('raw_norm',phiInfo.raw_norm,'bounded_norm',norm(psi),'limiter_active',phiInfo.limiter_active, ...
            'rbf_rows',rbfRows,'phi_rows',phiRows,'z1_rows',z1Rows,'z2_rows',z2Rows, ...
            'rbf_block',rbfBlock,'phi_block',phiBlock,'z1_block',z1Block,'z2_block',z2Block);
    end

    function [deltaForce,head,info]=rbf_context_update(head,psi,s,dt,mass,ramp,rbfCfg)
        before=double(head.weight); psi=double(psi(:)); s=double(s(:));
        rawAcceleration=before.'*psi; acceleration=max(min(rawAcceleration(:),double(rbfCfg.dmax(:))),-double(rbfCfg.dmax(:)));
        deltaForce=mass*double(ramp)*acceleration; sEff=max(min(s,double(rbfCfg.s_limit(:))),-double(rbfCfg.s_limit(:)));
        Wdot=-psi*(double(rbfCfg.gamma(:)).'.*sEff.')-before.*double(rbfCfg.sigma_w(:)).'; unprojected=before+Wdot*double(dt);
        after=max(min(unprojected,double(rbfCfg.wmax)),-double(rbfCfg.wmax)); head.weight=after;
        info=struct('weight_derivative_fro',norm(Wdot,'fro'),'weight_delta_fro',norm(after-before,'fro'), ...
            'projection_active',any(abs(after(:)-unprojected(:))>1e-12),'output_clipped',any(abs(rawAcceleration(:)-acceleration)>1e-12), ...
            'W_dot',Wdot,'W_before',before,'W_after',after);
    end

    function y=network_predict_dynamic(model,method,window)
        % FUNCTION:
        %   network_predict_dynamic
        % PURPOSE:
        %   按动态模型类型和历史窗口执行网络推理并返回物理输出。
        % INPUT:
        %   model: 冻结网络模型结构。
        %   cfg: Plant/configuration bound to the selected geometry arm.
        %   window: 历史输入窗口。
        % OUTPUT:
        %   y: 计算得到的数值、向量或记录。
        if isfield(model,'kind')&&strcmp(char(model.kind),'current_mlp_v1'),y=k0_current_mlp_predict_v1(model,window);
            return,end
            assert(isfield(model,'net')&&isfield(model,'normalization'),'TCN0901:NetworkCheckpoint','Checkpoint missing net/normalization.');
            mu=single(model.normalization.X_mean(:));
            sd=single(model.normalization.X_scale(:));
            ym=single(model.normalization.Y_mean(:));
            ys=single(model.normalization.Y_scale(:));
            u=(single(window)-mu)./sd;
            if startsWith(method,'MLP-'),x=dlarray(u(:,end),'CB');
        else,x=dlarray(reshape(u,28,64,1),'CTB');
        end
        if gpuDeviceCount('available')>0,x=gpuArray(x);
        end
        p=double(gather(extractdata(reshape(forward(model.net,x),6,1))));
        y=p.*double(ys)+double(ym);
        assert(numel(y)==6&&all(isfinite(y)),'TCN0901:NetworkOutput','Network output is nonfinite.');
    end

    function [y,dbg]=network_predict_frozen(model,method,currentFeature,history)
        % FUNCTION:
        %   network_predict_frozen
        % PURPOSE:
        %   按冻结模型特征合同完成归一化、历史编码和物理输出映射。
        % INPUT:
        %   model: 冻结网络模型结构。
        %   cfg: Plant/configuration bound to the selected geometry arm.
        %   currentFeature: currentFeature 输入量。
        %   history: history 输入量。
        % OUTPUT:
        %   y: 计算得到的数值、向量或记录。
        %   dbg: dbg 输出量。
        % Frozen PyTorch V2 forward, exported as plain MATLAB arrays; no learning.
        currentFeature=currentFeature(:);
        if isfield(model,'kind')&&strcmp(char(model.kind),'ablation_force_v1')
            [y,ablationDebug]=tcn0916_ablation_predict(model,currentFeature,history);
            dbg=ablationDebug;
            return
        end
        if isfield(model,'kind')&&strcmp(char(model.kind),'m2_knockout_v1')
            [y,knockoutDebug]=tcn0916_m2_knockout_predict(model,currentFeature,history);
            dbg=knockoutDebug;
            return
        end
        if isfield(model,'kind')&&strcmp(char(model.kind),'lstm_force_v1')
            [y,lstmDebug]=tcn0916_lstm_predict(model,currentFeature,history);
            dbg=lstmDebug;
            return
        end
        fastFeature=[currentFeature(1:16);currentFeature(25:28)];
        u=(fastFeature(:)-model.fast_mean(:))./model.fast_scale(:);
        cmdNorm=(currentFeature(17:24)-model.command_mean(:))./model.command_scale(:);
        dbg=struct('fast_norm',u,'command_norm',cmdNorm,'mapper_input_norm',nan(36,1),'history_norm',nan(16,253),'c8',nan(8,1),'std_output',nan(6,1),'physical_output',nan(6,1));
        if isfield(model,'kind')&&strcmp(char(model.kind),'multiscale_force_v2')
            [y,seedDebug]=tcn0916_seed_predict(model,currentFeature,history);
            dbg=seedDebug;
            return
        elseif strcmp(method,'B1-PMForce')
            z=[u;cmdNorm];
            z=max(z,-realmax);
            z=min(z,realmax);
            h=max(model.pm_w1*z+model.pm_b1(:),0);
            h=max(model.pm_w2*h+model.pm_b2(:),0);
            p=model.pm_w3*h+model.pm_b3(:);
            dbg.mapper_input_norm=z;
        else
            [c,convDebug]=relu_conv(model,history);
            z=[u;cmdNorm;c];
            h1=max(model.response_map_w1*z+model.response_map_b1(:),0);
            h2=max(model.response_map_w2*h1+model.response_map_b2(:),0);
            p=model.response_map_w3*h2+model.response_map_b3(:);
            dbg.mapper_input_norm=z;
            dbg.history_norm=convDebug.history_norm;
            dbg.c8=c;
        end
        y=p(:).*model.label_scale(:)+model.label_mean(:);
        dbg.std_output=p(:);
        dbg.physical_output=y(:);
        assert(numel(y)==6&&all(isfinite(y)),'TCN0901:FrozenForceOutput','Frozen V2 output is nonfinite.');
    end

    function [c,dbg]=multiscale_conv(model,hist)
        % Multi-scale V2 encoder: block 3 is the short tap, block 6 the long tap.
        hist=(hist-model.context_mean(:))./model.context_scale(:);
        dbg=struct('history_norm',hist);
        h=max(model.response_proj_w*hist+model.response_proj_b(:),0);
        short=zeros(8,1); long=zeros(8,1);
        for ii=1:6
            d=2^(ii-1); r=h;
            h=max(causal_conv(model.(['response_conv1_' num2str(ii) '_w']),model.(['response_conv1_' num2str(ii) '_b']),h,d),0);
            h=max(causal_conv(model.(['response_conv2_' num2str(ii) '_w']),model.(['response_conv2_' num2str(ii) '_b']),h,d),0);
            h=max(r+h,0);
            if ii==3, short=model.response_short_readout_w*h(:,end)+model.response_short_readout_b(:); end
            if ii==6, long=model.response_long_readout_w*h(:,end)+model.response_long_readout_b(:); end
        end
        c=[short;long];
    end

    function [c,dbg]=relu_conv(model,hist)
        % FUNCTION:
        %   relu_conv
        % PURPOSE:
        %   执行带 ReLU 激活的时序卷积编码并返回中间诊断信息。
        % INPUT:
        %   model: 冻结网络模型结构。
        %   hist: 历史表示矩阵。
        % OUTPUT:
        %   c: 计算结果或门控检查记录。
        %   dbg: dbg 输出量。
        idx=[1:12 17:20];
        cm=model.context_mean(idx(:)).';
        cs=model.context_scale(idx(:)).';
        hist=(hist-cm)./cs;
        dbg=struct('history_norm',hist);
        h=max(model.response_proj_w*hist+model.response_proj_b(:),0);
        for ii=1:6
            d=2^(ii-1);
            r=h;
            h=max(causal_conv(model.(['response_conv1_' num2str(ii) '_w']),model.(['response_conv1_' num2str(ii) '_b']),h,d),0);
            h=max(causal_conv(model.(['response_conv2_' num2str(ii) '_w']),model.(['response_conv2_' num2str(ii) '_b']),h,d),0);
            h=max(r+h,0);
        end
        c=model.response_readout_w*h(:,end)+model.response_readout_b(:);
    end

    function y=causal_conv(W,b,x,d)
        % FUNCTION:
        %   causal_conv
        % PURPOSE:
        %   对时间序列执行给定膨胀率的因果一维卷积。
        % INPUT:
        %   W: 权重矩阵。
        %   b: 卷积偏置或比较基准。
        %   x: 待处理状态或信号。
        %   d: 字段缺失时使用的默认值。
        % OUTPUT:
        %   y: 计算得到的数值、向量或记录。
        [co,~,~]=size(W);
        n=size(x,2);
        y=zeros(co,n);
        for t=1:n
            for j=0:2
                q=t-(2-j)*d;
                if q>=1, y(:,t)=y(:,t)+W(:,:,j+1)*x(:,q);
                end
            end
        end
        y=y+b(:);
    end

    function d=init_forward_debug(nmax,model,repeatCount)
        % FUNCTION:
        %   init_forward_debug
        % PURPOSE:
        %   预分配冻结网络前向传播的时序调试记录结构。
        % INPUT:
        %   nmax: nmax 输入量。
        %   model: 冻结网络模型结构。
        %   repeatCount: repeatCount 输入量。
        % OUTPUT:
        %   d: d 输出量。
        contextMean=double(model.context_mean(:));
        contextScale=double(model.context_scale(:));
        if numel(contextMean)==20
            contextMeanSelected=contextMean([1:12 17:20]).';
            contextScaleSelected=contextScale([1:12 17:20]).';
        else
            contextMeanSelected=contextMean.';
            contextScaleSelected=contextScale.';
        end
        mapperWidth=36;
        if isfield(model,'response_map_w1')
            mapperWidth=size(model.response_map_w1,2);
        elseif isfield(model,'mapper_w1')
            mapperWidth=size(model.mapper_w1,2);
        end
        c8Width=8;
        if isfield(model,'response_short_readout_w') && isfield(model,'response_long_readout_w')
            c8Width=size(model.response_short_readout_w,1)+size(model.response_long_readout_w,1);
        end
        d=struct('enabled',true,'count',0,'time',nan(nmax,1),'step',nan(nmax,1),'event_index',nan(nmax,1), ...
            'learner_enabled',false(nmax,1),'model_call',false(nmax,1),'history_ready',false(nmax,1),'history_valid_count',zeros(nmax,1), ...
            'oldest_history_time',nan(nmax,1),'newest_history_time',nan(nmax,1),'append_before_infer',false(nmax,1), ...
            'current_feature_raw',nan(28,nmax),'current20_raw',nan(20,nmax),'command_state_raw',nan(8,nmax),'previous_motor_squared',nan(4,nmax), ...
            'fast_norm',nan(20,nmax),'command_norm',nan(8,nmax),'mapper_input_norm',nan(mapperWidth,nmax),'phi32',nan(32,nmax), ...
            'history_raw',nan(16,253,nmax),'history_norm',nan(16,253,nmax),'c8',nan(c8Width,nmax),'std_output',nan(6,nmax),'physical_output',nan(6,nmax), ...
            'force_selected',nan(3,nmax),'applied_force',nan(3,nmax),'zoh_force',nan(3,nmax),'requested_force',nan(3,nmax), ...
            'requested_force_norm',nan(nmax,1),'release',nan(nmax,1),'saturation',false(nmax,1),'allocation_clip',false(nmax,1), ...
            'input_mutation_max',nan(nmax,1),'history_input_mutation_max',nan(nmax,1),'network_call_time_s',nan(nmax,1), ...
            'repeat_physical',nan(6,repeatCount,nmax), ...
            'input_dtype','double','device','MATLAB CPU','model_training',false,'model_eval',true,'history_shape',[16 253], ...
            'normalization',struct('fast_mean',double(model.fast_mean(:)),'fast_scale',double(model.fast_scale(:)), ...
            'command_mean',double(model.command_mean(:)),'command_scale',double(model.command_scale(:)), ...
            'context_mean_selected',contextMeanSelected,'context_scale_selected',contextScaleSelected, ...
            'label_mean',double(model.label_mean(:)),'label_scale',double(model.label_scale(:))));
    end

    function d=trim_forward_debug(d)
        % FUNCTION:
        %   trim_forward_debug
        % PURPOSE:
        %   按有效记录数裁剪前向传播调试结构中的向量、矩阵和张量。
        % INPUT:
        %   d: 字段缺失时使用的默认值。
        % OUTPUT:
        %   d: d 输出量。
        n=d.count;
        vectorFields={'time','step','event_index','learner_enabled','model_call','history_ready','history_valid_count','oldest_history_time','newest_history_time','append_before_infer','requested_force_norm','release','saturation','allocation_clip','input_mutation_max','history_input_mutation_max','network_call_time_s'};
        for k=1:numel(vectorFields),f=vectorFields{k};
            d.(f)=d.(f)(1:n);
        end
        matrixFields={'current_feature_raw','current20_raw','command_state_raw','previous_motor_squared','fast_norm','command_norm','mapper_input_norm','phi32','c8','std_output','physical_output','force_selected','applied_force','zoh_force','requested_force'};
        for k=1:numel(matrixFields),f=matrixFields{k};
            d.(f)=d.(f)(:,1:n);
        end
        tensorFields={'history_raw','history_norm'};
        for k=1:numel(tensorFields),f=tensorFields{k};
            d.(f)=d.(f)(:,:,1:n);
        end
        if ~isempty(d.repeat_physical),d.repeat_physical=d.repeat_physical(:,:,1:n);
        end
    end


    function u=nominal_virtual_input(state,motor,P)
        % FUNCTION:
        %   nominal_virtual_input
        % PURPOSE:
        %   由名义质量、惯量、姿态和电机量计算平动及姿态虚拟输入。
        % INPUT:
        %   state: 当前状态向量。
        %   motor: 电机输入记录。
        %   P: Plant 参数结构。
        % OUTPUT:
        %   u: 计算得到的虚拟控制输入。
        w=P.allocation.C*motor.^2;
        eta=state(7:9);
        omega=state(10:12);
        R=rotation_zyx(eta);
        a=R*[0;0;w(1)]/P.mass-[0;0;P.g];
        [T,Tdot]=euler_kinematics(eta,omega);
        etaDD=T*(diag(diag(P.inertia))\w(2:4))+Tdot*omega;
        u=[a;etaDD];
    end
    % FUNCTION:
    %   rotation_zyx
    % PURPOSE:
    %   根据滚转、俯仰和偏航欧拉角构造 ZYX 旋转矩阵。
    % INPUT:
    %   e: e 输入量。
    % OUTPUT:
    %   R: 旋转矩阵或报告结构。
    function R=rotation_zyx(e),p=e(1);
        q=e(2);
        y=e(3);
        R=[cos(y)*cos(q),cos(y)*sin(q)*sin(p)-sin(y)*cos(p),cos(y)*sin(q)*cos(p)+sin(y)*sin(p);sin(y)*cos(q),sin(y)*sin(q)*sin(p)+cos(y)*cos(p),sin(y)*sin(q)*cos(p)-cos(y)*sin(p);-sin(q),cos(q)*sin(p),cos(q)*cos(p)];
    end
    % FUNCTION:
    %   euler_kinematics
    % PURPOSE:
    %   计算机体系角速度到欧拉角速度的映射及其时间导数。
    % INPUT:
    %   eta: 欧拉角向量。
    %   omega: 机体系角速度向量。
    % OUTPUT:
    %   T: 指标表或运动学映射矩阵。
    %   Tdot: 欧拉运动学映射的时间导数。
    function [T,Tdot]=euler_kinematics(eta,omega),p=eta(1);
        q=max(min(eta(2),pi/2-1e-4),-pi/2+1e-4);
        T=[1 sin(p)*tan(q) cos(p)*tan(q);0 cos(p) -sin(p);0 sin(p)/cos(q) cos(p)/cos(q)];
        er=T*omega;
        Tp=[0 cos(p)*tan(q) -sin(p)*tan(q);0 -sin(p) -cos(p);0 cos(p)/cos(q) -sin(p)/cos(q)];
        Tq=[0 sin(p)/cos(q)^2 cos(p)/cos(q)^2;0 0 0;0 sin(p)*tan(q)/cos(q) cos(p)*tan(q)/cos(q)];
        Tdot=Tp*er(1)+Tq*er(2);
    end
    % FUNCTION:
    %   reference_row
    % PURPOSE:
    %   从参考轨迹指定采样点组装单步参考结构。
    % INPUT:
    %   a: 待处理的数值数组或记录结构。
    %   k: k 输入量。
    % OUTPUT:
    %   r: 结果记录结构。
    function r=reference_row(a,k),r=struct('position',a.position(k,:).','velocity',a.velocity(k,:).','acceleration',a.acceleration(k,:).','euler',[0;0;a.yaw(k)],'euler_rate',[0;0;a.yaw_rate(k)],'euler_acceleration',[0;0;a.yaw_acceleration(k)]);
    end
    % FUNCTION:
    %   trim_reference
    % PURPOSE:
    %   将参考结构中的时序字段截取到选定索引。
    % INPUT:
    %   a: 待处理的数值数组或记录结构。
    %   q: 有效采样索引。
    % OUTPUT:
    %   a: a 输出量。
    function a=trim_reference(a,q),n=fieldnames(a);
        for i=1:numel(n),a.(n{i})=a.(n{i})(q,:);
        end,end
        % FUNCTION:
        %   trim_arms
        % PURPOSE:
        %   将形态记录结构中的时序字段截取到指定索引范围。
        % INPUT:
        %   a: 待处理的数值数组或记录结构。
        %   q: 有效采样索引。
        % OUTPUT:
        %   a: a 输出量。
        function a=trim_arms(a,q),n=fieldnames(a);
            for i=1:numel(n),if size(a.(n{i}),1)>=max(q),a.(n{i})=a.(n{i})(q,:);
            end,end,end
            % FUNCTION:
            %   attitude_input
            % PURPOSE:
            %   按误差和滑模面顺序打包姿态 learner 输入向量。
            % INPUT:
            %   i: i 输入量。
            % OUTPUT:
            %   z: z 输出量。
            function z=attitude_input(i),z=[i.error(1);i.surface(1);i.error(2);i.surface(2);i.error(3);i.surface(3)];
            end
            % FUNCTION:
            %   wrap
            % PURPOSE:
            %   将角度误差折返到 [-π, π] 主值区间。
            % INPUT:
            %   x: 待处理状态或信号。
            % OUTPUT:
            %   x: 处理后的数值、数组或记录。
            function x=wrap(x),x=atan2(sin(x),cos(x));
            end
            % FUNCTION:
            %   field_or
            % PURPOSE:
            %   为按选定基线、场景和选项执行闭环仿真，并记录状态、参考、控制输入及诊断信号。提供field_or辅助处理。
            % INPUT:
            %   s: DL1018_GATE_INSPECTION_HOLDOUT_V1 scene payload.
            %   n: 样本数、索引或字段标识（按函数接口解释）。
            %   d: 字段缺失时使用的默认值。
            % OUTPUT:
            %   v: v 输出量。
            function v=field_or(s,n,d),if isfield(s,n),v=s.(n);
            else,v=d;
            end,end
            function a=trim_rbf_audit(a,n,maxN)
                % FUNCTION:
                %   trim_rbf_audit
                % PURPOSE:
                %   将 RBF audit 结构的各字段裁剪到有效采样长度。
                % INPUT:
                %   a: 待处理的数值数组或记录结构。
                %   n: 样本数、索引或字段标识（按函数接口解释）。
                %   maxN: maxN 输入量。
                % OUTPUT:
                %   a: a 输出量。
                n=min(n,maxN);
                f=fieldnames(a);
                for i=1:numel(f),v=a.(f{i});
                    if ndims(v)==3,a.(f{i})=v(:,:,1:n);
                    elseif size(v,2)==maxN,a.(f{i})=v(:,1:n);
                    else,a.(f{i})=v(1:n,:);
                    end,end
                end
function [currentForce,futurePointForce,nextHoldAverageForce]=truth_wind_oracle_candidates(s,cfg,k,stateNow,Ptrue,wcfg,horizonSamples)
    % Truth-wind counterfactual: future wind/morphology is exposed, while the
    % event state is held fixed so the shared plant/controller loop remains the
    % only state propagator. This is intentionally non-deployable preview.
    currentForce=morphology_aware_wind_load(stateNow,Ptrue,s.environment_wind_I(k,:).',wcfg);
    N=numel(s.time);
    futureK=min(k+horizonSamples,N);
    Pfuture=simulation_parameters(cfg,s.arms.rho_true(futureK,:).',s.arms.rhoDot_true(futureK,:).');
    futurePointForce=morphology_aware_wind_load(stateNow,Pfuture,s.environment_wind_I(futureK,:).',wcfg);
    holdForce=zeros(3,1);
    for ii=1:horizonSamples
        kk=min(k+ii,N);
        Pii=simulation_parameters(cfg,s.arms.rho_true(kk,:).',s.arms.rhoDot_true(kk,:).');
        [fii,~]=morphology_aware_wind_load(stateNow,Pii,s.environment_wind_I(kk,:).',wcfg);
        holdForce=holdForce+fii;
    end
    nextHoldAverageForce=holdForce/horizonSamples;
end

function dtUsed=rbf_dt_used(opts,dtActual)
    dtUsed=dtActual;
    if isfield(opts,'rbf_update_dt_override')
        dtUsed=double(opts.rbf_update_dt_override);
        assert(isscalar(dtUsed)&&isfinite(dtUsed)&&dtUsed>0,'TCN0916:RbfUpdateDtOverride','Audit RBF update dt override must be positive and finite.');
    end
end

function y=limit_vector_norm(x,limit)
    y=double(x(:));
    if isfinite(limit)
        magnitude=norm(y,2);
        if magnitude>limit,y=y*(limit/magnitude);end
    end
end

