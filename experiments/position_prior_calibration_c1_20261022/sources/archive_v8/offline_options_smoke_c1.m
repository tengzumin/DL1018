function offline_options_smoke_c1
% Offline-only: verify pinned sources, C1 options and output-before-update helper behavior.
here=fileparts(mfilename('fullpath')); repoRoot=fileparts(fileparts(here));
lockPath=fullfile(here,'C1_SOURCE_LOCK_v2.json'); releasePath=fullfile(here,'C1_RELEASE_v7.json');
lock=jsondecode(fileread(lockPath)); release=jsondecode(fileread(releasePath));
assert(strcmp(lock.schema,'C1_PRIOR_SCALE_SCREEN_V1') && strcmpi(lock.repo_root,repoRoot));
assert(strcmpi(sha256_file_local(lockPath),release.source_lock_sha256));
assert(strcmpi(sha256_file_local(lock.r2_lock.path),lock.r2_lock.sha256));
assert(strcmpi(sha256_file_local(lock.calibration.result_path),lock.calibration.result_sha256));
assert(strcmpi(sha256_file_local(lock.calibration.fit_script_path),lock.calibration.fit_script_sha256));
assert(strcmpi(sha256_file_local(lock.taskbook.path),lock.taskbook.sha256));
assert(strcmpi(sha256_file_local(lock.resource_timing_clarification.path),lock.resource_timing_clarification.sha256));
r2=jsondecode(fileread(lock.r2_lock.path));
verify_file(r2.model.mat_path,r2.model.mat_sha256,'model MAT');
verify_file(r2.model_binding.path,r2.model_binding.sha256,'model binding');
verify_file(r2.normalizer.npz_path,r2.normalizer.npz_file_sha256,'normalizer NPZ');
verify_file(r2.normalizer.train_only_report_path,r2.normalizer.train_only_report_sha256,'normalizer report');
verify_file(r2.scene_list.path,r2.scene_list.sha256,'scene list');
verify_file(r2.scene_payload_identity.path,r2.scene_payload_identity.sha256,'scene payload identity');
verify_file(r2.reuse_manifest.path,r2.reuse_manifest.sha256,'reuse manifest');
for k=1:numel(r2.runtimeFiles), verify_file(r2.runtimeFiles(k).path,r2.runtimeFiles(k).sha256,'runtime'); end
for k=1:numel(r2.plantFiles), verify_file(r2.plantFiles(k).path,r2.plantFiles(k).sha256,'Plant source'); end
assert(strcmpi(sha256_file_local(fullfile(here,'build_c1_options.m')),release.builder_sha256));
assert(strcmpi(sha256_file_local(fullfile(here,'run_c1_screen.m')),release.runner_sha256));
assert(strcmpi(sha256_file_local(fullfile(here,'preflight_c1.ps1')),release.preflight_sha256));
assert(strcmpi(sha256_file_local(fullfile(here,'offline_options_smoke_c1.m')),release.smoke_sha256));
sceneTable=readtable(r2.scene_list.path,'TextType','string','VariableNamingRule','preserve');
evidence=readtable(r2.scene_payload_identity.path,'TextType','string','VariableNamingRule','preserve');
manifest=readtable(r2.reuse_manifest.path,'TextType','string','VariableNamingRule','preserve');
expected=string({r2.scenes.scene_id}).';
assert(height(sceneTable)==12 && isequal(sceneTable.scene_id(:),expected) && ...
    height(evidence)==12 && isequal(evidence.scene_id(:),expected) && all(evidence.status=="IDENTICAL") && ...
    all(evidence.physical_field_count==14) && all(evidence.time_samples==20001) && ...
    all(evidence.max_abs_physical_scene_diff==0) && height(manifest)==24 && all(manifest.split=="VAL"), ...
    'C1:SceneEvidence','Frozen 12-scene shared physical-payload evidence is incomplete.');
for k=1:numel(expected)
    rows=manifest(manifest.scene_id==expected(k),:);
    assert(height(rows)==2 && sum(rows.role=="B_BASELINE")==1 && sum(rows.role=="ON_CANDIDATE")==1, ...
        'C1:SceneManifest','Expected one frozen B and one ON raw per scene.');
end
restoredefaultpath;
idx=find(endsWith(string({r2.runtimeFiles.path}),string(filesep)+"init_dl1018.m"),1,'first');
assert(~isempty(idx)); addpath(fileparts(r2.runtimeFiles(idx).path),'-begin');
clear init_dl1018; rehash; activeInit=which('init_dl1018');
assert(~isempty(activeInit)&&strcmpi(char(java.io.File(activeInit).getCanonicalPath()), ...
    char(java.io.File(r2.runtimeFiles(idx).path).getCanonicalPath())),'C1:InitPath','Smoke init source is not the locked file.');
[cfg,~,resolvedRoot]=init_dl1018();
assert(strcmpi(char(java.io.File(resolvedRoot).getCanonicalPath()),char(java.io.File(repoRoot).getCanonicalPath())));
addpath(here,'-begin'); addpath(fullfile(repoRoot,'matlab','core'),'-begin');
lockedRuntimeDir=fileparts(r2.runtimeFiles(1).path); addpath(lockedRuntimeDir,'-begin');
clear position_only_search_options position_only_search_head_step position_filter_realization_pcf_step_v3_5
rehash;
for k=1:numel(r2.runtimeFiles)
    path=char(r2.runtimeFiles(k).path); [~,name,ext]=fileparts(path);
    if strcmpi(ext,'.m'), active=which(name); assert(~isempty(active) && ...
            strcmpi(char(java.io.File(active).getCanonicalPath()),char(java.io.File(path).getCanonicalPath()))); end
end
modelPack=load(r2.model.mat_path,'model'); c1=jsondecode(fileread(lock.calibration.result_path));
[optsB,opts1,optsC,audit]=build_c1_options(cfg,modelPack.model,c1.solver.c_star,r2);
phi=sin((1:33)'*0.19); sEff=[0.3;-0.5;0.8]; beta=0.4; eventDt=0.01; dmax=double(cfg.rbf.position.dmax(:));
state=double(optsC.stage1_position_runtime.weight); W0=double(modelPack.model.output_W);
[rawA,appliedA,nextA]=position_only_search_head_step(phi,W0,state,'FEATURE',12,1,sEff,eventDt,beta,dmax);
[rawC,appliedC,nextC]=position_only_search_head_step(phi,W0,state,'FEATURE',12,c1.solver.c_star,sEff,eventDt,beta,dmax);
assert(max(abs(rawA-state.'*phi))<=1e-12 && isequal(rawA,rawC) && isequal(appliedA,appliedC) && ...
    isequal(nextA,nextC) && norm(nextC-state,'fro')>0 && ...
    isequal(double(optsC.stage1_position_runtime.model.output_W),W0), ...
    'C1:OutputBeforeUpdate','FEATURE output must use the pre-update c*W0 state; kappa metadata cannot rescale it.');
report=struct('status','OFFLINE_OPTIONS_SMOKE_PASS','created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'closed_loop_called',false,'run_episode_called',false,'plant_called',false,'raw_scene_loaded',false, ...
    'optimizer_steps',0,'gpu_jobs',0,'test_accessed',false,'dev_labels_used',false, ...
    'frozen_scene_count',height(sceneTable),'shared_payload_pairs_identical',height(evidence), ...
    'physical_fields_per_scene',14,'samples_per_scene',20001,'condition_order',{{'B','ON1','ONC'}}, ...
    'probe_actual_runs',3,'remaining_scene_runs',33,'max_total_runs',36,'output_budget_bytes',6442450944, ...
    'minimum_free_bytes',30000000000,'single_heavy_job_required',true,'c_star',c1.solver.c_star, ...
    'options_audit',audit,'output_before_update_max_abs_error',max(abs(rawA-state.'*phi)), ...
    'feature_kappa_metadata_effect_on_raw',max(abs(rawA-rawC)),'source_lock_sha256',sha256_file_local(lockPath), ...
    'release_sha256',sha256_file_local(releasePath),'builder_sha256',sha256_file_local(fullfile(here,'build_c1_options.m')), ...
    'runner_sha256',sha256_file_local(fullfile(here,'run_c1_screen.m')),'smoke_sha256',sha256_file_local(fullfile(here,'offline_options_smoke_c1.m')), ...
    'runtime_source_count',numel(r2.runtimeFiles),'plant_source_count',numel(r2.plantFiles));
reportPath=fullfile(here,'reports','offline_options_smoke_C1_v7.json');
assert(~isfile(reportPath),'C1:NoOverwrite','Refusing to overwrite an existing smoke result.');
if ~isfolder(fileparts(reportPath)), mkdir(fileparts(reportPath)); end
fid=fopen(reportPath,'w','n','UTF-8'); assert(fid>=0); c=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(report),'char'); clear c;
fprintf('C1_OFFLINE_OPTIONS_SMOKE PASS c*=%.15g scenes=%d payload_pairs=%d Plant=0\n',c1.solver.c_star,height(sceneTable),height(evidence));
end
function verify_file(path,expected,label)
assert(isfile(path),'C1:MissingInput','Missing %s: %s',label,char(path));
assert(strcmpi(sha256_file_local(path),char(expected)),'C1:InputSHA','SHA mismatch for %s: %s',label,char(path));
end
function h=sha256_file_local(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0); c=onCleanup(@()fclose(fid));
while true, block=fread(fid,1024*1024,'*uint8'); if isempty(block), break; end; md.update(typecast(block(:),'int8')); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end



