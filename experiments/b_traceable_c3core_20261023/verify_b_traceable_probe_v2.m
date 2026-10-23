function result=verify_b_traceable_probe_v2()
% Read-only verification of the completed no-Plant B setup; never calls an episode.
here=fileparts(mfilename('fullpath')); repoRoot=fileparts(fileparts(here));
lockPath=fullfile(here,'B_TRACEABLE_INPUT_LOCK_v2.json'); contractPath=fullfile(here,'B_TRACEABLE_RUN_CONTRACT_v2.json');
preparePath=fullfile(here,'B_TRACEABLE_PREPARE_RESULT_v2.json'); snapshotPath=fullfile(here,'B_TRACEABLE_PREPARED_CFG_OPTS_v2.mat');
outPath=fullfile(here,'B_TRACEABLE_VERIFY_RESULT_v2.json');
assert(~isfile(outPath)&&isfile(lockPath)&&isfile(contractPath)&&isfile(preparePath)&&isfile(snapshotPath), ...
    'BTRACE:VerifyFiles','Required frozen setup outputs missing or verify result already exists.');
lock=jsondecode(fileread(lockPath)); contract=jsondecode(fileread(contractPath)); prep=jsondecode(fileread(preparePath));
verify_file(lockPath,prep.input_lock_sha256); verify_file(contractPath,prep.contract_sha256);
verify_file(snapshotPath,prep.snapshot_sha256); verify_file(lock.source_files.runner.path,prep.runner_sha256);
verify_file(contractPath,lock.source_files.contract.sha256); verify_file(lock.source_files.prepare_entry.path,lock.source_files.prepare_entry.sha256);
verify_file(lock.source_files.input_lock_builder.path,lock.source_files.input_lock_builder.sha256);
for k=1:numel(lock.active_source_inventory), verify_file(lock.active_source_inventory(k).path,lock.active_source_inventory(k).sha256); end
upstreamNames=fieldnames(lock.upstream_refs);
for k=1:numel(upstreamNames), item=lock.upstream_refs.(upstreamNames{k}); verify_file(item.path,item.sha256); end
assert(strcmp(prep.status,'PREPARED_NO_PLANT_WAIT_PARENT_RELEASE')&&prep.plant_calls==0&& ...
    ~prep.run_episode_called&&prep.training_steps==0&&prep.optimizer_steps==0&&~prep.TEST_accessed&& ...
    strcmp(prep.scene_id,contract.scene_id)&&strcmp(prep.scene_id,lock.scene_id)&&prep.which_checks==31&&prep.active_sources==32, ...
    'BTRACE:PrepareResult','Prepared result does not certify the fixed no-Plant scope.');
assert(~isfolder(fullfile(here,'runs_b'))&&~isfile(fullfile(here,'B_TRACEABLE_RELEASE_v2.json')), ...
    'BTRACE:UnexpectedRun','A B attempt root or release unexpectedly exists.');
pack=load(snapshotPath,'cfg','opts','sceneIdentity','sourceIdentity');
assert(isfield(pack,'cfg')&&isfield(pack,'opts')&&isfield(pack,'sceneIdentity')&&isfield(pack,'sourceIdentity'), ...
    'BTRACE:Snapshot','Prepared snapshot fields are incomplete.');
assert(strcmpi(pack.sourceIdentity.input_lock_sha256,sha256_file(lockPath))&& ...
    strcmpi(pack.sourceIdentity.runner_sha256,prep.runner_sha256)&& ...
    strcmpi(pack.sceneIdentity.B_raw_sha256,lock.scene_raw_sha256)&& ...
    strcmpi(pack.sceneIdentity.external_identity_sha256,lock.scene_external_identity_sha256), ...
    'BTRACE:SnapshotIdentity','Snapshot source or scene identity differs from the frozen input lock.');
verify_file(lock.scene_raw_path,lock.scene_raw_sha256);
active=lock.active_source_inventory; initPath=source_path(active,'init_dl1018.m');
optionsPath=source_path(active,'controller_options_dl1018.m'); corePath=source_path(active,'run_dl1018_closed_loop.m');
forwardPath=source_path(active,'position_stage1_model_forward_v2.m'); headPath=source_path(active,'position_only_search_head_step.m');
archiveDirs=unique({fileparts(forwardPath),fileparts(headPath),fileparts(source_path(active,'position_only_search_options.m'))},'stable');
add_active_paths(active); addpath(fullfile(repoRoot,'matlab','runtime'),'-end'); addpath(fullfile(repoRoot,'matlab','core'),'-end');
addpath(fileparts(initPath),'-begin'); addpath(fileparts(optionsPath),'-begin');
for di=1:numel(archiveDirs), addpath(archiveDirs{di},'-begin'); end
addpath(fileparts(corePath),'-begin'); addpath(here,'-begin');
clear init_dl1018 controller_options_dl1018 run_episode_dl1018 run_dl1018_closed_loop; rehash;
assert(same_path(which('init_dl1018'),initPath)&&same_path(which('controller_options_dl1018'),optionsPath), ...
    'BTRACE:InitPath','Frozen init/options source resolves to a shadow.');
[cfg,optsInit,resolvedRoot]=init_dl1018();
assert(same_path(resolvedRoot,repoRoot)&&isequaln(cfg,pack.cfg), ...
    'BTRACE:CfgMismatch','Fresh config differs from the saved prepared config.');
add_active_paths(active); addpath(fullfile(repoRoot,'matlab','runtime'),'-end'); addpath(fullfile(repoRoot,'matlab','core'),'-end');
addpath(fileparts(initPath),'-begin'); addpath(fileparts(optionsPath),'-begin');
for di=1:numel(archiveDirs), addpath(archiveDirs{di},'-begin'); end
addpath(fileparts(corePath),'-begin'); addpath(here,'-begin');
clear controller_options_dl1018 run_episode_dl1018 run_dl1018_closed_loop; rehash;
whichCount=0;
for k=1:numel(active)
    item=active(k); [~,name,ext]=fileparts(item.path);
    if strcmpi(ext,'.m'), assert(same_path(which(name),item.path),'BTRACE:WhichShadow','Active source %s resolves to a shadow.',name); whichCount=whichCount+1; end
end
assert(whichCount==31&&same_path(which('init_dl1018'),initPath)&& ...
    same_path(which('controller_options_dl1018'),optionsPath)&& ...
    same_path(which('run_episode_dl1018'),source_path(active,'run_episode_dl1018.m'))&& ...
    same_path(which('run_dl1018_closed_loop'),corePath), ...
    'BTRACE:RuntimePath','Fresh runtime/wrapper/core path differs from the lock.');
opts=controller_options_dl1018(cfg,'B');
assert(isequaln(opts,optsInit)&&isequaln(opts,pack.opts)&&logical(opts.rbf_position_output_enabled)&& ...
    logical(opts.rbf_position_update_enabled)&&logical(opts.rbf_attitude_enabled)&& ...
    logical(opts.rbf_attitude_output_enabled)&&logical(opts.rbf_attitude_update_enabled)&& ...
    double(opts.position_rbf_frequency_hz)==100&&double(opts.attitude_rbf_frequency_hz)==100&&~logical(opts.v1_adaptive), ...
    'BTRACE:BOpts','Fresh baseline B opts differ from both init and the saved snapshot.');
result=struct('schema','B_TRACEABLE_READONLY_VERIFY_V2','status','PASS_NO_PLANT', ...
    'verified_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'prepare_result_sha256',sha256_file(preparePath),'snapshot_sha256',sha256_file(snapshotPath), ...
    'input_lock_sha256',sha256_file(lockPath),'contract_sha256',sha256_file(contractPath), ...
    'B_raw_sha256',sha256_file(lock.scene_raw_path),'cfg_matches_snapshot',true,'fresh_B_opts_match_init_and_snapshot',true, ...
    'which_checks',whichCount,'active_source_count',numel(active),'plant_calls',0,'episode_called',false);
write_json_new(outPath,result);
fprintf('B_TRACEABLE_VERIFY=PASS_NO_PLANT WHICH=%d\n',whichCount);
end
function add_active_paths(items)
for k=1:numel(items), [~,~,ext]=fileparts(items(k).path); if strcmpi(ext,'.m'), addpath(fileparts(items(k).path),'-end'); end, end
end
function path=source_path(items,name)
names=cell(1,numel(items)); for k=1:numel(items), [~,n,e]=fileparts(items(k).path); names{k}=[n e]; end
idx=find(strcmpi(names,name)); assert(numel(idx)==1,'BTRACE:SourceName','Expected exactly one source %s.',name); path=items(idx).path;
end
function verify_file(path,expected)
assert(isfile(path),'BTRACE:MissingFile','Missing frozen file: %s.',path);
assert(strcmpi(sha256_file(path),expected),'BTRACE:SHA','SHA-256 mismatch: %s.',path);
end
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0,'BTRACE:ReadFile','Cannot read %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end; md.update(typecast(b,'int8')); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function tf=same_path(a,b), tf=strcmpi(char(java.io.File(a).getCanonicalPath()),char(java.io.File(b).getCanonicalPath())); end
function write_json_new(path,value)
assert(~isfile(path),'BTRACE:NoOverwrite','Refusing to overwrite %s.',path); fid=fopen(path,'w'); assert(fid>=0,'BTRACE:Write','Cannot write %s.',path); c=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(value),'char');
end