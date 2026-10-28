function run_mlp15_physical_residual_screen()
% Run remaining authorized scenes, preserving and skipping completed attempts.
entry=fileparts(mfilename('fullpath'));
studyRoot=fileparts(fileparts(fileparts(entry)));
release=jsondecode(fileread(fullfile(studyRoot,'RELEASE.json')));
manifest=jsondecode(fileread(fullfile(studyRoot,'MLP15_DEV72_PAYLOAD_MANIFEST_v2.json')));
sceneIds=cellstr(string(release.authorized_scenes));
for i=1:numel(sceneIds)
    sceneId=sceneIds{i};
    hit=find(strcmp({manifest.records.scene_id},sceneId));
    assert(isscalar(hit),'DLMLP:PayloadManifest','No unique payload for %s.',sceneId);
    attemptDir=fullfile(studyRoot,'runs',sceneId,'PHYS_RESIDUAL_ATTEMPT_01');
    statusPath=fullfile(attemptDir,'run_status.json');
    if isfile(statusPath)
        status=jsondecode(fileread(statusPath));
        assert(strcmp(char(status.scene_id),sceneId)&&strcmp(char(status.state),'COMPLETED'), ...
            'DLMLP:PriorAttempt','Existing attempt for %s is not a completed run.',sceneId);
        fprintf('SKIP_COMPLETED=%s\n',sceneId);
        continue;
    end
    run_mlp15_physical_residual_attempt(char(manifest.records(hit).payload_path),attemptDir);
    fprintf('\nCOMPLETED=%s\n',sceneId);
end
end
