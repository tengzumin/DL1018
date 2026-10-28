function audit=run_train24_prepare_dryrun_v2()
% Resolve each locked TRAIN scene in memory; never call the runner or Plant.
entry=fileparts(mfilename('fullpath'));studyRoot=entry;
input=jsondecode(fileread(fullfile(studyRoot,'BATCH_INPUT_v2.json')));
release=jsondecode(fileread(fullfile(studyRoot,'RELEASE.json')));
lockPath=fullfile(studyRoot,'SOURCE_LOCK_TRAIN24_v2.json');
assert(strcmpi(sha256_file(lockPath),char(release.source_lock_sha256)), ...
    'N4Train24:Lock','Source lock changed.');
lock=jsondecode(fileread(lockPath));checked=0;
for i=1:numel(lock.files)
    p=char(lock.files(i).path);
    assert(isfile(p)&&strcmpi(sha256_file(p),char(lock.files(i).sha256)), ...
        'N4Train24:SourceHash','Locked source changed: %s.',p);
    checked=checked+1;
end
runtime=fullfile(studyRoot,char(input.n4_gate_v2.shared_runtime_relative),'matlab','runtime');
addpath(runtime);addpath(fullfile(studyRoot,'candidate_runner_work','matlab','runtime'));
ids=cellstr(string(release.authorized_scenes));entries=cell(numel(ids),1);
for i=1:numel(ids)
    prepared=prepare_causal_n4_train24_scene_no_plant(ids{i});
    entries{i}=struct('scene_id',prepared.scene_id,'binding_path',prepared.binding_path, ...
        'binding_sha256',prepared.binding_sha256,'scene_audit',prepared.scene_audit, ...
        'identity',prepared.identity,'payload_sha256',prepared.payload_sha256, ...
        'parent_raw_sha256',prepared.parent_raw_sha256,'c5_raw_sha256',prepared.c5_raw_sha256, ...
        'b_raw_sha256',prepared.b_raw_sha256,'attempt',prepared.candidate_attempt, ...
        'marker_path',prepared.marker_path);
end
runs=fullfile(studyRoot,'runs');audits=fullfile(studyRoot,'audits');
assert(~isfolder(runs)&&~isfolder(audits), ...
    'N4Train24:DryRunMutation','Dry-run must not create runs or audit marker directories.');
out=fullfile(studyRoot,'DRY_RUN_PREPARED_v2.json');
assert(~isfile(out),'N4Train24:NoOverwrite','Refusing to overwrite dry-run output.');
audit=struct('status','PASS_TRAIN24_DYNAMIC_PREPARE_DRY_RUN','study_id',release.study_id, ...
    'scene_count',numel(ids),'ordered_scene_ids',{ids},'source_lock_sha256',sha256_file(lockPath), ...
    'source_hashes_checked',checked,'Plant_calls',0,'authorized_Plant_calls',0, ...
    'potential_budget_calls',0,'TEST_read',false,'VAL_read',false, ...
    'inertia_reconstruction_enabled',false,'extra_position_residual_gru_enabled',false, ...
    'attempt_directories_created',0,'attempt_markers_created',0,'first_plant_markers_created',0, ...
    'entries',{entries});
fid=fopen(out,'w');assert(fid>=0,'N4Train24:Write','Cannot write %s.',out);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(audit) newline],'char');clear cleanup;
disp(['TRAIN24_DYNAMIC_PREPARE=' out]);
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'N4Train24:Read','Cannot open %s.',path);
cleanup=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cleanup;
end
