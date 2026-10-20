function report=collect_student_refine(root,modelIds,limitPerModel)
if nargin<3||isempty(limitPerModel),limitPerModel=inf;end
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','gru14_dssm14_student_refine_v1');
pre=jsondecode(fileread(fullfile(out,'reports','zero_plant_preflight.json')));
assert(strcmp(pre.status,'ZERO_PLANT_PREFLIGHT_PASS')&&pre.plant_starts==0, ...
    'STUDENT:Preflight','Zero-Plant preflight must pass before collection.');
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'STUDENT:Root','Unexpected project root.');
search=fullfile(root,'experiments','position_only_closed_loop_search_v1','local_runtime');
teacher=fullfile(root,'experiments','teacher_reuse_model_screen_v1','local_runtime');
addpath(genpath(search),'-begin');addpath(genpath(teacher),'-begin');rehash;
plan=readtable(fullfile(out,'manifests','student_scene_plan.csv'),'TextType','string');
startedBefore=count_plants(out);rows=struct([]);
statePath=fullfile(out,'state','state.json');
for mi=1:numel(modelIds)
    modelId=char(modelIds{mi});
    assert(ismember(modelId,{'GRU14','DSSM14'}),'STUDENT:Model','Unexpected model %s.',modelId);
    cp=jsondecode(fileread(fullfile(out,'protocol.json')));identity=cp.checkpoints.(modelId);
    package=fullfile(root,identity.matlab_package);
    saved=load(package,'model');model=saved.model;model.model_id=modelId;
    selected=plan(plan.model_id==modelId,:);
    completedForModel=0;
    for ri=1:height(selected)
        r=selected(ri,:);split=char(r.split);sceneId=char(r.scene_id);
        folder=fullfile(out,'student_raw',modelId,split,sceneId);
        if ~isfolder(folder),mkdir(folder);end
        completed=dir(fullfile(folder,'attempt_*','manifest_row.json'));
        if ~isempty(completed)
            donePath=fullfile(completed(1).folder,completed(1).name);
            savedRow=jsondecode(fileread(donePath));rows=append_row(rows,savedRow);completedForModel=completedForModel+1;
            if ~strcmp(char(savedRow.status),'STABLE'),break;end
            if completedForModel>=limitPerModel,break;end
            continue
        end
        attempts=dir(fullfile(folder,'attempt_*'));attemptNumber=numel(attempts)+1;
        legacyFailure=isfile(fullfile(folder,'plant_started.marker'))&& ...
            ~isfile(fullfile(folder,'raw_run.mat'))&&isfile(fullfile(folder,'error.json'));
        if legacyFailure,attemptNumber=max(attemptNumber,2);end
        attemptFolder=fullfile(folder,sprintf('attempt_%02d',attemptNumber));
        if ~isfolder(attemptFolder),mkdir(attemptFolder);end
        raw=fullfile(attemptFolder,'raw_run.mat');start=fullfile(attemptFolder,'run_start.mat');
        marker=fullfile(attemptFolder,'plant_started.marker');metricPath=fullfile(attemptFolder,'metrics.json');
        eventPath=fullfile(attemptFolder,'position_events.h5');sequencePath=fullfile(attemptFolder,'sequence_cache.mat');
        rowPath=fullfile(attemptFolder,'manifest_row.json');
        if isfile(marker)&&~isfile(raw)
            error('STUDENT:InterruptedPlant','Plant start was recorded without completed raw log: %s',raw);
        end
        if isfile(raw)
            q=load(raw,'log','scene');log=q.log;scene=q.scene;
            assert(isfile(start),'STUDENT:MissingRunStart','Existing raw has no run_start: %s',raw);
            rs=load(start,'runStart');runStart=rs.runStart;
        else
            generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
            addpath(genpath(search),'-begin');addpath(genpath(teacher),'-begin');rehash;
            opts=position_only_search_options(cfg,model,'FEATURE',12,1);
            assert(~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
                opts.rbf_attitude_enabled&&opts.rbf_attitude_update_enabled&& ...
                opts.stage1_position_runtime.update_enabled, ...
                'STUDENT:Controller','Controller isolation changed before %s.',sceneId);
            opts.r2e_first_plant_step_marker=marker;
            runId=sprintf('STUDENT_%s_%s_%s_ATTEMPT_%02d',modelId,upper(split),sceneId,attemptNumber);
            runStart=struct('run_id',runId,'model_id',modelId,'role',char(r.role), ...
                'split',split,'scene_id',sceneId,'scene_spec',r,'scene',scene, ...
                'cfg',cfg,'opts',opts,'model',model,'package_path',package, ...
                'package_sha256',identity.matlab_package_sha256, ...
                'source_checkpoint',identity.checkpoint,'source_checkpoint_sha256',identity.checkpoint_sha256, ...
                'head_type','FEATURE','gamma',12,'kappa',1,'pcf_enabled',true, ...
                'started_at_utc',utc_now());
            save(start,'runStart','-v7.3');
            state=load_state(statePath);state.status='IN_PROGRESS';state.phase='STUDENT_COLLECTION';
            state.active_model=modelId;state.active_split=split;state.active_scene=sceneId;
            state.plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
            try
                episode=@run_episode_dl1018;
                log=episode(scene,'P_A',cfg,opts,raw);
            catch err
                write_json(fullfile(folder,'error.json'),struct('identifier',err.identifier, ...
                    'message',err.message,'plant_started',isfile(marker),'scene_id',sceneId));
                if isfile(marker),append_ledger(out,runId,'ENGINEERING_OR_RUNTIME_ERROR',err.identifier);end
                rethrow(err)
            end
        end
        assert(isfile(marker),'STUDENT:PlantMarker','Runner did not record the first Plant transition.');
        if numel(log.transition_time)~=20000||~strcmp(char(log.status),'STABLE')
            failure=struct('run_id',runStart.run_id,'model_id',modelId,'role',char(r.role), ...
                'split',split,'scene_id',sceneId,'status',char(log.status), ...
                'transitions',numel(log.transition_time),'expected_transitions',20000, ...
                'event_count',0,'ready_count',0,'position_Q_0_20_m',NaN, ...
                'position_axis_rmse_m',[NaN NaN NaN],'max_label_closure_mps2',NaN, ...
                'valid_position_inference_events',0,'online_weight_update_events',0, ...
                'plant_started',true,'raw_path',relpath(root,raw),'run_start_path',relpath(root,start), ...
                'event_path','','sequence_cache_path','','eligible_for_training',false, ...
                'finished_at_utc',utc_now());
            write_json(fullfile(attemptFolder,'failure_record.json'),failure);
            write_json(metricPath,failure);write_json(rowPath,failure);
            append_ledger(out,runStart.run_id,'PHYSICAL_OR_INCOMPLETE_FAILURE',char(log.status));
            rows=append_row(rows,failure);refresh_manifest(out);completedForModel=completedForModel+1;
            fprintf('STUDENT_EPISODE_FAILED model=%s split=%s scene=%s status=%s transitions=%d/20000; stopping this model and continuing the other.\n', ...
                modelId,split,sceneId,char(log.status),numel(log.transition_time));
            break
        end
        [events,eventMeta]=export_position_events_dl1018(log,scene,cfg,char(r.role),upper(split),r);
        assert(height(events)==1999&&eventMeta.ready_count==1968&&eventMeta.max_label_closure_mps2<=1e-9, ...
            'STUDENT:Export','Event count/readiness/label closure failed for %s.',sceneId);
        metadata=struct('run_id',runStart.run_id,'model_id',modelId,'role',char(r.role), ...
            'split',split,'scene_id',sceneId,'source_package_sha256',identity.matlab_package_sha256, ...
            'event_count',eventMeta.event_count,'ready_count',eventMeta.ready_count, ...
            'max_label_closure_mps2',eventMeta.max_label_closure_mps2);
        if ~isfile(eventPath),write_events_h5_dl1018(events,eventPath,metadata);end
        if ~isfile(sequencePath)
            X=table2array(events(:,compose("x14_%d",1:14)));
            Y=table2array(events(:,compose("target_clip_%d",1:3)));
            Yraw=table2array(events(:,compose("target_raw_%d",1:3)));
            phase=uint8(events.phase_code);ready=logical(events.ready);event_time=double(events.event_time_s);
            run_id=runStart.run_id;save(sequencePath,'X','Y','Yraw','phase','ready','event_time','run_id','-v7');
        end
        tt=double(log.transition_time(:));
        stateX=double(log.state(1:numel(tt),1:3));refX=double(log.reference.position(1:numel(tt),:));
        mask=tt>=0&tt<20;err=stateX(mask,:)-refX(mask,:);
        axisRmse=sqrt(mean(err.^2,1));q=sqrt(mean(sum(err.^2,2)));
        updates=0;if isfield(log,'stage1_position_event_weight_delta_fro')
            updates=nnz(double(log.stage1_position_event_weight_delta_fro(:))>1e-12);
        end
        inferenceCount=nnz(log.stage1_position_event_inference_valid(:));
        metrics=struct('run_id',runStart.run_id,'model_id',modelId,'role',char(r.role), ...
            'split',split,'scene_id',sceneId,'status',char(log.status),'transitions',numel(tt),'expected_transitions',20000, ...
            'event_count',eventMeta.event_count,'ready_count',eventMeta.ready_count, ...
            'position_Q_0_20_m',q,'position_axis_rmse_m',axisRmse, ...
            'max_label_closure_mps2',eventMeta.max_label_closure_mps2, ...
            'valid_position_inference_events',inferenceCount,'online_weight_update_events',updates, ...
            'plant_started',true,'raw_path',relpath(root,raw),'run_start_path',relpath(root,start), ...
            'event_path',relpath(root,eventPath),'sequence_cache_path',relpath(root,sequencePath), ...
            'eligible_for_training',true,'finished_at_utc',utc_now());
        assert(isfinite(q)&&inferenceCount==1968&&updates>0, ...
            'STUDENT:OnlineUse','The 32-event online position model was not used as expected for %s.',sceneId);
        write_json(metricPath,metrics);write_json(rowPath,metrics);append_ledger(out,runStart.run_id,char(log.status),'');
        rows=append_row(rows,metrics);completedForModel=completedForModel+1;
        refresh_manifest(out);state=load_state(statePath);state.active_model='';state.active_split='';state.active_scene='';
        state.phase='STUDENT_COLLECTION';state.completed_student_episodes=count_complete(out);
        state.plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
        fprintf('STUDENT_EPISODE_DONE model=%s split=%s completed=%d/120 scene=%s status=%s Q=%.9g axes=[%.7g %.7g %.7g] events=%d/%d closure=%.3g updates=%d elapsed_minutes=%.2f\n', ...
            modelId,split,completedForModel,sceneId,char(log.status),q,axisRmse(1),axisRmse(2),axisRmse(3), ...
            eventMeta.event_count,eventMeta.ready_count,eventMeta.max_label_closure_mps2,updates, ...
            minutes_since(runStart.started_at_utc));
        if completedForModel>=limitPerModel,break;end
    end
end
report=struct('status','STUDENT_COLLECTION_PARTIAL_OR_COMPLETE','new_plant_starts',count_plants(out)-startedBefore, ...
    'terminal_episode_rows',count_complete(out),'stable_episodes',count_stable(out), ...
    'failed_episodes',count_complete(out)-count_stable(out),'planned_episodes',240,'plant_starts_total',count_plants(out), ...
    'models',{modelIds},'created_at_utc',utc_now());
write_json(fullfile(out,'reports','collection_state.json'),report);
fprintf('STUDENT_COLLECTION_PROGRESS stable=%d/240 failed=%d terminal=%d/240 plants=%d new_this_call=%d\n', ...
    report.stable_episodes,report.failed_episodes,report.terminal_episode_rows, ...
    report.plant_starts_total,report.new_plant_starts);
end

function rows=append_row(rows,row)
fields={'run_id','model_id','role','split','scene_id','status','transitions','expected_transitions', ...
    'event_count','ready_count','position_Q_0_20_m','position_axis_rmse_m', ...
    'max_label_closure_mps2','valid_position_inference_events','online_weight_update_events', ...
    'plant_started','raw_path','run_start_path','event_path','sequence_cache_path', ...
    'eligible_for_training','finished_at_utc'};
if ~isfield(row,'expected_transitions'),row.expected_transitions=20000;end
if ~isfield(row,'eligible_for_training')
    row.eligible_for_training=strcmp(char(row.status),'STABLE')&&double(row.transitions)==20000;
end
row=orderfields(row,fields);
if isempty(rows),rows=row;else,rows=orderfields(rows,fields);rows(end+1)=row;end
end
function n=count_plants(out)
d=dir(fullfile(out,'student_raw','**','plant_started.marker'));n=numel(d);
end
function n=count_complete(out)
d=dir(fullfile(out,'student_raw','**','manifest_row.json'));n=numel(d);
end
function n=count_stable(out)
d=dir(fullfile(out,'student_raw','**','manifest_row.json'));n=0;
for i=1:numel(d)
    r=jsondecode(fileread(fullfile(d(i).folder,d(i).name)));
    n=n+(strcmp(char(r.status),'STABLE')&&double(r.transitions)==20000);
end
end
function s=load_state(path)
if isfile(path),s=jsondecode(fileread(path));else,s=struct;end
end
function refresh_manifest(out)
files=dir(fullfile(out,'student_raw','**','manifest_row.json'));rows=struct([]);
for i=1:numel(files),rows=append_row(rows,jsondecode(fileread(fullfile(files(i).folder,files(i).name))));end
if isempty(rows),return;end
writetable(struct2table(rows,'AsArray',true),fullfile(out,'manifests','student_episode_manifest.csv'));
end
function append_ledger(out,id,status,note)
path=fullfile(out,'RESOURCE_LEDGER.csv');
if ~isfile(path),fid=fopen(path,'w');fprintf(fid,'timestamp_utc,resource,identity,count,status,notes\n');fclose(fid);end
if contains(fileread(path),id),return;end
fid=fopen(path,'a');fprintf(fid,'%s,Plant,%s,1,%s,%s\n',utc_now(),id,status,strrep(note,',',';'));fclose(fid);
end
function s=utc_now()
s=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
end
function p=relpath(root,path)
p=strrep(char(java.io.File(path).getCanonicalPath()),[root filesep],'');p=strrep(p,filesep,'/');
end
function t=minutes_since(started)
t=minutes(datetime('now','TimeZone','UTC')-datetime(started, ...
    'InputFormat','yyyy-MM-dd''T''HH:mm:ss.SSSXXX','Locale','en_US','TimeZone','UTC'));
end
function write_json(path,value)
fid=fopen(path,'w');assert(fid>0,'STUDENT:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');
end
