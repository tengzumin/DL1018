function audit=verify_single_call_prepare_v2()
% Verify only the first real one-scene release path; this never calls Plant.
studyRoot=fileparts(fileparts(mfilename('fullpath')));
releasePath=fullfile(studyRoot,'RELEASE.json');lockPath=fullfile(studyRoot,'SOURCE_LOCK_TRAIN24_v2.json');
baseReleaseBytes=read_bytes(releasePath);baseRelease=jsondecode(fileread(releasePath));
lockSha=sha256_file(lockPath);baseReleaseSha=sha256_file(releasePath);
assert(strcmpi(lockSha,char(baseRelease.source_lock_sha256))&& ...
    strcmp(baseRelease.schema,'DL1018_CAUSAL_N4_GATE_TRAIN24_NOPLANT_V2')&& ...
    baseRelease.authorized_Plant_calls==0&&baseRelease.Plant_calls==0, ...
    'N4BatchCheck:BaseRelease','Expected the frozen zero-Plant release template.');
protocol=jsondecode(fileread(fullfile(studyRoot,'BATCH_EXECUTION_PROTOCOL_v2.json')));
sceneId=char(protocol.new_attempt_scene_ids{1});
single=baseRelease;single.schema='DL1018_CAUSAL_N4_GATE_TRAIN24_SINGLE_CALL_V2';
single.status='RELEASED';single.fixed_scene_id=sceneId;single.authorized_scenes={sceneId};
single.authorized_Plant_calls=1;single.Plant_calls=1;single.potential_budget_calls=1;
write_json_replace(releasePath,single);
try
    runtime=fullfile(studyRoot,'candidate_runner_work','matlab','runtime');
    addpath(runtime);activate_paired_runner();addpath(runtime);
    prepared=prepare_causal_n4_train24_scene_no_plant(sceneId);
    assert(strcmp(prepared.scene_id,sceneId)&&~prepared.opts.no_plant_boundary_check&& ...
        ~isfield(prepared.opts.stage1_position_runtime,'residual_gru'), ...
        'N4BatchCheck:PreparedIdentity','Single-call prepare returned an invalid execution identity.');
    audit=struct('status','PASS_SINGLE_CALL_PREPARE_ONLY_NO_PLANT','scene_id',sceneId, ...
        'source_lock_sha256',lockSha,'binding_sha256',prepared.binding_sha256, ...
        'execution_identity',prepared.execution_identity,'Plant_calls',0, ...
        'authorized_budget_written_for_prepare_only',false,'runner_invoked',false, ...
        'attempt_markers_created',0,'first_plant_markers_created',0, ...
        'TEST_read',false,'VAL_read',false,'inertia_reconstruction_enabled',false);
catch ME
    write_bytes_replace(releasePath,baseReleaseBytes);rethrow(ME);
end
write_bytes_replace(releasePath,baseReleaseBytes);
assert(strcmpi(sha256_file(releasePath),baseReleaseSha)&& ...
    ~isfile(fullfile(studyRoot,'BUDGET_JOURNAL_v2.jsonl'))&& ...
    ~isfile(fullfile(studyRoot,'BATCH_PROGRESS_v2.json'))&& ...
    ~isfolder(fullfile(studyRoot,'runs'))&&~isfolder(fullfile(studyRoot,'audits'))&& ...
    ~isfolder(fullfile(studyRoot,'scores')), ...
    'N4BatchCheck:NoPlantMutation','Prepare-only check wrote run/budget/marker artifacts.');
out=fullfile(studyRoot,'PRECALL_SOURCE_SNAPSHOTS','PREPARE_ONLY_SINGLE_RELEASE_v2.json');
fid=fopen(out,'w');assert(fid>=0,'N4BatchCheck:Write','Cannot write %s.',out);
c=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(audit,'PrettyPrint',true) newline],'char');clear c;
disp(['SINGLE_CALL_PREPARE_ONLY=' out]);
end
function write_json_replace(path,x)
tmp=[path '.tmp'];if isfile(tmp),delete(tmp);end
fid=fopen(tmp,'w');assert(fid>=0,'N4BatchCheck:Write','Cannot write %s.',tmp);
c=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(x,'PrettyPrint',true) newline],'char');clear c;
[ok,msg]=movefile(tmp,path,'f');assert(ok,'N4BatchCheck:Move','Cannot replace %s: %s',path,msg);
end
function write_bytes_replace(path,bytes)
tmp=[path '.tmp'];if isfile(tmp),delete(tmp);end
fid=fopen(tmp,'wb');assert(fid>=0,'N4BatchCheck:Write','Cannot write %s.',tmp);
c=onCleanup(@()fclose(fid));fwrite(fid,bytes,'uint8');clear c;
[ok,msg]=movefile(tmp,path,'f');assert(ok,'N4BatchCheck:Move','Cannot restore %s: %s',path,msg);
end
function bytes=read_bytes(path)
fid=fopen(path,'rb');assert(fid>=0,'N4BatchCheck:Read','Cannot open %s.',path);
c=onCleanup(@()fclose(fid));bytes=fread(fid,Inf,'*uint8');clear c;
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'N4BatchCheck:Read','Cannot open %s.',path);
c=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear c;
end
