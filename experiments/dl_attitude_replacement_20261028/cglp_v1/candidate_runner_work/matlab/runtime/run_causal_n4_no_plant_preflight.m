function audit=run_causal_n4_no_plant_preflight(sceneId)
% Run the isolated full runner through its hard stop before the first loop.
entry=fileparts(mfilename('fullpath'));studyRoot=fileparts(fileparts(fileparts(entry)));
releasePath=fullfile(studyRoot,'RELEASE.json');lockPath=fullfile(studyRoot,'SOURCE_LOCK_v2.json');
release=jsondecode(fileread(releasePath));lock=jsondecode(fileread(lockPath));
assert(strcmpi(sha256_file(lockPath),release.source_lock_sha256),'N4Gate:Lock','Source lock changed.');
for i=1:numel(lock.files)
    p=char(lock.files(i).path);
    assert(isfile(p)&&strcmpi(sha256_file(p),char(lock.files(i).sha256)), ...
        'N4Gate:SourceHash','Locked source changed: %s',p);
end
assert(release.authorized_Plant_calls==0&&release.Plant_calls==0&&release.potential_budget_calls==0, ...
    'N4Gate:Budget','Preflight requires zero Plant budget.');
prepared=prepare_causal_n4_scene_no_plant(sceneId);marker=prepared.marker_path;
assert(~isfile(marker),'N4Gate:NoOverwrite','A marker already exists for %s.',sceneId);
write_json(marker,struct('scene_id',prepared.scene_id,'stage','RUNNING','Plant_calls',0));
try
    run_mlp15_dev72_closed_loop(prepared.scene,prepared.cfg,prepared.opts);
    error('N4Gate:MissingStop','Runner returned without stopping before the Plant loop.');
catch ME
    if ~strcmp(ME.identifier,'PositionNotch:NoPlantPreflightStop')
        write_json(fullfile(studyRoot,'audits',[prepared.scene_id '_failure.json']), ...
            struct('status','FAIL','scene_id',prepared.scene_id,'Plant_calls',0, ...
            'error_identifier',ME.identifier,'error_message',ME.message));
        rethrow(ME);
    end
    stopId=ME.identifier;stopMessage=ME.message;
end
write_json(marker,struct('scene_id',prepared.scene_id,'stage','COMPLETED_NO_PLANT_BOUNDARY', ...
    'Plant_calls',0,'stop_identifier',stopId));
attempts=dir(fullfile(studyRoot,'runs','**','attempt_started.marker'));
plants=dir(fullfile(studyRoot,'runs','**','first_plant_step.marker'));
assert(isempty(attempts)&&isempty(plants),'N4Gate:UnexpectedPlant','Unexpected Plant or attempt marker.');
audit=struct('status','PASS_FULL_RUNNER_NOPLANT_BOUNDARY','scene_id',prepared.scene_id, ...
    'source_lock_sha256',sha256_file(lockPath),'release_sha256',sha256_file(releasePath), ...
    'binding_sha256',prepared.binding_sha256,'payload_sha256',prepared.payload_sha256, ...
    'parent_raw_sha256',prepared.parent_raw_sha256,'c5_raw_sha256',prepared.c5_raw_sha256, ...
    'b_raw_sha256',prepared.b_raw_sha256,'runner_stop_identifier',stopId, ...
    'runner_stop_message',stopMessage,'stopped_before_main_loop',true,'Plant_calls',0, ...
    'attempt_markers',0,'first_plant_step_markers',0,'extra_position_gru_enabled',false, ...
    'frozen_C5_exact_options_match',true,'TEST_read',false,'VAL_read',false, ...
    'inertia_reconstruction_enabled',false);
out=fullfile(studyRoot,'audits',[prepared.scene_id '_no_plant.json']);
assert(~isfile(out),'N4Gate:NoOverwrite','Refusing to overwrite audit.');write_json(out,audit);
fprintf('CAUSAL_N4_NO_PLANT=%s\n',out);
end

function write_json(path,x)
fid=fopen(path,'w');assert(fid>=0,'N4Gate:Write','Cannot write %s.',path);
c=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(x,'PrettyPrint',true) newline],'char');clear c;
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'N4Gate:Read','Cannot open %s.',path);
c=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear c;
end
