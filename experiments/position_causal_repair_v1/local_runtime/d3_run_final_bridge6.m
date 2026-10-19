function result=d3_run_final_bridge6(root,action)
% Offline identity preflight, then only the six authorized Final P_A bridge Plant runs.
if nargin<2,action='run';end
action=lower(char(action));assert(any(strcmp(action,{'preflight','run'})),'D3:Action','Action must be preflight or run.');
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','position_causal_repair_v1');
addpath(genpath(fullfile(root,'matlab')));
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'D3:Root','Unexpected DL1018 root.');
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
B=readtable(fullfile(out,'manifests','BRIDGE6.csv'),'TextType','string');
paired=readtable(fullfile(out,'reports','D1_G04_PAIRED_ALL.csv'),'TextType','string');
ids=unique(B.scene_id,'stable');assert(numel(ids)==6,'D3:SceneCount','Expected exactly six predeclared scenes.');
q=load(fullfile(root,'models','position','selected','matlab_model_and_parity.mat'),'model');pModel=q.model;
modelSelection=jsondecode(fileread(fullfile(root,'configs','selected_models.json')));
selectedId=char(modelSelection.position_selected.selected_model_id);
assert(strcmp(selectedId,'DL1018_POSITION_SELECTED'),'D3:FinalModel','Selected model identity mismatch.');
pre=struct([]);

% Finish all identity checks before starting the first Plant transition.
for si=1:numel(ids)
    sceneId=char(ids(si));spec=M(M.scene_id==sceneId,:);assert(height(spec)==1,'D3:Spec','Missing/nonunique scene spec.');
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    hist=B(B.scene_id==sceneId,:);refScene=[];refCfg=[];refOpts=[];
    for ri=1:height(hist)
        r=hist(ri,:);raw=fullfile(root,strrep(char(r.raw_path),'/',filesep));
        d=load(raw,'scene');s=load(fullfile(fileparts(raw),'run_start.mat'),'runStart');
        assert(strcmp(char(s.runStart.run_id),char(r.run_id)),'D3:RunIdentity','Historical run_start mismatch.');
        if isempty(refScene)
            refScene=d.scene;refCfg=s.runStart.cfg;refOpts=s.runStart.opts;
        else
            assert(scene_equal(refScene,d.scene),'D3:TripletScene','Historical triplet scene mismatch: %s.',sceneId);
            assert(isequaln(refCfg,s.runStart.cfg),'D3:TripletCfg','Historical cfg mismatch: %s.',sceneId);
            assert(attitude_options_equal(refOpts,s.runStart.opts),'D3:TripletAttitude','Attitude RBF mismatch: %s.',sceneId);
        end
    end
    assert(scene_equal(scene,refScene),'D3:GeneratedScene','Generated scene differs from saved triplet: %s.',sceneId);
    assert(isequaln(refCfg,cfg),'D3:CurrentCfg','Historical cfg differs from current frozen cfg.');
    opts=controller_options_dl1018(cfg,'P_A',pModel,[],'online');
    assert(logical(opts.rbf_attitude_enabled)&&logical(opts.rbf_attitude_output_enabled)&&logical(opts.rbf_attitude_update_enabled), ...
        'D3:Attitude','Original attitude RBF must remain on.');
    assert(~logical(opts.rbf_position_output_enabled)&&~logical(opts.rbf_position_update_enabled)&& ...
        logical(opts.stage1_position_runtime.enabled)&&logical(opts.stage1_position_runtime.update_enabled), ...
        'D3:PositionMode','Final P_A must use online student position Head.');
    z=struct('scene_id',sceneId,'task',char(spec.task),'class_index',double(spec.c),'wind_cell',double(spec.w), ...
        'generated_scene_equals_historical',true,'cfg_equals_current',true,'attitude_rbf_identity_exact',true, ...
        'same_c0_and_controller_parameters',true,'selected_model_id',selectedId, ...
        'position_head_mode','online');
    if isempty(pre),pre=z;else,pre(end+1,1)=z;end %#ok<AGROW>
end
fid=fopen(fullfile(out,'reports','D3_PREFLIGHT.json'),'w');
fwrite(fid,jsonencode(struct('status','PASS','plant_starts',0,'checks',pre),'PrettyPrint',true),'char');fclose(fid);
if strcmp(action,'preflight')
    result=struct('status','PREFLIGHT_PASS','plant_starts',0,'checks',numel(pre));
    return
end

runRoot=fullfile(out,'runs','D3_FINAL_INITIAL_BRIDGE');if ~isfolder(runRoot),mkdir(runRoot);end
metricsRows=struct([]);completed=0;plantCount=0;
for si=1:numel(ids)
    sceneId=char(ids(si));spec=M(M.scene_id==sceneId,:);runId=['D3_FINAL_BRIDGE_' sceneId '_P_A'];
    sceneDir=fullfile(runRoot,sceneId,'P_A');rawPath=fullfile(sceneDir,'raw_run.mat');
    startPath=fullfile(sceneDir,'run_start.mat');marker=fullfile(sceneDir,'plant_started.marker');metricPath=fullfile(sceneDir,'metrics.json');
    if isfile(metricPath)&&isfile(rawPath)
        z=jsondecode(fileread(metricPath));
        if isempty(metricsRows),metricsRows=z.metrics_row;else,metricsRows(end+1,1)=z.metrics_row;end %#ok<AGROW>
        completed=completed+1;plantCount=plantCount+logical(z.plant_started);continue
    end
    if ~isfolder(sceneDir),mkdir(sceneDir);end
    if isfile(rawPath)
        d=load(rawPath,'log','scene');log=d.log;scene=d.scene;
        if ~isfile(startPath),error('D3:MissingRunStart','Raw log exists without run_start; preserve and inspect: %s',rawPath);end
        s=load(startPath,'rs');rs=s.rs;plantStarted=isfile(marker);
        plantCount=plantCount+logical(plantStarted);
    else
        if isfile(marker)
            error('D3:InterruptedPlant','Plant marker exists without complete raw log; do not repeat this scene: %s',sceneId);
        end
        generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
        opts=controller_options_dl1018(cfg,'P_A',pModel,[],'online');
        started=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
        rs=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
            'gate_id','D3_FINAL_INITIAL_BRIDGE','collector_id','P_A','model_id',selectedId, ...
            'scene_spec',spec,'cfg',cfg,'opts',opts,'initial_state',scene.initial_state,'started_at',started);
        save(startPath,'rs','-v7');opts.r2e_first_plant_step_marker=marker;
        update_state(out,completed,plantCount,runId);
        try
            log=run_episode_dl1018(scene,'P_A',cfg,opts,rawPath);plantStarted=isfile(marker);
        catch err
            plantStarted=isfile(marker);update_state(out,completed,plantCount+logical(plantStarted),runId);
            append_ledger_once(out,runId,plantStarted,'ENGINEERING_ERROR');
            fid=fopen(fullfile(sceneDir,'error.json'),'w');
            fwrite(fid,jsonencode(struct('identifier',err.identifier,'message',err.message,'plant_started',logical(plantStarted)), ...
                'PrettyPrint',true),'char');fclose(fid);
            rethrow(err);
        end
        plantCount=plantCount+logical(plantStarted);
    end
    core=measure_pcf_dl1018(log,scene,double(rs.opts.stage1_position_runtime.weight));
    old=paired(paired.scene_id==sceneId,:);assert(height(old)==1,'D3:PairedRow','No same-scene D1 row.');
    met=metrics_dl1018(log,scene,spec,core,double(old.B_Q_0_20_m),double(old.B_A_0_20_rad), ...
    double(old.B_position_peak_m),parse_bool(old.B_complete));
    row=make_metrics_row(sceneId,runId,selectedId,rawPath,startPath,plantStarted,log,core,met);
    if isempty(metricsRows),metricsRows=row;else,metricsRows(end+1,1)=row;end %#ok<AGROW>
    rec=struct('status',char(log.status),'plant_started',logical(plantStarted),'metrics_row',row, ...
        'finished_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
    fid=fopen(metricPath,'w');fwrite(fid,jsonencode(rec,'PrettyPrint',true),'char');fclose(fid);
    completed=completed+1;update_state(out,completed,plantCount,runId);append_ledger_once(out,runId,plantStarted,char(log.status));
    fprintf('D3 progress %d/6 %s status=%s Q=%.8g A=%.8g\n',completed,sceneId,char(log.status),met.Q_0_20_m,met.A_0_20_rad);
    if ~core.complete||~core.finite||~strcmpi(char(log.status),'STABLE')
        error('D3:CandidateHardStop','Preserve this run and stop remaining candidate runs at %s.',sceneId);
    end
end
T=struct2table(metricsRows);writetable(T,fullfile(out,'reports','D3_FINAL_INITIAL_BRIDGE_MATLAB.csv'));
result=struct('status','COMPLETE','plant_starts',plantCount,'completed_runs',completed,'preflight_status','PASS');
fid=fopen(fullfile(out,'reports','D3_MATLAB_RESULT.json'),'w');fwrite(fid,jsonencode(result,'PrettyPrint',true),'char');fclose(fid);
end

function row=make_metrics_row(sceneId,runId,modelId,rawPath,startPath,plantStarted,log,core,met)
t=double(log.transition_time(:));x=double(log.state(1:numel(t),:));r=double(log.reference.position(1:numel(t),:));e=r-x(:,1:3);
bins={'T_0_1p8',0,1.8;'T_1p8_5',1.8,5;'T_5_10',5,10;'T_10_15',10,15;'T_15_20',15,20};tb=struct;
for i=1:size(bins,1)
    m=t>=bins{i,2}&t<bins{i,3};tb.(bins{i,1})=sqrt(mean(sum(e(m,:).^2,2)));
end
row=struct('scene_id',sceneId,'run_id',runId,'model_id',modelId,'status',char(log.status), ...
    'complete',logical(core.complete),'finite',logical(core.finite),'transitions',double(core.transitions), ...
    'plant_started',logical(plantStarted),'Q_0_20_m',double(met.Q_0_20_m),'Q_5_20_m',double(met.Q_5_20_m), ...
    'A_0_20_rad',double(met.A_0_20_rad),'axis_rmse_x_m',double(met.position_axis_rmse_m(1)), ...
    'axis_rmse_y_m',double(met.position_axis_rmse_m(2)),'axis_rmse_z_m',double(met.position_axis_rmse_m(3)), ...
    'position_peak_m',double(met.position_peak_m),'position_p95_m',double(met.position_p95_m), ...
    'motor_TV_normalized_per_s',double(met.motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(met.motor_saturation_fraction), ...
    'generalized_clip_fraction',double(met.generalized_clip_fraction),'time_bin_Q_json',jsonencode(tb), ...
    'phase_metrics_json',char(met.phase_metrics_json),'raw_path',relpath(rawPath),'run_start_path',relpath(startPath));
end

function yes=scene_equal(a,b)
yes=isequaln(a.time,b.time)&&isequaln(a.initial_state,b.initial_state)&& ...
    isequaln(a.environment_wind_I,b.environment_wind_I)&&isequaln(a.reference.position,b.reference.position)&& ...
    isequaln(a.reference.velocity,b.reference.velocity)&&isequaln(a.reference.acceleration,b.reference.acceleration)&& ...
    isequaln(a.reference.yaw,b.reference.yaw)&&isequaln(a.reference.yaw_rate,b.reference.yaw_rate)&& ...
    isequaln(a.reference.yaw_acceleration,b.reference.yaw_acceleration)&&isequaln(a.arms.command,b.arms.command)&& ...
    isequaln(a.arms.rho_true,b.arms.rho_true)&&isequaln(a.arms.rhoDot_true,b.arms.rhoDot_true);
end

function yes=attitude_options_equal(a,b)
names={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled', ...
    'attitude_rbf_frequency_hz','rbf_attitude_gamma_scale'};yes=true;
for i=1:numel(names),yes=yes&&isfield(a,names{i})&&isfield(b,names{i})&&isequaln(a.(names{i}),b.(names{i}));end
end

function y=parse_bool(v)
if islogical(v),y=v;elseif isnumeric(v),y=(v~=0);else,y=any(strcmpi(strtrim(char(string(v))),{'true','1','yes'}));end
end

function p=relpath(path)
root=char(java.io.File(pwd).getCanonicalPath());p=strrep(char(java.io.File(path).getCanonicalPath()),[root filesep],'');p=strrep(p,filesep,'/');
end

function update_state(out,n,plantCount,runId)
p=fullfile(out,'state','state.json');s=jsondecode(fileread(p));s.phase='D3_RUNNING';s.next='D3_FINAL_INITIAL_SAME_SCENE_BRIDGE6';
s.d3_completed_runs=n;s.plant_starts_new=plantCount;s.active_run_id=runId;
s.updated_at_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
fid=fopen(p,'w');fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
end

function append_ledger_once(out,runId,started,status)
path=fullfile(out,'RESOURCE_LEDGER.csv');
if isfile(path)&&contains(fileread(path),runId),return;end
fid=fopen(path,'a');
fprintf(fid,'%s,D3,Plant,%s,%d,%s,New isolated Final P_A bridge scene.\n', ...
    char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')),runId,double(started),status);fclose(fid);
end
