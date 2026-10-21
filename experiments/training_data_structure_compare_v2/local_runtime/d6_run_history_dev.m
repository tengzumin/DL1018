function report=d6_run_history_dev(root)
% Isolated 24-scene P_F/P_A DEV evaluation of the frozen user-paused History KAN snapshot.
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','training_data_structure_compare_v2');
pre=jsondecode(fileread(fullfile(out,'reports','D6_PREFLIGHT_HISTORY.json')));
assert(strcmp(pre.status,'PASS')&&pre.plant_starts==0,'D6:Preflight','D6 zero-Plant preflight must pass.');
q=load(fullfile(out,'models','HISTORY_KAN','seed2026101911','matlab_model_and_parity.mat'),'model');model=q.model;
export=jsondecode(fileread(fullfile(out,'models','HISTORY_KAN','seed2026101911','export_report.json')));
addpath(genpath(fullfile(root,'matlab')));[cfg,~,resolved]=init_dl1018();
assert(strcmp(root,resolved),'D6:Root','Unexpected DL1018 root.');
local=fullfile(out,'local_runtime');addpath(genpath(local),'-begin');rehash;
clear run_episode_dl1018 run_dl1018_closed_loop position_stage1_model_forward_v2
assert(startsWith(which('run_dl1018_closed_loop'),local,'IgnoreCase',true)&& ...
    startsWith(which('position_stage1_model_forward_v2'),local,'IgnoreCase',true)&& ...
    startsWith(which('run_episode_dl1018'),local,'IgnoreCase',true), ...
    'D6:PathIsolation','The isolated candidate runtime is not active.');
episodeHandle=@run_episode_dl1018;episodeInfo=functions(episodeHandle);
assert(startsWith(episodeInfo.file,local,'IgnoreCase',true),'D6:EpisodeHandle','Episode wrapper escaped isolated runtime.');
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');M=M(M.split=="DEV",:);
assert(height(M)==24,'D6:SceneCount','Expected 24 fixed DEV scenes.');
baseline=readtable(fullfile(root,'reports','POSITION_DEV.csv'),'TextType','string');
baseline=baseline(baseline.method=="B",:);assert(height(baseline)==24,'D6:Baseline','Expected 24 reused B rows.');
runRoot=fullfile(out,'runs','D6_HISTORY_CANDIDATE_DEV');if ~isfolder(runRoot),mkdir(runRoot);end
reportPath=fullfile(out,'reports','D6_HISTORY_CANDIDATE_DEV.csv');rows=struct([]);halt=false;newPlants=0;
update_state(out,'P_F',0,'',false);
for mi=1:2
    if halt,break;end
    if mi==1,method='P_F';headMode='frozen';else,method='P_A';headMode='online';end
    update_state(out,method,0,'',false);
    for si=1:height(M)
        spec=M(si,:);sceneId=char(spec.scene_id);b=baseline(baseline.scene_id==sceneId,:);
        assert(height(b)==1&&b.status=="STABLE"&&b.complete&&b.finite&&b.transitions==20000, ...
            'D6:BaselineStatus','Reused B row is invalid at %s.',sceneId);
        runId=sprintf('D6_HISTORY15K_%s_%s',sceneId,method);
        sceneDir=fullfile(runRoot,sceneId,method);rawPath=fullfile(sceneDir,'raw_run.mat');
        startPath=fullfile(sceneDir,'run_start.mat');marker=fullfile(sceneDir,'plant_started.marker');
        metricPath=fullfile(sceneDir,'metrics.json');
        if isfile(metricPath)&&isfile(rawPath)
            saved=jsondecode(fileread(metricPath));row=saved.metrics_row;runId=char(string(row.run_id));
            plantStarted=isfile(marker);rows=append_row(rows,row);writetable(struct2table(rows,'AsArray',true),reportPath);
            update_state(out,method,si,runId,true);fprintf('D6 %s %d/24 %s STABLE Q=%.8g A=%.8g Plant=%d (resumed)\n', ...
                method,si,sceneId,double(row.Q_0_20_m),double(row.A_0_20_rad),double(plantStarted));
            if ~logical(row.complete)||~logical(row.finite)||~strcmpi(char(row.status),'STABLE')
                halt=true;break
            end
            continue
        end
        if isfile(marker)&&~isfile(rawPath)
            error('D6:InterruptedPlant','Marker exists without raw evidence at %s; preserve and inspect.',sceneDir);
        end
        if isfile(fullfile(sceneDir,'error.json'))&&~isfile(rawPath)
            error('D6:PriorError','Prior engineering error requires inspection at %s.',sceneDir);
        end
        if ~isfolder(sceneDir),mkdir(sceneDir);end
        if isfile(rawPath)
            d=load(rawPath,'log','scene');log=d.log;scene=d.scene;
            assert(isfile(startPath),'D6:MissingRunStart','Raw exists without run-start record.');
            sr=load(startPath,'runStart');runStart=sr.runStart;plantStarted=isfile(marker);
        else
            assert(count_plants(out)<80,'D6:PlantBudget','The 80-start task budget is exhausted.');
            sceneBuilt=make_scenes_dl1018('GET',root,sceneId);scene=sceneBuilt.scene;
            opts=controller_options_dl1018(cfg,method,model,[],headMode);
            assert(opts.stage1_position_runtime.enabled&& ...
                (strcmp(method,'P_F')&&~opts.stage1_position_runtime.update_enabled|| ...
                 strcmp(method,'P_A')&&opts.stage1_position_runtime.update_enabled), ...
                'D6:HeadMode','Incorrect frozen/online Head mode for %s.',method);
            opts.r2e_first_plant_step_marker=marker;
            started=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
            runStart=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
                'gate_id','D6_HISTORY_CANDIDATE_DEV','split','DEV','collector_id',method, ...
                'model_id',char(model.model_id),'candidate_family','HISTORY_KAN', ...
                'candidate_fit_status','PAUSED_BY_USER_PARTIAL_FIT','candidate_selected_step',15000, ...
                'candidate_checkpoint_sha256',export.checkpoint_sha256,'scene_spec',spec,'cfg',cfg, ...
                'opts',rmfield_if(opts,'r2e_first_plant_step_marker'),'initial_state',scene.initial_state, ...
                'started_at',started,'reused_B_run_id',char(b.run_id));
            save(startPath,'runStart','-v7');
            update_state(out,method,si,runId,false);
            try
                log=episodeHandle(scene,method,cfg,opts,rawPath);plantStarted=isfile(marker);newPlants=newPlants+double(plantStarted);
            catch err
                plantStarted=isfile(marker);append_ledger(out,runId,plantStarted,'ENGINEERING_ERROR');
                fid=fopen(fullfile(sceneDir,'error.json'),'w');
                fwrite(fid,jsonencode(struct('identifier',err.identifier,'message',err.message, ...
                    'plant_started',plantStarted),'PrettyPrint',true),'char');fclose(fid);
                update_state(out,method,si,runId,false);rethrow(err);
            end
        end

        core=measure_pcf_dl1018(log,scene,zeros(33,3));
        met=metrics_dl1018(log,scene,spec,core,double(b.Q_0_20_m),double(b.A_0_20_rad), ...
            double(b.position_peak_m),true);
        row=make_row(method,sceneId,char(spec.task),double(spec.c),double(spec.w),runId, ...
            char(model.model_id),rawPath,startPath,plantStarted,log,core,met,b);
        rec=struct('status',char(log.status),'plant_started',logical(plantStarted),'metrics_row',row, ...
            'finished_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
        fid=fopen(metricPath,'w');fwrite(fid,jsonencode(rec,'PrettyPrint',true),'char');fclose(fid);
        append_ledger(out,runId,plantStarted,char(log.status));rows=append_row(rows,row);
        writetable(struct2table(rows,'AsArray',true),reportPath);update_state(out,method,si,runId,true);
        fprintf('D6 %s %d/24 %s %s Q=%.8g B=%.8g A=%.8g Plant=%d\n', ...
            method,si,sceneId,char(log.status),double(met.Q_0_20_m),double(b.Q_0_20_m), ...
            double(met.A_0_20_rad),double(plantStarted));
        if ~core.complete||~core.finite||~strcmpi(char(log.status),'STABLE')
            halt=true;update_state(out,method,si,runId,true);break
        end
    end
end

if isfile(reportPath),candidate=readtable(reportPath,'TextType','string');else,candidate=table();end
baseB=baseline;
scoreF=score_mode(candidate,baseB,'P_F',M);scoreA=score_mode(candidate,baseB,'P_A',M);
chosen=choose_mode(scoreF,scoreA);
allRuns=number_started(out);status='STOP_POSITION_NOT_QUALIFIED';if ~isempty(chosen),status='PASS_EXPLORATORY_POSITION_DEV';end
report=struct('gate_id','D6_HISTORY_CANDIDATE_DEV','status',status,'original_G06_status_unchanged',true, ...
    'candidate_family','HISTORY_KAN','model_id',char(model.model_id),'seed',2026101911,'selected_step',15000, ...
    'fit_status','PAUSED_BY_USER_PARTIAL_FIT','upstream_canary_passed',true, ...
    'actual_counts',struct('new_plant_starts',allRuns,'completed_candidate_rows',height(candidate), ...
    'complete',height(candidate)>0&&all(candidate.complete),'finite',height(candidate)>0&&all(candidate.finite), ...
    'physical_failures',height(candidate)>0&&nnz(candidate.status~="STABLE")), ...
    'checks',struct('P_F',scoreF,'P_A',scoreA,'position_selected_head_mode',chosen, ...
        'P_STAR',iff(strcmp(chosen,'frozen'),'P_F',iff(strcmp(chosen,'online'),'P_A','')), ...
        'scenes',24,'B_reused_rows',height(baseB)), ...
    'next_gate_allowed',~isempty(chosen),'plant_budget_max',80,'reserved_dev_budget',0, ...
    'notes',{{'This independent exploratory DEV does not overwrite reports/G06_P_DEV.json or the original selected-model config.', ...
    'The model is the frozen user-paused best checkpoint at 15k/60k; no training or second seed was run.'}});
fid=fopen(fullfile(out,'reports','D6_HISTORY_CANDIDATE_DEV.json'),'w');
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fclose(fid);
if ~isempty(candidate)
    basePair=baseB(:,{'scene_id','Q_0_20_m','A_0_20_rad','position_peak_m'});
    basePair.Properties.VariableNames={'scene_id','B_Q_0_20_m','B_A_0_20_rad','B_position_peak_m'};
    paired=join(candidate,basePair,'Keys','scene_id');
    writetable(paired,fullfile(out,'reports','D6_HISTORY_CANDIDATE_DEV_PAIRED.csv'));
end
update_final_state(out,status,chosen,allRuns);
if ~isempty(chosen),write_position_ready(out,report);end
fprintf('D6 complete: status=%s P_F=%d P_A=%d new Plant=%d P_STAR=%s\n', ...
    status,scoreF.pass,scoreA.pass,allRuns,chosen);
end

function row=make_row(method,sceneId,task,c,w,runId,modelId,rawPath,startPath,plantStarted,log,core,met,b)
row=struct('run_id',runId,'gate_id','D6_HISTORY_CANDIDATE_DEV','scene_id',sceneId,'task',task, ...
    'class_index',c,'wind_cell',w,'method',method,'model_id',modelId,'status',char(log.status), ...
    'complete',logical(core.complete),'finite',logical(core.finite),'transitions',double(core.transitions), ...
    'plant_started',logical(plantStarted),'Q_0_20_m',double(met.Q_0_20_m),'Q_5_20_m',double(met.Q_5_20_m), ...
    'A_0_20_rad',double(met.A_0_20_rad),'B_Q_0_20_m',double(b.Q_0_20_m),'B_A_0_20_rad',double(b.A_0_20_rad), ...
    'B_position_peak_m',double(b.position_peak_m),'delta_Q_vs_B_m',double(met.Q_0_20_m)-double(b.Q_0_20_m), ...
    'position_peak_m',double(met.position_peak_m),'position_p95_m',double(met.position_p95_m), ...
    'position_axis_rmse_m',jsonencode(met.position_axis_rmse_m), ...
    'attitude_axis_rmse_rad',jsonencode(met.attitude_axis_rmse_rad), ...
    'motor_saturation_fraction',double(met.motor_saturation_fraction), ...
    'generalized_clip_fraction',double(met.generalized_clip_fraction), ...
    'motor_TV_normalized_per_s',double(met.motor_TV_normalized_per_s), ...
    'motor_min_rad_s',double(met.motor_min_rad_s),'motor_max_rad_s',double(met.motor_max_rad_s), ...
    'controller_p99_ms',double(met.controller_p99_ms),'controller_worst_ms',double(met.controller_worst_ms), ...
    'control_loop_p99_ms',double(met.control_loop_p99_ms),'position_head_update_count',double(met.position_head_update_count), ...
    'position_head_max_fro',double(met.position_head_max_fro),'phase_metrics_json',char(met.phase_metrics_json), ...
    'safety_stop_reason',char(met.safety_stop_reason), ...
    'raw_path',relpath(rawPath),'run_start_path',relpath(startPath));
end

function s=score_mode(C,B,method,M)
s=struct('method',method,'pass',false,'n',0,'macro_Q',NaN,'macro_B_Q',NaN,'macro_peak',NaN,'total_wins',0, ...
    'peak_warnings',0,'severe_peaks',0,'per_task',struct,'checks',struct);
if isempty(C)||isempty(B),return;end
c=C(C.method==method,:);b=B(B.method=="B",:);s.n=height(c);if isempty(c),return;end
coverage=height(c)==height(M)&&numel(unique(c.scene_id))==height(M)&&all(ismember(M.scene_id,c.scene_id));
tasks=unique(M.task,'stable');allTask=coverage;wins=0;warnings=0;severe=0;qC=[];qB=[];pC=[];per=struct;
for i=1:numel(tasks)
    task=tasks(i);bt=b(b.task==task,:);ct=c(c.task==task,:);
    [~,ib,ic]=intersect(bt.scene_id,ct.scene_id,'stable');bt=bt(ib,:);ct=ct(ic,:);
    full=height(bt)==8&&height(ct)==8&&all(bt.complete)&&all(ct.complete)&&all(bt.finite)&&all(ct.finite)&& ...
        all(bt.transitions==20000)&&all(ct.transitions==20000)&&all(bt.status=="STABLE")&&all(ct.status=="STABLE");
    qb=mean(bt.Q_0_20_m);qc=mean(ct.Q_0_20_m);ab=mean(bt.A_0_20_rad);ac=mean(ct.A_0_20_rad);
    nw=nnz(ct.Q_0_20_m<bt.Q_0_20_m-1e-9);
    nwarn=nnz(ct.position_peak_m>1.2*bt.position_peak_m+.01);
    nsevere=nnz(ct.position_peak_m>2*bt.position_peak_m&(ct.position_peak_m-bt.position_peak_m)>.05);
    sat=all(ct.motor_saturation_fraction<=bt.motor_saturation_fraction+.005);
    clip=all(ct.generalized_clip_fraction<=bt.generalized_clip_fraction+.005);
    timing=all(ct.controller_p99_ms<10);
    motors=all(ct.motor_min_rad_s>=0&ct.motor_max_rad_s<=1900);
    pass=full&&qc<=1.05*qb+.002&&nw>=4&&ac<=1.10*ab+.002&&sat&&clip&&timing&&motors&&nsevere<3;
    key=matlab.lang.makeValidName(char(task));per.(key)=struct('n',height(ct),'Q_B_m',qb,'Q_candidate_m',qc, ...
        'A_B_rad',ab,'A_candidate_rad',ac,'wins',nw,'peak_warnings',nwarn, ...
        'severe_peaks',nsevere,'complete_finite',full,'pass',pass);
    allTask=allTask&&pass;wins=wins+nw;warnings=warnings+nwarn;severe=severe+nsevere;
    qB(end+1)=qb;qC(end+1)=qc;pC(end+1)=mean(ct.position_peak_m); %#ok<AGROW>
end
macroB=mean(qB);macroC=mean(qC);
s.pass=allTask&&macroC<macroB-1e-9&&wins>=18&&warnings<=1;
s.macro_Q=macroC;s.macro_B_Q=macroB;s.macro_peak=mean(pC);s.total_wins=wins;s.peak_warnings=warnings;
s.severe_peaks=severe;s.per_task=per;
s.checks=struct('candidate_scene_coverage',coverage,'macro_Q_improves',macroC<macroB-1e-9, ...
    'total_win_count',wins,'total_wins_pass',wins>=18,'peak_warning_count',warnings, ...
    'peak_warning_pass',warnings<=1,'per_task_rules_pass',allTask);
end
function mode=choose_mode(f,a)
mode='';if f.pass&&~a.pass,mode='frozen';elseif a.pass&&~f.pass,mode='online';elseif f.pass&&a.pass
    if f.macro_Q<a.macro_Q-1e-9,mode='frozen';elseif a.macro_Q<f.macro_Q-1e-9,mode='online';
    elseif f.macro_peak<=a.macro_peak,mode='frozen';else,mode='online';end
end
end
function rows=append_row(rows,row)
if isempty(rows),rows=row;else,rows(end+1,1)=row;end %#ok<AGROW>
end
function update_state(out,method,n,runId,isComplete)
p=fullfile(out,'state','state.json');s=jsondecode(fileread(p));s.phase='D6_HISTORY_CANDIDATE_DEV';
s.status='IN_PROGRESS';s.next='RUN_FROZEN_HISTORY_15K_PF_PA_ON_24_DEV_SCENES';s.active_candidate='HISTORY_KAN_STEP15000';
s.active_mode=method;s.completed_runs_in_mode=n;s.active_run_id=runId;s.new_plant_starts=count_plants(out);
s.plant_started=s.new_plant_starts;s.updated_at_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
if isComplete,s.active_run_id='';end
fid=fopen(p,'w');fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
end
function update_final_state(out,status,mode,n)
p=fullfile(out,'state','state.json');s=jsondecode(fileread(p));s.phase='D6_POSITION_DEV_COMPLETE';
s.status=status;s.next=iff(isempty(mode),'STOP_NO_POSITION_CANDIDATE_QUALIFIED','POSITION_READY_FOR_ATTITUDE_REVIEW');
s.active_candidate='';s.active_mode='';s.active_run_id='';s.position_star_mode=mode;
s.new_plant_starts=count_plants(out);s.plant_started=s.new_plant_starts;s.d6_plant_starts=n;
s.updated_at_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
fid=fopen(p,'w');fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
end
function n=count_plants(out),[n,~]=ledger_summary(out);end
function [n,ids]=ledger_summary(out)
lines=regexp(fileread(fullfile(out,'RESOURCE_LEDGER.csv')),'\r?\n','split');n=0;ids={};
for i=2:numel(lines)
    if isempty(lines{i}),continue;end;p=strsplit(lines{i},',');
    if numel(p)>=5&&strcmp(p{3},'Plant'),v=str2double(p{5});if isfinite(v)&&v>0,n=n+v;ids{end+1}=p{4};end,end %#ok<AGROW>
end
end
function append_ledger(out,id,started,status)
path=fullfile(out,'RESOURCE_LEDGER.csv');if isfile(path)&&contains(fileread(path),id),return;end
f=fopen(path,'a');fprintf(f,'%s,D6_POSITION_DEV,Plant,%s,%d,%s,Frozen History KAN step15000 candidate P_F/P_A on fixed DEV.\n', ...
    char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')),id,double(started),status);fclose(f);
end
function n=number_started(out)
lines=regexp(fileread(fullfile(out,'RESOURCE_LEDGER.csv')),'\r?\n','split');n=0;
for i=2:numel(lines)
    if isempty(lines{i}),continue;end;p=strsplit(lines{i},',');
    if numel(p)>=5&&strcmp(p{2},'D6_POSITION_DEV')&&strcmp(p{3},'Plant')
        v=str2double(p{5});if isfinite(v),n=n+v;end
    end
end
end
function yes=scene_equal(a,b)
yes=isequaln(a.time,b.time)&&isequaln(a.initial_state,b.initial_state)&& ...
    isequaln(a.environment_wind_I,b.environment_wind_I)&&isequaln(a.reference.position,b.reference.position)&& ...
    isequaln(a.reference.velocity,b.reference.velocity)&&isequaln(a.reference.acceleration,b.reference.acceleration)&& ...
    isequaln(a.reference.yaw,b.reference.yaw)&&isequaln(a.reference.yaw_rate,b.reference.yaw_rate)&& ...
    isequaln(a.reference.yaw_acceleration,b.reference.yaw_acceleration)&&isequaln(a.arms.command,b.arms.command)&& ...
    isequaln(a.arms.rho_true,b.arms.rho_true)&&isequaln(a.arms.rhoDot_true,b.arms.rhoDot_true);
end
function write_position_ready(out,report)
text={ '# POSITION_READY_FOR_ATTITUDE', '', ...
    '本轮独立探索性 DEV 通过。锁定的是 `HISTORY_KAN_SEED2026101911_STEP15000`，当前候选文件位于 `models/HISTORY_KAN/seed2026101911/best_model.pt`，MATLAB 前向包为 `matlab_model_and_parity.mat`。该拟合按用户要求暂停于 18k/60k，因此这是冻结 checkpoint 的探索性结果，不是完整 60k fit。', '', ...
    '本报告不改变原 G06 失败、根目录的 selected_models.json、B、任务合同或原始 Plant。已有 B 的 24 场 DEV 记录经 scene/config/run identity 核验后复用；本轮 P_F/P_A 是新运行。', '', ...
    '姿态后续如开展，仅使用新锁定的位置包；姿态训练标签优先复用已有 B/Initial/Final 的姿态数据，按场景身份配对，并单独审查哪些数据的控制条件仍匹配。不要自动启动大规模姿态采集。', '', ...
    sprintf('DEV status: %s; selected Head mode: %s; new Plant starts: %d.',report.status,report.checks.position_selected_head_mode,report.actual_counts.new_plant_starts) };
fid=fopen(fullfile(out,'reports','POSITION_READY_FOR_ATTITUDE.md'),'w');fwrite(fid,strjoin(text,newline),'char');fwrite(fid,newline,'char');fclose(fid);
end
function p=relpath(path)
root=char(java.io.File(pwd).getCanonicalPath());p=strrep(char(java.io.File(path).getCanonicalPath()),[root filesep],'');p=strrep(p,filesep,'/');
end
function s=rmfield_if(x,n),if isfield(x,n),s=rmfield(x,n);else,s=x;end,end
function v=iff(c,a,b),if c,v=a;else,v=b;end,end
