function report=collect_g02_position_teacher(projectRoot)
% Collect the locked B/POS_OFF position Teacher pool from new DL1018 scenes.
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
prior=jsondecode(fileread(fullfile(projectRoot,'reports','G01_SCENES.json')));
assert(strcmp(prior.status,'PASS')&&prior.next_gate_allowed,'DL1018:GateLocked','G01 must PASS before G02.');
addpath(fullfile(projectRoot,'matlab','data'),fullfile(projectRoot,'matlab','scenes'), ...
    fullfile(projectRoot,'matlab','runtime'));
[cfg,~,root]=init_dl1018();assert(strcmp(root,projectRoot),'DL1018:RootMismatch','Unexpected project root.');
M=read_specs(fullfile(projectRoot,'configs','scene_specs.csv'));
assert(nnz(M.split=="TRAIN")==768&&nnz(M.split=="VAL")==48,'DL1018:ScenePlan','G02 scene plan is incomplete.');
attemptPath=fullfile(projectRoot,'logs','attempt_index.csv');episodePath=fullfile(projectRoot,'logs','episode_index.csv');
ensure_csv(attemptPath,attempt_columns());ensure_csv(episodePath,episode_columns());
attempts=readtable(attemptPath,'TextType','string');episodes=readtable(episodePath,'TextType','string');
firstBatch=first_batch(M);allRows=find(M.split=="TRAIN"|M.split=="VAL");
ordered=unique([firstBatch(:);setdiff(allRows,firstBatch(:),'stable')],'stable');
collectors=["B","POS_OFF"];totalExpected=1632;plantStarted=0;completed=0;engineeringErrors=0;physicalFailures=0;
trainCounts=struct('B',0,'POS_OFF',0);valCounts=struct('B',0,'POS_OFF',0);
acceptedIds=strings(0,1);
if ~isempty(attempts)
    if any(upper(string(attempts.status))=="RUNNING")
        error('DL1018:UnresolvedAttempt','attempt_index contains RUNNING rows. Inspect the marker and raw file before resume.');
    end
    plantColumn=logical_column(attempts.plant_started);plantStarted=nnz(plantColumn);
    engineeringErrors=nnz(upper(string(attempts.status))=="ENGINEERING_ERROR");
    physicalFailures=nnz(ismember(upper(string(attempts.status)),["SAFE_STOP","DIVERGED","PHYSICAL_FAILURE"]));
end
if ~isempty(episodes)
    accepted=logical_column(episodes.accepted);acceptedIds=string(episodes.run_id(accepted));
    assert(numel(unique(acceptedIds))==numel(acceptedIds),'DL1018:DuplicateAcceptedTuple', ...
        'episode_index contains duplicate accepted G02 tuples.');
    completed=nnz(accepted);
    for id=collectors
        key=char(id);
        trainCounts.(key)=nnz(accepted&(string(episodes.collector_id)==id)&(lower(string(episodes.split))=="train"));
        valCounts.(key)=nnz(accepted&(string(episodes.collector_id)==id)&(lower(string(episodes.split))=="val"));
    end
end
methods=struct('B',controller_options_dl1018(cfg,'B'), ...
    'POS_OFF',controller_options_dl1018(cfg,'POS_OFF'));
startedTimer=tic;
for r=1:numel(ordered)
    row=M(ordered(r),:);split=char(lower(row.split));sceneId=char(row.scene_id);
    sceneRunIds="G02_P_TEACHER_"+string(sceneId)+"_"+collectors;
    if all(ismember(sceneRunIds,acceptedIds))
        log_g02_progress(projectRoot,r,numel(ordered),sceneId,'REUSED_ACCEPTED_SCENE','',completed,plantStarted);
        continue;
    end
    log_g02_progress(projectRoot,r,numel(ordered),sceneId,'BUILD_SCENE','',completed,plantStarted);
    built=make_scenes_dl1018('GET',projectRoot,sceneId);scene=built.scene;
    log_g02_progress(projectRoot,r,numel(ordered),sceneId,'SCENE_READY','',completed,plantStarted);
    for ci=1:numel(collectors)
        collector=char(collectors(ci));runId=sprintf('G02_P_TEACHER_%s_%s',sceneId,collector);
        log_g02_progress(projectRoot,r,numel(ordered),sceneId,'CHECK_RUN',runId,completed,plantStarted);
        priorRows=find(string(attempts.run_id)==string(runId));
        acceptedRows=find(string(episodes.run_id)==string(runId)&logical_column(episodes.accepted));
        if ~isempty(acceptedRows)
            log_g02_progress(projectRoot,r,numel(ordered),sceneId,'REUSED_ACCEPTED',runId,completed,plantStarted);
            continue;
        end
        if ~isempty(priorRows)&&any(ismember(upper(string(attempts.status(priorRows))), ...
                ["SAFE_STOP","DIVERGED","PHYSICAL_FAILURE"]))
            report=make_report('STOPPED_UNSAFE');
            report.blocking_reason=sprintf('Previous physical failure is recorded for %s.',runId);
            write_gate_report_dl1018(fullfile(projectRoot,'reports','G02_P_TEACHER.json'),report);return;
        end
        attemptNo=1;if ~isempty(priorRows),attemptNo=max(double(attempts.attempt_no(priorRows)))+1;end
        attemptFolder=fullfile(projectRoot,'data','raw',split,sceneId,collector,sprintf('attempt_%02d',attemptNo));
        if ~isfolder(attemptFolder),mkdir(attemptFolder);end
        marker=fullfile(attemptFolder,'plant_started.marker');rawPath=fullfile(attemptFolder,'raw_run.mat');
        posPath=fullfile(projectRoot,'data','events','position',split,sceneId,[collector '.h5']);
        attitudePath='';if strcmp(collector,'B'),attitudePath=fullfile(projectRoot,'data','events','attitude',split,sceneId,[collector '.h5']);end
        posRel=relative_to_root(posPath,projectRoot);attRel='';if ~isempty(attitudePath),attRel=relative_to_root(attitudePath,projectRoot);end
        rawRel=relative_to_root(rawPath,projectRoot);runStartPath=fullfile(attemptFolder,'run_start.mat');
        opts=methods.(collector);opts.r2e_first_plant_step_marker=marker;
        runStart=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
            'collector_id',collector,'model_id',collector,'scene_spec',row, ...
            'initial_state',scene.initial_state,'cfg',cfg,'opts',rmfield_if_exists(opts,'r2e_first_plant_step_marker'), ...
            'started_at',datetime('now','TimeZone','UTC'),'raw_path',rawRel);
        save(runStartPath,'runStart','-v7');
        startedAt=now_utc();clock=tic;
        append_csv_record(attemptPath,attempt_columns(),{runId,'G02_P_TEACHER',split,sceneId, ...
            char(row.task),double(row.c),double(row.w),collector,collector, ...
            'DL1018_V311_R2E_PAPER_FINAL','MATLAB_R2025b',attemptNo,'RUNNING',false,0,false,false, ...
            '', '', '',rawRel,posRel,attRel,startedAt,'',NaN,false});
        fprintf('[G02] starting %4d/%4d %s %s %s\n',completed+1,totalExpected,split,sceneId,collector);
        try
            log=run_episode_dl1018(scene,collector,cfg,opts,rawPath);
            plantDidStart=isfile(marker);plantStarted=plantStarted+double(plantDidStart);
            [positionEvents,pMeta]=export_position_events_dl1018(log,scene,cfg,collector,upper(split),row);
            posMeta=struct('scene_id',sceneId,'collector_id',collector,'model_id',collector, ...
                'contract_version','DL1018_V311_R2E_PAPER_FINAL','split',upper(split), ...
                'role','position_teacher','units','x14: mixed physical units; target/applied_compensation: m/s^2', ...
                'feature_order',jsonencode({'e_p_xyz_m','s_p_xyz_mps','euler_rpy_rad','nominal_thrust_mps2','arm_command_1_to_4'}));
            write_events_h5_dl1018(positionEvents,posPath,posMeta);
            aMeta=[];
            if strcmp(collector,'B')
                [attitudeEvents,aMeta]=export_attitude_events_dl1018(log,scene,cfg,collector,upper(split));
                attMeta=struct('scene_id',sceneId,'collector_id',collector,'model_id',collector, ...
                    'contract_version','DL1018_V311_R2E_PAPER_FINAL','split',upper(split), ...
                    'role','attitude_teacher_reused_from_B','units','X29: mixed physical units; target_normalized: unitless; applied_compensation: N*m', ...
                    'feature_order',jsonencode({'error_rpy_rad','surface_rpy_radps','omega_B_radps', ...
                    'filtered_euler_rate_radps','filtered_euler_acceleration_radps2','euler_rpy_rad', ...
                    'inertial_velocity_mps','nominal_angular_acceleration_radps2','thrust_mps2', ...
                    'previous_event_motor_setpoint_over_1900'}));
                write_events_h5_dl1018(attitudeEvents,attitudePath,attMeta);
            else
                attitudeEvents=table();
            end
            transitions=numel(log.transition_time);complete=strcmp(log.status,'STABLE')&&transitions==20000;
            finite=episode_is_finite(log);safety=char(log.safety_stop_reason);
            if ~plantDidStart
                error('DL1018:PlantMarkerMissing','Episode returned without the first-transition marker.');
            end
            if ~finite||~complete
                physicalFailures=physicalFailures+1;failureStatus='SAFE_STOP';if strcmp(log.status,'DIVERGED'),failureStatus='DIVERGED';end
                update_csv_record(attemptPath,runId,attemptNo,{runId,'G02_P_TEACHER',split,sceneId, ...
                    char(row.task),double(row.c),double(row.w),collector,collector,'DL1018_V311_R2E_PAPER_FINAL', ...
                    'MATLAB_R2025b',attemptNo,failureStatus,plantDidStart,transitions,false,finite,safety,'', ...
                    '',rawRel,posRel,attRel,startedAt,now_utc(),toc(clock),false});
                append_csv_record(episodePath,episode_columns(),episodePath_fields(runId,split,sceneId,row,collector,collector, ...
                    posRel,attRel,false,finite,transitions,pMeta.event_count,field_or(aMeta,'event_count',0), ...
                    pMeta.ready_count,field_or(aMeta,'ready_count',0),false,safety));
                report=make_report('STOPPED_UNSAFE');
                report.blocking_reason=sprintf('%s stopped at %.6g s (%s).',collector,log.divergence_time_s,safety);
                write_gate_report_dl1018(fullfile(projectRoot,'reports','G02_P_TEACHER.json'),report);return;
            end
            assert(pMeta.event_count==1999&&pMeta.ready_count==1968&&pMeta.max_label_closure_mps2<=1e-9, ...
                'DL1018:PositionEpisodeContract','Position event count, readiness, or label closure failed.');
            if strcmp(collector,'B')
                assert(aMeta.event_count==1999&&aMeta.ready_count==1968&& ...
                    aMeta.max_requested_torque_closure_Nm<=1e-8&&aMeta.max_dynamics_closure_rads2<=1e-8, ...
                    'DL1018:AttitudeEpisodeContract','B attitude event/label contract failed.');
            end
            completed=completed+1;if strcmp(split,'train'),trainCounts.(collector)=trainCounts.(collector)+1; ...
            else,valCounts.(collector)=valCounts.(collector)+1;end
            update_csv_record(attemptPath,runId,attemptNo,{runId,'G02_P_TEACHER',split,sceneId, ...
                char(row.task),double(row.c),double(row.w),collector,collector,'DL1018_V311_R2E_PAPER_FINAL', ...
                'MATLAB_R2025b',attemptNo,'COMPLETE',true,transitions,true,finite,'','','',rawRel,posRel, ...
                attRel,startedAt,now_utc(),toc(clock),true});
            append_csv_record(episodePath,episode_columns(),episodePath_fields(runId,split,sceneId,row,collector,collector, ...
                posRel,attRel,true,finite,transitions,pMeta.event_count,field_or(aMeta,'event_count',0), ...
                pMeta.ready_count,field_or(aMeta,'ready_count',0),true,''));
            fprintf('[G02] accepted %4d/%4d %s %s %s, Q events=%d, position closure=%.3g\n', ...
                completed,totalExpected,split,sceneId,collector,pMeta.event_count,pMeta.max_label_closure_mps2);
        catch err
            plantDidStart=isfile(marker);plantStarted=plantStarted+double(plantDidStart);
            engineeringErrors=engineeringErrors+1;
            update_csv_record(attemptPath,runId,attemptNo,{runId,'G02_P_TEACHER',split,sceneId, ...
                char(row.task),double(row.c),double(row.w),collector,collector,'DL1018_V311_R2E_PAPER_FINAL', ...
                'MATLAB_R2025b',attemptNo,'ENGINEERING_ERROR',plantDidStart,0,false,false,'', ...
                err.identifier,err.message,rawRel,posRel,attRel,startedAt,now_utc(),toc(clock),false});
            report=make_report('FAIL_RUNTIME_CONTRACT');report.blocking_reason=sprintf('%s: %s',err.identifier,err.message);
            write_gate_report_dl1018(fullfile(projectRoot,'reports','G02_P_TEACHER.json'),report);
            update_plan_started(projectRoot,plantStarted);
            rethrow(err);
        end
        update_plan_started(projectRoot,plantStarted);
    end
end
assert(trainCounts.B==768&&trainCounts.POS_OFF==768&&valCounts.B==48&&valCounts.POS_OFF==48, ...
    'DL1018:G02Coverage','G02 accepted counts do not match the fixed TRAIN/VAL quotas.');
report=make_report('PASS');report.actual_counts.train_complete_per_collector=trainCounts;
report.actual_counts.val_complete_per_collector=valCounts;report.actual_counts.episodes_complete=completed;
report.actual_counts.plant_started=plantStarted;report.actual_counts.engineering_errors=engineeringErrors;
report.actual_counts.physical_failures=physicalFailures;report.elapsed_s=toc(startedTimer);
report.checks=struct('position_events_per_episode',1999,'position_ready_per_episode',1968, ...
    'position_label_closure_max_abs_mps2',1e-9,'B_attitude_events_per_episode',1999, ...
    'B_attitude_ready_per_episode',1968,'B_attitude_torque_closure_max_abs_Nm',1e-8, ...
    'B_attitude_dynamics_closure_max_abs_rads2',1e-8,'old_data_used',false, ...
    'unique_accepted_tuples',true,'first_batch_passed',true);
write_gate_report_dl1018(fullfile(projectRoot,'reports','G02_P_TEACHER.json'),report);
update_plan_status(projectRoot,'G02_P_TEACHER','PASS',plantStarted);

    function r=make_report(status)
        r=struct('gate_id','G02_P_TEACHER','status',status,'contract_version','DL1018_V311_R2E_PAPER_FINAL', ...
            'upstream_passed',true,'model_id','','actual_counts',struct('plant_started',plantStarted, ...
            'episodes_complete',completed,'engineering_errors',engineeringErrors,'physical_failures',physicalFailures), ...
            'checks',struct('position_events_per_episode',1999,'position_ready_per_episode',1968), ...
            'max_errors',struct,'artifacts',{{'data/raw','data/events/position','data/events/attitude', ...
            'logs/attempt_index.csv','logs/episode_index.csv','reports/G02_P_TEACHER.json'}}, ...
            'next_gate_allowed',strcmp(status,'PASS'),'blocking_reason','');
    end
end

function idx=first_batch(M)
idx=zeros(9,1);pos=0;
for t=0:2
    for w=[8 14 15]
        candidates=find(M.split=="TRAIN"&M.t==t&M.w==w&M.student_train&M.c>0);
        assert(~isempty(candidates),'DL1018:G02FirstBatch','No predetermined Student-eligible scene for t=%d w=%d.',t,w);
        [~,q]=min(M.c(candidates));pos=pos+1;idx(pos)=candidates(q);
    end
end
assert(pos==9&&numel(unique(idx))==9,'DL1018:G02FirstBatch','The predeclared first batch is malformed.');
end

function M=read_specs(path)
io=detectImportOptions(path,'VariableNamingRule','preserve');
io=setvartype(io,{'scene_id','split','task','class_id'},'string');M=readtable(path,io);
end

function columns=attempt_columns()
columns={'run_id','gate_id','split','scene_id','task','class_index','wind_cell','collector_id','model_id', ...
    'contract_version','runtime_mode','attempt_no','status','plant_started','returned_transitions','complete', ...
    'finite','safety_stop_reason','error_kind','error_message','raw_path','position_event_path', ...
    'attitude_event_path','started_at','finished_at','elapsed_s','accepted_for_training'};
end
function columns=episode_columns()
columns={'run_id','split','scene_id','task','class_index','wind_cell','source_role','collector_id', ...
    'behavior_model_id','contract_version','position_event_path','attitude_event_path','complete','finite', ...
    'transition_count','event_count_position','event_count_attitude','ready_count_position', ...
    'ready_count_attitude','accepted','rejection_reason'};
end
function ensure_csv(path,columns)
if isfile(path),return;end
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
fid=fopen(path,'w');assert(fid>=0,'DL1018:IndexCreate','Cannot create %s.',path);
fprintf(fid,'%s\n',strjoin(columns,','));fclose(fid);
end
function append_csv_record(path,columns,values)
assert(numel(columns)==numel(values),'DL1018:IndexShape','CSV row has wrong width.');
fid=fopen(path,'a');assert(fid>=0,'DL1018:IndexAppend','Cannot append %s.',path);
cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',csv_line(values));clear cleanup;
end
function update_csv_record(path,runId,attemptNo,values)
lines=readlines(path);found=0;
for i=numel(lines):-1:2
    parts=split(lines(i),',');
    if numel(parts)>=12&&parts(1)==string(runId)&&str2double(parts(12))==attemptNo
        lines(i)=string(csv_line(values));found=i;break;
    end
end
assert(found>0,'DL1018:AttemptUpdate','Could not find RUNNING attempt row %s/%d.',runId,attemptNo);
fid=fopen(path,'w');assert(fid>=0,'DL1018:AttemptRewrite','Cannot update %s.',path);
cleanup=onCleanup(@()fclose(fid));for i=1:numel(lines),fprintf(fid,'%s\n',char(lines(i)));end;clear cleanup;
end
function line=csv_line(values)
parts=cell(1,numel(values));for i=1:numel(values),parts{i}=csv_cell(values{i});end
line=strjoin(parts,',');
end
function s=csv_cell(v)
if isempty(v),s='';elseif islogical(v),s=char(string(v));elseif isnumeric(v),if isscalar(v)&&isnan(v),s='';else,s=sprintf('%.17g',v);end
else,s=char(string(v));end
s=strrep(s,',',';');s=strrep(s,'"','''');s=strrep(s,newline,' ');s=strrep(s,char(13),' ');
end
function tf=logical_column(x)
if islogical(x),tf=x(:);elseif isnumeric(x),tf=double(x(:))~=0;
else,v=lower(strtrim(string(x(:))));tf=v=="true"|v=="1"|v=="yes";end
end
function fields=episodePath_fields(runId,split,sceneId,row,role,model,posPath,attPath,complete,finite,n, ...
    nPos,nAtt,rPos,rAtt,accepted,rejection)
fields={runId,split,sceneId,char(row.task),double(row.c),double(row.w), ...
    role,role,model,'DL1018_V311_R2E_PAPER_FINAL',posPath,attPath,complete,finite,n, ...
    nPos,nAtt,rPos,rAtt,accepted,rejection};
end
function path=relative_to_root(path,root)
path=char(java.io.File(path).getCanonicalPath());root=char(java.io.File(root).getCanonicalPath());
assert(startsWith(lower(path),lower([root filesep])),'DL1018:DataPath','Data output escaped DL1018.');
path=path(numel(root)+2:end);path=strrep(path,'\','/');
end
function started=now_utc()
t=datetime('now','TimeZone','UTC');t.Format='yyyy-MM-dd''T''HH:mm:ss.SSS''Z''';started=char(t);
end
function finite=episode_is_finite(log)
fields={'state','transition_time','wind_force_I','wind_torque_B','requested_generalized', ...
    'controller_clipped_generalized','allocated_generalized','realized_generalized','motor_command', ...
    'motor_setpoint','position_compensation_applied_force_N','attitude_compensation_applied_torque_Nm'};
finite=true;
for i=1:numel(fields)
    if isfield(log,fields{i}),finite=finite&&all(isfinite(log.(fields{i})),'all');end
end
end
function s=rmfield_if_exists(s,name)
if isfield(s,name),s=rmfield(s,name);end
end
function v=field_or(s,name,default)
if isempty(s)||~isstruct(s)||~isfield(s,name),v=default;else,v=s.(name);end
end
function update_plan_started(root,n)
path=fullfile(root,'configs','dataset_plan.json');plan=jsondecode(fileread(path));plan.plant_runs_started=n;
write_gate_report_dl1018_json(path,plan);
end
function update_plan_status(root,gate,status,n)
path=fullfile(root,'configs','dataset_plan.json');plan=jsondecode(fileread(path));plan.plant_runs_started=n;
for i=1:numel(plan.roles),if strcmp(plan.roles(i).gate,gate),plan.roles(i).status=status;end,end
plan.quota_status=status;write_gate_report_dl1018_json(path,plan);
end
function write_gate_report_dl1018_json(path,value)
tmp=[path '.tmp'];fid=fopen(tmp,'w');assert(fid>=0,'DL1018:JsonWrite','Could not write dataset plan.');
cleanup=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');fwrite(fid,newline,'char');
clear cleanup;movefile(tmp,path,'f');
end
function log_g02_progress(root,sceneIndex,sceneTotal,sceneId,phase,runId,episodesComplete,plantStarted)
record=struct('time_utc',now_utc(),'gate','G02_P_TEACHER','scene_index',sceneIndex, ...
    'scene_total',sceneTotal,'scene_id',sceneId,'phase',phase,'run_id',runId, ...
    'episodes_complete',episodesComplete,'plant_started',plantStarted);
line=jsonencode(record);
try
    fid=fopen(fullfile(root,'logs','g02_progress.jsonl'),'a');
    if fid>=0
        cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',line);clear cleanup;
    end
catch
end
try,fprintf(1,'[DL1018_PROGRESS] %s\n',line);catch,end
end
