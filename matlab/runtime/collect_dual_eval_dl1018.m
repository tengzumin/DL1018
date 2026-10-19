function report=collect_dual_eval_dl1018(root,gateId)
% Collect fixed PA DEV or sealed FINAL_TEST runs without changing model locks.
root=char(java.io.File(root).getCanonicalPath());gateId=upper(char(gateId));
assert(ismember(gateId,{'G11_PA_DEV','G12_FINAL_TEST'}));
addpath(fullfile(root,'matlab','runtime'),fullfile(root,'matlab','data'), ...
    fullfile(root,'matlab','scenes'),fullfile(root,'matlab','models'),fullfile(root,'matlab','metrics'));
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved));
smPath=fullfile(root,'configs','selected_models.json');sm=jsondecode(fileread(smPath));
assert(isfield(sm,'position_star_method')&&isfield(sm,'position_selected_head_mode'));
p=load(fullfile(root,'models','position','selected','matlab_model_and_parity.mat'),'model');pModel=p.model;
a=load(fullfile(root,'models','attitude','selected','matlab_model_and_parity.mat'),'model');aModel=a.model;
if strcmp(gateId,'G11_PA_DEV')
    split='DEV';methods={'PA_F','PA_A'};csvPath=fullfile(root,'reports','ATTITUDE_DEV.csv');
else
    split='TEST';methods={'B','P_F','P_A','PA_F','PA_A'};csvPath=fullfile(root,'reports','FINAL_TEST.csv');
    lockPath=fullfile(root,'configs','test_lock.json');
    if isfile(lockPath)
        lock=jsondecode(fileread(lockPath));assert(isequaln(lock.models,sm), ...
            'DL1018:TestLockChanged','Selected models changed after TEST was locked.');
    else
        eligible=struct;for m={'P_F','P_A','PA_F','PA_A'},eligible.(m{1})=dev_safe(root,m{1});end
        lock=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','models',sm, ...
            'eligibility',eligible,'thresholds','Predeclared rules in sections 13.3-13.5 of the taskbook', ...
            'sealed_at',utc_now());
        write_json(lockPath,lock);
    end
    methods=methods([true lock.eligibility.P_F lock.eligibility.P_A lock.eligibility.PA_F lock.eligibility.PA_A]);
end
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');M=M(M.split==split,:);
expected=24;if strcmp(split,'TEST'),expected=48;end;assert(height(M)==expected);
attemptPath=fullfile(root,'logs','attempt_index.csv');ensure_attempt_file(attemptPath);
T=table();if isfile(csvPath),T=readtable(csvPath,'TextType','string');end
stopped=struct;for m=methods,stopped.(m{1})=~isempty(T)&&any(T.method==m{1}&(T.status~="STABLE"|~T.complete|~T.finite));end
for si=1:height(M)
    spec=M(si,:);sceneId=char(spec.scene_id);built=make_scenes_dl1018('GET',root,sceneId);scene=built.scene;
    for mi=1:numel(methods)
        method=methods{mi};if stopped.(method),continue;end
        runId=sprintf('%s_%s_%s',gateId,sceneId,method);
        if ~isempty(T)&&any(T.run_id==runId&T.status=="STABLE"&T.complete&T.finite),continue;end
        pm=[];am=[];headMode='frozen';
        if ismember(method,{'P_F','P_A','PA_F','PA_A'}),pm=pModel;headMode=char(sm.position_selected_head_mode);end
        if ismember(method,{'PA_F','PA_A'}),am=aModel;end
        opts=controller_options_dl1018(cfg,method,pm,am,headMode);
        modelId='NO_NEURAL_MODEL';if ~isempty(pm),modelId='DL1018_POSITION_SELECTED';end
        if ~isempty(am),modelId=[modelId '+DL1018_ATTITUDE_SELECTED'];end
        attempts=read_attempts(attemptPath);prior=find(strcmp({attempts.run_id},runId));
        attemptNo=1;rawPath='';log=[];
        if ~isempty(prior)
            last=attempts(prior(end));attemptNo=last.attempt_no;rawPath=fullfile(root,strrep(last.raw_path,'/',filesep));
            marker=fullfile(fileparts(rawPath),'plant_started.marker');
            if isfile(rawPath),d=load(rawPath,'log','scene');log=d.log;scene=d.scene;
            elseif isfile(marker),error('DL1018:UnresolvedAttempt','Plant marker exists but raw MAT is missing: %s',runId);
            else,attemptNo=attemptNo+1;end
        end
        if isempty(log)
            folder=fullfile(root,'data','raw',lower(split),sceneId,method,sprintf('attempt_%02d',attemptNo));
            if ~isfolder(folder),mkdir(folder);end
            rawPath=fullfile(folder,'raw_run.mat');marker=fullfile(folder,'plant_started.marker');
            opts.r2e_first_plant_step_marker=marker;started=utc_now();clock=tic;
            runStart=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
                'gate_id',gateId,'collector_id',method,'model_id',modelId,'scene_spec',spec,'cfg',cfg, ...
                'opts',rmfield_if(opts,'r2e_first_plant_step_marker'),'initial_state',scene.initial_state, ...
                'started_at',datetime('now','TimeZone','UTC'));
            save(fullfile(folder,'run_start.mat'),'runStart','-v7');
            attempt=attempt_record(runId,gateId,split,sceneId,spec,method,modelId,attemptNo, ...
                'RUNNING',false,0,false,false,'','','',relative(rawPath,root),started,'',NaN);
            append_attempt(attemptPath,attempt);fprintf('[%s] starting %d/%d %s %s\n',gateId,si,height(M),sceneId,method);
            try
                log=run_episode_dl1018(scene,method,cfg,opts,rawPath);
                n=numel(log.transition_time);complete=strcmp(log.status,'STABLE')&&n==20000;finite=episode_finite(log);
                status=char(log.status);if ~complete&&strcmp(status,'STABLE'),status='INCOMPLETE';end
                attempt=attempt_record(runId,gateId,split,sceneId,spec,method,modelId,attemptNo, ...
                    status,isfile(marker),n,complete,finite,char(field_or(log,'safety_stop_reason','')), ...
                    '','',relative(rawPath,root),started,utc_now(),toc(clock));
                update_attempt(attemptPath,attempt);
            catch err
                attempt=attempt_record(runId,gateId,split,sceneId,spec,method,modelId,attemptNo, ...
                    'ENGINEERING_ERROR',isfile(marker),0,false,false,'',err.identifier,err.message, ...
                    relative(rawPath,root),started,utc_now(),toc(clock));
                update_attempt(attemptPath,attempt);rethrow(err);
            end
        end
        core=measure_pcf_dl1018(log,scene,zeros(33,3));mm=metrics_dl1018(log,scene,spec,core,NaN,NaN,NaN,false);
        row=metric_table_row(runId,gateId,split,sceneId,spec,method,modelId,log,core,mm,relative(rawPath,root));
        if isempty(T),T=row;else,T=T(T.run_id~=runId,:);T=[T;row];end;writetable(T,csvPath);
        if ~row.complete||~row.finite||row.status~="STABLE",stopped.(method)=true;end
        fprintf('[%s] saved %s %s status=%s Q=%.8g A=%.8g\n',gateId,sceneId,method,log.status,mm.Q_0_20_m,mm.A_0_20_rad);
    end
end
T=readtable(csvPath,'TextType','string');
if strcmp(gateId,'G11_PA_DEV')
    pstar=char(sm.position_star_method);sf=score_dual(T,root,pstar,'PA_F','DEV');sa=score_dual(T,root,pstar,'PA_A','DEV');
    chosen=choose_dual(sf,sa);pass=~isempty(chosen);
    if pass
        sm.final_dual_head_mode=chosen;sm.final_dual_method=iff(strcmp(chosen,'frozen'),'PA_F','PA_A');
        sm.final_model_lock='LOCKED_BEFORE_TEST';write_json(smPath,sm);
    end
    reportStatus=iff(pass,'PASS','STOP_ATTITUDE_NOT_QUALIFIED');
    checks=struct('PA_F',sf,'PA_A',sa,'final_dual_head_mode',chosen, ...
        'selected_dual_method',iff(strcmp(chosen,'frozen'),'PA_F','PA_A'), ...
        'PA_A_minus_PA_F_macro_A_rad',sa.macro_A-sf.macro_A, ...
        'PA_A_minus_PA_F_macro_Q_m',sa.macro_Q-sf.macro_Q);
    block='';if ~pass,block='Neither PA_F nor PA_A passed all preregistered DEV rules.';end
    artifacts={'reports/ATTITUDE_DEV.csv','reports/POSITION_DEV.csv','configs/selected_models.json','data/raw/dev'};
else
    sf=score_position(T,'P_F','TEST',root);sa=score_position(T,'P_A','TEST',root);pstar=char(sm.position_star_method);
    pscore=score_position(T,pstar,'TEST',root);paF=score_dual(T,root,pstar,'PA_F','TEST');paA=score_dual(T,root,pstar,'PA_A','TEST');
    selectedPA=sm.final_dual_method;dualPass=(strcmp(selectedPA,'PA_F')&&paF.pass)||(strcmp(selectedPA,'PA_A')&&paA.pass);
    execComplete=test_methods_stopped_or_complete(T,methods);
    checks=struct('P_F',sf,'P_A',sa,'P_STAR',pscore,'PA_F',paF,'PA_A',paA, ...
        'locked_position_test_pass',pscore.pass,'locked_dual_method',selectedPA, ...
        'locked_dual_test_pass',dualPass,'locked_candidate_pass',[pscore.pass;dualPass], ...
        'PA_A_minus_PA_F_macro_A_rad',paA.macro_A-paF.macro_A, ...
        'PA_A_minus_PA_F_macro_Q_m',paA.macro_Q-paF.macro_Q, ...
        'test_execution_complete',execComplete,'dev_safety_eligibility',lock.eligibility);
    if execComplete
        reportStatus='COMPLETE_WITH_NEGATIVE_TEST_RESULT';if all([pscore.pass,dualPass]),reportStatus='PASS';end
        block='';if ~all([pscore.pass,dualPass]),block='TEST completed; at least one locked candidate missed its preregistered performance rules.';end
        next=true;
    else
        reportStatus='PAUSED_RESOURCE';block='TEST was interrupted before every active method was either complete or safely stopped.';next=false;
    end
    artifacts={'reports/FINAL_TEST.csv','configs/test_lock.json','data/raw/test'};
end
report=struct('gate_id',gateId,'status',reportStatus,'contract_version','DL1018_V311_R2E_PAPER_FINAL', ...
    'upstream_passed',true,'model_id','DL1018_SELECTED','actual_counts',struct( ...
    'plant_started',count_gate_attempts(attemptPath,gateId),'complete',nnz(T.gate_id==gateId&T.status=="STABLE"&T.complete), ...
    'physical_failures',nnz(T.gate_id==gateId&T.status~="STABLE"|T.gate_id==gateId&~T.complete), ...
    'engineering_errors',count_gate_status(attemptPath,gateId,'ENGINEERING_ERROR')), ...
    'checks',checks,'max_errors',struct,'artifacts',{artifacts}, ...
    'next_gate_allowed',next_flag(reportStatus),'blocking_reason',block);
if strcmp(gateId,'G12_FINAL_TEST'),report.artifacts{end+1}='reports/G12_FINAL_TEST.json';end
write_gate_report_dl1018(fullfile(root,'reports',[gateId '.json']),report);
end
function row=metric_table_row(id,gate,split,scene,spec,method,model,log,core,mm,raw)
row=table(string(id),string(gate),string(split),string(scene),string(spec.task),double(spec.c),double(spec.w), ...
    string(method),string(model),string(log.status),logical(core.complete),logical(core.finite),double(core.transitions), ...
    mm.Q_0_20_m,mm.Q_5_20_m,mm.A_0_20_rad,mm.position_peak_m,mm.position_p95_m, ...
    string(jsonencode(mm.position_axis_rmse_m)),string(jsonencode(mm.attitude_axis_rmse_rad)), ...
    mm.yaw_peak_abs_rad,mm.max_motor_step_rad_s,mm.max_motor_step_time_s, ...
    mm.motor_saturation_fraction,mm.generalized_clip_fraction,mm.motor_TV_normalized_per_s,mm.motor_min_rad_s,mm.motor_max_rad_s, ...
    mm.controller_p99_ms,mm.controller_worst_ms,mm.control_loop_p99_ms,mm.joint_event_count, ...
    mm.wind_speed_rms_mps,mm.wind_speed_peak_mps,mm.wind_force_rms_N,mm.wind_force_peak_N,mm.wind_force_dominant_hz, ...
    mm.wind_torque_rms_Nm,mm.wind_torque_peak_Nm,mm.wind_torque_dominant_hz,mm.wind_input_f1_hz,mm.wind_input_f2_hz, ...
    string(mm.phase_metrics_json),double(log.divergence_time_s),mm.position_head_max_fro,mm.head_max_fro, ...
    mm.position_head_update_count,mm.head_update_count,string(mm.safety_stop_reason),string(raw), ...
    'VariableNames',{'run_id','gate_id','split','scene_id','task','class_index','wind_cell','method','model_id','status', ...
    'complete','finite','transitions','Q_0_20_m','Q_5_20_m','A_0_20_rad','position_peak_m','position_p95_m', ...
    'position_axis_rmse_m','attitude_axis_rmse_rad','yaw_peak_abs_rad','max_motor_step_rad_s','max_motor_step_time_s', ...
    'motor_saturation_fraction','generalized_clip_fraction','motor_TV_normalized_per_s','motor_min_rad_s','motor_max_rad_s', ...
    'controller_p99_ms','controller_worst_ms','control_loop_p99_ms','joint_event_count','wind_speed_rms_mps','wind_speed_peak_mps', ...
    'wind_force_rms_N','wind_force_peak_N','wind_force_dominant_hz','wind_torque_rms_Nm','wind_torque_peak_Nm', ...
    'wind_torque_dominant_hz','wind_input_f1_hz','wind_input_f2_hz','phase_metrics_json','time_to_stop_s', ...
    'position_head_max_fro','attitude_head_max_fro', ...
    'position_head_update_count','attitude_head_update_count','safety_stop_reason','raw_path'});
end
function s=score_position(T,method,split,root)
b=T(T.method=="B"&T.split==split,:);c=T(T.method==method&T.split==split,:);
s=struct('method',method,'pass',false,'n',height(c),'macro_Q',NaN,'macro_peak',NaN,'total_wins',0, ...
    'peak_warnings',0,'severe_peaks',0,'per_task',struct,'checks',struct);
if isempty(b)||isempty(c),return;end
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');M=M(M.split==split,:);
coverageB=expected_scene_rows(b,M);coverageC=expected_scene_rows(c,M);
tasks=unique(b.task,'stable');per=struct;allTask=true;wins=0;warnings=0;serious=0;qb=[];qc=[];pc=[];
nTask=16;minTotal=36;maxWarn=2;if strcmp(split,'DEV'),nTask=8;minTotal=18;maxWarn=1;end
for i=1:numel(tasks)
    task=tasks(i);bt=b(b.task==task,:);ct=c(c.task==task,:);[~,ib,ic]=intersect(bt.scene_id,ct.scene_id,'stable');bt=bt(ib,:);ct=ct(ic,:);
    full=coverageB&&coverageC&&height(ct)==nTask&&all(bt.complete)&&all(ct.complete)&&all(bt.finite)&&all(ct.finite)&&all(bt.transitions==20000)&&all(ct.transitions==20000);
    qbase=mean(bt.Q_0_20_m);q=mean(ct.Q_0_20_m);abase=mean(bt.A_0_20_rad);aa=mean(ct.A_0_20_rad);
    nw=nnz(ct.Q_0_20_m<bt.Q_0_20_m-1e-9);np=nnz(ct.position_peak_m>1.2*bt.position_peak_m+.01);
    ns=nnz(ct.position_peak_m>2*bt.position_peak_m&(ct.position_peak_m-bt.position_peak_m)>.05);
    sat=all(ct.motor_saturation_fraction<=bt.motor_saturation_fraction+.005);
    clip=all(ct.generalized_clip_fraction<=bt.generalized_clip_fraction+.005);
    time=all(ct.controller_p99_ms<10);motors=all(ct.motor_min_rad_s>=0&ct.motor_max_rad_s<=1900);
    taskPass=full&&q<=1.05*qbase+.002&&nw>=ceil(.5*nTask)&&aa<=1.10*abase+.002&&sat&&clip&&time&&motors&&ns<3;
    per.(matlab.lang.makeValidName(char(task)))=struct('n',height(ct),'Q_B_m',qbase,'Q_method_m',q, ...
        'A_B_rad',abase,'A_method_rad',aa,'wins',nw,'peak_warnings',np,'severe_peaks',ns, ...
        'complete_finite',full,'pass',taskPass);
    allTask=allTask&&taskPass;wins=wins+nw;warnings=warnings+np;serious=serious+ns;
    qb(end+1)=qbase;qc(end+1)=q;pc(end+1)=mean(ct.position_peak_m); %#ok<AGROW>
end
macroB=mean(qb);macro=mean(qc);s.pass=allTask&&macro<macroB-1e-9&&wins>=minTotal&&warnings<=maxWarn;
s.macro_Q=macro;s.macro_peak=mean(pc);s.total_wins=wins;s.peak_warnings=warnings;s.severe_peaks=serious;s.per_task=per;
s.checks=struct('baseline_scene_coverage',coverageB,'candidate_scene_coverage',coverageC, ...
    'macro_Q_improves',macro<macroB-1e-9,'win_count',wins,'win_rule_pass',wins>=minTotal, ...
    'peak_warnings',warnings,'peak_rule_pass',warnings<=maxWarn,'per_task_pass',allTask);
end
function s=score_dual(T,root,pstarMethod,method,split)
if strcmp(split,'DEV')
    pfile=fullfile(root,'reports','POSITION_DEV.csv');P=readtable(pfile,'TextType','string');
else
    P=T;
end
if strcmp(split,'DEV'),b=P(P.method=="B"&P.split==split,:);else,b=T(T.method=="B"&T.split==split,:);end
a=T(T.method==method&T.split==split,:);p=P(P.method==pstarMethod&P.split==split,:);
s=struct('method',method,'pass',false,'n',height(a),'macro_A',NaN,'macro_Q',NaN,'per_task',struct,'checks',struct);
if isempty(b)||isempty(a)||isempty(p),return;end
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');M=M(M.split==split,:);
coverageB=expected_scene_rows(b,M);coverageP=expected_scene_rows(p,M);coverageA=expected_scene_rows(a,M);
tasks=unique(b.task,'stable');per=struct;allTask=true;AB=[];AP=[];AA=[];QB=[];QP=[];QA=[];warnB=0;warnP=0;sevB=0;sevP=0;
nTask=16;maxWarn=2;if strcmp(split,'DEV'),nTask=8;maxWarn=1;end
for i=1:numel(tasks)
    task=tasks(i);bt=b(b.task==task,:);pt=p(p.task==task,:);at=a(a.task==task,:);
    [~,ib,ip]=intersect(bt.scene_id,pt.scene_id,'stable');bt=bt(ib,:);pt=pt(ip,:);
    [~,ib,ia]=intersect(bt.scene_id,at.scene_id,'stable');bt=bt(ib,:);at=at(ia,:);pt=pt(ib,:);
    full=coverageB&&coverageP&&coverageA&&height(at)==nTask&&all(bt.complete)&&all(pt.complete)&&all(at.complete)&& ...
        all(bt.finite)&&all(pt.finite)&&all(at.finite)&&all(bt.transitions==20000)&&all(pt.transitions==20000)&&all(at.transitions==20000);
    qb=mean(bt.Q_0_20_m);qp=mean(pt.Q_0_20_m);qa=mean(at.Q_0_20_m);
    ab=mean(bt.A_0_20_rad);ap=mean(pt.A_0_20_rad);aa=mean(at.A_0_20_rad);
    sat=all(at.motor_saturation_fraction<=bt.motor_saturation_fraction+.005)&all(at.motor_saturation_fraction<=pt.motor_saturation_fraction+.005);
    clip=all(at.generalized_clip_fraction<=bt.generalized_clip_fraction+.005)&all(at.generalized_clip_fraction<=pt.generalized_clip_fraction+.005);
    timing=all(at.controller_p99_ms<10);motors=all(at.motor_min_rad_s>=0&at.motor_max_rad_s<=1900);
    wb=nnz(at.position_peak_m>1.2*bt.position_peak_m+.01);wp=nnz(at.position_peak_m>1.2*pt.position_peak_m+.01);
    sb=nnz(at.position_peak_m>2*bt.position_peak_m&(at.position_peak_m-bt.position_peak_m)>.05);
    sp=nnz(at.position_peak_m>2*pt.position_peak_m&(at.position_peak_m-pt.position_peak_m)>.05);
    taskPass=full&&qa<=1.10*qb+.002&&qa<=1.05*qp+.002&&aa<=1.10*ab+.002&&aa<=1.10*ap+.002&& ...
        sat&&clip&&timing&&motors&&sb<3&&sp<3;
    per.(matlab.lang.makeValidName(char(task)))=struct('n',height(at),'Q_B_m',qb,'Q_PSTAR_m',qp,'Q_PA_m',qa, ...
        'A_B_rad',ab,'A_PSTAR_rad',ap,'A_PA_rad',aa,'peak_warnings_vs_B',wb,'peak_warnings_vs_PSTAR',wp, ...
        'severe_peaks_vs_B',sb,'severe_peaks_vs_PSTAR',sp,'complete_finite',full,'pass',taskPass);
    allTask=allTask&&taskPass;AB(end+1)=ab;AP(end+1)=ap;AA(end+1)=aa;QB(end+1)=qb;QP(end+1)=qp;QA(end+1)=qa; %#ok<AGROW>
    warnB=warnB+wb;warnP=warnP+wp;sevB=sevB+sb;sevP=sevP+sp;
end
macroA=mean(AA);macroAB=mean(AB);macroAP=mean(AP);macroQ=mean(QA);macroQB=mean(QB);macroQP=mean(QP);
passA=macroA<macroAB-1e-9&&macroA<macroAP-1e-9;passQ=macroQ<macroQB-1e-9&&macroQ<=1.03*macroQP+.002;
peak=warnB<=maxWarn&&warnP<=maxWarn;s.pass=allTask&&passA&&passQ&&peak;s.macro_A=macroA;s.macro_Q=macroQ;s.per_task=per;
s.checks=struct('baseline_scene_coverage',coverageB,'PSTAR_scene_coverage',coverageP,'candidate_scene_coverage',coverageA, ...
    'macro_A_vs_B_and_PSTAR',passA,'macro_Q_vs_B_and_PSTAR',passQ,'peak_warnings_vs_B',warnB, ...
    'peak_warnings_vs_PSTAR',warnP,'peak_rule_pass',peak,'severe_peaks_vs_B',sevB,'severe_peaks_vs_PSTAR',sevP, ...
    'all_task_rules_pass',allTask);
end
function ok=expected_scene_rows(R,M)
ok=height(R)==height(M)&&numel(unique(R.scene_id))==height(M)&&all(ismember(M.scene_id,R.scene_id));
if ~ok,return;end
[found,ix]=ismember(M.scene_id,R.scene_id);
ok=all(found)&&all(R.task(ix)==M.task)&&all(R.class_index(ix)==M.c)&&all(R.wind_cell(ix)==M.w);
end
function chosen=choose_dual(f,a)
chosen='';if f.pass&&~a.pass,chosen='frozen';elseif a.pass&&~f.pass,chosen='online';elseif f.pass&&a.pass
    if f.macro_A<a.macro_A-1e-9,chosen='frozen';elseif a.macro_A<f.macro_A-1e-9,chosen='online';
    elseif f.macro_Q<=a.macro_Q,chosen='frozen';else,chosen='online';end
end
end
function tf=dev_safe(root,m)
if startsWith(m,'PA_'),p=fullfile(root,'reports','ATTITUDE_DEV.csv');else,p=fullfile(root,'reports','POSITION_DEV.csv');end
tf=false;if ~isfile(p),return;end;T=readtable(p,'TextType','string');z=T(T.method==m,:);tf=height(z)==24&&all(z.complete)&&all(z.finite)&&all(z.transitions==20000);
end
function yes=test_methods_stopped_or_complete(T,methods)
yes=true;for m=methods,z=T(T.method==m{1}&T.split=="TEST",:);if isempty(z),yes=false;return;end
    stopped=any(~z.complete|~z.finite|z.status~="STABLE");yes=yes&&(height(z)==48||stopped);end
end
function row=attempt_record(id,gate,split,scene,spec,method,model,no,status,started,n,complete,finite,safety,err,msg,raw,t0,t1,elapsed)
row=struct('run_id',id,'gate_id',gate,'split',lower(split),'scene_id',scene,'task',char(spec.task), ...
    'class_index',double(spec.c),'wind_cell',double(spec.w),'collector_id',method,'model_id',model, ...
    'contract_version','DL1018_V311_R2E_PAPER_FINAL','runtime_mode','MATLAB_R2025b','attempt_no',no, ...
    'status',status,'plant_started',started,'returned_transitions',n,'complete',complete,'finite',finite, ...
    'safety_stop_reason',safety,'error_kind',err,'error_message',msg,'raw_path',raw, ...
    'position_event_path','','attitude_event_path','','started_at',t0,'finished_at',t1, ...
    'elapsed_s',elapsed,'accepted_for_training',false);
end
function ensure_attempt_file(p)
if isfile(p),return;end;c=attempt_cols();f=fopen(p,'w');assert(f>=0);fprintf(f,'%s\n',strjoin(c,','));fclose(f);
end
function c=attempt_cols()
c={'run_id','gate_id','split','scene_id','task','class_index','wind_cell','collector_id','model_id','contract_version','runtime_mode', ...
    'attempt_no','status','plant_started','returned_transitions','complete','finite','safety_stop_reason','error_kind','error_message', ...
    'raw_path','position_event_path','attitude_event_path','started_at','finished_at','elapsed_s','accepted_for_training'};
end
function a=read_attempts(p)
a=struct([]);if ~isfile(p),return;end;T=readtable(p,'TextType','string');for i=1:height(T)
    z=table2struct(T(i,:));z.run_id=char(z.run_id);z.gate_id=char(z.gate_id);z.raw_path=char(z.raw_path);
    z.attempt_no=double(z.attempt_no);z.plant_started=logical_value(z.plant_started);a(i)=z;end
end
function append_attempt(p,a)
f=fopen(p,'a');assert(f>=0);c=onCleanup(@()fclose(f));fprintf(f,'%s\n',csvline(struct2cell(orderfields(a,attempt_cols()))));clear c;
end
function update_attempt(p,a)
L=readlines(p);for i=numel(L):-1:2,q=split(L(i),',');if numel(q)>=12&&q(1)==string(a.run_id)&&str2double(q(12))==a.attempt_no
    L(i)=string(csvline(struct2cell(orderfields(a,attempt_cols()))));break;end,end
f=fopen(p,'w');assert(f>=0);c=onCleanup(@()fclose(f));for i=1:numel(L),fprintf(f,'%s\n',char(L(i)));end;clear c;
end
function s=csvline(v)
p=cell(size(v));for i=1:numel(v),x=v{i};if isempty(x),p{i}='';elseif islogical(x),p{i}=char(string(x));elseif isnumeric(x),if isscalar(x)&&isnan(x),p{i}='';else,p{i}=sprintf('%.17g',x);end;else,p{i}=char(string(x));end;p{i}=strrep(strrep(strrep(strrep(p{i},',',';'),newline,' '),char(13),' '),'"','''');end;s=strjoin(p,',');
end
function n=count_gate_attempts(p,g),a=read_attempts(p);n=nnz(strcmp({a.gate_id},g)&[a.plant_started]);end
function n=count_gate_status(p,g,s),a=read_attempts(p);n=nnz(strcmp({a.gate_id},g)&strcmp({a.status},s));end
function y=episode_finite(log)
f={'state','transition_time','wind_force_I','wind_torque_B','requested_generalized','controller_clipped_generalized','realized_generalized', ...
    'motor_command','motor_setpoint','position_compensation_applied_force_N','attitude_compensation_applied_torque_Nm'};y=true;
for i=1:numel(f),if isfield(log,f{i}),y=y&&all(isfinite(log.(f{i})),'all');end,end
end
function s=relative(p,r),p=char(java.io.File(p).getCanonicalPath());r=char(java.io.File(r).getCanonicalPath());assert(startsWith(lower(p),lower([r filesep])));s=strrep(p(numel(r)+2:end),'\','/');end
function s=utc_now(),d=datetime('now','TimeZone','UTC');d.Format='yyyy-MM-dd''T''HH:mm:ss.SSS''Z''';s=char(d);end
function y=field_or(x,n,d),if isfield(x,n),y=x.(n);else,y=d;end,end
function y=rmfield_if(x,n),if isfield(x,n),y=rmfield(x,n);end,end
function write_json(p,v),tmp=[p '.tmp'];f=fopen(tmp,'w');assert(f>=0);c=onCleanup(@()fclose(f));fwrite(f,jsonencode(v,'PrettyPrint',true),'char');fwrite(f,newline,'char');clear c;movefile(tmp,p,'f');end
function y=iff(c,a,b),if c,y=a;else,y=b;end,end
function y=next_flag(s),y=ismember(s,{'PASS','COMPLETE_WITH_NEGATIVE_TEST_RESULT'});end
