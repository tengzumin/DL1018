function result=d5_run_candidate_bridge6(root,candidate)
% Execute one frozen D5 P_A candidate over BRIDGE6 after its zero-Plant PASS.
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','position_causal_repair_v1');
candidate=upper(char(candidate));assert(any(strcmp(candidate,{'C1','C2'})),'D5:Candidate','Candidate must be C1 or C2.');
if strcmp(candidate,'C1'),family='C1_X20_FIXED_INFORMATION';else,family='C2_X14_ADAPTATION_AWARE';end
seed=2026101901;modelId=[family '_SEED' num2str(seed)];package=fullfile(out,'models',family,['seed' num2str(seed)]);
preflight=jsondecode(fileread(fullfile(out,'reports',['D5_PREFLIGHT_' candidate '.json'])));
assert(strcmp(preflight.status,'PASS')&&preflight.plant_starts==0,'D5:Preflight','Candidate zero-Plant preflight must pass.');
export=jsondecode(fileread(fullfile(package,'export_report.json')));
assert(strcmp(export.status,'MATLAB_PARITY_PASS')&&strcmp(export.checkpoint_sha256,preflight.checkpoint_sha256), ...
    'D5:Export','MATLAB parity report or checkpoint identity is missing.');
q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;
assert(strcmp(char(model.model_id),modelId),'D5:ModelIdentity','Candidate MAT model identity mismatch.');

addpath(genpath(fullfile(root,'matlab')));
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'D5:Root','Unexpected DL1018 root.');
local=fullfile(out,'local_runtime');addpath(genpath(local),'-begin');rehash;
clear run_episode_dl1018 run_dl1018_closed_loop position_stage1_model_forward_v2
assert(startsWith(which('run_dl1018_closed_loop'),local,'IgnoreCase',true)&& ...
    startsWith(which('position_stage1_model_forward_v2'),local,'IgnoreCase',true)&& ...
    startsWith(which('run_episode_dl1018'),local,'IgnoreCase',true), ...
    'D5:PathIsolation','Candidate-only runtime path is not active.');
episodeHandle=@run_episode_dl1018;episodeInfo=functions(episodeHandle);
assert(startsWith(episodeInfo.file,local,'IgnoreCase',true), ...
    'D5:EpisodeHandle','Episode handle did not resolve to the isolated wrapper.');
manifest=readtable(fullfile(out,'manifests','BRIDGE6.csv'),'TextType','string');
paired=readtable(fullfile(out,'reports','D1_G04_PAIRED_ALL.csv'),'TextType','string');
c0=readtable(fullfile(out,'reports','D3_INITIAL_FINAL_BRIDGE.csv'),'TextType','string');
ids=unique(manifest.scene_id,'stable');assert(numel(ids)==6,'D5:BridgeCount','Expected six frozen BRIDGE6 scenes.');
runRoot=fullfile(out,'runs',['D5_POSITION_REPAIR_' candidate '_SEED' num2str(seed)]);
if ~isfolder(runRoot),mkdir(runRoot);end
completed=0;newPlants=0;rows=struct([]);
for si=1:numel(ids)
    sceneId=char(ids(si));specRow=manifest(manifest.scene_id==sceneId,:);assert(height(specRow)==3,'D5:Triplet','BRIDGE6 triplet is incomplete.');
    sceneSpec=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');spec=sceneSpec(sceneSpec.scene_id==sceneId,:);
    assert(height(spec)==1,'D5:SceneSpec','Scene specification missing or repeated.');
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    opts=controller_options_dl1018(cfg,'P_A',model,[],'online');
    assert(opts.rbf_attitude_enabled&&opts.rbf_attitude_output_enabled&&opts.rbf_attitude_update_enabled&& ...
        ~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
        opts.stage1_position_runtime.enabled&&opts.stage1_position_runtime.update_enabled, ...
        'D5:ControllerMode','Candidate must use online position Head and original attitude RBF.');
    for ri=1:height(specRow)
        hist=specRow(ri,:);histRaw=fullfile(root,strrep(char(hist.raw_path),'/',filesep));
        hd=load(histRaw,'scene');hs=load(fullfile(fileparts(histRaw),'run_start.mat'),'runStart');
        assert(strcmp(char(hs.runStart.run_id),char(hist.run_id))&&scene_equal(scene,hd.scene)&& ...
            isequaln(cfg,hs.runStart.cfg),'D5:SceneCfg','Candidate scene/cfg differs from frozen same-scene evidence.');
        if strcmpi(char(hist.role),'P_INIT_STUDENT')
            assert(attitude_equal(opts,hs.runStart.opts),'D5:Attitude','Candidate changed original attitude RBF settings.');
        end
    end
    runId=['D5_' candidate '_SEED' num2str(seed) '_' sceneId '_P_A'];
    sceneDir=fullfile(runRoot,sceneId,'P_A');rawPath=fullfile(sceneDir,'raw_run.mat');
    startPath=fullfile(sceneDir,'run_start.mat');marker=fullfile(sceneDir,'plant_started.marker');metricPath=fullfile(sceneDir,'metrics.json');
    if isfile(metricPath)&&isfile(rawPath)
        saved=jsondecode(fileread(metricPath));row=saved.metrics_row;plantStarted=isfile(marker);
        runId=char(string(row.run_id));
        newPlants=newPlants+double(plantStarted);completed=completed+1;
        append_ledger_once(out,runId,plantStarted,char(saved.status));update_state(out,completed,runId,true);
        if isempty(rows),rows=row;else,rows(end+1,1)=row;end %#ok<AGROW>
        writetable(struct2table(rows),fullfile(out,'reports',['D5_POSITION_CANDIDATE_' candidate '.csv']));
        continue
    end
    if isfile(fullfile(sceneDir,'error.json'))&&~isfile(rawPath)
        assert(isfile(fullfile(sceneDir,'error.json')),'D5:InterruptedPlant', ...
            'Plant marker without raw/error record; preserve and inspect before retry.');
        retryNo=1;archivedAttempt=fullfile(runRoot,sceneId,sprintf('P_A_ATTEMPT_%02d',retryNo));
        while isfolder(archivedAttempt),retryNo=retryNo+1;archivedAttempt=fullfile(runRoot,sceneId,sprintf('P_A_ATTEMPT_%02d',retryNo));end
        [moved,msg]=movefile(sceneDir,archivedAttempt);assert(moved,'D5:AttemptArchive','%s',msg);
        runId=[runId '_RETRY' sprintf('%02d',retryNo)];sceneDir=fullfile(runRoot,sceneId,'P_A');
        rawPath=fullfile(sceneDir,'raw_run.mat');startPath=fullfile(sceneDir,'run_start.mat');
        marker=fullfile(sceneDir,'plant_started.marker');metricPath=fullfile(sceneDir,'metrics.json');
    end
    if ~isfolder(sceneDir),mkdir(sceneDir);end
    if isfile(rawPath)
        d=load(rawPath,'log','scene');log=d.log;scene=d.scene;
        assert(isfile(startPath),'D5:MissingRunStart','Raw exists without run_start; preserve and inspect.');
        rsFile=load(startPath,'rs');rs=rsFile.rs;plantStarted=isfile(marker);
    else
        assert(~isfile(marker),'D5:InterruptedPlant','Plant marker without raw; do not repeat this scene.');
        started=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
        rs=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
            'gate_id','D5_POSITION_REPAIR_BRIDGE6','collector_id','P_A','model_id',modelId, ...
            'candidate',candidate,'input_dim',double(model.input_dim),'candidate_checkpoint_sha256',export.checkpoint_sha256, ...
            'scene_spec',spec,'cfg',cfg,'opts',opts,'initial_state',scene.initial_state,'started_at',started, ...
            'source_bridge6_scene_id',sceneId);
        save(startPath,'rs','-v7');opts.r2e_first_plant_step_marker=marker;
        update_state(out,completed,runId,false);
        try
            log=episodeHandle(scene,'P_A',cfg,opts,rawPath);plantStarted=isfile(marker);
        catch err
            plantStarted=isfile(marker);append_ledger_once(out,runId,plantStarted,'ENGINEERING_ERROR');
            fid=fopen(fullfile(sceneDir,'error.json'),'w');
            fwrite(fid,jsonencode(struct('identifier',err.identifier,'message',err.message,'plant_started',plantStarted), ...
                'PrettyPrint',true),'char');fclose(fid);
            update_state(out,completed,runId,false);rethrow(err);
        end
        newPlants=newPlants+double(plantStarted);
    end
    core=measure_pcf_dl1018(log,scene,double(rs.opts.stage1_position_runtime.weight));
    b=paired(paired.scene_id==sceneId,:);f=c0(c0.scene_id==sceneId,:);
    assert(height(b)==1&&height(f)==1,'D5:PairRows','Same-scene B/POS_OFF/Initial/Final row missing.');
    met=metrics_dl1018(log,scene,spec,core,double(b.B_Q_0_20_m),double(b.B_A_0_20_rad), ...
        double(b.B_position_peak_m),parse_bool(b.B_complete));
    row=make_row(candidate,seed,sceneId,char(spec.task),runId,modelId,rawPath,startPath,plantStarted,log,core,met,b,f);
    rec=struct('status',char(log.status),'plant_started',logical(plantStarted),'metrics_row',row, ...
        'finished_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
    fid=fopen(metricPath,'w');fwrite(fid,jsonencode(rec,'PrettyPrint',true),'char');fclose(fid);
    completed=completed+1;append_ledger_once(out,runId,plantStarted,char(log.status));update_state(out,completed,runId,true);
    if isempty(rows),rows=row;else,rows(end+1,1)=row;end %#ok<AGROW>
    writetable(struct2table(rows),fullfile(out,'reports',['D5_POSITION_CANDIDATE_' candidate '.csv']));
    fprintf('D5 %s %d/6 %s %s Q=%.8g A=%.8g Plant=%d\n',candidate,completed,sceneId,char(log.status), ...
        double(met.Q_0_20_m),double(met.A_0_20_rad),double(plantStarted));
    if ~core.complete||~core.finite||~strcmpi(char(log.status),'STABLE')
        error('D5:CandidateHardStop','Preserve this raw run and stop remaining candidate scenes at %s.',sceneId);
    end
end
if ~isempty(rows),writetable(struct2table(rows),fullfile(out,'reports',['D5_POSITION_CANDIDATE_' candidate '.csv']));end
result=struct('status','COMPLETE','candidate',candidate,'family',family,'seed',seed, ...
    'completed_runs',completed,'new_plant_starts',newPlants,'preflight_status','PASS', ...
    'report_csv',fullfile(out,'reports',['D5_POSITION_CANDIDATE_' candidate '.csv']));
fid=fopen(fullfile(out,'reports',['D5_RESULT_' candidate '.json']),'w');fwrite(fid,jsonencode(result,'PrettyPrint',true),'char');fclose(fid);
fprintf('D5 %s complete: %d/6 runs, new Plant=%d\n',candidate,completed,newPlants);
end

function row=make_row(candidate,seed,sceneId,task,runId,modelId,rawPath,startPath,plantStarted,log,core,met,b,f)
events=logical(log.stage1_position_event_inference_valid(:));
inference=double(log.stage1_position_event_inference_time_s(events));inference=inference(isfinite(inference)&inference>0);
dt=double(log.stage1_position_event_dt_s(events));dt=dt(isfinite(dt));
feature14=double(log.stage1_position_feature_14(events,:));
idx=find(events);
if isfield(log,'stage1_position_feature_input')
    featureInput=double(log.stage1_position_feature_input(events,:));featureSource='logged_candidate_input';
else
    assert(strcmp(candidate,'C2'),'D5:MissingCandidateFeature','X20 candidate input must be logged.');
    featureInput=feature14;featureSource='X14_is_runtime_input';
end
dim=size(featureInput,2);
vel=double(log.state(idx,4:6));nom=double(log.position_nominal_acceleration_mps2(idx,:));
expected=feature14;if dim==20,expected=[feature14,vel,nom];end
featureErr=max(abs(featureInput(:)-expected(:)));
tb=struct();t=double(log.transition_time(:));x=double(log.state(1:numel(t),:));r=double(log.reference.position(1:numel(t),:));e=r-x(:,1:3);
bins={'T_0_1p8',0,1.8;'T_1p8_5',1.8,5;'T_5_10',5,10;'T_10_15',10,15;'T_15_20',15,20};
for i=1:size(bins,1),m=t>=bins{i,2}&t<bins{i,3};tb.(bins{i,1})=sqrt(mean(sum(e(m,:).^2,2)));end
row=struct('candidate',candidate,'seed',seed,'scene_id',sceneId,'task',task,'run_id',runId, ...
    'model_id',modelId,'status',char(log.status),'complete',logical(core.complete),'finite',logical(core.finite), ...
    'transitions',double(core.transitions),'plant_started',logical(plantStarted),'Q_0_20_m',double(met.Q_0_20_m), ...
    'Q_5_20_m',double(met.Q_5_20_m),'A_0_20_rad',double(met.A_0_20_rad), ...
    'B_Q_0_20_m',double(b.B_Q_0_20_m),'POS_OFF_Q_0_20_m',double(b.POS_OFF_Q_0_20_m), ...
    'Initial_Q_0_20_m',double(b.P_INIT_STUDENT_Q_0_20_m),'C0_Final_Q_0_20_m',double(f.Final_Q_0_20_m), ...
    'B_A_0_20_rad',double(b.B_A_0_20_rad),'C0_Final_A_0_20_rad',double(f.Final_A_0_20_rad), ...
    'delta_Q_vs_B_m',double(met.Q_0_20_m)-double(b.B_Q_0_20_m), ...
    'delta_Q_vs_POS_OFF_m',double(met.Q_0_20_m)-double(b.POS_OFF_Q_0_20_m), ...
    'delta_Q_vs_Initial_m',double(met.Q_0_20_m)-double(b.P_INIT_STUDENT_Q_0_20_m), ...
    'delta_Q_vs_C0_Final_m',double(met.Q_0_20_m)-double(f.Final_Q_0_20_m), ...
    'position_peak_m',double(met.position_peak_m),'position_p95_m',double(met.position_p95_m), ...
    'axis_rmse_x_m',double(met.position_axis_rmse_m(1)),'axis_rmse_y_m',double(met.position_axis_rmse_m(2)), ...
    'axis_rmse_z_m',double(met.position_axis_rmse_m(3)),'motor_TV_normalized_per_s',double(met.motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(met.motor_saturation_fraction),'generalized_clip_fraction',double(met.generalized_clip_fraction), ...
    'position_event_count',nnz(log.position_event_flag),'valid_inference_event_count',nnz(events), ...
    'max_event_dt_abs_error_s',max(abs(dt-.01)),'inference_p99_s',percentile(inference,99), ...
    'inference_max_s',max_or_nan(inference),'inference_over_10ms_count',nnz(inference>.01), ...
    'runtime_feature_max_abs_error',featureErr,'time_bin_Q_json',jsonencode(tb), ...
    'runtime_feature_input_source',featureSource, ...
    'phase_metrics_json',char(met.phase_metrics_json),'raw_path',relpath(rawPath),'run_start_path',relpath(startPath));
end

function v=percentile(x,p)
if isempty(x),v=NaN;else,v=prctile(x,p);end
end
function v=max_or_nan(x)
if isempty(x),v=NaN;else,v=max(x);end
end
function yes=parse_bool(v)
if islogical(v),yes=v;elseif isnumeric(v),yes=(v~=0);else,yes=any(strcmpi(strtrim(char(string(v))),{'true','1','yes'}));end
end
function yes=scene_equal(a,b)
yes=isequaln(a.time,b.time)&&isequaln(a.initial_state,b.initial_state)&& ...
    isequaln(a.environment_wind_I,b.environment_wind_I)&&isequaln(a.reference.position,b.reference.position)&& ...
    isequaln(a.reference.velocity,b.reference.velocity)&&isequaln(a.reference.acceleration,b.reference.acceleration)&& ...
    isequaln(a.reference.yaw,b.reference.yaw)&&isequaln(a.reference.yaw_rate,b.reference.yaw_rate)&& ...
    isequaln(a.reference.yaw_acceleration,b.reference.yaw_acceleration)&&isequaln(a.arms.command,b.arms.command)&& ...
    isequaln(a.arms.rho_true,b.arms.rho_true)&&isequaln(a.arms.rhoDot_true,b.arms.rhoDot_true);
end
function yes=attitude_equal(a,b)
names={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled', ...
    'attitude_rbf_frequency_hz','rbf_attitude_gamma_scale'};yes=true;
for i=1:numel(names),yes=yes&&isfield(a,names{i})&&isfield(b,names{i})&&isequaln(a.(names{i}),b.(names{i}));end
end
function p=relpath(path)
root=char(java.io.File(pwd).getCanonicalPath());p=strrep(char(java.io.File(path).getCanonicalPath()),[root filesep],'');p=strrep(p,filesep,'/');
end
function update_state(out,n,runId,isComplete)
p=fullfile(out,'state','state.json');s=jsondecode(fileread(p));s.phase='D5_RUNNING';s.next='D5_POSITION_REPAIR_BRIDGE6';
s.d5_candidate_runs_completed=n;s.active_run_id=runId;s.d5_plant_starts_new=ledger_count(out,'D5');
s.plant_starts_new=double(s.d3_plant_starts_new)+double(s.d5_plant_starts_new);s.updated_at_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
if isComplete
    s.active_run_id=[];completed=s.completed_run_ids;
    if isstring(completed),completed=cellstr(completed);elseif ischar(completed),completed={completed};end
    if ~isempty(runId)&&~ismember(runId,completed),completed{end+1}=runId;end
    s.completed_run_ids=completed;
end
if ~isComplete,s.active_run_id=runId;end
fid=fopen(p,'w');fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
end
function n=ledger_count(out,phase)
T=readtable(fullfile(out,'RESOURCE_LEDGER.csv'),'Delimiter',',','TextType','string','VariableNamingRule','preserve');m=T.phase==string(phase)&T.resource_type=="Plant";n=sum(double(T.count(m)));
end
function append_ledger_once(out,runId,started,status)
path=fullfile(out,'RESOURCE_LEDGER.csv');if isfile(path)&&contains(fileread(path),runId),return;end
fid=fopen(path,'a');fprintf(fid,'%s,D5,Plant,%s,%d,%s,Isolated candidate P_A on frozen BRIDGE6.\n', ...
    char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')),runId,double(started),status);fclose(fid);
end
