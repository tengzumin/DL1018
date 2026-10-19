function report=run_position_only_closed_loop_search(root)
% Resumable FEATURE/BIAS position-only search followed by locked 24-scene DEV.
if nargin<1||isempty(root),root=pwd;end
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','position_only_closed_loop_search_v1');
local=fullfile(out,'local_runtime');addpath(genpath(fullfile(root,'matlab')));addpath(genpath(local),'-begin');rehash;
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'POSSEARCH:Root','Unexpected project root.');
addpath(genpath(local),'-begin');rehash;
prePath=fullfile(out,'reports','PREFLIGHT_ZERO_PLANT.json');
if isfile(prePath),pre=jsondecode(fileread(prePath));else,pre=position_only_search_preflight(root);end
assert(strcmp(pre.status,'PASS')&&pre.plant_starts==0,'POSSEARCH:Preflight','Zero-Plant preflight must pass.');
q=load(fullfile(root,'models','position','selected','matlab_model_and_parity.mat'),'model');model=q.model;
selection=jsondecode(fileread(fullfile(root,'configs','selected_models.json')));model.model_id=char(selection.position_selected.selected_model_id);
specs=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
bridge=readtable(fullfile(root,'experiments','position_causal_repair_v1','manifests','BRIDGE6.csv'),'TextType','string');
bridgePair=readtable(fullfile(root,'experiments','position_causal_repair_v1','reports','D1_G04_PAIRED_ALL.csv'),'TextType','string');
ids=unique(bridge.scene_id,'stable');dev=readtable(fullfile(root,'reports','POSITION_DEV.csv'),'TextType','string');devB=dev(dev.method=="B",:);
finalBridge=readtable(fullfile(root,'experiments','position_causal_repair_v1','reports','D3_INITIAL_FINAL_BRIDGE.csv'),'TextType','string');
assert(numel(ids)==6&&height(devB)==24,'POSSEARCH:Inputs','BRIDGE6 or DEV B baseline is incomplete.');
statePath=fullfile(out,'state','state.json');state=load_state(statePath);
if isempty(state.started_at_utc)||count_plants(out)==0,state.started_at_utc=utc_now();end
state.phase='POSITION_ONLY_SEARCH';state.status='IN_PROGRESS';state.selected_model_id=char(model.model_id);state.plant_budget_max=78;
state.expected_new_plant_starts=72;state.preflight_status='PASS';state.updated_at_utc=utc_now();write_json(statePath,state);
taskStart=datetime(state.started_at_utc,'InputFormat','yyyy-MM-dd''T''HH:mm:ss.SSSXXX', ...
    'TimeZone','UTC','Locale','en_US');
ledger=fullfile(out,'RESOURCE_LEDGER.csv');if ~isfile(ledger),write_text(ledger,['timestamp_utc,phase,resource_type,identity,count,status,notes' newline]);end
append_ledger(out,'PREFLIGHT','Plant','zero-plant-preflight',0,'PASS','Final replay and controller checks; zero Plant transitions.');
append_ledger(out,'MODEL_REUSE','encoder_fit','DL1018_POSITION_SELECTED',0,'READ_ONLY','Original Final encoder/normalizer reused; no fit.');
featureGrid=[1 .5;1 1;4 .5;4 1;12 .5;12 1];
searchRows=struct([]);scores=struct([]);featureScores=struct([]);biasScores=struct([]);
for gi=1:size(featureGrid,1)
    gamma=featureGrid(gi,1);kappa=featureGrid(gi,2);reuse=gamma==1&&kappa==1;
    group=sprintf('FEATURE_G%g_K%g',gamma,kappa);
    [r,s]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,taskStart,72,group,'FEATURE',gamma,kappa,reuse);
    searchRows=append_rows(searchRows,r);scores=append_score(scores,s);featureScores=append_score(featureScores,s);
    persist_rows(searchRows,fullfile(out,'reports','SEARCH_ALL_RUNS.csv'));write_json(fullfile(out,'reports','SEARCH_GROUP_SCORES.json'),struct('groups',scores));
    update_state(out,group,'FEATURE',count_plants(out),numel(searchRows),s);
end
bestFeature=choose_best(featureScores);biasKappa=.5;if ~isempty(bestFeature),biasKappa=bestFeature.kappa;end
biasGrid=[4 biasKappa;12 biasKappa];
for gi=1:size(biasGrid,1)
    gamma=biasGrid(gi,1);kappa=biasGrid(gi,2);group=sprintf('BIAS_G%g_K%g',gamma,kappa);
    [r,s]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,taskStart,72,group,'BIAS',gamma,kappa,false);
    searchRows=append_rows(searchRows,r);scores=append_score(scores,s);biasScores=append_score(biasScores,s);
    persist_rows(searchRows,fullfile(out,'reports','SEARCH_ALL_RUNS.csv'));write_json(fullfile(out,'reports','SEARCH_GROUP_SCORES.json'),struct('groups',scores));
    update_state(out,group,'BIAS',count_plants(out),numel(searchRows),s);
end
bestSix=choose_best(append_score(featureScores,biasScores));
if isempty(bestSix)
    report=struct('status','NO_COMPLETE_SIX_SCENE_CANDIDATE','plant_starts',count_plants(out),'dev_runs_started',0, ...
        'reason','No complete stable six-scene FEATURE or BIAS group.');
    write_json(fullfile(out,'reports','FINAL_RESULT.json'),report);update_state(out,'DONE',report.status,count_plants(out),numel(searchRows),[]);
    write_text(fullfile(out,'reports','FINAL_REPORT_ZH.md'),['# 位置闭环搜索结果' newline newline ...
        '特征头和偏置头都未形成完整稳定六场候选，因此无法锁定候选，也没有启动24场DEV。详见 SEARCH_ALL_RUNS.csv 和 SEARCH_GROUP_SCORES.json。']);
    return
end
% Required kappa=0 ablation of the best complete six-scene Head.
ablationHead=bestSix.head_type;ablationGamma=bestSix.gamma;ablation=sprintf('%s_G%g_K0_ABLATION',ablationHead,ablationGamma);
[r,s]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,taskStart,72,ablation,ablationHead,ablationGamma,0,false);
searchRows=append_rows(searchRows,r);scores=append_score(scores,s);persist_rows(searchRows,fullfile(out,'reports','SEARCH_ALL_RUNS.csv'));
write_json(fullfile(out,'reports','SEARCH_GROUP_SCORES.json'),struct('groups',scores));update_state(out,ablation,'KAPPA_ZERO_ABLATION',count_plants(out),numel(searchRows),s);
bestSix=choose_best(append_score(append_score(featureScores,biasScores),s));
if isempty(bestSix)
    report=struct('status','NO_COMPLETE_SIX_SCENE_CANDIDATE','plant_starts',count_plants(out),'dev_runs_started',0, ...
        'reason','No complete stable six-scene candidate after the zero-initialization ablation.');
    write_json(fullfile(out,'reports','FINAL_RESULT.json'),report);update_state(out,'DONE',report.status,count_plants(out),numel(searchRows),[]);return
end
candidate=make_candidate(bestSix,model,cfg);
save(fullfile(out,'models','position_only_candidate_package.mat'),'model','candidate','-v7.3');
copyfile(fullfile(root,'models','position','selected','normalizer.npz'),fullfile(out,'models','original_final_normalizer.npz'),'f');
manifest=struct('candidate',candidate,'mat_file','models/position_only_candidate_package.mat', ...
    'normalizer_file','models/original_final_normalizer.npz','runtime_helper','local_runtime/position_only_search_head_step.m', ...
    'runtime_entry','local_runtime/run_position_only_closed_loop_search.m', ...
    'reproduction_command','matlab -batch "addpath(genpath(pwd)); run_position_only_closed_loop_search(pwd)"');
write_json(fullfile(out,'models','candidate_manifest.json'),manifest);write_json(fullfile(out,'state','LOCKED_CANDIDATE.json'),candidate);
append_ledger(out,'LOCK_CANDIDATE','candidate',candidate.candidate_id,0,'LOCKED', ...
    sprintf('Locked before 24-scene DEV: %s gamma=%g kappa=%g.',candidate.head_type,candidate.gamma,candidate.kappa));
devScenes=specs(specs.split=="DEV",:);assert(height(devScenes)==24,'POSSEARCH:DevScenes','Expected 24 fixed DEV scenes.');
devRows=struct([]);for first=1:6:24
    chunk=struct([]);
    for si=first:min(first+5,24)
        spec=devScenes(si,:);sceneId=char(spec.scene_id);b=baseline_row('LOCKED_DEV',sceneId,bridge,bridgePair,finalBridge,devB);
        row=run_one(root,out,cfg,model,spec,'LOCKED_DEV','LOCKED_DEV',candidate.head_type,candidate.gamma,candidate.kappa,b,taskStart,72);
        chunk=append_rows(chunk,row);devRows=append_rows(devRows,row);persist_rows(devRows,fullfile(out,'reports','DEV_PAIRED_24.csv'));
        if ~row.complete||~row.finite||~strcmp(row.status,'STABLE'),break;end
    end
    emit_dev_chunk(out,chunk,devRows,candidate.head_type,candidate.gamma,candidate.kappa,count_plants(out),72,taskStart);
    if numel(chunk)<6||~all([chunk.complete])||~all([chunk.finite])||any(~strcmp({chunk.status},'STABLE')),break;end
end
persist_rows(devRows,fullfile(out,'reports','DEV_PAIRED_24.csv'));
complete24=numel(devRows)==24&&all([devRows.complete])&&all([devRows.finite])&&all(strcmp({devRows.status},'STABLE'))&& ...
    all(arrayfun(@(x)isempty(x.safety_stop_reason)||strcmpi(x.safety_stop_reason,'none'),devRows));
macroQ=NaN;macroB=mean([devRows.B_Q_0_20_m]);if complete24,macroQ=mean([devRows.Q_0_20_m]);end
pass=complete24&&isfinite(macroQ)&&macroQ<macroB;
report=struct('status',iff(pass,'PASS_POSITION_DEV_BEATS_B',iff(complete24,'COMPLETE_NOT_BEATS_B','INCOMPLETE_OR_PHYSICAL_FAILURE')), ...
    'selected_candidate',candidate,'completed_dev_rows',numel(devRows),'required_dev_rows',24, ...
    'complete_finite_no_physical_hard_stop',complete24,'macro_Q_0_20_m',macroQ,'same_scene_B_macro_Q_0_20_m',macroB, ...
    'candidate_minus_B_m',macroQ-macroB,'relative_change_vs_B',(macroQ-macroB)/macroB, ...
    'candidate_beats_B_by_position_only',pass,'cumulative_new_plant_starts',count_plants(out),'plant_budget_max',78, ...
    'encoder_fits',0,'original_G06_unchanged',true,'selection_metric','position Q only');
write_json(fullfile(out,'reports','FINAL_RESULT.json'),report);write_final_report(out,report,devRows,scores,model);
update_state_done(out,report.status,count_plants(out),candidate);
fprintf('POSITION_SEARCH_FINAL %s: %s gamma=%g kappa=%g DEV=%d/24 Q=%.10g B=%.10g starts=%d.\n', ...
    report.status,candidate.head_type,candidate.gamma,candidate.kappa,numel(devRows),macroQ,macroB,count_plants(out));
end

function [rows,score]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,taskStart,planned,group,headType,gamma,kappa,reuseFinal)
rows=struct([]);stop=false;dirGroup=fullfile(out,'runs',group);if ~isfolder(dirGroup),mkdir(dirGroup);end
if reuseFinal,assert(strcmp(headType,'FEATURE')&&gamma==1&&kappa==1,'POSSEARCH:Reuse','Invalid Final reuse.');end
for i=1:6
    if stop,break;end
    sceneId=char(ids(i));sceneDir=fullfile(dirGroup,sceneId);if ~isfolder(sceneDir),mkdir(sceneDir);end
    mp=fullfile(sceneDir,'metrics.json');
    if isfile(mp)
        saved=jsondecode(fileread(mp));row=saved.metrics_row;
        if ~logical(saved.source_reused),assert(isfile(fullfile(sceneDir,'raw_run.mat')),'POSSEARCH:MissingRaw','Missing raw log %s.',sceneId);end
    elseif reuseFinal
        f=finalBridge(finalBridge.scene_id==sceneId,:);spec=specs(specs.scene_id==sceneId,:);
        assert(height(f)==1&&height(spec)==1,'POSSEARCH:FinalRow','Missing original Final row.');
        b=baseline_row(group,sceneId,bridge,bridgePair,finalBridge,devB);
        row=make_reused_final_row(f,spec,model,b);write_json(mp,struct('metrics_row',row,'source_reused',true));
    else
        spec=specs(specs.scene_id==sceneId,:);b=baseline_row(group,sceneId,bridge,bridgePair,finalBridge,devB);
        row=run_one(root,out,cfg,model,spec,group,group,headType,gamma,kappa,b,taskStart,planned);
    end
    rows=append_rows(rows,row);if ~row.complete||~row.finite||~strcmp(row.status,'STABLE'),stop=true;end
end
score=score_six(rows,group,headType,gamma,kappa);emit_group(out,rows,score,planned,taskStart);
end

function row=run_one(root,out,cfg,model,spec,phase,group,headType,gamma,kappa,b,taskStart,planned)
sceneId=char(spec.scene_id);sceneDir=fullfile(out,'runs',group,sceneId);if ~isfolder(sceneDir),mkdir(sceneDir);end
raw=fullfile(sceneDir,'raw_run.mat');start=fullfile(sceneDir,'run_start.mat');marker=fullfile(sceneDir,'plant_started.marker');mp=fullfile(sceneDir,'metrics.json');
if isfile(mp)
    saved=jsondecode(fileread(mp));row=saved.metrics_row;assert(isfile(raw),'POSSEARCH:MissingRaw','Metrics without raw evidence.');return
end
if isfile(marker)&&~isfile(raw),error('POSSEARCH:InterruptedPlant','Plant marker exists without raw log at %s; do not rerun.',sceneId);end
if isfile(fullfile(sceneDir,'error.json'))&&~isfile(raw),error('POSSEARCH:PriorError','Inspect prior error at %s.',sceneDir);end
if isfile(raw)
    q=load(raw,'log','scene');log=q.log;scene=q.scene;assert(isfile(start),'POSSEARCH:MissingStart','Raw without run_start.');
    z=load(start,'runStart');rs=z.runStart;plantStarted=isfile(marker);
else
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    addpath(genpath(fullfile(out,'local_runtime')),'-begin');rehash;
    opts=feval('position_only_search_options',cfg,model,headType,gamma,kappa);
    rs=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',sprintf('POSONLY_%s_%s_G%g_K%g',phase,sceneId,gamma,kappa), ...
        'gate_id',group,'phase',phase,'split',char(spec.split),'collector_id','POSITION_ONLY_SEARCH', ...
        'model_id',char(model.model_id),'head_type',headType,'gamma',gamma,'kappa',kappa,'encoder_frozen',true, ...
        'candidate_fit_status','NO_FIT','scene_spec',spec,'cfg',cfg,'opts',opts,'initial_state',scene.initial_state, ...
        'reused_B_run_id',char(b.run_id),'started_at_utc',utc_now());
    runStart=rs;save(start,'runStart','-v7');state=load_state(fullfile(out,'state','state.json'));
    state.active_group=group;state.active_scene=sceneId;state.active_run_id=rs.run_id;state.head_type=headType;
    state.gamma=gamma;state.kappa=kappa;state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();
    write_json(fullfile(out,'state','state.json'),state);opts.r2e_first_plant_step_marker=marker;
    try
        episode=@run_episode_dl1018;log=episode(scene,'P_A',cfg,opts,raw);plantStarted=isfile(marker);
    catch err
        plantStarted=isfile(marker);if plantStarted,append_ledger(out,phase,'Plant',rs.run_id,1,'ENGINEERING_ERROR',err.identifier);end
        write_json(fullfile(sceneDir,'error.json'),struct('identifier',err.identifier,'message',err.message,'plant_started',plantStarted,'scene_id',sceneId));rethrow(err)
    end
end
core=measure_pcf_dl1018(log,scene,double(rs.opts.stage1_position_runtime.weight));
met=metrics_dl1018(log,scene,spec,core,double(b.Q_0_20_m),double(field_or(b,'A_0_20_rad',NaN)),double(b.position_peak_m),true);
row=make_row(rs.run_id,phase,sceneId,char(spec.task),headType,gamma,kappa,char(model.model_id),log,core,met,b,plantStarted, ...
    relpath(root,raw),relpath(root,start),cfg.rbf.position.dmax);
if plantStarted,append_ledger(out,phase,'Plant',rs.run_id,1,char(log.status),sprintf('%s %s gamma=%g kappa=%g',headType,sceneId,gamma,kappa));end
write_json(mp,struct('metrics_row',row,'source_reused',false,'finished_at_utc',utc_now()));
if ~strcmp(phase,'LOCKED_DEV'),persist_rows(row,fullfile(out,'reports','SEARCH_ALL_RUNS.csv'));end
state=load_state(fullfile(out,'state','state.json'));state.active_group='';state.active_scene='';state.active_run_id='';
state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(fullfile(out,'state','state.json'),state);
fprintf('POSITION_SEARCH_RUN %s %s status=%s Q=%.9g B=%.9g starts=%d ETA=%s\n',group,sceneId,row.status,row.Q_0_20_m,row.B_Q_0_20_m,count_plants(out),eta_text(count_plants(out),planned,taskStart));
end

function row=make_row(id,phase,sceneId,task,headType,gamma,kappa,modelId,log,core,met,b,started,raw,start,dmax)
event=logical(log.stage1_position_event_inference_valid(:));rawHead=double(log.stage1_position_event_raw_acceleration_mps2);
biasBefore=double(field_or(log,'stage1_position_event_bias_before_mps2',zeros(3,nnz(event))));
biasAfter=double(field_or(log,'stage1_position_event_bias_after_mps2',zeros(3,nnz(event))));
biasDelta=0;if ~isempty(biasBefore)&&~isempty(biasAfter),biasDelta=nnz(vecnorm(biasAfter-biasBefore,2,1)>0);end
clipCount=0;if any(event),clipCount=nnz(any(abs(rawHead(event,:))>double(dmax(:)).'+1e-12,2));end
row=struct('run_id',id,'phase',phase,'scene_id',sceneId,'task',task,'head_type',headType,'gamma',gamma,'kappa',kappa, ...
    'model_id',modelId,'status',char(log.status),'complete',logical(core.complete),'finite',logical(core.finite), ...
    'transitions',double(core.transitions),'plant_started',logical(started),'Q_0_20_m',double(met.Q_0_20_m), ...
    'B_run_id',char(b.run_id),'B_raw_path',char(b.raw_path),'B_Q_0_20_m',double(b.Q_0_20_m), ...
    'delta_Q_vs_B_m',double(met.Q_0_20_m)-double(b.Q_0_20_m), ...
    'Q_5_20_m',double(met.Q_5_20_m),'position_axis_rmse_m',jsonencode(met.position_axis_rmse_m), ...
    'attitude_axis_rmse_rad',jsonencode(met.attitude_axis_rmse_rad),'A_0_20_rad',double(met.A_0_20_rad), ...
    'position_peak_m',double(met.position_peak_m),'position_p95_m',double(met.position_p95_m), ...
    'B_position_peak_m',double(b.position_peak_m),'motor_TV_normalized_per_s',double(met.motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(met.motor_saturation_fraction),'generalized_clip_fraction',double(met.generalized_clip_fraction), ...
    'motor_min_rad_s',double(met.motor_min_rad_s),'motor_max_rad_s',double(met.motor_max_rad_s), ...
    'controller_p99_ms',double(met.controller_p99_ms),'controller_worst_ms',double(met.controller_worst_ms), ...
    'position_head_update_count',double(met.position_head_update_count),'position_head_projection_count',double(met.position_head_projection_count), ...
    'bias_update_count',biasDelta,'head_output_clip_count',clipCount, ...
    'bias_projection_count',nnz(double(field_or(log,'stage1_position_event_bias_projection',zeros(numel(log.transition_time),1)))~=0), ...
    'bias_final_mps2',jsonencode(double(field_or(log,'stage1_position_search_final_bias_mps2',zeros(3,1)))), ...
    'safety_stop_reason',char(met.safety_stop_reason),'source','NEW_PLANT','raw_path',raw,'run_start_path',start, ...
    'phase_metrics_json',char(met.phase_metrics_json));
end
function row=make_reused_final_row(f,spec,model,b)
row=struct('run_id',char(f.run_id),'phase','FEATURE_G1_K1','scene_id',char(spec.scene_id),'task',char(spec.task), ...
    'head_type','FEATURE','gamma',1,'kappa',1,'model_id',char(model.model_id),'status',char(f.status_final), ...
    'complete',parse_bool(f.complete_final),'finite',parse_bool(f.finite_final),'transitions',double(f.transitions), ...
    'plant_started',false,'Q_0_20_m',double(f.Final_Q_0_20_m),'B_run_id',char(b.run_id),'B_raw_path',char(b.raw_path), ...
    'B_Q_0_20_m',double(f.B_Q_0_20_m), ...
    'delta_Q_vs_B_m',double(f.Final_Q_0_20_m)-double(f.B_Q_0_20_m),'Q_5_20_m',NaN, ...
    'position_axis_rmse_m',jsonencode([f.Final_axis_rmse_x_m f.Final_axis_rmse_y_m f.Final_axis_rmse_z_m]), ...
    'attitude_axis_rmse_rad','[]','A_0_20_rad',double(f.Final_A_0_20_rad), ...
    'position_peak_m',double(f.Final_position_peak_m),'position_p95_m',double(f.Final_position_p95_m), ...
    'B_position_peak_m',double(b.position_peak_m),'motor_TV_normalized_per_s',double(f.Final_motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(f.Final_motor_saturation_fraction),'generalized_clip_fraction',double(f.Final_generalized_clip_fraction), ...
    'motor_min_rad_s',NaN,'motor_max_rad_s',NaN,'controller_p99_ms',NaN,'controller_worst_ms',NaN, ...
    'position_head_update_count',NaN,'position_head_projection_count',NaN,'bias_update_count',0,'head_output_clip_count',NaN, ...
    'bias_projection_count',0,'bias_final_mps2','[0,0,0]', ...
    'safety_stop_reason','','source','REUSED_VERIFIED_ORIGINAL_FINAL','raw_path',char(f.raw_path), ...
    'run_start_path','experiments/position_causal_repair_v1/runs/D3_FINAL_INITIAL_BRIDGE','phase_metrics_json','[]');
end

function b=baseline_row(group,sceneId,bridge,bridgePair,finalBridge,devB)
if contains(group,'LOCKED_DEV')
    z=devB(devB.scene_id==sceneId,:);assert(height(z)==1,'POSSEARCH:BRow','Missing DEV B for %s.',sceneId);
    b=struct('run_id',char(z.run_id),'Q_0_20_m',double(z.Q_0_20_m),'A_0_20_rad',double(z.A_0_20_rad), ...
        'position_peak_m',double(z.position_peak_m),'complete',parse_bool(z.complete),'finite',parse_bool(z.finite), ...
        'raw_path',char(z.raw_path));
else
    z=finalBridge(finalBridge.scene_id==sceneId,:);assert(height(z)==1,'POSSEARCH:BRow','Missing bridge B for %s.',sceneId);
    bp=bridgePair(bridgePair.scene_id==sceneId,:);bm=bridge(bridge.scene_id==sceneId&bridge.role=="B",:);
    assert(height(bp)==1&&height(bm)==1&&abs(double(bp.B_Q_0_20_m)-double(z.B_Q_0_20_m))<1e-9, ...
        'POSSEARCH:BPairIdentity','D3/D1 B baseline mismatch for %s.',sceneId);
    b=struct('run_id',char(bm.run_id),'Q_0_20_m',double(bp.B_Q_0_20_m),'A_0_20_rad',double(bp.B_A_0_20_rad), ...
        'position_peak_m',double(bp.B_position_peak_m),'complete',parse_bool(bp.B_complete), ...
        'finite',parse_bool(bp.B_finite),'raw_path',char(bm.raw_path));
end
assert(b.complete&&b.finite&&isfinite(b.Q_0_20_m),'POSSEARCH:BStatus','Invalid same-scene B for %s.',sceneId);
end
function score=score_six(rows,group,headType,gamma,kappa)
full=numel(rows)==6&&all([rows.complete])&&all([rows.finite])&&all([rows.transitions]==20000)&& ...
    all(strcmp({rows.status},'STABLE'))&&all(isfinite([rows.Q_0_20_m]));
q=NaN;b=mean([rows.B_Q_0_20_m]);if full,q=mean([rows.Q_0_20_m]);end
score=struct('group_id',group,'head_type',headType,'gamma',gamma,'kappa',kappa,'n',numel(rows), ...
    'expected_n',6,'complete_stable',full,'macro_Q_0_20_m',q,'same_scene_B_macro_Q_0_20_m',b, ...
    'delta_Q_vs_B_m',q-b,'wins',nnz([rows.Q_0_20_m]<[rows.B_Q_0_20_m]), ...
    'new_plant_starts',sum(double([rows.plant_started])));
end
function best=choose_best(scores)
best=[];if isempty(scores),return;end
ok=arrayfun(@(s)s.complete_stable&&isfinite(s.macro_Q_0_20_m),scores);scores=scores(ok);
if isempty(scores),return;end
[~,i]=min([scores.macro_Q_0_20_m]);best=scores(i);
end
function a=append_rows(a,b)
if isempty(b),return;elseif isempty(a),a=b(:);else,a=[a(:);b(:)];end
end
function a=append_score(a,b)
if isempty(a),a=b(:);elseif ~isempty(b),a=[a(:);b(:)];end
end
function persist_rows(rows,path)
if isempty(rows),return;end
writetable(struct2table(rows,'AsArray',true),path);
end
function emit_group(out,rows,s,planned,taskStart)
valid=~isempty(rows)&&all([rows.complete])&&all([rows.finite])&&all(strcmp({rows.status},'STABLE'));
q=NaN;b=NaN;if ~isempty(rows),b=mean([rows.B_Q_0_20_m]);if valid&&numel(rows)==6,q=mean([rows.Q_0_20_m]);end,end
txt=sprintf('POSITION_SEARCH_SIX %s head=%s gamma=%g kappa=%g stable=%d/6 macro_Q=%.10g same_scene_B=%.10g starts=%d/%d ETA=%s\n', ...
    s.group_id,s.head_type,s.gamma,s.kappa,nnz([rows.complete]&[rows.finite]&strcmp({rows.status},'STABLE')),q,b,count_plants(out),planned,eta_text(count_plants(out),planned,taskStart));
for i=1:numel(rows),txt=[txt sprintf('  %s Q=%.10g B=%.10g delta=%.10g status=%s source=%s\n', ...
        rows(i).scene_id,rows(i).Q_0_20_m,rows(i).B_Q_0_20_m,rows(i).delta_Q_vs_B_m,rows(i).status,rows(i).source)];end %#ok<AGROW>
txt=[txt sprintf('  cumulative_new_Plant=%d/%d remaining_estimate=%s\n',count_plants(out),planned,eta_text(count_plants(out),planned,taskStart))];
log_progress(out,txt);fprintf('%s',txt);
end
function emit_dev_chunk(out,chunk,allRows,headType,gamma,kappa,plants,planned,taskStart)
chunkStable=numel(chunk)==6&&all([chunk.complete])&&all([chunk.finite])&&all(strcmp({chunk.status},'STABLE'));
chunkQ=NaN;chunkB=mean([chunk.B_Q_0_20_m]);if chunkStable,chunkQ=mean([chunk.Q_0_20_m]);end
cumStable=~isempty(allRows)&&all([allRows.complete])&&all([allRows.finite])&&all(strcmp({allRows.status},'STABLE'));
cumQ=NaN;cumB=mean([allRows.B_Q_0_20_m]);if cumStable,cumQ=mean([allRows.Q_0_20_m]);end
txt=sprintf('POSITION_SEARCH_DEV_SIX head=%s gamma=%g kappa=%g completed=%d/24 chunk_stable=%d/6 chunk_Q=%.10g chunk_B=%.10g cumulative_Q=%.10g cumulative_B=%.10g starts=%d/%d ETA=%s\n', ...
    headType,gamma,kappa,numel(allRows),nnz([chunk.complete]&[chunk.finite]&strcmp({chunk.status},'STABLE')),chunkQ,chunkB,cumQ,cumB,plants,planned,eta_text(plants,planned,taskStart));
for i=1:numel(chunk),txt=[txt sprintf('  %s Q=%.10g B=%.10g delta=%.10g status=%s\n', ...
    chunk(i).scene_id,chunk(i).Q_0_20_m,chunk(i).B_Q_0_20_m,chunk(i).delta_Q_vs_B_m,chunk(i).status)];end %#ok<AGROW>
log_progress(out,txt);fprintf('%s',txt);
end
function candidate=make_candidate(best,model,cfg)
candidate=struct('candidate_id',sprintf('POSITION_%s_G%g_K%g',best.head_type,best.gamma,best.kappa), ...
    'head_type',best.head_type,'gamma',best.gamma,'kappa',best.kappa,'selected_six_scene_group',best.group_id, ...
    'model_id',char(model.model_id),'model_origin','FINAL','encoder_frozen',true, ...
    'normalizer_id','POSITION_INITIAL_TRAIN_ONLY','position_rbf_output_enabled',false,'position_rbf_update_enabled',false, ...
    'attitude_controller','original_B_RBF_unchanged','pcf_enabled',true,'position_event_hz',100, ...
    'plant_dt_s',cfg.plant.dt,'beta_rise_s',cfg.rbf.position.beta_rise_time,'feature_dimension',33, ...
    'W0',double(model.output_W),'weight_initial',best.kappa*double(model.output_W),'weight_bound',60, ...
    'bias_initial',zeros(3,1),'bias_bound_mps2',3,'output_dmax_mps2',double(cfg.rbf.position.dmax(:)), ...
    'leakage',.002,'state_reset_each_episode',true,'selection_metric','24-scene equal-weight mean Q_0_20_m only', ...
    'development_set_evaluated',true);
if strcmp(candidate.head_type,'BIAS'),candidate.weight_initial=double(model.output_W);end
end
function write_final_report(out,r,rows,scores,model)
% Normalize persisted rows before grouping. Cached JSON rows are structs,
% while MATLAB callers may pass a table after a resume/import.
if istable(rows),rows=table2struct(rows);end
if istable(scores),scores=table2struct(scores);end
L={'# 只优化位置补偿器：闭环搜索结果','', ...
    ['状态：**' char(r.status) '**'], ...
    sprintf('候选：%s，gamma=%g，kappa=%g；冻结编码器：%s。',r.selected_candidate.head_type,r.selected_candidate.gamma,r.selected_candidate.kappa,char(model.model_id)), ...
    sprintf('DEV：%d/24 完整稳定；候选宏 Q=%.10g m，同场 B 宏 Q=%.10g m，差（候选−B）=%.10g m，相对变化=%.4f%%。', ...
       r.completed_dev_rows,r.macro_Q_0_20_m,r.same_scene_B_macro_Q_0_20_m,r.candidate_minus_B_m,100*r.relative_change_vs_B), ...
    sprintf('只按位置 Q 判定是否超过 B：%d。姿态只记录；编码器 fit=0；新 Plant=%d/78。', ...
       r.candidate_beats_B_by_position_only,r.cumulative_new_plant_starts), ...
    '这24场已作为开发集观察，不是盲测；不据此宣称未见场景泛化。','','## 按任务汇总','','| 任务 | 场数 | 宏Q (m) | 同场B宏Q (m) | 差值 (m) | X/Y/Z位置轴RMSE (m) | 胜场 |', ...
    '|---|---:|---:|---:|---:|---|---:|'};
tasks=unique(string({rows.task}),'stable');
for ti=1:numel(tasks)
    use=string({rows.task})==tasks(ti);sub=rows(use);
    % Keep the aggregation on a normalized table so both imported and cached
    % rows use the same, explicit variable names.
    subTable=struct2table(sub,'AsArray',true);
    axisCell=cell(height(subTable),1);
    for ai=1:height(subTable),axisCell{ai}=reshape(jsondecode(char(subTable.position_axis_rmse_m(ai))),1,[]);end
    axisMat=vertcat(axisCell{:});axisR=sqrt(mean(axisMat.^2,1));q=mean(subTable.Q_0_20_m);b=mean(subTable.B_Q_0_20_m);
    L{end+1}=sprintf('| %s | %d | %.8g | %.8g | %.8g | %.7g / %.7g / %.7g | %d |', ...
        char(tasks(ti)),height(subTable),q,b,q-b,axisR(1),axisR(2),axisR(3),nnz(subTable.Q_0_20_m<subTable.B_Q_0_20_m)); %#ok<AGROW>
end
L=[L,{'','## 24场逐场配对','','| 场景 | 任务 | Q (m) | 同场 B (m) | 差值 (m) | 位置轴RMSE (m) | 姿态轴RMSE (rad) | 峰值 (m) | 电机TV | 状态 |', ...
    '|---|---|---:|---:|---:|---|---|---:|---:|---|'}];
for i=1:numel(rows)
    L{end+1}=sprintf('| %s | %s | %.8g | %.8g | %.8g | %s | %s | %.8g | %.8g | %s |', ...
        char(rows(i).scene_id),char(rows(i).task),double(rows(i).Q_0_20_m),double(rows(i).B_Q_0_20_m),double(rows(i).delta_Q_vs_B_m), ...
        char(rows(i).position_axis_rmse_m),char(rows(i).attitude_axis_rmse_rad),double(rows(i).position_peak_m),double(rows(i).motor_TV_normalized_per_s),char(rows(i).status)); %#ok<AGROW>
end
L=[L,{'','## BRIDGE6搜索组','','| 组 | Head | gamma | kappa | 稳定完整 | 宏Q (m) | B宏Q (m) | 差值 (m) | 新Plant |','|---|---|---:|---:|---:|---:|---:|---:|---:|'}];
for i=1:numel(scores)
    L{end+1}=sprintf('| %s | %s | %g | %g | %d/6 | %.8g | %.8g | %.8g | %d |', ...
        scores(i).group_id,scores(i).head_type,scores(i).gamma,scores(i).kappa,6*logical(scores(i).complete_stable), ...
        scores(i).macro_Q_0_20_m,scores(i).same_scene_B_macro_Q_0_20_m,scores(i).delta_Q_vs_B_m,scores(i).new_plant_starts); %#ok<AGROW>
end
L=[L,{'','候选包见 models/position_only_candidate_package.mat。复现命令见 models/candidate_manifest.json。原B、Final、合同和G06均未修改。'}];
write_text(fullfile(out,'reports','FINAL_REPORT_ZH.md'),strjoin(L,newline));
end
function update_state(out,group,phase,plants,rows,score)
p=fullfile(out,'state','state.json');s=load_state(p);s.phase=phase;s.status='IN_PROGRESS';s.active_group=group;
s.active_scene='';s.active_run_id='';s.cumulative_new_plant_starts=plants;s.completed_search_rows=rows;s.updated_at_utc=utc_now();
if ~isempty(score),s.last_group_complete_stable=score.complete_stable;s.last_group_macro_Q_0_20_m=score.macro_Q_0_20_m;s.last_group_B_macro_Q_0_20_m=score.same_scene_B_macro_Q_0_20_m;end
write_json(p,s);
end
function s=load_state(p)
if isfile(p),s=jsondecode(fileread(p));else,s=struct;end
if ~isfield(s,'started_at_utc'),s.started_at_utc='';end
end
function update_state_done(out,status,plants,candidate)
p=fullfile(out,'state','state.json');s=load_state(p);s.phase='POSITION_SEARCH_COMPLETE';s.status=status;s.active_group='';s.active_scene='';s.active_run_id='';
s.cumulative_new_plant_starts=plants;s.candidate=candidate;s.updated_at_utc=utc_now();write_json(p,s);
end
function n=count_plants(out),d=dir(fullfile(out,'runs','**','plant_started.marker'));n=numel(d);end
function s=eta_text(plants,planned,t0)
if plants<1,s='待首组实测';return;end
elapsed=max(1,seconds(datetime('now','TimeZone','UTC')-t0));remaining=max(0,planned-plants)*elapsed/plants;
if remaining<3600,s=sprintf('约 %.0f 分钟',remaining/60);else,s=sprintf('约 %.1f 小时',remaining/3600);end
end
function append_ledger(out,phase,kind,id,count,status,notes)
p=fullfile(out,'RESOURCE_LEDGER.csv');if contains(fileread(p),char(id)),return;end
f=fopen(p,'a');fprintf(f,'%s,%s,%s,%s,%d,%s,%s\n',utc_now(),phase,kind,id,count,status,strrep(char(notes),',',';'));fclose(f);
end
function log_progress(out,s)
f=fopen(fullfile(out,'reports','progress.log'),'a');fwrite(f,s,'char');fclose(f);
end
function write_json(p,s)
f=fopen(p,'w');assert(f>0,'POSSEARCH:Write','Cannot write %s.',p);fwrite(f,jsonencode(s,'PrettyPrint',true),'char');fclose(f);
end
function write_text(p,s)
f=fopen(p,'w');assert(f>0,'POSSEARCH:Write','Cannot write %s.',p);fwrite(f,char(s),'char');fclose(f);
end
function x=utc_now(),x=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));end
function p=relpath(root,path),p=strrep(char(java.io.File(path).getCanonicalPath()),[root filesep],'');p=strrep(p,filesep,'/');end
function v=field_or(s,n,d),if isfield(s,n),v=s.(n);else,v=d;end,end
function y=parse_bool(x),if islogical(x),y=x;elseif isnumeric(x),y=x~=0;else,y=any(strcmpi(char(string(x)),{'true','1'}));end,end
function y=iff(c,a,b),if c,y=a;else,y=b;end,end
