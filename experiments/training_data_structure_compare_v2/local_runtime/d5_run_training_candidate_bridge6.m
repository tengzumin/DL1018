function result=d5_run_training_candidate_bridge6(root,family)
% Run one user-authorized model on the frozen six-scene bridge after D5 preflight.
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','training_data_structure_compare_v2');
bridgeRoot=fullfile(root,'experiments','position_causal_repair_v1');
family=upper(char(family));seed=2026101911;
pre=jsondecode(fileread(fullfile(out,'reports',['D5_PREFLIGHT_' family '.json'])));
assert(strcmp(pre.status,'PASS')&&pre.plant_starts==0,'D5:Preflight','Zero-Plant preflight must pass.');
package=fullfile(out,'models',family,['seed' num2str(seed)]);
export=jsondecode(fileread(fullfile(package,'export_report.json')));
assert(strcmp(export.status,'MATLAB_PARITY_PASS')&&strcmp(export.checkpoint_sha256,pre.checkpoint_sha256), ...
    'D5:Export','MATLAB parity status/checkpoint identity mismatch.');
q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;
assert(strcmp(char(model.model_id),sprintf('%s_SEED%d_STEP%d',family,seed,pre.selected_step)), ...
    'D5:ModelIdentity','Exported model identity differs from preflight.');

addpath(genpath(fullfile(root,'matlab')));[cfg,~,resolved]=init_dl1018();
assert(strcmp(root,resolved),'D5:Root','Unexpected DL1018 root.');
local=fullfile(out,'local_runtime');addpath(genpath(local),'-begin');rehash;
clear run_episode_dl1018 run_dl1018_closed_loop position_stage1_model_forward_v2
assert(startsWith(which('run_dl1018_closed_loop'),local,'IgnoreCase',true)&& ...
    startsWith(which('position_stage1_model_forward_v2'),local,'IgnoreCase',true)&& ...
    startsWith(which('run_episode_dl1018'),local,'IgnoreCase',true), ...
    'D5:PathIsolation','Training-candidate runtime path is not active.');
episodeHandle=@run_episode_dl1018;episodeInfo=functions(episodeHandle);
assert(startsWith(episodeInfo.file,local,'IgnoreCase',true),'D5:EpisodeHandle','Episode wrapper escaped isolated runtime.');

manifest=readtable(fullfile(bridgeRoot,'manifests','BRIDGE6.csv'),'TextType','string');
paired=readtable(fullfile(bridgeRoot,'reports','D1_G04_PAIRED_ALL.csv'),'TextType','string');
c0=readtable(fullfile(bridgeRoot,'reports','D3_INITIAL_FINAL_BRIDGE.csv'),'TextType','string');
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
ids=unique(manifest.scene_id,'stable');assert(numel(ids)==6,'D5:BridgeCount','Expected exactly six frozen scenes.');
runRoot=fullfile(out,'runs',['D5_BRIDGE6_' family '_SEED' num2str(seed)]);
if ~isfolder(runRoot),mkdir(runRoot);end
reportPath=fullfile(out,'reports',['D5_BRIDGE6_' family '.csv']);
completed=0;newPlants=0;rows=struct([]);
update_state(out,completed,'',false,family);

for si=1:numel(ids)
    sceneId=char(ids(si));specRow=manifest(manifest.scene_id==sceneId,:);
    assert(height(specRow)==3,'D5:Triplet','BRIDGE6 triplet is incomplete for %s.',sceneId);
    spec=M(M.scene_id==sceneId,:);assert(height(spec)==1,'D5:SceneSpec','Scene spec missing or repeated.');
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    opts=controller_options_dl1018(cfg,'P_A',model,[],'online');
    assert(opts.rbf_attitude_enabled&&opts.rbf_attitude_output_enabled&&opts.rbf_attitude_update_enabled&& ...
        ~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
        opts.stage1_position_runtime.enabled&&opts.stage1_position_runtime.update_enabled, ...
        'D5:ControllerMode','Candidate must use original attitude RBF and the single online position Head.');
    for ri=1:height(specRow)
        hist=specRow(ri,:);histRaw=fullfile(root,strrep(char(hist.raw_path),'/',filesep));
        hd=load(histRaw,'scene');hs=load(fullfile(fileparts(histRaw),'run_start.mat'),'runStart');
        assert(strcmp(char(hs.runStart.run_id),char(hist.run_id))&&scene_equal(scene,hd.scene)&& ...
            isequaln(cfg,hs.runStart.cfg),'D5:SceneCfg','Candidate differs from frozen scene/cfg.');
        if strcmpi(char(hist.role),'P_INIT_STUDENT')
            assert(attitude_equal(opts,hs.runStart.opts),'D5:Attitude','Candidate changed original attitude RBF settings.');
        end
    end
    runId=sprintf('D5_%s_SEED%d_%s_P_A',family,seed,sceneId);
    sceneDir=fullfile(runRoot,sceneId,'P_A');rawPath=fullfile(sceneDir,'raw_run.mat');
    startPath=fullfile(sceneDir,'run_start.mat');marker=fullfile(sceneDir,'plant_started.marker');
    metricPath=fullfile(sceneDir,'metrics.json');
    if isfile(metricPath)&&isfile(rawPath)
        saved=jsondecode(fileread(metricPath));row=saved.metrics_row;plantStarted=isfile(marker);
        runId=char(string(row.run_id));completed=completed+1;newPlants=newPlants+double(plantStarted);
        append_ledger(out,runId,plantStarted,char(saved.status));update_state(out,completed,runId,true,family);
        rows=append_row(rows,row);writetable(struct2table(rows,'AsArray',true),reportPath);
        fprintf('D5 %s %d/6 %s %s Q=%.8g A=%.8g Plant=%d (resumed)\n', ...
            family,completed,sceneId,char(saved.status),double(row.Q_0_20_m),double(row.A_0_20_rad),double(plantStarted));
        continue
    end
    if isfile(marker)&&~isfile(rawPath)
        error('D5:InterruptedPlant','Plant marker exists without raw evidence at %s; preserve and inspect before retry.',sceneDir);
    end
    if isfile(fullfile(sceneDir,'error.json'))&&~isfile(rawPath)
        error('D5:PriorError','Previous engineering error at %s needs inspection before retry.',sceneDir);
    end
    if ~isfolder(sceneDir),mkdir(sceneDir);end
    if isfile(rawPath)
        d=load(rawPath,'log','scene');log=d.log;scene=d.scene;
        assert(isfile(startPath),'D5:MissingRunStart','Raw exists without run_start; preserve and inspect.');
        rsFile=load(startPath,'rs');rs=rsFile.rs;plantStarted=isfile(marker);
    else
        started=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
        rs=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
            'gate_id','D5_TRAINING_STRUCTURE_BRIDGE6','collector_id','P_A','model_id',char(model.model_id), ...
            'candidate_family',family,'candidate_seed',seed,'candidate_selected_step',pre.selected_step, ...
            'candidate_checkpoint_sha256',export.checkpoint_sha256,'scene_spec',spec,'cfg',cfg,'opts',opts, ...
            'initial_state',scene.initial_state,'started_at',started,'source_bridge6_scene_id',sceneId);
        save(startPath,'rs','-v7');opts.r2e_first_plant_step_marker=marker;
        update_state(out,completed,runId,false,family);
        try
            log=episodeHandle(scene,'P_A',cfg,opts,rawPath);plantStarted=isfile(marker);
        catch err
            plantStarted=isfile(marker);append_ledger(out,runId,plantStarted,'ENGINEERING_ERROR');
            fid=fopen(fullfile(sceneDir,'error.json'),'w');
            fwrite(fid,jsonencode(struct('identifier',err.identifier,'message',err.message, ...
                'plant_started',plantStarted),'PrettyPrint',true),'char');fclose(fid);
            update_state(out,completed,runId,false,family);rethrow(err);
        end
        newPlants=newPlants+double(plantStarted);
    end

    core=measure_pcf_dl1018(log,scene,double(rs.opts.stage1_position_runtime.weight));
    b=paired(paired.scene_id==sceneId,:);f=c0(c0.scene_id==sceneId,:);
    assert(height(b)==1&&height(f)==1,'D5:PairRows','Frozen same-scene B/Initial/Final rows missing.');
    met=metrics_dl1018(log,scene,spec,core,double(b.B_Q_0_20_m),double(b.B_A_0_20_rad), ...
        double(b.B_position_peak_m),parse_bool(b.B_complete));
    row=make_row(family,seed,pre,sceneId,char(spec.task),runId,char(model.model_id), ...
        rawPath,startPath,plantStarted,log,core,met,b,f);
    rec=struct('status',char(log.status),'plant_started',logical(plantStarted),'metrics_row',row, ...
        'finished_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
    fid=fopen(metricPath,'w');fwrite(fid,jsonencode(rec,'PrettyPrint',true),'char');fclose(fid);
    completed=completed+1;append_ledger(out,runId,plantStarted,char(log.status));
    update_state(out,completed,runId,true,family);rows=append_row(rows,row);writetable(struct2table(rows,'AsArray',true),reportPath);
    fprintf('D5 %s %d/6 %s %s Q=%.8g A=%.8g Plant=%d\n', ...
        family,completed,sceneId,char(log.status),double(met.Q_0_20_m),double(met.A_0_20_rad),double(plantStarted));
    if ~core.complete||~core.finite||~strcmpi(char(log.status),'STABLE')
        mark_candidate_status(out,family,'HARD_STOP');
        result=write_result(out,family,seed,completed,newPlants,'STOPPED_HARD_STOP',reportPath);
        warning('D5:CandidateHardStop','Preserved this run and stopped this candidate after %s.',sceneId);
        return
    end
end

mark_candidate_status(out,family,'COMPLETE');
result=write_result(out,family,seed,completed,newPlants,'COMPLETE',reportPath);
end

function row=make_row(family,seed,pre,sceneId,task,runId,modelId,rawPath,startPath,plantStarted,log,core,met,b,f)
events=logical(log.stage1_position_event_inference_valid(:));
inference=double(log.stage1_position_event_inference_time_s(events));inference=inference(isfinite(inference)&inference>0);
featureInput=double(log.stage1_position_feature_input(events,:));feature14=double(log.stage1_position_feature_14(events,:));
expected=feature14;featureErr=max(abs(featureInput(:)-expected(:)));
t=double(log.transition_time(:));n=min(numel(t),size(log.state,1)-1);t=t(1:n);
x=double(log.state(1:n,:));r=double(log.reference.position(1:n,:));e=r-x(:,1:3);
bins={'T_0_1p8',0,1.8;'T_1p8_5',1.8,5;'T_5_10',5,10;'T_10_15',10,15;'T_15_20',15,20};
tb=struct();for i=1:size(bins,1),m=t>=bins{i,2}&t<bins{i,3};tb.(bins{i,1})=sqrt(mean(sum(e(m,:).^2,2)));end
row=struct('candidate_family',family,'seed',seed,'fit_status',pre.fit_status,'selected_step',pre.selected_step, ...
    'scene_id',sceneId,'task',task,'run_id',runId,'model_id',modelId,'status',char(log.status), ...
    'complete',logical(core.complete),'finite',logical(core.finite),'transitions',double(core.transitions), ...
    'plant_started',logical(plantStarted),'Q_0_20_m',double(met.Q_0_20_m),'Q_5_20_m',double(met.Q_5_20_m), ...
    'A_0_20_rad',double(met.A_0_20_rad),'B_Q_0_20_m',double(b.B_Q_0_20_m), ...
    'POS_OFF_Q_0_20_m',double(b.POS_OFF_Q_0_20_m),'Initial_Q_0_20_m',double(b.P_INIT_STUDENT_Q_0_20_m), ...
    'Final_Q_0_20_m',double(f.Final_Q_0_20_m),'B_A_0_20_rad',double(b.B_A_0_20_rad), ...
    'Final_A_0_20_rad',double(f.Final_A_0_20_rad),'delta_Q_vs_B_m',double(met.Q_0_20_m)-double(b.B_Q_0_20_m), ...
    'delta_Q_vs_POS_OFF_m',double(met.Q_0_20_m)-double(b.POS_OFF_Q_0_20_m), ...
    'delta_Q_vs_Initial_m',double(met.Q_0_20_m)-double(b.P_INIT_STUDENT_Q_0_20_m), ...
    'delta_Q_vs_Final_m',double(met.Q_0_20_m)-double(f.Final_Q_0_20_m), ...
    'position_peak_m',double(met.position_peak_m),'position_p95_m',double(met.position_p95_m), ...
    'axis_rmse_x_m',double(met.position_axis_rmse_m(1)),'axis_rmse_y_m',double(met.position_axis_rmse_m(2)), ...
    'axis_rmse_z_m',double(met.position_axis_rmse_m(3)),'motor_TV_normalized_per_s',double(met.motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(met.motor_saturation_fraction), ...
    'generalized_clip_fraction',double(met.generalized_clip_fraction), ...
    'position_event_count',nnz(log.position_event_flag),'valid_inference_event_count',nnz(events), ...
    'inference_p99_s',percentile(inference,99),'inference_max_s',max_or_nan(inference), ...
    'inference_over_10ms_count',nnz(inference>.01),'runtime_feature_max_abs_error',featureErr, ...
    'controller_p99_ms',double(core.controller_p99_ms),'controller_worst_ms',double(core.controller_worst_ms), ...
    'position_head_update_count',double(met.position_head_update_count), ...
    'position_head_max_fro',double(met.position_head_max_fro), ...
    'time_bin_Q_json',jsonencode(tb),'phase_metrics_json',char(met.phase_metrics_json), ...
    'safety_stop_reason',char(met.safety_stop_reason),'raw_path',relpath(rawPath),'run_start_path',relpath(startPath));
end

function rows=append_row(rows,row)
if isempty(rows),rows=row;else,rows(end+1,1)=row;end %#ok<AGROW>
end
function p=percentile(x,q)
if isempty(x),p=NaN;else,p=prctile(x,q);end
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
function result=write_result(out,family,seed,completed,newPlants,status,reportPath)
result=struct('status',status,'family',family,'seed',seed,'completed_runs',completed, ...
    'new_plant_starts',newPlants,'report_csv',reportPath);
fid=fopen(fullfile(out,'reports',['D5_RESULT_' family '.json']),'w');
fwrite(fid,jsonencode(result,'PrettyPrint',true),'char');fclose(fid);
end
function update_state(out,n,runId,isComplete,family)
p=fullfile(out,'state','state.json');s=jsondecode(fileread(p));
s.phase='D5_BRIDGE6';s.next='D5_TRAINING_STRUCTURE_BRIDGE6';s.status='IN_PROGRESS';s.active_fit='';
s.active_candidate=family;s.active_run_id=runId;s.completed_runs_in_active_candidate=n;
s.new_plant_starts=count_plants(out);s.plant_started=s.new_plant_starts;
[~,ids]=ledger_summary(out);s.plant_completed=ids;
s.updated_at_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
if isComplete,s.active_run_id='';end
fid=fopen(p,'w');fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
end
function mark_candidate_status(out,family,status)
p=fullfile(out,'state','state.json');s=jsondecode(fileread(p));
s.status='IN_PROGRESS';s.active_candidate=family;s.active_run_id='';
s.last_candidate_status=status;s.new_plant_starts=count_plants(out);
s.updated_at_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
fid=fopen(p,'w');fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
end
function n=count_plants(out)
[n,~]=ledger_summary(out);
end
function [n,ids]=ledger_summary(out)
lines=regexp(fileread(fullfile(out,'RESOURCE_LEDGER.csv')),'\r?\n','split');n=0;ids={};
for i=2:numel(lines)
    if isempty(lines{i}),continue;end
    p=strsplit(lines{i},',');
    if numel(p)>=5&&strcmp(p{3},'Plant')
        count=str2double(p{5});if isfinite(count)&&count>0,n=n+count;ids{end+1}=p{4};end %#ok<AGROW>
    end
end
end
function append_ledger(out,runId,started,status)
path=fullfile(out,'RESOURCE_LEDGER.csv');
if isfile(path)&&contains(fileread(path),runId),return;end
fid=fopen(path,'a');fprintf(fid,'%s,D5_BRIDGE6,Plant,%s,%d,%s,Frozen BRIDGE6 same-scene candidate run.\n', ...
    char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')), ...
    runId,double(started),status);fclose(fid);
end
