function audit=run_static_n4_no_plant_preflight()
% Exercise the complete isolated runner up to its hard pre-Plant boundary.
entry=fileparts(mfilename('fullpath'));runnerRoot=fileparts(fileparts(entry));studyRoot=fileparts(runnerRoot);
lockPath=fullfile(studyRoot,'SOURCE_LOCK_NO_PLANT_v1.json');releasePath=fullfile(studyRoot,'RELEASE.json');
lock=jsondecode(fileread(lockPath));release=jsondecode(fileread(releasePath));
assert(strcmpi(sha256_file(lockPath),release.source_lock_sha256), ...
    'StaticN4:Lock','No-Plant lock does not match the release.');
for i=1:numel(lock.files)
    p=char(lock.files(i).path);
    assert(isfile(p)&&strcmpi(sha256_file(p),char(lock.files(i).sha256)), ...
        'StaticN4:SourceHash','Locked source changed: %s',p);
end
assert(strcmp(release.status,'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT')&& ...
    release.authorized_Plant_calls==0&&release.Plant_calls==0&& ...
    ~release.TEST_read&&~release.VAL_data_read&&~release.inertia_reconstruction_enabled, ...
    'StaticN4:Budget','Preflight must have a hard zero-Plant budget.');
prepared=prepare_static_n4_train_scene_no_plant();marker=prepared.marker_path;
assert(~isfile(marker),'StaticN4:NoOverwrite','Refusing to reuse a no-Plant marker.');
write_json(marker,struct('schema','STATIC_N4_PREFLIGHT_MARKER_V1','scene_id',prepared.scene_id, ...
    'stage','RUNNING','Plant_calls',0));
try
    run_mlp15_dev72_closed_loop(prepared.scene,prepared.cfg,prepared.opts);
    error('StaticN4:MissingStop','Runner returned instead of stopping before the Plant loop.');
catch ME
    if strcmp(ME.identifier,'PositionNotch:NoPlantPreflightStop')
        stopId=ME.identifier;stopMessage=ME.message;
    else
        write_json(fullfile(studyRoot,'audits','NO_PLANT_FAILURE_v1.json'), ...
            struct('status','FAIL','scene_id',prepared.scene_id,'Plant_calls',0, ...
            'error_identifier',ME.identifier,'error_message',ME.message));
        rethrow(ME);
    end
end
write_json(marker,struct('schema','STATIC_N4_PREFLIGHT_MARKER_V1','scene_id',prepared.scene_id, ...
    'stage','COMPLETED_NO_PLANT_BOUNDARY','Plant_calls',0,'stop_identifier',stopId));
attempts=dir(fullfile(studyRoot,'runs','**','attempt_started.marker'));
plants=dir(fullfile(studyRoot,'runs','**','first_plant_step.marker'));
assert(isempty(attempts)&&isempty(plants),'StaticN4:UnexpectedPlant','A Plant or attempt marker exists.');
audit=struct('status','PASS_FULL_RUNNER_NOPLANT_BOUNDARY','study_id',release.study_id, ...
    'scene_id',prepared.scene_id,'source_lock_sha256',sha256_file(lockPath), ...
    'release_sha256',sha256_file(releasePath),'binding_sha256',prepared.binding_sha256, ...
    'payload_sha256',prepared.payload_sha256,'parent_raw_sha256',prepared.parent_raw_sha256, ...
    'c5_raw_sha256',prepared.c5_raw_sha256,'b_raw_sha256',prepared.b_raw_sha256, ...
    'runner_stop_identifier',stopId,'runner_stop_message',stopMessage, ...
    'stopped_before_main_loop',true,'Plant_calls',0,'attempt_markers',0, ...
    'first_plant_step_markers',0,'position_residual_gru_runtime_field_present',false, ...
    'extra_position_gru_loaded_or_forwarded',false,'frozen_C5_exact_options_match',true, ...
    'centers_hz',[2.2,3.2,3.7,4.8],'quality_factor_each',[4,4,4,4], ...
    'sample_rate_hz',100,'TEST_read',false,'VAL_read',false,'inertia_reconstruction_enabled',false);
out=fullfile(studyRoot,'audits','NO_PLANT_PREFLIGHT_v1.json');
assert(~isfile(out),'StaticN4:NoOverwrite','Refusing to overwrite the no-Plant audit.');
write_json(out,audit);fprintf('STATIC_N4_NO_PLANT_PREFLIGHT=%s\n',out);
end

function write_json(path,x)
fid=fopen(path,'w');assert(fid>=0,'StaticN4:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(x,'PrettyPrint',true) newline],'char');clear cleanup;
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'StaticN4:Read','Cannot open %s.',path);
cleanup=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cleanup;
end
