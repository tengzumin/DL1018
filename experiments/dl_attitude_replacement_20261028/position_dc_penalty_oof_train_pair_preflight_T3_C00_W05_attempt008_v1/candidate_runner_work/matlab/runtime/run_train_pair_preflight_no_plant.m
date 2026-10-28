function audit=run_train_pair_preflight_no_plant()
% Verify a fixed TRAIN fold checkpoint and stop immediately before the main loop.
entry=fileparts(mfilename('fullpath'));
runnerRoot=fileparts(fileparts(entry));
studyRoot=fileparts(runnerRoot);
lockPath=fullfile(studyRoot,'SOURCE_LOCK_NO_PLANT_v1.json');
releasePath=fullfile(studyRoot,'RELEASE.json');
lock=jsondecode(fileread(lockPath));release=jsondecode(fileread(releasePath));
assert(strcmpi(sha256_file(lockPath),char(release.source_lock_sha256)), ...
    'TRAINPair:ReleaseLock','Source lock changed after the no-Plant release was written.');
for i=1:numel(lock.files)
    path=char(lock.files(i).path);
    assert(isfile(path)&&strcmpi(sha256_file(path),char(lock.files(i).sha256)), ...
        'TRAINPair:SourceHash','Locked source changed: %s',path);
end
assert(strcmp(char(release.status),'PREPARED_NO_PLANT_PENDING_ROOT_AUDIT')&& ...
    double(release.authorized_Plant_calls)==0&&double(release.Plant_calls)==0&& ...
    ~logical(release.TEST_read)&&~logical(release.inertia_reconstruction_enabled), ...
    'TRAINPair:NoPlantOnly','Release must have a hard zero Plant budget and forbidden-scope flags off.');
parity=verify_train_oof_fold_matlab_parity(studyRoot);
prepared=prepare_train_scene_no_plant();
markerPath=prepared.marker_path;
assert(~isfile(markerPath),'TRAINPair:ExistingMarker','Refusing to reuse a previous preflight marker.');
write_json_new(markerPath,struct('schema','POSITION_DC_OOF_TRAIN_PAIR_PREFLIGHT_MARKER_V1', ...
    'scene_id',prepared.scene_id,'stage','RUNNING','Plant_calls',0));
opts=prepared.opts;
try
    run_mlp15_dev72_closed_loop(prepared.scene,prepared.cfg,opts);
    error('TRAINPair:MissingStop','No-Plant runner returned instead of stopping before the main loop.');
catch ME
    if strcmp(char(ME.identifier),'PositionNotch:NoPlantPreflightStop')
        stopId=char(ME.identifier);stopMessage=char(ME.message);
    else
        failure=struct('schema','POSITION_DC_OOF_TRAIN_PAIR_NO_PLANT_PREFLIGHT_FAILURE_V1', ...
            'status','FAIL','scene_id',prepared.scene_id,'fold_id',prepared.fold_id, ...
            'error_identifier',char(ME.identifier),'error_message',char(ME.message), ...
            'Plant_calls',0,'VAL_read',false,'TEST_read',false);
        write_json_new(fullfile(studyRoot,'audits','NO_PLANT_PREFLIGHT_FAILURE_v1.json'),failure);
        rethrow(ME);
    end
end
write_json_overwrite(markerPath,struct('schema','POSITION_DC_OOF_TRAIN_PAIR_PREFLIGHT_MARKER_V1', ...
    'scene_id',prepared.scene_id,'stage','COMPLETED_NO_PLANT_BOUNDARY','Plant_calls',0, ...
    'expected_stop_identifier',stopId));
attemptMarkers=dir(fullfile(studyRoot,'runs','**','attempt_started.marker'));
plantMarkers=dir(fullfile(studyRoot,'runs','**','first_plant_step.marker'));
assert(isempty(attemptMarkers)&&isempty(plantMarkers), ...
    'TRAINPair:UnexpectedAttempt','NoPlant preflight unexpectedly produced an attempt or Plant marker.');
audit=struct('schema','POSITION_DC_OOF_TRAIN_PAIR_NO_PLANT_PREFLIGHT_V1','status','PASS', ...
    'study_id',char(release.study_id),'scene_id',prepared.scene_id,'fold_id',prepared.fold_id, ...
    'source_lock_sha256',sha256_file(lockPath),'release_sha256',sha256_file(releasePath), ...
    'train_scene_binding_sha256',prepared.binding_sha256,'weights_sha256',prepared.weights_sha256, ...
    'parent_raw_sha256',prepared.parent_raw_sha256,'c5_raw_sha256',prepared.c5_raw_sha256, ...
    'matlab_parity_status',char(parity.status), ...
    'matlab_parity_result_sha256',sha256_file(fullfile(studyRoot,'audits','MATLAB_EVENTWISE_PARITY_v1.json')), ...
    'runner_stop_identifier',stopId,'runner_stop_message',stopMessage, ...
    'stopped_before_main_loop',true,'Plant_calls',0,'VAL_read',false,'TEST_read',false, ...
    'inertia_reconstruction_enabled',false,'attempt_markers',0,'first_plant_step_markers',0, ...
    'preflight_marker_path',markerPath,'preflight_marker_sha256',sha256_file(markerPath));
resultPath=fullfile(studyRoot,'audits','NO_PLANT_PREFLIGHT_v1.json');
write_json_new(resultPath,audit);
fprintf('TRAIN_PAIR_NO_PLANT_PREFLIGHT=%s\n',resultPath);
end

function write_json_new(path,x)
assert(~isfile(path),'TRAINPair:NoOverwrite','Refusing to overwrite %s.',path);
write_json_overwrite(path,x);
end
function write_json_overwrite(path,x)
fid=fopen(path,'w');assert(fid>=0,'TRAINPair:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(x,'PrettyPrint',true) newline],'char');clear cleanup;
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'TRAINPair:Read','Cannot open %s.',path);
cleanup=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cleanup;
end
