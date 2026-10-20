function run_old_kan_transfer_experiment(projectRoot)
% Resume the frozen task: two historical reproductions, then 32 current scenes,
% then the preregistered conditional bridge. No training or TEST access.
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
expDir=fullfile(projectRoot,'experiments','old_kan_fig8_transfer_compare_v1');
preflight=jsondecode(fileread(fullfile(expDir,'reports','ZERO_PLANT_PREFLIGHT.json')));
assert(strcmp(preflight.status,'PASS')&&preflight.plant_calls_started==0, ...
    'OLDKAN:Preflight','A passing zero-Plant preflight is required.');
state=read_json(fullfile(expDir,'state','state.json'));
assert(strcmp(state.zero_plant_preflight,'PASS')&&double(state.plant_calls_started)<=48, ...
    'OLDKAN:State','State is not eligible to run.');
run_historical(expDir);

% The historical stage has its own legacy-only path. Reset before current DL1018.
restoredefaultpath;addpath(fullfile(projectRoot,'matlab','runtime'));
[cfg,~,root]=init_dl1018();assert(strcmp(root,projectRoot),'OLDKAN:Root','Unexpected current root.');
local=fullfile(expDir,'local_runtime');addpath(local,'-begin');rehash;
assert(startsWith(which('run_dl1018_closed_loop'),local,'IgnoreCase',true), ...
    'OLDKAN:PathIsolation','Current task runtime is not first on path.');
oldModel=load_old_adapter_model();newModel=load_new_adapter_model(projectRoot);
sceneIds={'DL1018_DEV_T2_C00_W04','DL1018_DEV_T2_C02_W15', ...
    'DL1018_DEV_T2_C03_W01','DL1018_DEV_T2_C06_W07', ...
    'DL1018_DEV_T2_C08_W08','DL1018_DEV_T2_C09_W10', ...
    'DL1018_DEV_T2_C12_W13','DL1018_DEV_T2_C14_W14'};
conditions={'OLD_G1_R32','NEW_G1_R32','OLD_G12_R32','NEW_G12_R32'};
matrixTotal=32;state=read_json(fullfile(expDir,'state','state.json'));
state.phase='MAIN_MATRIX';state.status='RUNNING_MAIN_MATRIX';write_state(expDir,state);
wall=tic;
for si=1:numel(sceneIds)
    sid=sceneIds{si};G=make_scenes_dl1018('GET',projectRoot,sid);
    scene=G.scene;spec=G.spec;sceneMeta=G.metadata;
    % GET resets MATLAB's path through init_dl1018; restore the isolated runner.
    addpath(local,'-begin');rehash;
    base=load_official_B(projectRoot,sid,scene,spec);
    for ci=1:numel(conditions)
        condition=conditions{ci};
        gamma=str2double(extractBetween(string(condition),'_G','_R'));
        if startsWith(condition,'OLD_'),model=oldModel;else,model=newModel;end
        opts=position_only_search_options(cfg,model,'FEATURE',gamma,1);
        p=opts.stage1_position_runtime;p.readiness_events=32;
        p.command_filter_coordination_v3_5=struct('enabled',true);
        p.position_only_search_head.state_reset_each_episode=true;
        p.position_only_search_head.encoder_frozen=true;opts.stage1_position_runtime=p;
        assert(isequal(double(p.weight),double(model.output_W))&& ...
            isequal(double(p.position_only_search_head.W0),double(model.output_W))&& ...
            double(p.readiness_events)==32,'OLDKAN:EpisodeReset','W0/readiness reset failed.');
        md='OLD_N_KAN_REPAIR';if startsWith(condition,'NEW_'),md='NEW_KAN14_FINAL60K';end
        [metrics,~]=run_current_cell(projectRoot,expDir,cfg,scene,sceneMeta,spec, ...
            sid,condition,md,model,gamma,base,'MAIN_MATRIX',struct('parent_scene_id',sid));
        state=read_json(fullfile(expDir,'state','state.json'));
        matrixDone=count_terminal_cells(expDir,'main_matrix');
        state.phase='MAIN_MATRIX';state.status='RUNNING_MAIN_MATRIX';
        state.main_matrix_completed=matrixDone;state.main_matrix_total=matrixTotal;
        state.last_completed_cell=struct('scene_id',sid,'method_id',condition, ...
            'Q_0_20_m',metrics.Q_0_20_m,'Q_0_5_m',metrics.Q_0_5_m, ...
            'Q_5_20_m',metrics.Q_5_20_m,'attitude_RMSE_0_20_rad',metrics.A_0_20_rad, ...
            'status',metrics.status);
        write_state(expDir,state);
        if mod(matrixDone,4)==0||matrixDone==matrixTotal
            elapsed=toc(wall);avg=mean_call_s(expDir);eta=max(0,matrixTotal-matrixDone)*avg;
            fprintf('MATRIX_PROGRESS %d/%d latest=%s %s Q=%.6f m B=%.6f m dQ=%.6f m A=%.6f rad Plant=%d/48 elapsed=%.1fmin ETA=%.1fmin\n', ...
                matrixDone,matrixTotal,sid,condition,metrics.Q_0_20_m,base.core.Q_0_20_m, ...
                metrics.Q_0_20_m-base.core.Q_0_20_m,metrics.A_0_20_rad, ...
                count_plant_markers(expDir),elapsed/60,eta/60);
            write_transfer_runs(projectRoot,expDir,sceneIds,conditions);
        end
    end
end
write_transfer_runs(projectRoot,expDir,sceneIds,conditions);
state=read_json(fullfile(expDir,'state','state.json'));state.main_matrix_completed=32;
state.phase='GAMMA_GATE';state.status='ANALYZING_GAMMA_GATE';write_state(expDir,state);
[bridgeRequired,gate]=bridge_gate(expDir,sceneIds);
write_json(fullfile(expDir,'reports','OLD_PACKAGE_RECOVERY_GATE.json'),gate);
if bridgeRequired
    state=read_json(fullfile(expDir,'state','state.json'));state.phase='ENVIRONMENT_BRIDGE';
    state.status='RUNNING_ENVIRONMENT_BRIDGE';write_state(expDir,state);
    run_environment_bridge(projectRoot,expDir,cfg,oldModel);
else
    state=read_json(fullfile(expDir,'state','state.json'));
    state.bridge_status='SKIPPED_OLD_PACKAGE_RECOVERED';
    write_json(fullfile(expDir,'reports','ENVIRONMENT_BRIDGE.json'), ...
        struct('status','SKIPPED_OLD_PACKAGE_RECOVERED','reason','At least one old package Gamma met all preregistered recovery criteria.'));
end
addpath(fullfile(expDir,'scripts'),'-begin');finalize_old_kan_transfer(projectRoot);
state=read_json(fullfile(expDir,'state','state.json'));state.status='COMPLETE';
state.phase='FINAL_REPORT';state.completed_local=char(datetime('now','TimeZone','local', ...
    'Format','yyyy-MM-dd''T''HH:mm:ssXXX'));write_state(expDir,state);
fprintf('TASK_COMPLETE total_Plant_calls=%d bridge=%s report=%s\n', ...
    count_plant_markers(expDir),char(string(field_or(state,'bridge_status','RUNNED'))), ...
    fullfile(expDir,'reports','FINAL_REPORT_ZH.md'));
end

function run_historical(expDir)
oldRoot='C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1009';oldBase=fullfile(oldRoot,'RBF-BS0');
oldV2=fullfile(oldBase,'experiments','kan_position_attitude_followup_v2');
oldK1=fullfile(oldBase,'experiments','k1_command_filter_update_coordination_v3_5');
oldV21=fullfile(oldBase,'experiments','kan_contract_zoh_repair_v2_1');oldAdv=fullfile(oldBase,'experiments','position_advantage_stage1_v1');
restoredefaultpath;addpath(fullfile(oldBase,'code','code'),'-begin');
addpath(fullfile(oldAdv,'methods'),'-begin');addpath(fullfile(oldV2,'local_runtime'),'-begin');
addpath(fullfile(oldV21,'local_runtime'),'-begin');addpath(fullfile(oldK1,'local_runtime'),'-begin');rehash;
assert(startsWith(which('run_position_stage1_closed_loop_pcf_v3_5'), ...
    fullfile(oldK1,'local_runtime'),'IgnoreCase',true)&& ...
    startsWith(which('position_stage1_model_forward_v2'),fullfile(oldV2,'local_runtime'),'IgnoreCase',true)&& ...
    startsWith(which('position_stage1_update_head_pcf_v3_5'),fullfile(oldK1,'local_runtime'),'IgnoreCase',true), ...
    'OLDKAN:HistoricalPath','Historical execution resolved outside frozen DL1009 sources.');
sceneIds={'PDEV_DIAG_D1_C01_1','PDEV_DIAG_D1_C12_124'};
pairPath=fullfile(oldK1,'reports','P_CF_DEV_PAIR_METRICS_V3_5.csv');
P=readtable(pairPath,'TextType','string','VariableNamingRule','preserve');
for i=1:2
    sid=sceneIds{i};outDir=fullfile(expDir,'runs','historical_repro',sid,'attempt_01');
    if ~isfolder(outDir),mkdir(outDir);end
    rawPath=fullfile(outDir,'raw_run.mat');statusPath=fullfile(outDir,'run_status.json');
    if isfile(statusPath)
        st=read_json(statusPath);
        if any(strcmp(char(string(st.status)),{'PASS','FAIL'}))&&isfile(rawPath),continue,end
        if isfile(fullfile(outDir,'plant_started.marker'))
            error('OLDKAN:NoRetry','Historical Plant call started without terminal raw: %s.',sid);
        end
    end
    rows=find(string(P.scene_id)==sid);assert(isscalar(rows),'OLDKAN:PairRow','Missing frozen old P_CF pair row %s.',sid);
    d=dir(fullfile(oldK1,'runs','DEV',sid,'P_CF','attempt_*','run_start.mat'));
    assert(isscalar(d),'OLDKAN:HistoricalStart','Expected one original run_start for %s.',sid);
    sourceStart=fullfile(d.folder,d.name);S=load(sourceStart,'scene','sceneMeta','cfg','opts');
    W0=double(S.opts.stage1_position_runtime.model.output_W);
    runId=char(java.util.UUID.randomUUID());
    meta=struct('run_id',runId,'phase','HISTORICAL_REPRODUCTION','scene_id',sid, ...
        'model_id','OLD_N_KAN_REPAIR','gamma',1,'readiness_events',32, ...
        'source_run_start_path',sourceStart,'source_repo_head','3671d2d212af927abdb6d9149a1b249c372ac55e', ...
        'plant_call_started',false,'status','PREPLANT_VALIDATION_PASS','created_utc',utc_now(), ...
        'attempt_dir',outDir);
    scene=S.scene;sceneMeta=S.sceneMeta;cfg=S.cfg;opts=S.opts;
    save(fullfile(outDir,'run_start.mat'),'meta','scene','sceneMeta','cfg','opts','-v7.3');
    write_json(statusPath,meta);
    before=count_plant_markers(expDir);assert(before<48,'OLDKAN:PlantLimit','48-call limit reached.');
    meta.plant_call_started=true;meta.status='PLANT_CALL_STARTING';meta.started_utc=utc_now();
    write_text(fullfile(outDir,'plant_started.marker'),meta.started_utc);
    write_json(statusPath,meta);set_task_state(expDir,'HISTORICAL_REPRODUCTION',sid,'PLANT_CALL_STARTING');
    ledger(expDir,meta,'PLANT_CALL_STARTED',NaN,0,0,'','','','');
    timer=tic;
    try
        log=run_position_stage1_closed_loop_pcf_v3_5(scene,'B2-RBF-Full-SPLIT',cfg,opts);
        elapsed=toc(timer);metrics=measure_pcf_v3_5(log,scene,W0);
        target=[double(P.P_CF_Q_0_5_m(rows)),double(P.P_CF_Q_5_20_m(rows)),double(P.P_CF_Q_0_20_m(rows))];
        observed=[double(metrics.Q_0_5_m),double(metrics.Q_5_20_m),double(metrics.Q_0_20_m)];
        complete=logical(metrics.complete)&&logical(metrics.finite)&&metrics.transitions==20000;
        pass=complete&&all(abs(observed-target)<=1e-6);
        meta.status=ternary(pass,'PASS','FAIL');meta.complete=complete;meta.finite=logical(metrics.finite);
        meta.transitions=metrics.transitions;meta.elapsed_s=elapsed;meta.Q_0_5_m=observed(1);
        meta.Q_5_20_m=observed(2);meta.Q_0_20_m=observed(3);meta.expected_Q=target;
        meta.Q_abs_diff=abs(observed-target);meta.B_Q_5_20_m=double(P.B_Q_5_20_m(rows));
        meta.completed_utc=utc_now();meta.raw_path=rawPath;
        save(rawPath,'meta','scene','sceneMeta','cfg','opts','log','metrics','-v7.3');
        meta.raw_sha256=sha256_file(rawPath);
        write_json(fullfile(outDir,'metrics.json'),metrics);write_json(statusPath,meta);
        ledger(expDir,meta,meta.status,elapsed,complete,metrics.transitions,rawPath,meta.raw_sha256,'','');
        state=read_json(fullfile(expDir,'state','state.json'));state=update_counts(expDir,state);
        write_state(expDir,state);
        fprintf('HISTORICAL %s %s Q0-5=%.6f Q5-20=%.6f Q0-20=%.6f target_diff_max=%.3g B_Q5-20=%.6f elapsed=%.1fs Plant=%d/48\n', ...
            sid,meta.status,observed(1),observed(2),observed(3),max(meta.Q_abs_diff),meta.B_Q_5_20_m,elapsed,count_plant_markers(expDir));
        if ~pass
            fprintf('HISTORICAL_REPRODUCTION_MISMATCH %s; identity is retained and current matrix will proceed.\n',sid);
        end
    catch ME
        elapsed=toc(timer);meta.status='RUNNER_ERROR';meta.elapsed_s=elapsed;meta.error_identifier=ME.identifier;
        meta.error_message=ME.message;meta.completed_utc=utc_now();write_json(statusPath,meta);
        save(fullfile(outDir,'failure.mat'),'ME','meta','scene','sceneMeta','cfg','opts');
        ledger(expDir,meta,'RUNNER_ERROR',elapsed,0,0,'','',ME.identifier,ME.message);
        state=read_json(fullfile(expDir,'state','state.json'));state=update_counts(expDir,state);write_state(expDir,state);
        rethrow(ME)
    end
end
write_historical_report(expDir,sceneIds);
state=read_json(fullfile(expDir,'state','state.json'));state.phase='MAIN_MATRIX';
state.status='RUNNING_MAIN_MATRIX';state.historical_completed=2;write_state(expDir,state);
end

function [metrics,runDir]=run_current_cell(~,expDir,cfg,scene,sceneMeta,spec,sid,methodId,modelId,model,gamma,base,phase,extra)
local=fullfile(expDir,'local_runtime');addpath(local,'-begin');rehash;
assert(startsWith(which('run_dl1018_closed_loop'),local,'IgnoreCase',true), ...
    'OLDKAN:PathIsolation','Task local Plant runner lost path priority.');
stage='main_matrix';if strcmp(phase,'ENVIRONMENT_BRIDGE'),stage='environment_bridge';end
runDir=fullfile(expDir,'runs',stage,sid,methodId,'attempt_01');
if ~isfolder(runDir),mkdir(runDir);end
rawPath=fullfile(runDir,'raw_run.mat');statusPath=fullfile(runDir,'run_status.json');
if isfile(statusPath)
    st=read_json(statusPath);
    if any(strcmp(char(string(st.status)),{'PASS','FAIL'}))&&isfile(rawPath)
        z=load(rawPath,'metrics');metrics=z.metrics;return
    end
    if isfile(fullfile(runDir,'plant_started.marker'))
        error('OLDKAN:NoRetry','Plant call started without terminal raw; refusing retry: %s %s.',sid,methodId);
    end
end
isBaseline=strcmp(methodId,'B');
if isBaseline,opts=controller_options_dl1018(cfg,'B');W0=zeros(33,3);
else
    opts=position_only_search_options(cfg,model,'FEATURE',gamma,1);
    p=opts.stage1_position_runtime;p.readiness_events=32;
    p.command_filter_coordination_v3_5=struct('enabled',true);
    p.position_only_search_head.state_reset_each_episode=true;
    p.position_only_search_head.encoder_frozen=true;opts.stage1_position_runtime=p;
    W0=double(model.output_W);
end
runId=char(java.util.UUID.randomUUID());
modelContext=0;if ~isBaseline,modelContext=double(field_or(model,'context_length',0));end
meta=struct('run_id',runId,'phase',phase,'scene_id',sid,'method_id',methodId, ...
    'model_id',modelId,'gamma',gamma,'readiness_events',ternary(isBaseline,0,32), ...
    'model_context_length',modelContext, ...
    'input_hash',scene_hash(scene),'plant_call_started',false,'status','PREPLANT_VALIDATION_PASS', ...
    'created_utc',utc_now(),'attempt_dir',runDir,'extra',extra);
if isfile(fullfile(runDir,'run_start.mat'))
    error('OLDKAN:AttemptExists','A preexisting run_start exists without a completed raw: %s.',runDir);
end
save(fullfile(runDir,'run_start.mat'),'meta','scene','sceneMeta','spec','cfg','opts','-v7.3');
write_json(statusPath,meta);
assert(count_plant_markers(expDir)<48,'OLDKAN:PlantLimit','48-call experiment budget reached.');
meta.plant_call_started=true;meta.status='PLANT_CALL_STARTING';meta.started_utc=utc_now();
write_text(fullfile(runDir,'plant_started.marker'),meta.started_utc);write_json(statusPath,meta);
set_task_state(expDir,phase,sid,methodId);ledger(expDir,meta,'PLANT_CALL_STARTED',NaN,0,0,'','','','');
state=read_json(fullfile(expDir,'state','state.json'));state=update_counts(expDir,state);write_state(expDir,state);
timer=tic;
try
    log=run_dl1018_closed_loop(scene,'B2-RBF-Full-SPLIT',cfg,opts);elapsed=toc(timer);
    core=measure_pcf_dl1018(log,scene,W0);
    BQ=NaN;BA=NaN;BPeak=NaN;Bcomplete=false;
    if ~isempty(base)
        BQ=base.core.Q_0_20_m;BA=base.core.attitude_RMSE_0_20_rad;BPeak=base.position_peak_m;
        Bcomplete=base.core.complete&&base.core.finite;
    end
    metrics=metrics_dl1018(log,scene,spec,core,BQ,BA,BPeak,Bcomplete);
    metrics.Q_0_5_m=core.Q_0_5_m;metrics.Q_5_20_m=core.Q_5_20_m;
    metrics.attitude_RMSE_0_20_rad=core.attitude_RMSE_0_20_rad;
    metrics.attitude_RMSE_5_20_rad=core.attitude_RMSE_5_20_rad;
    metrics.scheduled_events=core.scheduled_events;metrics.valid_inference_events=core.valid_inference_events;
    metrics.effective_update_dt_median_s=core.effective_update_dt_median_s;
    metrics.weight_reset_fro_error=core.weight_reset_fro_error;
    metrics.eta_abs_max_mps=core.eta_abs_max_mps;metrics.rf_abs_max_mps2=core.rf_abs_max_mps2;
    complete=logical(metrics.complete)&&logical(metrics.finite)&&metrics.transitions==20000;
    pass=complete&&strcmpi(char(string(log.status)),'STABLE');
    meta.status=ternary(pass,'PASS','FAIL');meta.complete=complete;meta.finite=logical(metrics.finite);
    meta.transitions=metrics.transitions;meta.elapsed_s=elapsed;meta.Q_0_20_m=metrics.Q_0_20_m;
    meta.Q_0_5_m=metrics.Q_0_5_m;meta.Q_5_20_m=metrics.Q_5_20_m;
    meta.B_Q_0_20_m=BQ;meta.position_rmse_m=metrics.Q_0_20_m;meta.attitude_rmse_rad=metrics.A_0_20_rad;
    meta.scheduled_events=double(field_or(metrics,'scheduled_events',0));
    meta.valid_inference_events=double(field_or(metrics,'valid_inference_events',0));
    meta.completed_utc=utc_now();meta.raw_path=rawPath;meta.safety_stop_reason=char(string(field_or(metrics,'safety_stop_reason','')));
    save(rawPath,'meta','scene','sceneMeta','spec','cfg','opts','log','core','metrics','-v7.3');
    meta.raw_sha256=sha256_file(rawPath);write_json(fullfile(runDir,'metrics.json'),metrics);write_json(statusPath,meta);
    ledger(expDir,meta,meta.status,elapsed,complete,metrics.transitions,rawPath,meta.raw_sha256,'','');
    state=read_json(fullfile(expDir,'state','state.json'));state=update_counts(expDir,state);
    state.elapsed_total_s=double(field_or(state,'elapsed_total_s',0))+elapsed;write_state(expDir,state);
    fprintf('RUN_DONE phase=%s scene=%s method=%s status=%s Q=%.6f m B=%.6f m A=%.6f rad events=%d/%d elapsed=%.1fs Plant=%d/48\n', ...
        phase,sid,methodId,meta.status,metrics.Q_0_20_m,BQ,metrics.A_0_20_rad, ...
        double(field_or(metrics,'valid_inference_events',0)),double(field_or(metrics,'scheduled_events',0)), ...
        elapsed,count_plant_markers(expDir));
catch ME
    elapsed=toc(timer);meta.status='RUNNER_ERROR';meta.elapsed_s=elapsed;meta.error_identifier=ME.identifier;
    meta.error_message=ME.message;meta.completed_utc=utc_now();write_json(statusPath,meta);
    save(fullfile(runDir,'failure.mat'),'ME','meta','scene','sceneMeta','spec','cfg','opts');
    ledger(expDir,meta,'RUNNER_ERROR',elapsed,0,0,'','',ME.identifier,ME.message);
    state=read_json(fullfile(expDir,'state','state.json'));state=update_counts(expDir,state);write_state(expDir,state);
    rethrow(ME)
end
end

function B=load_official_B(root,sid,scene,spec)
T=readtable(fullfile(root,'reports','POSITION_DEV.csv'),'TextType','string','VariableNamingRule','preserve');
ix=find(string(T.scene_id)==sid&string(T.method)=='B');assert(isscalar(ix),'OLDKAN:BRow','Missing B row: %s.',sid);
rawPath=fullfile(root,char(T.raw_path(ix)));R=load(rawPath,'scene','log');
assert(same_scene(scene,R.scene),'OLDKAN:BChanged','Official B input changed: %s.',sid);
core=measure_pcf_dl1018(R.log,R.scene,zeros(33,3));
peak=max(vecnorm(double(R.scene.reference.position(1:20000,:))-double(R.log.state(1:20000,1:3)),2,2));
assert(core.complete&&core.finite&&core.transitions==20000,'OLDKAN:BIncomplete','B raw incomplete: %s.',sid);
B=struct('core',core,'position_peak_m',peak,'raw_path',rawPath,'spec',spec,'scene',scene);
end

function write_historical_report(expDir,sceneIds)
rows=struct([]);
for i=1:numel(sceneIds)
    d=dir(fullfile(expDir,'runs','historical_repro',sceneIds{i},'attempt_01','raw_run.mat'));
    if isempty(d),continue,end
    X=load(fullfile(d.folder,d.name),'meta','metrics');m=X.meta;
    row=struct('scene_id',sceneIds{i},'status',m.status,'complete',m.complete, ...
        'finite',m.finite,'transitions',m.transitions,'Q_0_5_m',m.Q_0_5_m, ...
        'Q_5_20_m',m.Q_5_20_m,'Q_0_20_m',m.Q_0_20_m, ...
        'expected_Q_0_5_m',m.expected_Q(1),'expected_Q_5_20_m',m.expected_Q(2), ...
        'expected_Q_0_20_m',m.expected_Q(3),'max_abs_Q_difference_m',max(m.Q_abs_diff), ...
        'B_Q_5_20_m',m.B_Q_5_20_m,'elapsed_s',m.elapsed_s,'raw_path',relative_path(expDir,d.folder));
    if isempty(rows),rows=row;else,rows(end+1,1)=row;end %#ok<AGROW>
end
if ~isempty(rows),writetable(struct2table(rows),fullfile(expDir,'reports','HISTORICAL_REPRODUCTION.csv'));end
end

function write_transfer_runs(root,expDir,sceneIds,conditions)
rows=struct([]);T=readtable(fullfile(root,'reports','POSITION_DEV.csv'), ...
    'TextType','string','VariableNamingRule','preserve');
for si=1:numel(sceneIds)
    sid=sceneIds{si};bix=find(string(T.scene_id)==sid&string(T.method)=='B');
    Bq=double(T.Q_0_20_m(bix));braw=load(fullfile(root,char(T.raw_path(bix))),'scene','log');
    bcore=measure_pcf_dl1018(braw.log,braw.scene,zeros(33,3));
    assert(bcore.complete&&bcore.finite&&abs(bcore.Q_0_20_m-Bq)<=1e-6, ...
        'OLDKAN:BReport','B report/raw mismatch while writing paired table: %s.',sid);
    brow=struct('phase','MAIN_MATRIX','scene_id',sid,'method_id','B','model_id','B', ...
        'gamma',0,'readiness_events',0,'status','REUSED_STABLE','complete',true, ...
        'finite',true,'transitions',20000,'Q_0_20_m',Bq,'Q_0_5_m',bcore.Q_0_5_m,'Q_5_20_m',bcore.Q_5_20_m, ...
        'B_Q_0_20_m',Bq,'delta_Q_vs_B_m',0,'relative_Q_improvement_vs_B',0, ...
        'win_vs_B',false,'A_0_20_rad',double(T.A_0_20_rad(bix)), ...
        'position_axis_rmse_m','[]','attitude_axis_rmse_rad','[]', ...
        'position_peak_m',double(T.position_peak_m(bix)), ...
        'position_p95_m',double(T.position_p95_m(bix)), ...
        'motor_TV_normalized_per_s',double(T.motor_TV_normalized_per_s(bix)), ...
        'motor_saturation_fraction',double(T.motor_saturation_fraction(bix)), ...
        'generalized_clip_fraction',double(T.generalized_clip_fraction(bix)), ...
        'controller_p99_ms',double(T.controller_p99_ms(bix)), ...
        'scheduled_events',1999,'valid_inference_events',0,'raw_path',char(T.raw_path(bix)), ...
        'phase_metrics_json',char(T.phase_metrics_json(bix)));
    rows=append_struct(rows,brow);
    for ci=1:numel(conditions)
        method=conditions{ci};rawPath=fullfile(expDir,'runs','main_matrix',sid,method,'attempt_01','raw_run.mat');
        if ~isfile(rawPath),continue,end
        Z=load(rawPath,'meta','metrics');m=Z.metrics;meta=Z.meta;
        row=struct('phase','MAIN_MATRIX','scene_id',sid,'method_id',method, ...
            'model_id',meta.model_id,'gamma',meta.gamma,'readiness_events',meta.readiness_events, ...
            'status',meta.status,'complete',meta.complete,'finite',meta.finite, ...
            'transitions',meta.transitions,'Q_0_20_m',m.Q_0_20_m,'Q_0_5_m',m.Q_0_5_m, ...
            'Q_5_20_m',m.Q_5_20_m,'B_Q_0_20_m',Bq,'delta_Q_vs_B_m',m.Q_0_20_m-Bq, ...
            'relative_Q_improvement_vs_B',(Bq-m.Q_0_20_m)/Bq, ...
            'win_vs_B',logical(m.Q_0_20_m<Bq),'A_0_20_rad',m.A_0_20_rad, ...
            'position_axis_rmse_m',jsonencode(m.position_axis_rmse_m), ...
            'attitude_axis_rmse_rad',jsonencode(m.attitude_axis_rmse_rad), ...
            'position_peak_m',m.position_peak_m,'position_p95_m',m.position_p95_m, ...
            'motor_TV_normalized_per_s',m.motor_TV_normalized_per_s, ...
            'motor_saturation_fraction',m.motor_saturation_fraction, ...
            'generalized_clip_fraction',m.generalized_clip_fraction, ...
            'controller_p99_ms',m.controller_p99_ms,'scheduled_events',meta.scheduled_events, ...
            'valid_inference_events',meta.valid_inference_events, ...
            'raw_path',relative_path(root,rawPath),'phase_metrics_json',m.phase_metrics_json);
        rows=append_struct(rows,row);
    end
end
if ~isempty(rows),writetable(struct2table(rows),fullfile(expDir,'reports','TRANSFER_ALL_RUNS.csv'));end
end

function [required,gate]=bridge_gate(expDir,sceneIds)
methods={'OLD_G1_R32','OLD_G12_R32'};rows=struct([]);required=true;
for mi=1:numel(methods)
    qs=nan(numel(sceneIds),1);bq=qs;valid=false(size(qs));wins=false(size(qs));
    for i=1:numel(sceneIds)
        path=fullfile(expDir,'runs','main_matrix',sceneIds{i},methods{mi},'attempt_01','raw_run.mat');
        if ~isfile(path),continue,end
        Z=load(path,'meta','metrics');qs(i)=Z.metrics.Q_0_20_m;bq(i)=Z.meta.B_Q_0_20_m;
        valid(i)=logical(Z.meta.complete)&&logical(Z.meta.finite)&&Z.meta.transitions==20000;
        wins(i)=qs(i)<bq(i);
    end
    allValid=all(valid);macroB=mean(bq,'omitnan');macroQ=mean(qs,'omitnan');improvement=(macroB-macroQ)/macroB;
    ok=allValid&&improvement>=.10&&nnz(wins)>=6;required=required&&~ok;
    row=struct('method_id',methods{mi},'valid_scenes',nnz(valid),'expected_scenes',8, ...
        'macro_B_Q_0_20_m',macroB,'macro_Q_0_20_m',macroQ, ...
        'macro_improvement_vs_B',improvement,'wins_vs_B',nnz(wins), ...
        'required_all_8_valid',allValid,'meets_recovery_threshold',ok);
    rows=append_struct(rows,row);
end
gate=struct('status',ternary(required,'BRIDGE_REQUIRED','SKIPPED_OLD_PACKAGE_RECOVERED'), ...
    'trigger_rule','If neither old Gamma has 8/8 complete, >=10% macro improvement, and >=6/8 strict B wins, run the bridge.', ...
    'configurations',rows,'bridge_required',required,'created_utc',utc_now());
end

function run_environment_bridge(root,expDir,cfg,oldModel)
parent='DL1018_DEV_T2_C09_W10';G=make_scenes_dl1018('GET',root,parent);
baseScene=G.scene;spec=G.spec;local=fullfile(expDir,'local_runtime');addpath(local,'-begin');rehash;
officialB=load_official_B(root,parent,baseScene,spec);
oldPath=fullfile(expDir,'runs','main_matrix',parent,'OLD_G1_R32','attempt_01','raw_run.mat');
assert(isfile(oldPath),'OLDKAN:BridgeReuse','C09 OLD_G1 must exist from main matrix.');
oldCurrent=load(oldPath,'metrics');
refs={'REF_CURRENT','REF_CURRENT','REF_CURRENT','REF_LEGACY','REF_LEGACY','REF_LEGACY'};
winds={'WIND_CURRENT','WIND_LOW','WIND_ZERO','WIND_CURRENT','WIND_LOW','WIND_ZERO'};
rows=struct([]);manifest=struct([]);
for i=1:numel(refs)
    refId=refs{i};windId=winds{i};cellId=[refId '__' windId];scene=baseScene;
    if strcmp(refId,'REF_LEGACY'),scene.reference=legacy_reference(double(scene.time(:)));end
    if strcmp(windId,'WIND_LOW'),scene.environment_wind_I=wind_for_spec(scene.time,spec,.5,.8);
    elseif strcmp(windId,'WIND_ZERO'),scene.environment_wind_I=zeros(size(scene.environment_wind_I));end
    sid=[parent '__' cellId];scene.scene_id=string(sid);changed={};
    if strcmp(refId,'REF_LEGACY'),changed{end+1}='reference.position/velocity/acceleration/yaw';end %#ok<AGROW>
    if ~strcmp(windId,'WIND_CURRENT'),changed{end+1}='environment_wind_I';end %#ok<AGROW>
    assert(isequaln(scene.time,baseScene.time)&&isequaln(scene.initial_state,baseScene.initial_state)&& ...
        isequaln(scene.arms,baseScene.arms),'OLDKAN:BridgeMutation','Bridge changed non-whitelisted inputs.');
    sceneDir=fullfile(expDir,'runs','environment_bridge','scenes',cellId);if ~isfolder(sceneDir),mkdir(sceneDir);end
    sceneMeta=struct('parent_scene_id',parent,'bridge_cell_id',cellId,'reference_id',refId, ...
        'wind_id',windId,'changed_fields',{changed},'created_utc',utc_now());
    sh=scene_hash(scene);rh=scene_hash_reference(scene.reference);wh=sha256_numeric(scene.environment_wind_I);
    save(fullfile(sceneDir,'bridge_scene.mat'),'scene','sceneMeta','spec','-v7.3');
    mrow=struct('bridge_cell_id',cellId,'parent_scene_id',parent,'reference_id',refId, ...
        'wind_id',windId,'changed_fields',strjoin(changed,';'),'scene_sha256',sh, ...
        'reference_sha256',rh,'wind_sha256',wh,'plant_calls_added',0);
    manifest=append_struct(manifest,mrow);
    if strcmp(refId,'REF_CURRENT')&&strcmp(windId,'WIND_CURRENT')
        B=officialB;oldM=oldCurrent.metrics;bcalls=0;runB=officialB.raw_path;runOld=oldPath;
    else
        [~,bDir]=run_current_cell(root,expDir,cfg,scene,sceneMeta,spec,sid,'B','B',[],0,[], ...
            'ENVIRONMENT_BRIDGE',struct('parent_scene_id',parent,'reference_id',refId,'wind_id',windId));
        runB=fullfile(bDir,'raw_run.mat');
        Braw=load(runB,'core','metrics');
        B=struct('core',Braw.core,'position_peak_m',Braw.metrics.position_peak_m,'raw_path',runB);
        [oldM,oDir]=run_current_cell(root,expDir,cfg,scene,sceneMeta,spec,sid,'OLD_G1_R32', ...
            'OLD_N_KAN_REPAIR',oldModel,1,B,'ENVIRONMENT_BRIDGE', ...
            struct('parent_scene_id',parent,'reference_id',refId,'wind_id',windId));
        runOld=fullfile(oDir,'raw_run.mat');
        bcalls=2;
    end
    bq=B.core.Q_0_20_m;oq=oldM.Q_0_20_m;
    row=struct('bridge_cell_id',cellId,'parent_scene_id',parent,'reference_id',refId, ...
        'wind_id',windId,'B_status',char(string(B.core.status)), ...
        'B_complete',logical(B.core.complete)&&logical(B.core.finite),'B_Q_0_20_m',bq, ...
        'OLD_G1_status',char(string(oldM.status)), ...
        'OLD_G1_complete',logical(oldM.complete)&&logical(oldM.finite), ...
        'OLD_G1_Q_0_20_m',oq,'delta_Q_old_minus_B_m',oq-bq, ...
        'relative_improvement_vs_B',(bq-oq)/bq,'strict_win_vs_B',oq<bq, ...
        'B_raw_path',relative_path(root,runB),'OLD_G1_raw_path',relative_path(root,runOld), ...
        'new_plant_calls',bcalls,'scene_sha256',sh);
    rows=append_struct(rows,row);mrow.plant_calls_added=bcalls;manifest(end)=mrow;
    writetable(struct2table(manifest),fullfile(expDir,'reports','BRIDGE_SCENE_MANIFEST.csv'));
    writetable(struct2table(rows),fullfile(expDir,'reports','ENVIRONMENT_BRIDGE.csv'));
    state=read_json(fullfile(expDir,'state','state.json'));state.phase='ENVIRONMENT_BRIDGE';
    state.status='RUNNING_ENVIRONMENT_BRIDGE';state.bridge_completed=i;state.bridge_total=6;
    state.updated_local=local_now();write_state(expDir,state);
    fprintf('BRIDGE_PROGRESS %d/6 cell=%s B_Q=%.6f OLD_G1_Q=%.6f improve=%.2f%% added_Plant=%d total=%d/48\n', ...
        i,cellId,bq,oq,100*(bq-oq)/bq,bcalls,count_plant_markers(expDir));
end
state=read_json(fullfile(expDir,'state','state.json'));state.bridge_status='COMPLETE';write_state(expDir,state);
write_json(fullfile(expDir,'reports','ENVIRONMENT_BRIDGE.json'), ...
    struct('status','COMPLETE','parent_scene_id',parent,'cells',6,'new_plant_calls',10, ...
    'calls_reused',struct('B_current',officialB.raw_path,'OLD_G1_current',oldPath), ...
    'reference_frequency_hz_current',[double(spec.f1_hz),double(spec.f2_hz)], ...
    'low_wind_frequency_hz',[.5,.8],'zero_wind_keeps_aerodynamics',true));
end

function ref=legacy_reference(t)
t=double(t(:));s=t/20;u=3*s.^2-2*s.^3;ud=(6*s-6*s.^2)/20;udd=(6-12*s)/400;
th=2*pi*u;thd=2*pi*ud;thdd=2*pi*udd;
p=[1.5*sin(th),sin(2*th),.5*(1-cos(th))];
v=[1.5*cos(th).*thd,2*cos(2*th).*thd,.5*sin(th).*thd];
a=[1.5*(-sin(th).*thd.^2+cos(th).*thdd), ...
    -4*sin(2*th).*thd.^2+2*cos(2*th).*thdd, ...
    .5*(cos(th).*thd.^2+sin(th).*thdd)];
ref=struct('position',p,'velocity',v,'acceleration',a,'yaw',zeros(size(t)), ...
    'yaw_rate',zeros(size(t)),'yaw_acceleration',zeros(size(t)));
end

function wind=wind_for_spec(t,spec,f1,f2)
az=deg2rad(double(spec.azimuth_deg));el=deg2rad(double(spec.elevation_deg));
wc=struct('type','biased_dual_sine','direction',[cos(el)*cos(az);cos(el)*sin(az);sin(el)], ...
    'V0',9,'A1',double(spec.A1_mps),'f1',f1,'phi1',double(spec.phase1_rad), ...
    'A2',double(spec.A2_mps),'f2',f2,'phi2',double(spec.phase2_rad), ...
    'rise_time_s',.8,'rho_air',1.225,'CdBody',1,'CdArm',1);
[w,~]=wind_velocity_profile(double(t(:)),wc);wind=w.';
end

function model=load_old_adapter_model()
p='C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1009\RBF-BS0\experiments\kan_position_attitude_followup_v2\models\repair\N_KAN\matlab_model_and_parity.mat';
S=load(p,'model');model=S.model;model.input_dim=14;model.window=32;model.context_length=1;
end
function model=load_new_adapter_model(root)
p=fullfile(root,'experiments','kan14_task_specialist_compare_v1','models','shared', ...
    'KAN14','seed2026102001','final_step','matlab_model_and_parity.mat');
S=load(p,'model');model=S.model;model.input_dim=14;model.window=32;model.context_length=1;
end
function set_task_state(expDir,phase,sid,method)
path=fullfile(expDir,'state','state.json');s=read_json(path);s.phase=phase;
s.status=['RUNNING_' upper(phase)];s.current_scene_id=sid;s.current_method_id=method;
s=update_counts(expDir,s);write_state(expDir,s);
end
function n=count_plant_markers(expDir)
d=dir(fullfile(expDir,'runs','**','plant_started.marker'));n=sum(~[d.isdir]);
end
function n=count_terminal_cells(expDir,stage)
files=dir(fullfile(expDir,'runs',stage,'**','run_status.json'));n=0;
for i=1:numel(files)
    s=read_json(fullfile(files(i).folder,files(i).name));
    if any(strcmp(char(string(s.status)),{'PASS','FAIL','RUNNER_ERROR'})),n=n+1;end
end
end
function s=update_counts(expDir,s)
s.plant_calls_started=count_plant_markers(expDir);L=read_ledger(fullfile(expDir,'reports','RESOURCE_LEDGER.csv'));
if height(L)==0,s.plant_calls_completed=0;else
    s.plant_calls_completed=nnz(ismember(string(L.status),["PASS","FAIL","RUNNER_ERROR"]));
end
s.updated_local=local_now();
end
function avg=mean_call_s(expDir)
L=read_ledger(fullfile(expDir,'reports','RESOURCE_LEDGER.csv'));avg=NaN;
if height(L)==0,return,end
x=str2double(string(L.elapsed_s));x=x(isfinite(x)&x>=0);
if ~isempty(x),avg=mean(x);else,avg=20;end
end
function ledger(expDir,meta,status,elapsed,complete,transitions,rawPath,rawSha,errId,errMsg)
path=fullfile(expDir,'reports','RESOURCE_LEDGER.csv');
names={'run_id','phase','scene_id','method_id','model_id','gamma','readiness_events', ...
    'plant_call_started','status','complete','finite','transitions','elapsed_s','raw_path', ...
    'raw_sha256','error_identifier','error_message'};
values={field_or(meta,'run_id',''),field_or(meta,'phase',''),field_or(meta,'scene_id',''), ...
    field_or(meta,'method_id','P_CF'),field_or(meta,'model_id','OLD_N_KAN_REPAIR'), ...
    field_or(meta,'gamma',NaN),field_or(meta,'readiness_events',32), ...
    field_or(meta,'plant_call_started',true),status,complete,field_or(meta,'finite',false), ...
    transitions,elapsed,rawPath,rawSha,errId,errMsg};
vals=cellfun(@as_string,values,'UniformOutput',false);row=array2table(string(vals),'VariableNames',names);
L=read_ledger(path);idx=[];if height(L)>0,idx=find(L.run_id==row.run_id(1),1);end
if isempty(idx)
    if height(L)==0,writetable(row,path);else,writetable(row,path,'WriteMode','append','WriteVariableNames',false);end
else
    for k=1:numel(names),L.(names{k})(idx)=row.(names{k})(1);end
    writetable(L,path);
end
end
function L=read_ledger(path)
if ~isfile(path),L=table;return,end
io=detectImportOptions(path,'Delimiter',',','VariableNamingRule','preserve');
io=setvartype(io,io.VariableNames,'string');L=readtable(path,io);
end
function s=as_string(x)
if isstring(x)
    s=char(x);
elseif ischar(x)
    s=x;
elseif islogical(x)
    s=char(string(x));
elseif isnumeric(x)&&isscalar(x)
    if isnan(x),s='NaN';else,s=sprintf('%.15g',double(x));end
else
    s=char(string(x));
end
end
function state=read_json(path)
state=jsondecode(fileread(path));
end
function write_state(expDir,state)
write_json(fullfile(expDir,'state','state.json'),state);
end
function write_json(path,value)
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
tmp=[path '.tmp'];fid=fopen(tmp,'w');assert(fid>=0,'OLDKAN:JsonWrite','Cannot write %s.',tmp);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');fwrite(fid,newline,'char');
clear cleanup;movefile(tmp,path,'f');
end
function write_text(path,value)
fid=fopen(path,'w');assert(fid>=0,'OLDKAN:TextWrite','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,value,'char');fwrite(fid,newline,'char');clear cleanup;
end
function rows=append_struct(rows,row)
if isempty(rows),rows=row;else,rows(end+1,1)=row;end
end
function v=field_or(s,name,default)
if isstruct(s)&&isfield(s,name),v=s.(name);else,v=default;end
end
function out=ternary(cond,a,b)
if cond,out=a;else,out=b;end
end
function path=relative_path(root,file)
rp=char(java.io.File(root).getCanonicalPath());fp=char(java.io.File(file).getCanonicalPath());
if startsWith(fp,[rp filesep],'IgnoreCase',true),path=fp(numel(rp)+2:end);else,path=fp;end
end
function h=scene_hash(s)
md=java.security.MessageDigest.getInstance('SHA-256');
hash_update(md,'scene_id',uint8(unicode2native(char(string(s.scene_id)),'UTF-8')));
numeric={'time','initial_state','reference.position','reference.velocity','reference.acceleration', ...
    'reference.yaw','reference.yaw_rate','reference.yaw_acceleration','arms.command', ...
    'arms.rho_true','arms.rhoDot_true','environment_wind_I'};
for i=1:numel(numeric)
    v=s;parts=split(string(numeric{i}),'.');
    for j=1:numel(parts),v=v.(char(parts(j)));end
    hash_update(md,numeric{i},typecast(double(v(:)),'uint8'));
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8')).',1,[]));
end
function h=scene_hash_reference(ref)
md=java.security.MessageDigest.getInstance('SHA-256');names={'position','velocity','acceleration','yaw','yaw_rate','yaw_acceleration'};
for i=1:numel(names),hash_update(md,names{i},typecast(double(ref.(names{i})(:)),'uint8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8')).',1,[]));
end
function h=sha256_numeric(x)
md=java.security.MessageDigest.getInstance('SHA-256');hash_update(md,'array',typecast(double(x(:)),'uint8'));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8')).',1,[]));
end
function hash_update(md,label,bytes)
md.update(uint8(unicode2native([label ':' sprintf('%d,',size(bytes)) '|'],'UTF-8')));md.update(uint8(bytes(:)));
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'OLDKAN:HashOpen','Cannot open %s.',path);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');while true,b=fread(fid,1024*1024,'*uint8');if isempty(b),break,end;md.update(b);end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8')).',1,[]));clear cleanup
end
function same=same_scene(a,b)
same=strcmp(char(string(a.scene_id)),char(string(b.scene_id)))&&isequaln(a.time,b.time)&& ...
    isequaln(a.initial_state,b.initial_state)&&isequaln(a.reference.position,b.reference.position)&& ...
    isequaln(a.reference.velocity,b.reference.velocity)&&isequaln(a.reference.acceleration,b.reference.acceleration)&& ...
    isequaln(a.reference.yaw,b.reference.yaw)&&isequaln(a.reference.yaw_rate,b.reference.yaw_rate)&& ...
    isequaln(a.reference.yaw_acceleration,b.reference.yaw_acceleration)&&isequaln(a.arms,b.arms)&& ...
    isequaln(a.environment_wind_I,b.environment_wind_I);
end
function t=utc_now()
t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end
function t=local_now()
t=char(datetime('now','TimeZone','local','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
end
