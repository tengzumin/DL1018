function audit=run_reuse_identity_dryrun_v2()
% Recompute only the three already-completed scenes' execution identity; no runner/Plant call.
studyRoot=fileparts(mfilename('fullpath'));
input=jsondecode(fileread(fullfile(studyRoot,'BATCH_INPUT_v2.json')));
release=jsondecode(fileread(fullfile(studyRoot,'RELEASE.json')));
lockPath=fullfile(studyRoot,'SOURCE_LOCK_TRAIN24_v2.json');
assert(strcmpi(sha256_file(lockPath),char(release.source_lock_sha256)), ...
    'N4Train24:Lock','Source lock changed.');
lock=jsondecode(fileread(lockPath));
helper=fullfile(studyRoot,'candidate_runner_work','matlab','runtime', ...
    'prepare_causal_n4_train24_scene_no_plant.m');
currentScript=[mfilename('fullpath') '.m'];
assert(locked_hash(lock,helper)&&locked_hash(lock,currentScript), ...
    'N4Train24:SourceHash','Updated preparer or reuse-identity harness is not locked.');
protocol=jsondecode(fileread(fullfile(studyRoot,'..','n4cg_v2','CALL_PROTOCOL_v2.json')));
ids=cellstr(string(protocol.call_order));
assert(numel(ids)==3,'N4Train24:ReuseScope','Expected only the three already-completed gate scenes.');
addpath(fullfile(studyRoot,char(input.n4_gate_v2.shared_runtime_relative),'matlab','runtime'));
entries=cell(numel(ids),1);
for i=1:numel(ids)
    prepared=prepare_causal_n4_train24_scene_no_plant(ids{i});
    entries{i}=struct('scene_id',prepared.scene_id,'binding_sha256',prepared.binding_sha256, ...
        'identity',prepared.identity,'execution_identity',prepared.execution_identity, ...
        'identity_mode_audit',prepared.identity_mode_audit,'scene_audit',prepared.scene_audit, ...
        'payload_sha256',prepared.payload_sha256,'parent_raw_sha256',prepared.parent_raw_sha256, ...
        'c5_raw_sha256',prepared.c5_raw_sha256,'b_raw_sha256',prepared.b_raw_sha256);
end
assert(~isfolder(fullfile(studyRoot,'runs'))&&~isfolder(fullfile(studyRoot,'audits')), ...
    'N4Train24:DryRunMutation','Reuse-identity check must not create run or marker directories.');
out=fullfile(studyRoot,'REUSE_IDENTITIES_v2.json');
assert(~isfile(out),'N4Train24:NoOverwrite','Refusing to overwrite reuse-identity output.');
audit=struct('status','PASS_THREE_SCENE_EXECUTION_IDENTITY_DRY_RUN','scene_count',numel(ids), ...
    'ordered_scene_ids',{ids},'source_lock_sha256',sha256_file(lockPath),'Plant_calls',0, ...
    'authorized_Plant_calls',0,'potential_budget_calls',0,'runner_invoked',false, ...
    'attempt_markers_created',0,'first_plant_markers_created',0,'entries',{entries});
fid=fopen(out,'w');assert(fid>=0,'N4Train24:Write','Cannot write %s.',out);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(audit) newline],'char');clear cleanup;
disp(['THREE_SCENE_EXECUTION_IDENTITY=' out]);
end
function tf=locked_hash(lock,path)
p=char(path);h=sha256_file(p);tf=false;
for i=1:numel(lock.files)
    if strcmpi(char(lock.files(i).path),p),tf=strcmpi(h,char(lock.files(i).sha256));return;end
end
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'N4Train24:Read','Cannot open %s.',path);
cleanup=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cleanup;
end
