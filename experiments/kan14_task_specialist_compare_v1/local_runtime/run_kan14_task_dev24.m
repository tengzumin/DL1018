function summary=run_kan14_task_dev24(projectRoot,preflightOnly)
% Resumable, paired 24-scene evaluation of shared vs task-routed KAN14.
if nargin<1||isempty(projectRoot),projectRoot=pwd;end
if nargin<2,preflightOnly=false;end
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
out=fullfile(projectRoot,'experiments','kan14_task_specialist_compare_v1');local=fullfile(out,'local_runtime');
addpath(genpath(fullfile(projectRoot,'matlab')));
[cfg,~,resolved]=init_dl1018();assert(strcmp(projectRoot,resolved),'KAN14TASK:Root','Unexpected project root.');
addpath(genpath(local),'-begin');rehash;clear position_stage1_model_forward_v2 run_dl1018_closed_loop
parity=jsondecode(fileread(fullfile(out,'reports','EXPORT_PARITY.json')));
assert(strcmp(parity.status,'PASS')&&parity.package_count==4&&parity.fixture_total==256&&parity.plant_starts==0, ...
    'KAN14TASK:ParityGate','Four-package zero-Plant parity must pass before DEV Plant runs.');
assert(abs(cfg.plant.dt-.001)<1e-12&&cfg.rbf.runtime.position_update_hz==100, ...
    'KAN14TASK:Clock','Expected 1 ms Plant and 100 Hz position update.');
dev=readtable(fullfile(projectRoot,'reports','POSITION_DEV.csv'),'TextType','string');
devB=dev(dev.method=="B",:);
specs=readtable(fullfile(projectRoot,'configs','scene_specs.csv'),'TextType','string');
assert(height(devB)==24&&numel(unique(devB.scene_id))==24,'KAN14TASK:DEV24','Expected the frozen 24-scene same-scene B baseline.');
taskNames=["HELIX","FIG8_3D","SQUARE"];
assert(all(arrayfun(@(i)nnz(devB.task==taskNames(i))==8,1:numel(taskNames))), ...
    'KAN14TASK:TaskBalance','DEV24 must contain eight scenes per task.');
assert(nnz(devB.class_index==0)==3&&nnz(devB.wind_cell==15)==3, ...
    'KAN14TASK:DEVComposition','Expected three C00 scenes and three W15 scenes.');
assert(all(strcmp(string(devB.status),'STABLE'))&&all(double(devB.complete)==1)&& ...
    all(double(devB.finite)==1)&&all(double(devB.transitions)==20000), ...
    'KAN14TASK:Baseline','All same-scene B references must be stable, finite, and complete.');
for i=1:height(devB)
    sid=char(devB.scene_id(i));spec=specs(specs.scene_id==string(sid),:);
    assert(height(spec)==1&&spec.split=="DEV"&&spec.task==devB.task(i), ...
        'KAN14TASK:SceneSpec','Missing/mismatched DEV scene spec for %s.',sid);
    bpath=fullfile(projectRoot,strrep(char(devB.raw_path(i)),'/',filesep));
    assert(isfile(bpath)&&contains(string(devB.raw_path(i)),string(sid))&&contains(string(devB.raw_path(i)),"/B/"), ...
        'KAN14TASK:BaselineRaw','Missing or mismatched same-scene B raw file for %s.',sid);
end
preflight=struct('status','PASS_BEFORE_FIRST_DEV_PLANT','scenes',24,'scenes_per_task',[8 8 8], ...
    'c00_scenes',3,'w15_scenes',3,'deformation_scenes',21,'same_scene_B_raw_present',true, ...
    'parity_status','PASS','parity_fixture_count',256,'shared_runs_expected',24, ...
    'expert_runs_expected',24,'plant_starts_before',count_plant_markers(out),'test_accessed',false, ...
    'created_at_utc',utc_now());
write_json(fullfile(out,'reports','DEV24_PREFLIGHT.json'),preflight);
assert(preflight.plant_starts_before<=48,'KAN14TASK:UnexpectedPlants','DEV24 Plant marker count exceeds the frozen budget.');
protocolSha=sha256_file(fullfile(out,'protocol.json'));

registry=readcell(fullfile(out,'manifests','package_registry.csv'),'Delimiter',',','Encoding','UTF-8');
headers=string(registry(1,:));headers(1)=erase(headers(1),char(65279));
packages=struct([]);
for i=2:size(registry,1)
    policy=celltext(registry,i,headers,'policy_id');
    modelPath=fullfile(projectRoot,strrep(celltext(registry,i,headers,'mat_path'),'/',filesep));
    F=load(modelPath,'model');q=F.model;q.model_id='KAN14';
    item=struct('policy_id',policy,'task',celltext(registry,i,headers,'task'), ...
        'seed',str2double(celltext(registry,i,headers,'seed')),'selected_step',str2double(celltext(registry,i,headers,'selected_step')),...
        'model',q,'package_path',celltext(registry,i,headers,'mat_path'));
    if isempty(packages),packages=item;else,packages(end+1,1)=item;end %#ok<AGROW>
end
sharedIndex=find(strcmp({packages.policy_id},'SHARED_KAN14'),1);
assert(~isempty(sharedIndex),'KAN14TASK:SharedPackage','Shared KAN14 package is missing.');
for task=taskNames
    assert(any(strcmp({packages.policy_id},['TASK_KAN14_' char(task)])), ...
        'KAN14TASK:ExpertPackage','Missing task specialist %s.',char(task));
end
if preflightOnly
    summary=preflight;fprintf('KAN14_TASK_DEV24_PREFLIGHT status=%s scenes=%d C00=%d W15=%d Plant=%d\n', ...
        summary.status,summary.scenes,summary.c00_scenes,summary.w15_scenes,summary.plant_starts_before);return
end

statePath=fullfile(out,'state','state.json');state=jsondecode(fileread(statePath));
if ~isfield(state,'started_at_utc')||isempty(state.started_at_utc),state.started_at_utc=utc_now();end
state.status='IN_PROGRESS';state.phase='DEV24_CLOSED_LOOP';state.active_policy='';state.active_scene='';
state.plant_budget_max=48;state.updated_at_utc=utc_now();write_json(statePath,state);
resultsPath=fullfile(out,'reports','DEV24_PAIRED_RESULTS.csv');
progressPath=fullfile(out,'reports','DEV24_PROGRESS.json');
rows=struct([]);completed=0;startedAt=tic;expected=48;
policies={'SHARED_KAN14','TASK_SPECIALIST'};
for pi=1:numel(policies)
    policyType=policies{pi};
    for si=1:height(devB)
        sid=char(devB.scene_id(si));task=char(devB.task(si));
        if strcmp(policyType,'SHARED_KAN14')
            pkg=packages(sharedIndex);policyId='SHARED_KAN14';
        else
            policyId=['TASK_KAN14_' task];ix=find(strcmp({packages.policy_id},policyId),1);pkg=packages(ix);
            assert(strcmp(pkg.task,task),'KAN14TASK:Router','Wrong expert routed to %s.',sid);
        end
        sceneDir=fullfile(out,'runs',policyId,sid);if ~isfolder(sceneDir),mkdir(sceneDir);end
        rawPath=fullfile(sceneDir,'raw_run.mat');startPath=fullfile(sceneDir,'run_start.mat');
        marker=fullfile(sceneDir,'plant_started.marker');metricsPath=fullfile(sceneDir,'metrics.json');
        b=baseline_row(devB(si,:));
        if isfile(metricsPath)
            saved=jsondecode(fileread(metricsPath));row=saved.metrics_row;
            assert(isfile(rawPath)&&isfile(startPath),'KAN14TASK:MissingEvidence','Metrics saved without raw/start evidence: %s.',sid);
        elseif isfile(marker)&&~isfile(rawPath)
            error('KAN14TASK:InterruptedPlant','Plant-start marker exists without raw MAT at %s; refusing duplicate Plant.',sid);
        elseif isfile(fullfile(sceneDir,'error.json'))&&~isfile(rawPath)
            error('KAN14TASK:PriorError','Existing error record without raw MAT at %s needs inspection.',sid);
        elseif isfile(rawPath)
            assert(isfile(startPath),'KAN14TASK:MissingStart','Raw MAT exists without run_start MAT at %s.',sid);
            q=load(rawPath,'log','scene');z=load(startPath,'runStart');runStart=z.runStart;
            log=q.log;scene=q.scene;opts=runStart.opts;spec=specs(specs.scene_id==string(sid),:);
            core=measure_pcf_dl1018(log,scene,double(opts.stage1_position_runtime.weight));
            met=metrics_dl1018(log,scene,spec,core,b.Q_0_20_m,b.A_0_20_rad,b.position_peak_m,true);
            runId=char(runStart.run_id);
            row=make_row(runId,policyId,task,sid,pkg,log,core,met,b,isfile(marker), ...
                relative_path(projectRoot,rawPath),relative_path(projectRoot,startPath),cfg.rbf.position.dmax);
            write_json(metricsPath,struct('metrics_row',row,'source_reused',false,'recovered_from_raw',true,'finished_at_utc',utc_now()));
            if isfile(marker),append_ledger(out,runId,char(log.status),policyId,sid);end
        else
            spec=specs(specs.scene_id==string(sid),:);sceneOut=make_scenes_dl1018('GET',projectRoot,sid);scene=sceneOut.scene;
            % Scene retrieval calls init_dl1018, which restores MATLAB's default path.
            addpath(genpath(local),'-begin');rehash;
            opts=position_only_search_options(cfg,pkg.model,'FEATURE',12,1);
            p=opts.stage1_position_runtime;
            assert(~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
                opts.rbf_attitude_enabled&&opts.rbf_attitude_output_enabled&&opts.rbf_attitude_update_enabled&& ...
                p.command_filter_coordination_v3_5.enabled&&p.update_enabled&& ...
                opts.position_rbf_frequency_hz==100&&norm(double(p.weight)-double(pkg.model.output_W),'fro')<1e-12, ...
                'KAN14TASK:ControllerIsolation','Frozen outer/attitude/PCF contract mismatch before %s.',sid);
            runId=sprintf('KAN14_TASK_DEV_%s_%s_SEED%d',policyType,sid,pkg.seed);
            runStart=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',runId, ...
                'gate_id','G_KAN14_TASK_SPECIALIST_DEV24','phase','DEV24','split','dev', ...
                'collector_id','KAN14_TASK_SPECIALIST_COMPARE_V1','model_id','KAN14','policy_id',policyId, ...
                'task',task,'seed',pkg.seed,'checkpoint_kind','final_step','selected_step',pkg.selected_step, ...
                'head_type','FEATURE','gamma',12,'kappa',1,'normalizer_id','TEACHER_TRAIN_INITIAL_X14_PLUS_TRAIN_X20_EXTRAS', ...
                'encoder_frozen',true,'scene_spec',table2struct(spec),'cfg',cfg,'opts',opts, ...
                'initial_state',scene.initial_state,'same_scene_B_run_id',b.run_id,'same_scene_B_raw_path',b.raw_path, ...
                'model_package_path',pkg.package_path,'started_at_utc',utc_now(), ...
                'protocol_sha256',protocolSha);
            save(startPath,'runStart','-v7');
            state=jsondecode(fileread(statePath));state.active_policy=policyId;state.active_scene=sid;
            state.active_run_id=runId;state.updated_at_utc=utc_now();write_json(statePath,state);
            opts.r2e_first_plant_step_marker=marker;
            try
                log=run_episode_dl1018(scene,'P_A',cfg,opts,rawPath);
            catch err
                write_json(fullfile(sceneDir,'error.json'),struct('identifier',err.identifier,'message',err.message, ...
                    'plant_started',isfile(marker),'scene_id',sid,'policy_id',policyId));
                if isfile(marker),append_ledger(out,runId,'ENGINEERING_ERROR',policyId,sid);end
                rethrow(err)
            end
            core=measure_pcf_dl1018(log,scene,double(opts.stage1_position_runtime.weight));
            met=metrics_dl1018(log,scene,spec,core,b.Q_0_20_m,b.A_0_20_rad,b.position_peak_m,true);
            row=make_row(runId,policyId,task,sid,pkg,log,core,met,b,isfile(marker), ...
                relative_path(projectRoot,rawPath),relative_path(projectRoot,startPath),cfg.rbf.position.dmax);
            write_json(metricsPath,struct('metrics_row',row,'source_reused',false,'finished_at_utc',utc_now()));
            if isfile(marker),append_ledger(out,runId,char(log.status),policyId,sid);end
        end
        rows=append_rows(rows,row);completed=completed+1;
        persist_rows(rows,resultsPath);
        elapsed=toc(startedAt);rate=completed/max(elapsed,eps);remaining=max(0,expected-completed)/max(rate,eps);
        progress=struct('phase','DEV24_CLOSED_LOOP','status','IN_PROGRESS','completed_runs',completed, ...
            'expected_runs',expected,'shared_completed',nnz(strcmp({rows.policy_id},'SHARED_KAN14')), ...
            'expert_completed',nnz(strcmp({rows.policy_id},'TASK_KAN14_HELIX')|strcmp({rows.policy_id},'TASK_KAN14_FIG8_3D')|strcmp({rows.policy_id},'TASK_KAN14_SQUARE')), ...
            'latest_policy',policyId,'latest_scene_id',sid,'latest_task',task,'latest_Q_0_20_m',row.Q_0_20_m, ...
            'latest_same_scene_B_Q_0_20_m',row.B_Q_0_20_m,'latest_delta_Q_m',row.delta_Q_vs_B_m, ...
            'cumulative_Plant_starts',count_plant_markers(out),'elapsed_s',elapsed, ...
            'throughput_runs_per_hour',rate*3600,'eta_remaining_s',remaining, ...
            'updated_at_utc',utc_now());
        write_json(progressPath,progress);
        state=jsondecode(fileread(statePath));state.status='IN_PROGRESS';state.phase='DEV24_CLOSED_LOOP';
        state.completed_runs=completed;state.expected_runs=expected;state.cumulative_new_plant_starts=count_plant_markers(out);
        state.active_policy='';state.active_scene='';state.active_run_id='';state.updated_at_utc=utc_now();write_json(statePath,state);
        fprintf('KAN14_TASK_DEV_RUN completed=%d/%d policy=%s task=%s scene=%s Q=%.9g B=%.9g status=%s Plant=%d ETA=%s\n', ...
            completed,expected,policyId,task,sid,row.Q_0_20_m,row.B_Q_0_20_m,row.status, ...
            count_plant_markers(out),eta_text(remaining));
    end
end
assert(numel(rows)==48,'KAN14TASK:Count','Expected all 48 runs; got %d.',numel(rows));
summary=struct('status','DEV24_CLOSED_LOOP_COMPLETE','completed_runs',numel(rows), ...
    'shared_runs',nnz(strcmp({rows.policy_id},'SHARED_KAN14')),'expert_runs',nnz(~strcmp({rows.policy_id},'SHARED_KAN14')),...
    'plant_starts',count_plant_markers(out),'max_plant_starts',48,'results_csv',relative_path(projectRoot,resultsPath), ...
    'same_scene_B_reused',true,'test_accessed',false,'completed_at_utc',utc_now());
write_json(fullfile(out,'reports','DEV24_SUMMARY.json'),summary);
state=jsondecode(fileread(statePath));state.status='IN_PROGRESS';state.phase='DEV24_CLOSED_LOOP_COMPLETE';
state.completed_runs=48;state.expected_runs=48;state.cumulative_new_plant_starts=summary.plant_starts;
state.updated_at_utc=summary.completed_at_utc;write_json(statePath,state);
fprintf('KAN14_TASK_DEV24_COMPLETE runs=48 shared=24 experts=24 Plant=%d\n',summary.plant_starts);
end

function b=baseline_row(z)
b=struct('run_id',char(z.run_id),'Q_0_20_m',double(z.Q_0_20_m),'A_0_20_rad',double(z.A_0_20_rad), ...
    'position_peak_m',double(z.position_peak_m),'complete',logical(z.complete),'finite',logical(z.finite), ...
    'raw_path',char(z.raw_path));
assert(b.complete&&b.finite&&strcmp(char(z.status),'STABLE')&&isfinite(b.Q_0_20_m), ...
    'KAN14TASK:Baseline','Invalid same-scene B reference for %s.',char(z.scene_id));
end

function row=make_row(id,policy,task,sid,pkg,log,core,met,b,started,raw,start,dmax)
event=logical(log.stage1_position_event_inference_valid(:));rawHead=double(log.stage1_position_event_raw_acceleration_mps2);
clipCount=0;if any(event),clipCount=nnz(any(abs(rawHead(event,:))>double(dmax(:)).'+1e-12,2));end
row=struct('run_id',id,'policy_id',policy,'task',task,'scene_id',sid,'model_id','KAN14', ...
    'seed',pkg.seed,'selected_step',pkg.selected_step,'checkpoint_kind','final_step','head_type','FEATURE', ...
    'gamma',12,'kappa',1,'status',char(log.status),'complete',logical(core.complete),'finite',logical(core.finite), ...
    'transitions',double(core.transitions),'plant_started',logical(started),'Q_0_20_m',double(met.Q_0_20_m), ...
    'B_run_id',b.run_id,'B_raw_path',b.raw_path,'B_Q_0_20_m',b.Q_0_20_m, ...
    'delta_Q_vs_B_m',double(met.Q_0_20_m)-b.Q_0_20_m,'Q_0_5_m',double(core.Q_0_5_m), ...
    'Q_5_20_m',double(met.Q_5_20_m),'dynamic_Q_5_20_m',double(core.dynamic_Q_5_20_m), ...
    'position_axis_rmse_m',jsonencode(met.position_axis_rmse_m),'attitude_axis_rmse_rad',jsonencode(met.attitude_axis_rmse_rad), ...
    'A_0_20_rad',double(met.A_0_20_rad),'yaw_peak_abs_rad',double(met.yaw_peak_abs_rad), ...
    'position_peak_m',double(met.position_peak_m),'position_p95_m',double(met.position_p95_m), ...
    'B_position_peak_m',b.position_peak_m,'motor_TV_normalized_per_s',double(met.motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(met.motor_saturation_fraction),'generalized_clip_fraction',double(met.generalized_clip_fraction), ...
    'max_motor_step_rad_s',double(met.max_motor_step_rad_s),'max_motor_step_time_s',double(met.max_motor_step_time_s), ...
    'motor_min_rad_s',double(met.motor_min_rad_s),'motor_max_rad_s',double(met.motor_max_rad_s), ...
    'controller_p99_ms',double(met.controller_p99_ms),'controller_worst_ms',double(met.controller_worst_ms), ...
    'control_loop_p99_ms',double(met.control_loop_p99_ms),'position_head_update_count',double(met.position_head_update_count), ...
    'position_head_projection_count',double(met.position_head_projection_count), ...
    'head_output_clip_count',clipCount,'safety_stop_reason',char(met.safety_stop_reason), ...
    'source','NEW_PLANT','raw_path',raw,'run_start_path',start,'phase_metrics_json',char(met.phase_metrics_json));
end

function rows=append_rows(rows,row)
if isempty(rows),rows=row;else,rows(end+1,1)=row;end
end

function persist_rows(rows,path)
if isempty(rows),return;end
writetable(struct2table(rows,'AsArray',true),path);
end

function append_ledger(out,identity,status,policy,sid)
path=fullfile(out,'RESOURCE_LEDGER.csv');
if isfile(path)
    C=readcell(path,'Delimiter',',','Encoding','UTF-8');h=string(C(1,:));h(1)=erase(h(1),char(65279));
    col=find(h=="identity",1);
    for i=2:size(C,1),if strcmp(cell_value(C{i,col}),identity),return;end,end
else
    fid=fopen(path,'w','n','UTF-8');fprintf(fid,'timestamp_utc,phase,resource_type,identity,count,status,notes\n');fclose(fid);
end
fid=fopen(path,'a','n','UTF-8');assert(fid>=0,'KAN14TASK:Ledger','Could not append resource ledger.');
notes=csv_quote(sprintf('%s scene=%s',policy,sid));
fprintf(fid,'%s,DEV24,Plant,%s,1,%s,%s\n',utc_now(),identity,status,notes);fclose(fid);
end

function n=count_plant_markers(out)
files=dir(fullfile(out,'runs','**','plant_started.marker'));n=numel(files);
end

function p=relative_path(root,path)
p=strrep(path(length(root)+2:end),'\','/');
end

function txt=eta_text(seconds)
if seconds<60,txt=sprintf('%.0f sec',seconds);else,txt=sprintf('%.1f min',seconds/60);end
end

function s=utc_now()
s=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
end

function write_json(path,value)
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
fid=fopen(path,'w','n','UTF-8');assert(fid>=0,'KAN14TASK:Write','Could not write %s.',path);
c=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');fwrite(fid,newline,'char');
end

function hash=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'KAN14TASK:Hash','Could not read %s.',path);
c=onCleanup(@()fclose(fid));bytes=fread(fid,inf,'*uint8');md=java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(bytes(:),'int8'));digest=typecast(md.digest(),'uint8');hash=lower(reshape(dec2hex(digest,2).',1,[]));
end

function i=column_index(headers,name)
i=find(headers==string(name),1);assert(~isempty(i),'KAN14TASK:Registry','Missing registry column %s.',name);
end

function value=celltext(C,row,headers,name)
i=column_index(headers,name);value=char(string(C{row,i}));
end

function value=cell_value(x)
value=char(string(x));
end

function value=csv_quote(x)
value=strrep(char(x),'"','""');value=['"' value '"'];
end
