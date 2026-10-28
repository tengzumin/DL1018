function dirs=run_gru_tracking_force09_screen()
% Root entry for the exact frozen 12-scene screen.
studyRoot=fileparts(mfilename('fullpath'));
release=jsondecode(fileread(fullfile(studyRoot,'RELEASE.json')));
assert(strcmp(char(release.status),'RELEASED')&& ...
    double(release.authorized_Plant_calls)==12&&numel(release.authorized_scenes)==12, ...
    'GRUForce09:Release','Screen release is not ready for root launch.');
scenes=cellstr(string(release.authorized_scenes));
dirs=cell(size(scenes));
for i=1:numel(scenes)
    sceneDir=fullfile(studyRoot,'runs',scenes{i},'GRU_FORCE09_ATTEMPT_01');
    statusPath=fullfile(sceneDir,'run_status.json');
    if isfolder(sceneDir)||isfile(statusPath)
        assert(isfile(statusPath),'GRUForce09:ExistingAttempt', ...
            'Existing attempt for %s is incomplete; refusing to overwrite.',scenes{i});
        status=jsondecode(fileread(statusPath));
        assert(strcmp(char(status.state),'COMPLETED')&& ...
            strcmp(char(status.scene_id),scenes{i})&& ...
            double(status.Plant_calls)==1&& ...
            abs(double(status.position_nn_compensation_scale)-.9)<1e-12, ...
            'GRUForce09:ExistingAttempt','Existing attempt for %s is not a matching complete force09 run.',scenes{i});
        dirs{i}=sceneDir;
    else
        dirs{i}=run_gru_tracking_force09_attempt(scenes{i});
    end
end
end
