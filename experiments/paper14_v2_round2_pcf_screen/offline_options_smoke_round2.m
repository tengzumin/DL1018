function offline_options_smoke_round2
% Offline-only: initialize project, verify active locked helper paths, build options.
% This function must never call a runner, episode, Plant, or create runs/attempt data.
here=fileparts(mfilename('fullpath')); repoRoot=fileparts(fileparts(here));
lockPath=fullfile(here,'frozen_inputs.json'); lock=jsondecode(fileread(lockPath));
assert(strcmp(lock.schema,'ROUND2_PCF_SCREEN_INPUTS_V1'));
assert(strcmpi(sha256_file_local(lock.taskbook.path),lock.taskbook.sha256));
for k=1:numel(lock.setupFiles), assert(strcmpi(sha256_file_local(lock.setupFiles(k).path),lock.setupFiles(k).sha256)); end
for k=1:numel(lock.runtimeFiles), assert(strcmpi(sha256_file_local(lock.runtimeFiles(k).path),lock.runtimeFiles(k).sha256)); end
assert(strcmpi(sha256_file_local(lock.model.mat_path),lock.model.mat_sha256));
assert(strcmpi(sha256_file_local(lock.model_binding.path),lock.model_binding.sha256));
assert(strcmpi(sha256_file_local(lock.normalizer.npz_path),lock.normalizer.npz_file_sha256));
restoredefaultpath;
idx=find(endsWith(string({lock.runtimeFiles.path}),string(filesep)+"init_dl1018.m"),1,'first');
assert(~isempty(idx)); initDir=fileparts(lock.runtimeFiles(idx).path); addpath(initDir,'-begin');
[cfg,~,resolvedRoot]=init_dl1018();
assert(strcmpi(char(java.io.File(resolvedRoot).getCanonicalPath()),char(java.io.File(repoRoot).getCanonicalPath())));
coreDir=fullfile(repoRoot,'matlab','core'); lockedDir=fileparts(lock.runtimeFiles(1).path);
addpath(here,'-begin'); addpath(coreDir,'-begin'); addpath(lockedDir,'-begin');
clear position_only_search_options position_only_search_head_step position_filter_realization_pcf_step_v3_5
rehash;
for k=1:numel(lock.runtimeFiles)
    path=char(lock.runtimeFiles(k).path); [~,name,ext]=fileparts(path);
    if strcmpi(ext,'.m'), active=which(name); assert(~isempty(active)&&strcmpi(char(java.io.File(active).getCanonicalPath()),char(java.io.File(path).getCanonicalPath()))); end
end
modelPack=load(lock.model.mat_path,'model'); [opts,audit]=build_round2_pcf_off_options(cfg,modelPack.model);
assert(logical(opts.stage1_position_runtime.update_enabled));
assert(logical(opts.stage1_position_runtime.position_only_search_head.enabled));
assert(~logical(opts.stage1_position_runtime.command_filter_coordination_v3_5.enabled));
fusionEnabled=isfield(opts,'attitude_fusion_v3_6')&&isstruct(opts.attitude_fusion_v3_6)&&logical(opts.attitude_fusion_v3_6.enabled); assert(~fusionEnabled);
fusionEnabled=isfield(opts,'attitude_fusion_v3_6')&&isstruct(opts.attitude_fusion_v3_6)&&logical(opts.attitude_fusion_v3_6.enabled); assert(~fusionEnabled);
headIdx=find(endsWith(string({lock.runtimeFiles.path}),string(filesep)+"position_only_search_head_step.m"),1,'first');
assert(~isempty(headIdx));
assert(strcmpi(which('position_only_search_head_step'),char(lock.runtimeFiles(headIdx).path)));
builderIdx=find(strcmp(string({lock.setupFiles.name}),"build_round2_pcf_off_options.m"),1,'first');
assert(~isempty(builderIdx));
assert(strcmpi(which('build_round2_pcf_off_options'),char(lock.setupFiles(builderIdx).path)));
assert(strcmpi(sha256_file_local(lock.setupFiles(builderIdx).path),lock.setupFiles(builderIdx).sha256));
report=struct('status','OFFLINE_OPTIONS_SMOKE_PASS','closed_loop_called',false,'run_episode_called',false,'plant_called',false, ...
    'scene_or_raw_read',false,'optimizer_steps',0,'pcf_enabled',false,'update_enabled',true, ...
    'head_type',audit.head_type,'single_difference',audit.experimental_difference,'attitude_fusion_enabled',fusionEnabled, ...
    'normalizer_identity_sha256',audit.normalizer_identity_sha256,'W0_output_W_sha256',audit.W0_output_W_sha256, ...
    'position_only_search_head_step_path',which('position_only_search_head_step'), ...
    'position_only_search_head_step_sha256',lock.runtimeFiles(headIdx).sha256, ...
    'options_builder_path',which('build_round2_pcf_off_options'), ...
    'options_builder_sha256',lock.setupFiles(builderIdx).sha256, ...
    'attitude_fusion_contract_blocked_by_enabled_flag',false, ...
    'frozen_inputs_path',char(java.io.File(lockPath).getCanonicalPath()), ...
    'frozen_inputs_sha256',sha256_file_local(lockPath),'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')));
reportPath=fullfile(here,'reports','offline_options_smoke_20261022_v8.json'); assert(~isfile(reportPath),'Refusing to overwrite an existing offline smoke report.'); fid=fopen(reportPath,'w','n','UTF-8'); assert(fid>=0); c=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(report),'char'); clear c;
fprintf('OFFLINE_OPTIONS_SMOKE PASS PCF=false update=true helper=%s\n',which('position_only_search_head_step'));
end
function h=sha256_file_local(path)
md=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'r');assert(fid>=0);c=onCleanup(@()fclose(fid));
while true,b=fread(fid,1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end



