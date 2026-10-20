function report=run_student_refine_physical(root,phase)
% Resumable six-scene BRIDGE6 or locked four-package 24-scene DEV runner.
root=char(java.io.File(root).getCanonicalPath());phase=upper(char(phase));out=fullfile(root,'experiments','gru14_dssm14_student_refine_v1');
assert(ismember(phase,{'BRIDGE6','DEV24'}),'STUDENT:Phase','Unknown phase %s.',phase);
pre=jsondecode(fileread(fullfile(out,'reports','export_zero_plant_parity.json')));
assert(strcmp(pre.status,'PASS'),'STUDENT:PackageParity','Zero-Plant package parity must pass first.');
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'STUDENT:Root','Unexpected project root.');
search=fullfile(root,'experiments','position_only_closed_loop_search_v1','local_runtime');
teacher=fullfile(root,'experiments','teacher_reuse_model_screen_v1','local_runtime');
addpath(genpath(search),'-begin');addpath(genpath(teacher),'-begin');rehash;
if strcmp(phase,'BRIDGE6')
    packages=readtable(fullfile(out,'manifests','canonical_packages.csv'),'TextType','string');
    protocol=jsondecode(fileread(fullfile(out,'protocol.json')));suffix=string(protocol.canary.scenes(:));
    specs=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
    scenes=specs(ismember(extractAfter(specs.scene_id,'DL1018_TRAIN_'),suffix),:);
    assert(height(scenes)==6&&numel(unique(scenes.scene_id))==6,'STUDENT:BridgeScenes','Expected six frozen bridge scenes.');
    stageDir=fullfile(out,'bridge6');
else
    lock=readtable(fullfile(out,'manifests','locked_candidates.csv'),'TextType','string');
    assert(height(lock)==4&&numel(unique(lock.package_id))==4,'STUDENT:Lock','Four distinct groups must be locked before DEV.');
    frozen=jsondecode(fileread(fullfile(out,'state','LOCKED_CANDIDATES.json')));
    assert(strcmp(frozen.status,'LOCKED_BEFORE_DEV')&&frozen.locked_count==4, ...
        'STUDENT:LockStatus','The four-candidate BRIDGE6 lock is not frozen.');
    packages=lock;
    specs=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');scenes=specs(specs.split=="DEV",:);
    assert(height(scenes)==24&&numel(unique(scenes.scene_id))==24,'STUDENT:DevScenes','Expected fixed 24-scene DEV.');
    stageDir=fullfile(out,'dev24');
end
if ~isfolder(stageDir),mkdir(stageDir);end
taskStart=tic;newRows=struct([]);plantBefore=count_plants(out);
for pi=1:height(packages)
    pkgId=char(packages.package_id(pi));pkgRel=char(packages.package_path(pi));
    pkgFolder=fullfile(root,strrep(pkgRel,'/',filesep));matPath=fullfile(pkgFolder,'matlab_model_and_parity.mat');
    saved=load(matPath,'model');model=saved.model;model.model_id=char(packages.model_id(pi));
    modelFolder=fullfile(stageDir,safe_id(pkgId));if ~isfolder(modelFolder),mkdir(modelFolder);end
    modelRows=struct([]);
    for si=1:height(scenes)
        spec=scenes(si,:);sceneId=char(spec.scene_id);sceneFolder=fullfile(modelFolder,sceneId);
        if ~isfolder(sceneFolder),mkdir(sceneFolder);end
        raw=fullfile(sceneFolder,'raw_run.mat');start=fullfile(sceneFolder,'run_start.mat');marker=fullfile(sceneFolder,'plant_started.marker');mp=fullfile(sceneFolder,'metrics.json');
        if isfile(mp)
            savedMetric=jsondecode(fileread(mp));row=savedMetric.metrics_row;
            assert(isfile(raw),'STUDENT:MissingRaw','Metrics exist without raw Plant evidence: %s.',sceneId);
        else
            b=baseline_for(root,sceneId,char(spec.split));
            if isfile(marker)&&~isfile(raw),error('STUDENT:InterruptedPlant','Plant started without raw log: %s.',raw);end
            if isfile(raw)
                z=load(raw,'log');log=z.log;assert(isfile(start),'STUDENT:MissingStart','Raw run lacks run_start.');
                zz=load(start,'runStart');runStart=zz.runStart;
            else
                generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
                addpath(genpath(search),'-begin');addpath(genpath(teacher),'-begin');rehash;
                opts=position_only_search_options(cfg,model,'FEATURE',12,1);
                assert(opts.stage1_position_runtime.update_enabled&& ...
                    ~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
                    opts.rbf_attitude_enabled&&opts.rbf_attitude_update_enabled, ...
                    'STUDENT:Controller','Position-only/B-attitude isolation failed.');
                opts.r2e_first_plant_step_marker=marker;
                runStart=struct('run_id',sprintf('%s_%s',pkgId,sceneId),'phase',phase,'package_id',pkgId, ...
                    'model_id',model.model_id,'training_group',char(packages.group(pi)),'scene_id',sceneId, ...
                    'scene_spec',spec,'cfg',cfg,'opts',opts,'package_path',pkgRel, ...
                    'package_sha256',char(packages.mat_sha256(pi)),'started_at_utc',utc_now());
                save(start,'runStart','-v7');
                statePath=fullfile(out,'state','state.json');st=load_state(statePath);st.phase=phase;st.status='IN_PROGRESS';
                st.active_package=pkgId;st.active_scene=sceneId;st.cumulative_plant_starts=count_plants(out);st.updated_at_utc=utc_now();write_json(statePath,st);
                try
                    episode=@run_episode_dl1018;log=episode(scene,'P_A',cfg,opts,raw);
                catch err
                    write_json(fullfile(sceneFolder,'error.json'),struct('identifier',err.identifier,'message',err.message,'scene_id',sceneId,'plant_started',isfile(marker)));
                    if isfile(marker),append_ledger(out,runStart.run_id,'ENGINEERING_OR_PHYSICAL_ERROR',err.identifier);end
                    rethrow(err)
                end
            end
            assert(isfile(marker),'STUDENT:PlantMarker','Plant marker missing for %s.',sceneId);
            t=double(log.transition_time(:));mask=t>=0&t<20;state=double(log.state(1:numel(t),:));ref=double(log.reference.position(1:numel(t),:));
            ep=ref(mask,:)-state(mask,1:3);axis=sqrt(mean(ep.^2,1));q=sqrt(mean(sum(ep.^2,2)));
            aref=double(log.filtered_attitude_reference(1:numel(t),:));ae=atan2(sin(aref(mask,:)-state(mask,7:9)),cos(aref(mask,:)-state(mask,7:9)));
            attAxis=sqrt(mean(ae.^2,1));att=sqrt(mean(sum(ae.^2,2)));n=numel(t);status=char(log.status);
            row=struct('run_id',runStart.run_id,'phase',phase,'package_id',pkgId,'model_id',model.model_id, ...
                'group',char(packages.group(pi)),'seed',double(packages.seed(pi)),'checkpoint_kind',char(packages.checkpoint_kind(pi)), ...
                'scene_id',sceneId,'task',char(spec.task),'status',status,'complete',n==20000,'finite',all(isfinite([q,axis,att,attAxis])), ...
                'transitions',n,'Q_0_20_m',q,'position_axis_rmse_m',jsonencode(axis), ...
                'attitude_Q_0_20_rad',att,'attitude_axis_rmse_rad',jsonencode(attAxis), ...
                'B_run_id',b.run_id,'B_raw_path',b.raw_path,'B_Q_0_20_m',b.Q_0_20_m,'delta_Q_vs_B_m',q-b.Q_0_20_m, ...
                'safety_stop_reason',field_text(log,'safety_stop_reason',''),'plant_started',true, ...
                'raw_path',relpath(root,raw),'run_start_path',relpath(root,start),'source','NEW_PLANT','finished_at_utc',utc_now());
            write_json(mp,struct('metrics_row',row,'source_reused',false));append_ledger(out,runStart.run_id,status,sprintf('%s %s %s',phase,pkgId,sceneId));
        end
        modelRows=append_rows(modelRows,row);newRows=append_rows(newRows,row);
        fprintf('STUDENT_%s_RUN package=%s scene=%s status=%s Q=%.9g same_scene_B=%.9g attitude=%.9g starts=%d/%d elapsed_min=%.1f\n', ...
            phase,pkgId,sceneId,row.status,row.Q_0_20_m,row.B_Q_0_20_m,row.attitude_Q_0_20_rad,count_plants(out), ...
            432,(toc(taskStart)/60));
        if strcmp(phase,'DEV24')&&mod(si,6)==0,emit_chunk(pkgId,modelRows(end-5:end),count_plants(out),toc(taskStart));end
    end
    if strcmp(phase,'BRIDGE6'),emit_chunk(pkgId,modelRows,count_plants(out),toc(taskStart));end
    persist_all(stageDir);
end
report=struct('status','COMPLETE','phase',phase,'packages',height(packages),'scenes_per_package',height(scenes), ...
    'rows',height_or_num(newRows),'new_plant_starts',count_plants(out)-plantBefore,'plant_starts_total',count_plants(out), ...
    'plant_budget_max',432,'completed_at_utc',utc_now());
write_json(fullfile(out,'reports',[lower(phase) '_state.json']),report);
fprintf('STUDENT_%s_COMPLETE rows=%d packages=%d PlantStarts=%d/432\n',phase,report.rows,height(packages),count_plants(out));
end
function b=baseline_for(root,sceneId,split)
persistent baselineCache
if isempty(baselineCache),baselineCache=containers.Map('KeyType','char','ValueType','any');end
key=[root '|' sceneId];if isKey(baselineCache,key),b=baselineCache(key);return;end
if strcmpi(split,'DEV')
    tab=readtable(fullfile(root,'reports','POSITION_DEV.csv'),'TextType','string');z=tab(tab.scene_id==string(sceneId)&tab.method=="B",:);
else
    tab=readtable(fullfile(root,'experiments','teacher_reuse_model_screen_v1','manifests','teacher_reuse_manifest.csv'),'TextType','string');z=tab(tab.scene_id==string(sceneId)&tab.role=="B",:);
end
assert(height(z)==1,'STUDENT:Baseline','Need exactly one same-scene B for %s; found %d.',sceneId,height(z));
raw=fullfile(root,strrep(char(z.raw_path(1)),'/',filesep));assert(isfile(raw),'STUDENT:BaselineRaw','Missing same-scene B raw: %s.',raw);
q=load(raw,'log');log=q.log;t=double(log.transition_time(:));mask=t>=0&t<20;state=double(log.state(1:numel(t),1:3));ref=double(log.reference.position(1:numel(t),:));e=ref(mask,:)-state(mask,:);bq=sqrt(mean(sum(e.^2,2)));
if ismember('Q_0_20_m',z.Properties.VariableNames),reported=double(z.Q_0_20_m(1));elseif ismember('position_Q_0_20_m',z.Properties.VariableNames),reported=double(z.position_Q_0_20_m(1));else,reported=bq;end
assert(abs(reported-bq)<=1e-8,'STUDENT:BaselineMismatch','Raw baseline disagrees with its accepted report for %s.',sceneId);
b=struct('run_id',char(z.run_id(1)),'raw_path',char(z.raw_path(1)),'Q_0_20_m',bq);
baselineCache(key)=b;
end
function emit_chunk(id,rows,starts,elapsed)
stable=nnz([rows.complete]&[rows.finite]&strcmp({rows.status},'STABLE'));q=mean([rows.Q_0_20_m]);b=mean([rows.B_Q_0_20_m]);
fprintf('STUDENT_CHUNK package=%s rows=%d stable=%d Q_macro=%.9g same_scene_B=%.9g delta=%.9g cumulative_Plant=%d elapsed_min=%.1f\n', ...
    id,numel(rows),stable,q,b,q-b,starts,elapsed/60);
for k=1:numel(rows),fprintf('  %s Q=%.9g B=%.9g attitude=%.9g status=%s\n',rows(k).scene_id,rows(k).Q_0_20_m,rows(k).B_Q_0_20_m,rows(k).attitude_Q_0_20_rad,rows(k).status);end
end
function persist_all(stageDir)
d=dir(fullfile(stageDir,'**','metrics.json'));rows=struct([]);
for i=1:numel(d),q=jsondecode(fileread(fullfile(d(i).folder,d(i).name)));if isfield(q,'metrics_row'),rows=append_rows(rows,q.metrics_row);end,end
if ~isempty(rows),writetable(struct2table(rows,'AsArray',true),fullfile(stageDir,'all_runs.csv'));end
end
function a=append_rows(a,b),if isempty(a),a=b(:);else,a=[a(:);b(:)];end,end
function n=height_or_num(x),n=numel(x);end
function n=count_plants(out),d=dir(fullfile(out,'**','plant_started.marker'));n=numel(d);end
function s=load_state(p),if isfile(p),s=jsondecode(fileread(p));else,s=struct;end,end
function append_ledger(out,id,status,note)
p=fullfile(out,'RESOURCE_LEDGER.csv');f=fopen(p,'a');assert(f>0);fprintf(f,'%s,Plant,%s,1,%s,%s\n',utc_now(),id,status,strrep(char(note),',',';'));fclose(f);
end
function write_json(p,s),fid=fopen(p,'w');assert(fid>0);c=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');end
function s=utc_now(),s=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));end
function p=relpath(root,path),p=strrep(char(java.io.File(path).getCanonicalPath()),[root filesep],'');p=strrep(p,filesep,'/');end
function id=safe_id(id),id=regexprep(char(id),'[^A-Za-z0-9_.-]','_');end
function v=field_text(s,n,d),if isfield(s,n),v=char(string(s.(n)));else,v=d;end,end
