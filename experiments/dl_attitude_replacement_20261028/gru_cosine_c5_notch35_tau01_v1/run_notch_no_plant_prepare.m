function receipt=run_notch_no_plant_prepare()
% Entry point for the fixed C01_W14 no-Plant notch preflight.
studyRoot=fileparts(mfilename('fullpath'));
oldFolder=pwd;restoreFolder=onCleanup(@()cd(oldFolder));
cd(studyRoot);addpath(fullfile(studyRoot,'audits'),'-begin');
prepare_applied_notch_no_plant(true);
receipt=jsondecode(fileread(fullfile(studyRoot,'NO_PLANT_PREPARE_RESULT_v1.json')));
clear restoreFolder
end
