function receipt=run_gru_tau01_delayed_start_prepare()
% Run frozen source and one-event rho schedule checks; this entry never starts Plant.
studyRoot=fileparts(mfilename('fullpath'));cd(studyRoot);
addpath(fullfile(studyRoot,'candidate_runner_work','matlab','runtime'),'-begin');
release=jsondecode(fileread(fullfile(studyRoot,'RELEASE.json')));
p=prepare_gru_tau01_delayed_start_no_plant(char(release.expected_no_plant_scene),true);
receipt=jsondecode(fileread(fullfile(studyRoot,'NO_PLANT_PREPARE_RESULT_v1.json')));
assert(strcmp(char(receipt.status),'PASS_NO_PLANT_PREPARE')&&receipt.Plant_calls==0&&~receipt.plant_called);
fprintf('GRU_TAU01_DELAYED_START_NOPLANT=PASS scene=%s\n',p.scene_id);
end
