function result=check_dl1018_reference_cache_guard()
% Small synthetic fixtures verify old pipeline evidence is rejected before reuse.
projectRoot=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(projectRoot,'matlab','scenes'),fullfile(projectRoot,'matlab','runtime'));
fixtureDir=fullfile(projectRoot,'reports','integration_next14_v1','engineering','fixtures');
if ~isfolder(fixtureDir),mkdir(fixtureDir);end
root=tempname(fixtureDir);mkdir(root);
validRoot=fullfile(root,'valid_identity');mkdir(validRoot);
mkdir(fullfile(validRoot,'reports'));
write_text(fullfile(validRoot,'reports','G01_SCENES.json'), ...
    "{""status"":""PASS"",""next_gate_allowed"":true,""reference_contract_id"":""DL1018_SCENE_REF_FIG8_A2_V2""}"+newline);
assert_scene_reference_contract_dl1018(validRoot);
mkdir(fullfile(root,'reports'));mkdir(fullfile(root,'logs'));
for folder={'data','scenes','runtime','models','metrics'}
    mkdir(fullfile(root,'matlab',folder{1}));
end
write_text(fullfile(root,'logs','attempt_index.csv'), ...
    "run_id,status"+newline+"G02_P_TEACHER_OLD_B,STABLE"+newline);
assert_error(@()make_scenes_dl1018('BUILD',root),'DL1018:LegacySceneEvidence');
assert(~isfile(fullfile(root,'reports','G01_SCENES.json'))&& ...
    ~isfile(fullfile(root,'configs','scene_specs.csv')), ...
    'DL1018:CacheGuardTestWrite','BUILD wrote output before rejecting legacy evidence.');

write_text(fullfile(root,'reports','G01_SCENES.json'), ...
    "{""status"":""PASS"",""next_gate_allowed"":true}"+newline);
assert_error(@()make_scenes_dl1018('BUILD',root),'DL1018:ReferenceIdentityConflict');
write_text(fullfile(root,'logs','episode_index.csv'), ...
    "run_id,source_role,accepted"+newline+"G02_P_TEACHER_OLD_B,B,true"+newline);
rawFolder=fullfile(root,'data','raw','dev','FAKE_SCENE','B','attempt_01');mkdir(rawFolder);
write_text(fullfile(rawFolder,'raw_run.mat'),'fixture only; no MATLAB payload');

assert_error(@()collect_g02_position_teacher(root),'DL1018:ReferenceIdentityMismatch');
assert_error(@()collect_position_role_dl1018(root,'G04_P_STUDENT','P_INIT_STUDENT'), ...
    'DL1018:ReferenceIdentityMismatch');
assert_error(@()collect_position_dev_dl1018(root),'DL1018:ReferenceIdentityMismatch');
assert_error(@()collect_dual_eval_dl1018(root,'G11_PA_DEV'),'DL1018:ReferenceIdentityMismatch');
assert_error(@()run_gate_dl1018('G02_P_TEACHER',root,root),'DL1018:ReferenceIdentityMismatch');
assert(isfile(fullfile(root,'logs','attempt_index.csv'))&& ...
    isfile(fullfile(root,'logs','episode_index.csv'))&&isfile(fullfile(rawFolder,'raw_run.mat')), ...
    'DL1018:CacheGuardTestMutation','A collector changed or removed a fixture cache.');
result=struct('old_pass_rejected',true,'missing_g01_with_ledger_rejected',true, ...
    'accepted_cache_collectors_rejected',true,'valid_reference_identity_allowed',true, ...
    'plant_calls',0,'optimizer_steps',0,'test_accesses',0);
fprintf('DL1018 cache guard fixtures: valid identity allowed; stale G01, missing G01 with ledger, and accepted/raw cache paths rejected before collection; Plant=0, optimizer=0, TEST=0. Fixture: %s\n',root);
end

function assert_error(f,expected)
try
    f();
catch err
    assert(strcmp(err.identifier,expected),'DL1018:CacheGuardTestError', ...
        'Expected %s, received %s: %s',expected,err.identifier,err.message);
    return;
end
error('DL1018:CacheGuardTestAccepted','Expected %s but call returned.',expected);
end

function write_text(path,value)
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
f=fopen(path,'w');assert(f>=0);c=onCleanup(@()fclose(f));fprintf(f,'%s',char(value));clear c;
end
