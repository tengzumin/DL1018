% Offline label replay for two existing attitude-event records only.
% This script loads recorded data and calls repository dynamics functions;
% it does not start a runner, integrate a trajectory, or modify any data.
clear; clc;
repoRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
coreDir = fullfile(repoRoot,'matlab','core');
addpath(coreDir,'-begin');

cases = {
    'train','DL1018_TRAIN_T1_C01_W00';
    'val','DL1018_VAL_T1_C01_W08'};
rows = repmat(struct(),size(cases,1),1);
for s = 1:size(cases,1)
    split = cases{s,1}; sceneId = cases{s,2};
    rawDir = fullfile(repoRoot,'data','raw',split,sceneId,'B','attempt_01');
    eventPath = fullfile(repoRoot,'data','events','attitude',split,sceneId,'B.h5');
    rawPath = fullfile(rawDir,'raw_run.mat');
    startPath = fullfile(rawDir,'run_start.mat');
    assert(isfile(rawPath)&&isfile(startPath)&&isfile(eventPath), ...
        'Expected existing raw/run-start/event files are missing.');
    raw = load(rawPath,'scene','log','method');
    start = load(startPath,'runStart');
    cfg = start.runStart.cfg;
    log = raw.log; scene = raw.scene;
    idx = find(log.attitude_event_flag(:)~=0);
    N = numel(idx);
    plantIndex = double(h5read(eventPath,'/plant_index')); plantIndex = plantIndex(:);
    eventIndex = double(h5read(eventPath,'/event_index')); eventIndex = eventIndex(:);
    eventTime = double(h5read(eventPath,'/event_time_s')); eventTime = eventTime(:);
    targetH5 = event_rows3(h5read(eventPath,'/target_raw'),N);
    targetClip = event_rows3(h5read(eventPath,'/target_clip'),N);
    timeRaw = double(log.transition_time(idx)); timeRaw = timeRaw(:);
    assert(numel(plantIndex)==N && numel(eventIndex)==N && numel(eventTime)==N, ...
        'H5 event arrays have inconsistent lengths.');
    assert(isequal(plantIndex,double(idx)) && isequal(eventIndex,(1:N).') && ...
        isequal(eventTime,timeRaw), 'Raw/H5 event identity or timing mismatch.');

    Pplant0 = simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
    Pnom = controller_parameters(cfg,Pplant0,'fixed');
    yReplay = zeros(N,3); yModel = zeros(N,3); yOutput = zeros(N,3);
    yWind = zeros(N,3); yReqClosure = zeros(N,3); yRealReq = zeros(N,3);
    Jdelta = zeros(N,1); JdotNorm = zeros(N,1);
    requestedTorqueClosure = zeros(N,3); realizedRequested = zeros(N,4);
    realizedAllocated = zeros(N,4); allocatedClipped = zeros(N,4);
    requestedClipped = zeros(N,4); trueThrustError = zeros(N,1);
    rhoAtEvent = zeros(N,4); rhoDotAtEvent = zeros(N,4);
    motorSaturated = false(N,4);
    for q = 1:N
        k = idx(q);
        x = double(log.state(k,:)).';
        omega = x(10:12);
        tauNominal = double(log.attitude_bs_nominal_torque_Nm(k,:)).';
        tauBehavior = double(log.attitude_compensation_applied_torque_Nm(k,:)).';
        tauVirtual = tauNominal-tauBehavior;
        tauRequested = double(log.requested_generalized(k,2:4)).';
        tauRealized = double(log.realized_generalized(k,2:4)).';
        tauWind = double(log.wind_torque_B(k,:)).';
        rho = double(scene.arms.rho_true(k,:)).';
        rhoDot = double(scene.arms.rhoDot_true(k,:)).';
        rhoAtEvent(q,:) = rho.'; rhoDotAtEvent(q,:) = rhoDot.';
        Ptrue = simulation_parameters(cfg,rho,rhoDot);
        dxTrue = vehicle_derivative(x,double(log.realized_generalized(k,:)).', ...
            double(log.wind_force_I(k,:)).',tauWind,Ptrue);
        yReplay(q,:) = (dxTrue(10:12)-Pnom.inertia \ ...
            (tauVirtual-cross(omega,Pnom.inertia*omega)- ...
            Pnom.inertia_dot_for_bs*omega)).';

        gyroTrue = cross(omega,Ptrue.inertia*omega);
        gyroNom = cross(omega,Pnom.inertia*omega);
        alphaTrueVirtualTorque = Ptrue.inertia \ ...
            (tauVirtual-gyroTrue-Ptrue.inertia_dot*omega);
        alphaNomVirtualTorque = Pnom.inertia \ ...
            (tauVirtual-gyroNom-Pnom.inertia_dot_for_bs*omega);
        yModel(q,:) = (alphaTrueVirtualTorque-alphaNomVirtualTorque).';
        yOutput(q,:) = (Ptrue.inertia \ (tauRealized-tauRequested)).';
        yWind(q,:) = (Ptrue.inertia \ tauWind).';
        yReqClosure(q,:) = (Ptrue.inertia \ (tauRequested-tauVirtual)).';
        yRealReq(q,:) = (tauRealized-tauRequested).';
        Jdelta(q) = norm(Ptrue.inertia-Pnom.inertia,'fro');
        JdotNorm(q) = norm(Ptrue.inertia_dot,'fro');

        requestedTorqueClosure(q,:) = (tauRequested-tauVirtual).';
        requestedClipped(q,:) = double(log.requested_generalized(k,:))- ...
            double(log.controller_clipped_generalized(k,:));
        allocatedClipped(q,:) = double(log.allocated_generalized(k,:))- ...
            double(log.controller_clipped_generalized(k,:));
        realizedAllocated(q,:) = double(log.realized_generalized(k,:))- ...
            double(log.allocated_generalized(k,:));
        realizedRequested(q,:) = double(log.realized_generalized(k,:))- ...
            double(log.requested_generalized(k,:));
        trueThrustError(q) = realizedRequested(q,1);
        motorSaturated(q,:) = logical(log.motor_saturated(k,:));
    end
    decomp = yModel+yOutput+yWind+yReqClosure;
    rows(s).split = split;
    rows(s).scene_id = sceneId;
    rows(s).run_id = char(string(start.runStart.run_id));
    rows(s).collector_id = char(string(start.runStart.collector_id));
    rows(s).model_id = char(string(start.runStart.model_id));
    rows(s).contract = char(string(start.runStart.contract_version));
    rows(s).source_hash_present_in_run_start = any(contains(lower(string(fieldnames(start.runStart))),'source'));
    rows(s).event_count = N;
    rows(s).event_alignment_exact = true;
    rows(s).event_time_first_s = eventTime(1);
    rows(s).event_time_last_s = eventTime(end);
    rows(s).rho_event_min_m = min(rhoAtEvent,[],1);
    rows(s).rho_event_max_m = max(rhoAtEvent,[],1);
    rows(s).rhoDot_event_maxabs_mps = max(abs(rhoDotAtEvent),[],1);
    rows(s).Jnom_kgm2 = Pnom.inertia;
    rows(s).max_fro_Jtrue_minus_Jnom_kgm2 = max(Jdelta);
    rows(s).max_fro_Jdot_true_kgm2ps = max(JdotNorm);
    rows(s).target_h5_maxabs_rads2_by_axis = max(abs(targetH5),[],1);
    rows(s).target_h5_rms_rads2_by_axis = sqrt(mean(targetH5.^2,1));
    rows(s).target_h5_maxabs_rads2 = max(abs(targetH5),[],'all');
    rows(s).target_h5_rms_vector_rads2 = sqrt(mean(sum(targetH5.^2,2)));
    rows(s).target_clip_maxabs_rads2_by_axis = max(abs(targetClip),[],1);
    rows(s).target_clip_equals_target_raw = isequal(targetClip,targetH5);
    rows(s).replay_maxabs_error_rads2_by_axis = max(abs(yReplay-targetH5),[],1);
    rows(s).replay_rmse_rads2_by_axis = sqrt(mean((yReplay-targetH5).^2,1));
    rows(s).replay_maxabs_error_rads2 = max(abs(yReplay-targetH5),[],'all');
    rows(s).replay_rms_vector_error_rads2 = sqrt(mean(sum((yReplay-targetH5).^2,2)));
    rows(s).decomposition_closure_maxabs_rads2 = max(abs(yReplay-decomp),[],'all');
    rows(s).model_component_rms_vector_rads2 = sqrt(mean(sum(yModel.^2,2)));
    rows(s).output_mismatch_component_rms_vector_rads2 = sqrt(mean(sum(yOutput.^2,2)));
    rows(s).wind_component_rms_vector_rads2 = sqrt(mean(sum(yWind.^2,2)));
    rows(s).request_virtual_closure_component_rms_vector_rads2 = sqrt(mean(sum(yReqClosure.^2,2)));
    rows(s).maxabs_requested_virtual_torque_gap_Nm = max(abs(requestedTorqueClosure),[],'all');
    rows(s).maxabs_realized_minus_requested_wrench_by_channel = max(abs(realizedRequested),[],1);
    rows(s).rms_realized_minus_requested_wrench_by_channel = sqrt(mean(realizedRequested.^2,1));
    rows(s).maxabs_realized_minus_allocated_wrench_by_channel = max(abs(realizedAllocated),[],1);
    rows(s).maxabs_allocated_minus_controller_clip_by_channel = max(abs(allocatedClipped),[],1);
    rows(s).maxabs_requested_minus_controller_clip_by_channel = max(abs(requestedClipped),[],1);
    rows(s).maxabs_realized_thrust_minus_requested_N = max(abs(trueThrustError));
    rows(s).motor_saturated_event_sample_count = nnz(motorSaturated);
    rows(s).motor_event_sample_count = numel(motorSaturated);
    rows(s).target_reconstruction_is_offline_diagnostic_only = true;
end

result = struct();
result.scope = 'two existing C01 TRAIN/VAL records; offline replay only; no runner, integration, Plant, training, or TEST';
result.source_paths = struct('simulation_parameters',which('simulation_parameters'), ...
    'controller_parameters',which('controller_parameters'), ...
    'distributed_mass_properties',which('distributed_mass_properties'), ...
    'vehicle_derivative',which('vehicle_derivative'));
result.scenes = rows;
resultPath = fullfile(fileparts(mfilename('fullpath')),'nonzero_pair_reconstruction_v1.json');
fid = fopen(resultPath,'w'); assert(fid>0,'Could not write result JSON.');
fwrite(fid,jsonencode(result),'char'); fclose(fid);
fprintf('Wrote %s\n',resultPath);
fprintf('%s\n',jsonencode(result));

function Y = event_rows3(X,N)
    X = double(X);
    if isequal(size(X),[N,3])
        Y = X;
    elseif isequal(size(X),[3,N])
        Y = X.';
    else
        error('target dataset dimensions do not match expected event rows: %s',mat2str(size(X)));
    end
end
