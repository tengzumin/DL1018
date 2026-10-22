function report=collect_position_dev_dl1018(root)
% Run fixed DEV scenes in paired B, P_F, P_A order and lock P_STAR by DEV only.
root=char(java.io.File(root).getCanonicalPath());
addpath(fullfile(root,'matlab','runtime'),fullfile(root,'matlab','data'), ...
    fullfile(root,'matlab','scenes'),fullfile(root,'matlab','models'),fullfile(root,'matlab','metrics'));
assert_scene_reference_contract_dl1018(root);
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved));
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
M=M(M.split=="DEV",:);assert(height(M)==24);
q=load(fullfile(root,'models','position','selected','matlab_model_and_parity.mat'),'model');pModel=q.model;
csvPath=fullfile(root,'reports','POSITION_DEV.csv');attemptPath=fullfile(root,'logs','attempt_index.csv');
ensure_attempt_file(attemptPath);T=table();if isfile(csvPath),T=readtable(csvPath,'TextType','string');end
methods={'B','P_F','P_A'};stopped=struct('B',false,'P_F',false,'P_A',false);
for mi=1:numel(methods),m=methods{mi};if ~isempty(T),z=T(T.method==m&(T.status~="STABLE"|~T.complete|~T.finite),:);stopped.(m)=~isempty(z);end,end
for si=1:height(M)
    spec=M(si,:);sceneId=char(spec.scene_id);built=make_scenes_dl1018('GET',root,sceneId);scene=built.scene;
    for mi=1:numel(methods)
        method=methods{mi};if stopped.(method),continue;end
        runId=sprintf('G06_P_DEV_%s_%s',sceneId,method);
        if ~isempty(T)&&any(T.run_id==runId&T.status=="STABLE"&T.complete&T.finite),continue;end
        model=[];headMode='frozen';if ~strcmp(method,'B'),model=pModel;end
        opts=controller_options_dl1018(cfg,method,model,[],headMode);
        modelId='NO_NEURAL_MODEL';if ~isempty(model),modelId='DL1018_POSITION_SELECTED';end
        attempts=read_attempts(attemptPath);prior=find(strcmp({attempts.run_id},runId));
        attemptNo=1;rawPath='';log=[];
        if ~isempty(prior)
            last=attempts(prior(end));attemptNo=last.attempt_no;
            rawPath=fullfile(root,strrep(last.raw_path,'/',filesep));marker=fullfile(fileparts(rawPath),'plant_started.marker');
            if isfile(rawPath)
                d=load(rawPath,'log','scene');log=d.log;scene=d.scene;
            elseif isfile(marker)
                error('DL1018:UnresolvedAttempt','Plant marker exists without complete raw: %s',runId);
            else
                attemptNo=attemptNo+1;
            end
        end
        if isempty(log)
            folder=fullfile(root,'data','raw','dev',sceneId,method,sprintf('attempt_%02d',attemptNo));
            if ~isfolder(folder),mkdir(folder);end
            rawPath=fullfile(folder,'raw_run.mat');marker=fullfile(folder,'plant_started.marker');
            opts.r2e_first_plant_step_marker=marker;started=utc_now();clock=tic;
            runStart=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
                'gate_id','G06_P_DEV','collector_id',method,'model_id',modelId,'scene_spec',spec, ...
                'cfg',cfg,'opts',rmfield_if(opts,'r2e_first_plant_step_marker'),'initial_state',scene.initial_state, ...
                'started_at',datetime('now','TimeZone','UTC'));
            save(fullfile(folder,'run_start.mat'),'runStart','-v7');
            a=attempt_record(runId,sceneId,spec,method,modelId,attemptNo,'RUNNING',false,0,false,false, ...
                '', '', '',relative(rawPath,root),started,'',NaN);
            append_attempt(attemptPath,a);fprintf('[G06_P_DEV] starting %d/24 %s %s\n',si,sceneId,method);
            try
                log=run_episode_dl1018(scene,method,cfg,opts,rawPath);
                n=numel(log.transition_time);complete=strcmp(log.status,'STABLE')&&n==20000;
                finite=episode_finite(log);status=char(log.status);if ~complete&&strcmp(status,'STABLE'),status='INCOMPLETE';end
                a=attempt_record(runId,sceneId,spec,method,modelId,attemptNo,status,isfile(marker),n,complete,finite, ...
                    char(field_or(log,'safety_stop_reason','')),'','',relative(rawPath,root),started,utc_now(),toc(clock));
                update_attempt(attemptPath,a);
            catch err
                a=attempt_record(runId,sceneId,spec,method,modelId,attemptNo,'ENGINEERING_ERROR',isfile(marker),0,false,false, ...
                    '',err.identifier,err.message,relative(rawPath,root),started,utc_now(),toc(clock));
                update_attempt(attemptPath,a);rethrow(err);
            end
        end
        core=measure_pcf_dl1018(log,scene,zeros(33,3));
        mm=metrics_dl1018(log,scene,spec,core,NaN,NaN,NaN,false);
        row=table(string(runId),string('G06_P_DEV'),string(sceneId),string(spec.task),double(spec.c),double(spec.w), ...
            string(method),string(modelId),string(log.status),logical(core.complete),logical(core.finite), ...
            double(core.transitions),mm.Q_0_20_m,mm.Q_5_20_m,mm.A_0_20_rad,mm.position_peak_m,mm.position_p95_m, ...
            string(jsonencode(mm.position_axis_rmse_m)),string(jsonencode(mm.attitude_axis_rmse_rad)), ...
            mm.yaw_peak_abs_rad,mm.max_motor_step_rad_s,mm.max_motor_step_time_s, ...
            mm.motor_saturation_fraction,mm.generalized_clip_fraction,mm.motor_TV_normalized_per_s, ...
            mm.motor_min_rad_s,mm.motor_max_rad_s,mm.controller_p99_ms,mm.controller_worst_ms, ...
            mm.control_loop_p99_ms,mm.joint_event_count,mm.wind_speed_rms_mps,mm.wind_speed_peak_mps,mm.wind_force_rms_N, ...
            mm.wind_force_peak_N,mm.wind_force_dominant_hz,mm.wind_torque_rms_Nm,mm.wind_torque_peak_Nm, ...
            mm.wind_torque_dominant_hz,mm.wind_input_f1_hz,mm.wind_input_f2_hz,string(mm.phase_metrics_json), ...
            double(log.divergence_time_s), ...
            mm.position_head_max_fro,mm.head_max_fro,mm.position_head_update_count,mm.head_update_count, ...
            string(mm.safety_stop_reason),string(relative(rawPath,root)), ...
            'VariableNames',{'run_id','gate_id','scene_id','task','class_index','wind_cell','method','model_id','status', ...
            'complete','finite','transitions','Q_0_20_m','Q_5_20_m','A_0_20_rad','position_peak_m','position_p95_m', ...
            'position_axis_rmse_m','attitude_axis_rmse_rad','yaw_peak_abs_rad','max_motor_step_rad_s','max_motor_step_time_s', ...
            'motor_saturation_fraction','generalized_clip_fraction','motor_TV_normalized_per_s','motor_min_rad_s', ...
            'motor_max_rad_s','controller_p99_ms','controller_worst_ms','control_loop_p99_ms','joint_event_count', ...
            'wind_speed_rms_mps','wind_speed_peak_mps','wind_force_rms_N','wind_force_peak_N','wind_force_dominant_hz', ...
            'wind_torque_rms_Nm','wind_torque_peak_Nm','wind_torque_dominant_hz','wind_input_f1_hz','wind_input_f2_hz', ...
            'phase_metrics_json','time_to_stop_s','position_head_max_fro','attitude_head_max_fro', ...
            'position_head_update_count','attitude_head_update_count','safety_stop_reason','raw_path'});
        if isempty(T),T=row;else,T=T(T.run_id~=runId,:);T=[T;row];end
        writetable(T,csvPath);
        if ~core.complete||~core.finite||~strcmp(log.status,'STABLE')
            stopped.(method)=true;if strcmp(method,'B'),error('DL1018:BaselineUnsafe','B failed on %s.',sceneId);end
        end
        fprintf('[G06_P_DEV] saved %s %s status=%s Q=%.8g A=%.8g\n',sceneId,method,log.status,mm.Q_0_20_m,mm.A_0_20_rad);
    end
end
scoreF=score_position_mode(T,'P_F',M);scoreA=score_position_mode(T,'P_A',M);
chosen=choose_position_mode(scoreF,scoreA);pass=~isempty(chosen);
if pass
    sm.position_selected_head_mode=chosen;sm.position_star_method=iff(strcmp(chosen,'frozen'),'P_F','P_A');
    sm.position_selected_id='DL1018_POSITION_SELECTED';write_json(fullfile(root,'configs','selected_models.json'),sm);
end
report=struct('gate_id','G06_P_DEV','status',iff(pass,'PASS','STOP_POSITION_NOT_QUALIFIED'), ...
    'contract_version','DL1018_V311_R2E_PAPER_FINAL','upstream_passed',true, ...
    'model_id','DL1018_POSITION_SELECTED','actual_counts',struct('plant_started',count_gate_attempts(attemptPath,'G06_P_DEV'), ...
    'complete',nnz(T.gate_id=="G06_P_DEV"&T.status=="STABLE"),'physical_failures',nnz(T.gate_id=="G06_P_DEV"&T.status~="STABLE"), ...
    'engineering_errors',count_gate_status(attemptPath,'G06_P_DEV','ENGINEERING_ERROR')), ...
    'checks',struct('P_F',scoreF,'P_A',scoreA,'position_selected_head_mode',chosen, ...
    'P_STAR',iff(strcmp(chosen,'frozen'),'P_F','P_A'),'scenes',24), ...
    'max_errors',struct,'artifacts',{{'reports/POSITION_DEV.csv','configs/selected_models.json', ...
    'logs/attempt_index.csv','data/raw/dev'}},'next_gate_allowed',pass, ...
    'blocking_reason',iff(pass,'','Neither P_F nor P_A passed the predeclared DEV thresholds.'));
write_gate_report_dl1018(fullfile(root,'reports','G06_P_DEV.json'),report);
end
function s=score_position_mode(T,method,M)
b=T(T.method=="B",:);c=T(T.method==method,:);tasks=unique(b.task,'stable');per=struct;allTask=true;wins=0;warn=0;serious=0;qBtask=[];qCtask=[];pCtask=[];
s=struct('method',method,'pass',false,'n',height(c),'macro_Q',NaN,'macro_peak',NaN,'total_wins',0, ...
    'peak_warnings',0,'severe_peaks',0,'per_task',struct,'checks',struct);
if isempty(b)||isempty(c),return;end
coverageB=expected_scene_rows(b,M);coverageC=expected_scene_rows(c,M);
for i=1:numel(tasks)
    task=tasks(i);bt=b(b.task==task,:);ct=c(c.task==task,:);[~,ib,ic]=intersect(bt.scene_id,ct.scene_id,'stable');bt=bt(ib,:);ct=ct(ic,:);
    n=8;full=coverageB&&coverageC&&height(ct)==n&&all(bt.complete)&&all(ct.complete)&&all(bt.finite)&&all(ct.finite)&&all(bt.transitions==20000)&&all(ct.transitions==20000);
    qb=mean(bt.Q_0_20_m);qc=mean(ct.Q_0_20_m);ab=mean(bt.A_0_20_rad);ac=mean(ct.A_0_20_rad);
    nw=nnz(ct.Q_0_20_m<bt.Q_0_20_m-1e-9);np=nnz(ct.position_peak_m>1.2*bt.position_peak_m+.01);
    ns=nnz(ct.position_peak_m>2*bt.position_peak_m&(ct.position_peak_m-bt.position_peak_m)>.05);
    sat=all(ct.motor_saturation_fraction<=bt.motor_saturation_fraction+.005);
    clip=all(ct.generalized_clip_fraction<=bt.generalized_clip_fraction+.005);
    timing=all(ct.controller_p99_ms<10);motor=all(ct.motor_min_rad_s>=0&ct.motor_max_rad_s<=1900);
    pass=full&&qc<=1.05*qb+.002&&nw>=4&&ac<=1.10*ab+.002&&sat&&clip&&timing&&motor&&ns<3;
    key=matlab.lang.makeValidName(char(task));per.(key)=struct('n',height(ct),'Q_B_m',qb,'Q_candidate_m',qc, ...
        'A_B_rad',ab,'A_candidate_rad',ac,'wins',nw,'peak_warnings',np,'severe_peaks',ns,'complete_finite',full,'pass',pass);
    allTask=allTask&&pass;wins=wins+nw;warn=warn+np;serious=serious+ns;qBtask(end+1)=qb;qCtask(end+1)=qc;pCtask(end+1)=mean(ct.position_peak_m); %#ok<AGROW>
end
macroB=mean(qBtask);macroC=mean(qCtask);macroPeak=mean(pCtask);
s.pass=allTask&&macroC<macroB-1e-9&&wins>=18&&warn<=1;s.macro_Q=macroC;s.macro_peak=macroPeak;
s.total_wins=wins;s.peak_warnings=warn;s.severe_peaks=serious;s.per_task=per;
s.checks=struct('baseline_scene_coverage',coverageB,'candidate_scene_coverage',coverageC, ...
    'macro_Q_improves',macroC<macroB-1e-9,'total_win_count',wins,'total_wins_pass',wins>=18, ...
    'peak_warning_count',warn,'peak_warning_pass',warn<=1,'per_task_rules_pass',allTask);
end
function ok=expected_scene_rows(R,M)
ok=height(R)==height(M)&&numel(unique(R.scene_id))==height(M)&&all(ismember(M.scene_id,R.scene_id));
if ~ok,return;end
[found,ix]=ismember(M.scene_id,R.scene_id);
ok=all(found)&&all(R.task(ix)==M.task)&&all(R.class_index(ix)==M.c)&&all(R.wind_cell(ix)==M.w);
end
function m=choose_position_mode(f,a)
m='';if f.pass&&~a.pass,m='frozen';elseif a.pass&&~f.pass,m='online';elseif f.pass&&a.pass
    if f.macro_Q<a.macro_Q-1e-9,m='frozen';elseif a.macro_Q<f.macro_Q-1e-9,m='online';
    elseif f.macro_peak<=a.macro_peak,m='frozen';else,m='online';end
end
end
function ensure_attempt_file(p)
if isfile(p),return;end;cols=attempt_cols();f=fopen(p,'w');assert(f>=0);fprintf(f,'%s\n',strjoin(cols,','));fclose(f);
end
function c=attempt_cols()
c={'run_id','gate_id','split','scene_id','task','class_index','wind_cell','collector_id','model_id','contract_version','runtime_mode', ...
    'attempt_no','status','plant_started','returned_transitions','complete','finite','safety_stop_reason','error_kind','error_message', ...
    'raw_path','position_event_path','attitude_event_path','started_at','finished_at','elapsed_s','accepted_for_training'};
end
function a=read_attempts(p)
a=struct([]);if ~isfile(p),return;end;T=readtable(p,'TextType','string');a=table2struct(T);
for i=1:numel(a),a(i).run_id=char(a(i).run_id);a(i).raw_path=char(a(i).raw_path);a(i).gate_id=char(a(i).gate_id);a(i).attempt_no=double(a(i).attempt_no);a(i).plant_started=logical_value(a(i).plant_started);end
end
function a=attempt_record(id,scene,spec,method,model,no,status,startedFlag,n,complete,finite,safety,err,msg,raw,start,finish,elapsed)
a=struct('run_id',id,'gate_id','G06_P_DEV','split','dev','scene_id',scene,'task',char(spec.task), ...
    'class_index',double(spec.c),'wind_cell',double(spec.w),'collector_id',method,'model_id',model, ...
    'contract_version','DL1018_V311_R2E_PAPER_FINAL','runtime_mode','MATLAB_R2025b','attempt_no',no, ...
    'status',status,'plant_started',startedFlag,'returned_transitions',n,'complete',complete,'finite',finite, ...
    'safety_stop_reason',safety,'error_kind',err,'error_message',msg,'raw_path',raw, ...
    'position_event_path','','attitude_event_path','','started_at',start,'finished_at',finish, ...
    'elapsed_s',elapsed,'accepted_for_training',false);
end
function append_attempt(p,a)
v=struct2cell(orderfields(a,attempt_cols()));f=fopen(p,'a');assert(f>=0);c=onCleanup(@()fclose(f));fprintf(f,'%s\n',csvline(v));clear c;
end
function update_attempt(p,a)
L=readlines(p);for i=numel(L):-1:2,q=split(L(i),',');if numel(q)>=12&&q(1)==string(a.run_id)&&str2double(q(12))==a.attempt_no,L(i)=string(csvline(struct2cell(orderfields(a,attempt_cols()))));break;end,end
f=fopen(p,'w');assert(f>=0);c=onCleanup(@()fclose(f));for i=1:numel(L),fprintf(f,'%s\n',char(L(i)));end;clear c;
end
function s=csvline(v)
p=cell(size(v));for i=1:numel(v),x=v{i};if isempty(x),p{i}='';elseif islogical(x),p{i}=char(string(x));elseif isnumeric(x),if isscalar(x)&&isnan(x),p{i}='';else,p{i}=sprintf('%.17g',x);end;else,p{i}=char(string(x));end;p{i}=strrep(strrep(strrep(strrep(p{i},',',';'),newline,' '),char(13),' '),'"','''');end;s=strjoin(p,',');
end
function n=count_gate_attempts(p,g),a=read_attempts(p);n=nnz(strcmp({a.gate_id},g)&[a.plant_started]);end
function n=count_gate_status(p,g,s),a=read_attempts(p);n=nnz(strcmp({a.gate_id},g)&strcmp({a.status},s));end
function y=logical_value(x),if islogical(x),y=x;elseif isnumeric(x),y=x~=0;else,y=ismember(lower(string(x)),["true","1","yes"]);end,end
function ok=episode_finite(log)
f={'state','transition_time','wind_force_I','wind_torque_B','requested_generalized','controller_clipped_generalized','realized_generalized', ...
    'motor_command','motor_setpoint','position_compensation_applied_force_N','attitude_compensation_applied_torque_Nm'};ok=true;
for i=1:numel(f),if isfield(log,f{i}),ok=ok&&all(isfinite(log.(f{i})),'all');end,end
end
function s=field_or(x,n,d),if isfield(x,n),s=x.(n);else,s=d;end,end
function s=rmfield_if(x,n),if isfield(x,n),s=rmfield(x,n);end,end
function s=relative(p,r),p=char(java.io.File(p).getCanonicalPath());r=char(java.io.File(r).getCanonicalPath());assert(startsWith(lower(p),lower([r filesep])));s=strrep(p(numel(r)+2:end),'\','/');end
function s=utc_now(),d=datetime('now','TimeZone','UTC');d.Format='yyyy-MM-dd''T''HH:mm:ss.SSS''Z''';s=char(d);end
function write_json(p,v),tmp=[p '.tmp'];f=fopen(tmp,'w');assert(f>=0);c=onCleanup(@()fclose(f));fwrite(f,jsonencode(v,'PrettyPrint',true),'char');fwrite(f,newline,'char');clear c;movefile(tmp,p,'f');end
function v=iff(c,a,b),if c,v=a;else,v=b;end,end
