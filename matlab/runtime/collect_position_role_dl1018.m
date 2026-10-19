function report=collect_position_role_dl1018(root,gateId,role)
% Fixed position/attitude Student and P_STAR collection using the one Plant runner.
root=char(java.io.File(root).getCanonicalPath());gateId=upper(char(gateId));role=upper(char(role));
assert(ismember(gateId,{'G04_P_STUDENT','G07_A_TEACHER','G09_A_STUDENT'}), ...
    'DL1018:CollectorGate','Unsupported role collection Gate.');
addpath(fullfile(root,'matlab','runtime'),fullfile(root,'matlab','data'), ...
    fullfile(root,'matlab','scenes'),fullfile(root,'matlab','models'));
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved));
M=read_specs(fullfile(root,'configs','scene_specs.csv'));
if strcmp(gateId,'G07_A_TEACHER')
    assert(strcmp(role,'P_STAR'));mask=M.split=="TRAIN"|M.split=="VAL";
    sm=jsondecode(fileread(fullfile(root,'configs','selected_models.json')));
    assert(isfield(sm,'position_selected_head_mode'),'DL1018:PStarUnlocked','G06 has not locked P_STAR.');
    headMode=char(sm.position_selected_head_mode);
else
    if strcmp(gateId,'G04_P_STUDENT')
        assert(strcmp(role,'P_INIT_STUDENT'));headMode='online';
    else
        assert(strcmp(role,'A_INIT_STUDENT'));
        sm=jsondecode(fileread(fullfile(root,'configs','selected_models.json')));
        headMode=char(sm.position_selected_head_mode);
    end
    mask=(M.split=="TRAIN"&logical(M.student_train))|(M.split=="VAL"&logical(M.student_val));
end
trainN=nnz(mask&M.split=="TRAIN");valN=nnz(mask&M.split=="VAL");
if strcmp(gateId,'G07_A_TEACHER'),assert(trainN==768&&valN==48);else,assert(trainN==384&&valN==48);end
first=student_first(M);rows=find(mask);first=first(ismember(first,rows));
order=unique([first(:);setdiff(rows,first(:),'stable')],'stable');
posPackage='selected';if strcmp(role,'P_INIT_STUDENT'),posPackage='initial';end
q=load(fullfile(root,'models','position',posPackage,'matlab_model_and_parity.mat'),'model');
positionModel=q.model;positionId=['DL1018_POSITION_' upper(posPackage)];
if strcmp(posPackage,'initial')
    z=jsondecode(fileread(fullfile(root,'models','position','initial','model.json')));positionId=z.model_id;
end
attitudeModel=[];attitudeId='';needA=ismember(role,{'P_STAR','A_INIT_STUDENT'});
if strcmp(role,'A_INIT_STUDENT')
    q=load(fullfile(root,'models','attitude','initial','matlab_model_and_parity.mat'),'model');
    attitudeModel=q.model;z=jsondecode(fileread(fullfile(root,'models','attitude','initial','model.json')));attitudeId=z.model_id;
end
modelId=char(positionId);if ~isempty(attitudeId),modelId=[modelId '+' char(attitudeId)];end
if ismember(gateId,{'G07_A_TEACHER','G09_A_STUDENT'}),modelId=[modelId '_' char(sm.position_star_method)];end
opts=controller_options_dl1018(cfg,role,positionModel,attitudeModel,headMode);
ap=fullfile(root,'logs','attempt_index.csv');ep=fullfile(root,'logs','episode_index.csv');
attemptCols=attempt_columns();episodeCols=episode_columns();ensure_csv(ap,attemptCols);ensure_csv(ep,episodeCols);
A=readtable(ap,'TextType','string');E=readtable(ep,'TextType','string');
accepted=logical_column(E.accepted)&string(E.source_role)==role;acceptedIds=string(E.run_id(accepted));
trainDone=nnz(accepted&lower(string(E.split))=="train");valDone=nnz(accepted&lower(string(E.split))=="val");
bReuse=struct('pass',true,'train_complete',0,'val_complete',0,'unique_scene_coverage',true, ...
    'attitude_event_files_present',true,'event_counts_correct',true);
if strcmp(gateId,'G07_A_TEACHER')
    bReuse=validate_b_attitude_reuse(E,M,root);
    assert(bReuse.pass,'DL1018:BTeacherReuse','G02 B attitude labels are incomplete or do not match the fixed TRAIN/VAL pool.');
end
prior=upper(string(A.gate_id))==gateId;plantCount=nnz(logical_column(A.plant_started(prior)));
physical=nnz(ismember(upper(string(A.status(prior))),["SAFE_STOP","DIVERGED","PHYSICAL_FAILURE"]));
eng=nnz(upper(string(A.status(prior)))=="ENGINEERING_ERROR");recovered=0;maxPos=0;maxTau=0;maxDyn=0;
firstPassed=false;newPlant=0;
for n=1:numel(order)
    row=M(order(n),:);sceneId=char(row.scene_id);split=char(lower(row.split));
    runId=sprintf('%s_%s_%s',gateId,sceneId,role);
    if any(acceptedIds==runId),if n<=9,firstPassed=true;end;continue;end
    priorRows=find(string(A.run_id)==runId);attemptNo=1;rawPath='';log=[];scene=[];marker='';plantDidStart=false;recoverCurrent=false;
    if ~isempty(priorRows)
        old=priorRows(end);rawPath=fullfile(root,strrep(char(A.raw_path(old)),'/',filesep));
        marker=fullfile(fileparts(rawPath),'plant_started.marker');attemptNo=double(A.attempt_no(old));
        oldStatus=upper(string(A.status(old)));
        if ismember(oldStatus,["SAFE_STOP","DIVERGED","PHYSICAL_FAILURE"])
            report=report_base('STOPPED_UNSAFE');report.blocking_reason=['Prior physical failure: ' runId];
            write_gate_report_dl1018(fullfile(root,'reports',[gateId '.json']),report);return;
        elseif isfile(rawPath)
            d=load(rawPath,'log','scene');log=d.log;scene=d.scene;plantDidStart=isfile(marker);recovered=recovered+1;recoverCurrent=true;
        elseif isfile(marker)
            report=report_base('STOPPED_INCOMPLETE');report.blocking_reason=['Plant started, raw MAT incomplete: ' runId];
            write_gate_report_dl1018(fullfile(root,'reports',[gateId '.json']),report);return;
        else
            attemptNo=attemptNo+1;
            if oldStatus=="RUNNING"
                oldValues={runId,gateId,split,sceneId,char(row.task),double(A.class_index(old)),double(A.wind_cell(old)), ...
                    role,modelId,'DL1018_V311_R2E_PAPER_FINAL','MATLAB_R2025b',double(A.attempt_no(old)), ...
                    'ENGINEERING_ERROR',false,0,false,false,'','DL1018:InterruptedBeforePlant', ...
                    'Attempt was interrupted before the first Plant transition.',char(A.raw_path(old)), ...
                    char(A.position_event_path(old)),char(A.attitude_event_path(old)),char(A.started_at(old)), ...
                    now_utc(),double(A.elapsed_s(old)),false};
                update_csv(ap,runId,double(A.attempt_no(old)),oldValues);eng=eng+1;
            end
        end
    end
    if isempty(log)
        built=make_scenes_dl1018('GET',root,sceneId);scene=built.scene;
        folder=fullfile(root,'data','raw',split,sceneId,role,sprintf('attempt_%02d',attemptNo));
        if ~isfolder(folder),mkdir(folder);end;rawPath=fullfile(folder,'raw_run.mat');marker=fullfile(folder,'plant_started.marker');
        runStart=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
            'gate_id',gateId,'collector_id',role,'model_id',modelId,'scene_spec',row,'cfg',cfg, ...
            'opts',rmfield_if_exists(opts,'r2e_first_plant_step_marker'),'initial_state',scene.initial_state, ...
            'started_at',datetime('now','TimeZone','UTC'));
        save(fullfile(folder,'run_start.mat'),'runStart','-v7');opts.r2e_first_plant_step_marker=marker;
        started=now_utc();clock=tic;
        vals={runId,gateId,split,sceneId,char(row.task),double(row.c),double(row.w),role,modelId, ...
            'DL1018_V311_R2E_PAPER_FINAL','MATLAB_R2025b',attemptNo,'RUNNING',false,0,false,false,'','','', ...
            rel(rawPath,root),'','',started,'',NaN,false};append_csv(ap,attemptCols,vals);
        fprintf('[%s] starting %d/%d %s %s\n',gateId,n,numel(order),sceneId,role);
        try
            log=run_episode_dl1018(scene,role,cfg,opts,rawPath);
            plantDidStart=isfile(marker);newPlant=newPlant+plantDidStart;
        catch err
            eng=eng+1;plantDidStart=isfile(marker);newPlant=newPlant+plantDidStart;
            vals{13}='ENGINEERING_ERROR';vals{14}=plantDidStart;vals{19}=err.identifier;vals{20}=err.message;
            vals{25}=now_utc();vals{26}=toc(clock);update_csv(ap,runId,attemptNo,vals);
            report=report_base('FAIL_RUNTIME_CONTRACT');report.blocking_reason=sprintf('%s: %s',err.identifier,err.message);
            write_gate_report_dl1018(fullfile(root,'reports',[gateId '.json']),report);rethrow(err);
        end
    else
        started=char(A.started_at(priorRows(end)));clock=tic;
    end
    try
        posFile=fullfile(root,'data','events','position',split,sceneId,[role '.h5']);
        attFile='';if needA,attFile=fullfile(root,'data','events','attitude',split,sceneId,[role '.h5']);end
        [PE,pm]=export_position_events_dl1018(log,scene,cfg,role,upper(split),row);
        if isfile(posFile)&&~h5_matches(posFile,pm.event_count),delete(posFile);end
        if ~isfile(posFile),write_events_h5_dl1018(PE,posFile,struct('scene_id',sceneId,'collector_id',role, ...
                'model_id',modelId,'contract_version','DL1018_V311_R2E_PAPER_FINAL','split',upper(split), ...
                'role','position_model_behavior','units','X14 mixed physical units; target/applied compensation: m/s^2', ...
                'feature_order',jsonencode({'e_p_xyz_m','s_p_xyz_mps','euler_rpy_rad','nominal_thrust_mps2','arm_command_1_to_4'})));
        end
        am=[];
        if needA
            [AE,am]=export_attitude_events_dl1018(log,scene,cfg,role,upper(split));
            if isfile(attFile)&&~h5_matches(attFile,am.event_count),delete(attFile);end
            if ~isfile(attFile),write_events_h5_dl1018(AE,attFile,struct('scene_id',sceneId,'collector_id',role, ...
                    'model_id',modelId,'contract_version','DL1018_V311_R2E_PAPER_FINAL','split',upper(split), ...
                    'role','attitude_model_behavior','units','X29 mixed physical units; normalized target unitless; applied torque N*m', ...
                    'feature_order',jsonencode({'error_rpy_rad','surface_rpy_radps','omega_B_radps', ...
                    'filtered_euler_rate_radps','filtered_euler_acceleration_radps2','euler_rpy_rad', ...
                    'inertial_velocity_mps','nominal_angular_acceleration_radps2','thrust_mps2', ...
                    'previous_event_motor_setpoint_over_1900'})));
            end
        end
        count=numel(log.transition_time);finite=episode_finite(log);complete=strcmp(log.status,'STABLE')&&count==20000;
        maxPos=max(maxPos,pm.max_label_closure_mps2);
        if needA,maxTau=max(maxTau,am.max_requested_torque_closure_Nm);maxDyn=max(maxDyn,am.max_dynamics_closure_rads2);end
        if ~finite||~complete
            physical=physical+1;failure='SAFE_STOP';if strcmp(log.status,'DIVERGED'),failure='DIVERGED';end
            save_episode(false,finite,count,pm,am,failure);
            report=report_base('STOPPED_UNSAFE');report.blocking_reason=sprintf('%s stopped at %.6g s (%s).',role, ...
                log.divergence_time_s,char(log.safety_stop_reason));
            write_gate_report_dl1018(fullfile(root,'reports',[gateId '.json']),report);return;
        end
        assert(pm.event_count==1999&&pm.ready_count==1968&&pm.max_label_closure_mps2<=1e-9, ...
            'DL1018:PositionContract','Position event contract failed.');
        if needA,assert(am.event_count==1999&&am.ready_count==1968&&am.max_requested_torque_closure_Nm<=1e-8&& ...
                am.max_dynamics_closure_rads2<=1e-8,'DL1018:AttitudeContract','Attitude event contract failed.');end
        save_episode(true,true,count,pm,am,'');acceptedIds(end+1)=runId;
        if strcmp(split,'train'),trainDone=trainDone+1;else,valDone=valDone+1;end
        if n<=9,firstPassed=true;end
        fprintf('[%s] accepted %d/%d %s %s\n',gateId,trainDone+valDone,numel(order),sceneId,role);
    catch err
        eng=eng+1;
        tr=numel(log.transition_time);fin=episode_finite(log);isComplete=strcmp(log.status,'STABLE')&&tr==20000;
        posRel='';attRel='';if exist('posFile','var')&&isfile(posFile),posRel=rel(posFile,root);end
        if exist('attFile','var')&&~isempty(attFile)&&isfile(attFile),attRel=rel(attFile,root);end
        failure='';if isfield(log,'safety_stop_reason'),failure=char(log.safety_stop_reason);end
        errorValues={runId,gateId,split,sceneId,char(row.task),double(row.c),double(row.w),role,modelId, ...
            'DL1018_V311_R2E_PAPER_FINAL','MATLAB_R2025b',attemptNo,'ENGINEERING_ERROR',plantDidStart,tr, ...
            isComplete,fin,failure,err.identifier,err.message,rel(rawPath,root),posRel,attRel,started, ...
            now_utc(),toc(clock),false};
        update_csv(ap,runId,attemptNo,errorValues);
        report=report_base('FAIL_RUNTIME_CONTRACT');report.blocking_reason=sprintf('%s: %s',err.identifier,err.message);
        write_gate_report_dl1018(fullfile(root,'reports',[gateId '.json']),report);rethrow(err);
    end
end
assert(trainDone==trainN&&valDone==valN,'DL1018:CollectionQuota','Fixed role quota is incomplete.');
E=readtable(ep,'TextType','string');roleCoverage=validate_role_rows(E,role,M(mask,:),root,needA);
assert(roleCoverage.pass,'DL1018:RoleCoverage','Accepted %s episodes do not match the fixed scene pool.',role);
report=report_base('PASS');report.actual_counts.train_complete=trainDone;report.actual_counts.val_complete=valDone;
report.actual_counts.episodes_complete=trainDone+valDone;report.actual_counts.plant_started=plantCount+newPlant;
report.actual_counts.raw_recovered_without_plant=recovered;report.actual_counts.engineering_errors=eng;
report.actual_counts.physical_failures=physical;
if strcmp(gateId,'G07_A_TEACHER')
    report.actual_counts.B_reused_train=bReuse.train_complete;report.actual_counts.B_reused_val=bReuse.val_complete;
    report.actual_counts.logical_teacher_train=trainDone+bReuse.train_complete;
    report.actual_counts.logical_teacher_val=valDone+bReuse.val_complete;
end
report.checks=struct('position_events_per_episode',1999,'position_ready_per_episode',1968, ...
    'max_position_label_closure_mps2',maxPos,'attitude_events_per_episode',iff(needA,1999,0), ...
    'attitude_ready_per_episode',iff(needA,1968,0),'max_attitude_torque_closure_Nm',maxTau, ...
    'max_attitude_dynamics_closure_rads2',maxDyn,'model_id',modelId,'position_head_mode',headMode, ...
    'first_batch_passed',firstPassed,'unique_accepted_run_ids',roleCoverage.unique_run_ids, ...
    'role_scene_coverage',roleCoverage,'raw_recovery_used',recovered>0);
if strcmp(gateId,'G07_A_TEACHER'),report.checks.B_reuse_from_G02=bReuse;end
report.artifacts={'data/raw','data/events/position','logs/attempt_index.csv','logs/episode_index.csv', ...
    ['reports/' gateId '.json']};if needA,report.artifacts{end+1}='data/events/attitude';end
report.next_gate_allowed=true;write_gate_report_dl1018(fullfile(root,'reports',[gateId '.json']),report);
    function save_episode(ok,fin,count,pm,am,why)
        nA=0;rA=0;ar='';if ~isempty(am),nA=am.event_count;rA=am.ready_count;ar=rel(attFile,root);end
        pr=rel(posFile,root);rr=rel(rawPath,root);
        append_csv(ep,episode_columns(),{runId,split,sceneId,char(row.task),double(row.c),double(row.w), ...
            role,role,modelId,'DL1018_V311_R2E_PAPER_FINAL',pr,ar,ok,fin,count,pm.event_count,nA,pm.ready_count,rA,ok,why});
        st='COMPLETE';if ~ok,st=why;end
        update_csv(ap,runId,attemptNo,{runId,gateId,split,sceneId,char(row.task),double(row.c),double(row.w), ...
            role,modelId,'DL1018_V311_R2E_PAPER_FINAL','MATLAB_R2025b',attemptNo,st,plantDidStart,count,ok,fin, ...
            why,'','',rr,pr,ar,started,now_utc(),toc(clock),ok});
    end
    function r=report_base(status)
        r=struct('gate_id',gateId,'status',status,'contract_version','DL1018_V311_R2E_PAPER_FINAL', ...
            'upstream_passed',true,'model_id',modelId,'actual_counts',struct('train_complete',trainDone, ...
            'val_complete',valDone,'plant_started',plantCount+newPlant,'engineering_errors',eng, ...
            'physical_failures',physical),'checks',struct,'max_errors',struct, ...
            'artifacts',{{'logs/attempt_index.csv','logs/episode_index.csv'}}, ...
            'next_gate_allowed',strcmp(status,'PASS'),'blocking_reason','');
    end
end
function r=validate_role_rows(E,role,expected,root,needAttitude)
rows=E(string(E.source_role)==string(role)&logical_column(E.accepted),:);
r=struct('pass',false,'episode_count',height(rows),'expected_count',height(expected), ...
    'unique_scene_coverage',false,'unique_run_ids',false,'event_files_present',false,'event_contract',false);
if height(rows)~=height(expected)||numel(unique(rows.scene_id))~=height(expected)|| ...
        ~all(ismember(expected.scene_id,rows.scene_id)),return;end
[found,ix]=ismember(expected.scene_id,rows.scene_id);
sceneCoverage=all(found)&&all(lower(string(rows.split(ix)))==lower(string(expected.split)))&& ...
    all(rows.task(ix)==expected.task)&&all(rows.class_index(ix)==expected.c)&&all(rows.wind_cell(ix)==expected.w);
uniqueRuns=numel(unique(rows.run_id))==height(expected);
events=all(double(rows.event_count_position)==1999)&&all(double(rows.ready_count_position)==1968);
if needAttitude
    events=events&&all(double(rows.event_count_attitude)==1999)&&all(double(rows.ready_count_attitude)==1968);
end
files=true;
for i=1:height(rows)
    paths={rows.position_event_path(i)};if needAttitude,paths{end+1}=rows.attitude_event_path(i);end
    for j=1:numel(paths)
        if strlength(string(paths{j}))==0||~isfile(fullfile(root,strrep(char(paths{j}), '/', filesep)))
            files=false;break;
        end
    end
    if ~files,break;end
end
events=events&&all(logical_column(rows.complete))&&all(logical_column(rows.finite))&& ...
    all(double(rows.transition_count)==20000);
r.unique_scene_coverage=sceneCoverage;r.unique_run_ids=uniqueRuns;
r.event_files_present=files;r.event_contract=events;
r.pass=sceneCoverage&&uniqueRuns&&files&&events;
end
function r=validate_b_attitude_reuse(E,M,root)
expected=M(M.split=="TRAIN"|M.split=="VAL",:);rows=E(string(E.source_role)=="B"&logical_column(E.accepted),:);
train=rows(lower(string(rows.split))=="train",:);val=rows(lower(string(rows.split))=="val",:);
r=struct('pass',false,'train_complete',height(train),'val_complete',height(val), ...
    'unique_scene_coverage',false,'attitude_event_files_present',false,'event_counts_correct',false);
if height(rows)~=height(expected)||numel(unique(rows.scene_id))~=height(expected)|| ...
        numel(unique(rows.run_id))~=height(expected)|| ...
        ~all(ismember(expected.scene_id,rows.scene_id)),return;end
[found,ix]=ismember(expected.scene_id,rows.scene_id);
metadata=all(found)&&all(lower(string(rows.split(ix)))==lower(string(expected.split)))&& ...
    all(rows.task(ix)==expected.task)&&all(rows.class_index(ix)==expected.c)&& ...
    all(rows.wind_cell(ix)==expected.w)&&all(logical_column(rows.complete(ix)))&& ...
    all(logical_column(rows.finite(ix)))&&all(double(rows.transition_count(ix))==20000);
files=all(strlength(string(rows.attitude_event_path))>0);
if files
    for i=1:height(rows)
        p=fullfile(root,strrep(char(rows.attitude_event_path(i)),'/',filesep));
        files=files&&isfile(p);if ~files,break;end
    end
end
counts=all(double(rows.event_count_attitude)==1999)&&all(double(rows.ready_count_attitude)==1968);
r.unique_scene_coverage=metadata;r.attitude_event_files_present=files;r.event_counts_correct=counts;
r.pass=metadata&&files&&counts&&height(train)==768&&height(val)==48&& ...
    nnz(lower(string(train.split))=="train")==768&&nnz(lower(string(val.split))=="val")==48;
end
function first=student_first(M)
first=zeros(9,1);n=0;for t=0:2,for w=[8 14 15]
    ix=find(M.split=="TRAIN"&M.student_train&M.t==t&M.w==w&M.c>0);
    assert(~isempty(ix),'DL1018:FirstBatch','Missing fixed Student first-batch scene.');
    [~,k]=min(M.c(ix));n=n+1;first(n)=ix(k);
end,end
end
function M=read_specs(p)
o=detectImportOptions(p,'VariableNamingRule','preserve');o=setvartype(o,{'scene_id','split','task','class_id'},'string');M=readtable(p,o);
end
function c=attempt_columns()
c={'run_id','gate_id','split','scene_id','task','class_index','wind_cell','collector_id','model_id','contract_version', ...
    'runtime_mode','attempt_no','status','plant_started','returned_transitions','complete','finite','safety_stop_reason', ...
    'error_kind','error_message','raw_path','position_event_path','attitude_event_path','started_at','finished_at', ...
    'elapsed_s','accepted_for_training'};
end
function c=episode_columns()
c={'run_id','split','scene_id','task','class_index','wind_cell','source_role','collector_id','behavior_model_id', ...
    'contract_version','position_event_path','attitude_event_path','complete','finite','transition_count', ...
    'event_count_position','event_count_attitude','ready_count_position','ready_count_attitude','accepted','rejection_reason'};
end
function ensure_csv(p,c)
if isfile(p),return;end;f=fopen(p,'w');assert(f>=0);fprintf(f,'%s\n',strjoin(c,','));fclose(f);
end
function yes=h5_matches(p,n)
try,yes=numel(h5read(p,'/event_index'))==n;catch,yes=false;end
end
function append_csv(p,c,v)
assert(numel(c)==numel(v));f=fopen(p,'a');assert(f>=0);z=onCleanup(@()fclose(f));fprintf(f,'%s\n',csv_line(v));clear z;
end
function update_csv(p,id,no,v)
L=readlines(p);found=false;for i=numel(L):-1:2
    q=split(L(i),',');if numel(q)>=12&&q(1)==string(id)&&str2double(q(12))==no,L(i)=string(csv_line(v));found=true;break;end
end
assert(found,'DL1018:AttemptUpdate','Attempt row was not updated.');
f=fopen(p,'w');assert(f>=0);z=onCleanup(@()fclose(f));for i=1:numel(L),fprintf(f,'%s\n',char(L(i)));end;clear z;
end
function s=csv_line(v)
p=cell(1,numel(v));for i=1:numel(v),x=v{i};if isempty(x),p{i}='';elseif islogical(x),p{i}=char(string(x));
elseif isnumeric(x),if isscalar(x)&&isnan(x),p{i}='';else,p{i}=sprintf('%.17g',x);end
else,p{i}=char(string(x));end;p{i}=strrep(strrep(strrep(strrep(p{i},',',';'),'"',''''),newline,' '),char(13),' ');end;s=strjoin(p,',');
end
function x=logical_column(v)
if islogical(v),x=v(:);elseif isnumeric(v),x=double(v(:))~=0;else,q=lower(strtrim(string(v(:))));x=q=="true"|q=="1"|q=="yes";end
end
function p=rel(p,r)
p=char(java.io.File(p).getCanonicalPath());r=char(java.io.File(r).getCanonicalPath());assert(startsWith(lower(p),lower([r filesep])));
p=strrep(p(numel(r)+2:end),'\','/');
end
function t=now_utc()
d=datetime('now','TimeZone','UTC');d.Format='yyyy-MM-dd''T''HH:mm:ss.SSS''Z''';t=char(d);
end
function s=rmfield_if_exists(s,n),if isfield(s,n),s=rmfield(s,n);end,end
function y=iff(c,a,b),if c,y=a;else,y=b;end,end
function f=episode_finite(log)
fields={'state','transition_time','wind_force_I','wind_torque_B','requested_generalized', ...
    'controller_clipped_generalized','realized_generalized','motor_command','motor_setpoint', ...
    'position_compensation_applied_force_N','attitude_compensation_applied_torque_Nm'};f=true;
for i=1:numel(fields),if isfield(log,fields{i}),f=f&&all(isfinite(log.(fields{i})),'all');end,end
end
