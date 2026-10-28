function audit=run_static_n4_helper_parity()
% Pure MATLAB helper parity on a frozen TRAIN-only action/event sequence.
here=fileparts(mfilename('fullpath'));studyRoot=fileparts(here);
inputPath=fullfile(studyRoot,'MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat');
metaPath=fullfile(studyRoot,'MATLAB_EVENTWISE_PARITY_INPUTS_v1.json');
outPath=fullfile(studyRoot,'audits','MATLAB_EVENTWISE_PARITY_v1.json');
assert(isfile(inputPath)&&isfile(metaPath)&&~isfile(outPath), ...
    'StaticN4:ParityFiles','Missing input or refusing to overwrite parity result.');
meta=jsondecode(fileread(metaPath));d=load(inputPath);
assert(strcmp(meta.status,'PASS_TRAIN_PARITY_INPUTS_READY')&& ...
    strcmp(meta.scene_id,'DL1018_DEV_T1_C00_W03')&&meta.Plant_calls==0&& ...
    ~meta.TEST_read&&~meta.VAL_read&&~meta.inertia_reconstruction_enabled, ...
    'StaticN4:ParityScope','Parity inputs are outside the fixed TRAIN/no-Plant scope.');
s=position_compensation_static_n4_init();
coeffError=max([abs(s.b(:)-d.b(:));abs(s.a(:)-d.a(:))]);
action=d.action_mps2;events=logical(d.event(:));expected=d.expected_mps2;
assert(isequal(size(action),[3,20000])&&isequal(size(expected),size(action))&& ...
    numel(events)==20000&&all(isfinite(action(:)))&&all(isfinite(expected(:))), ...
    'StaticN4:ParityShape','Malformed action/event sequence.');
output=zeros(size(action));
for k=1:numel(events)
    [s,output(:,k)]=position_compensation_static_n4_step(s,action(:,k),events(k));
end
actionError=max(abs(output(:)-expected(:)));expectedClips=double(d.clip_count);
pass=coeffError<=1e-12&&actionError<=1e-12&&s.clip_count==expectedClips;
audit=struct('status',ternary(pass,'PASS_STATIC_N4_HELPER_PARITY_NOPLANT', ...
    'FAIL_STATIC_N4_HELPER_PARITY_NOPLANT'),'scene_id',meta.scene_id, ...
    'max_abs_action_error_mps2',actionError,'max_abs_coefficient_error',coeffError, ...
    'matlab_clip_count',s.clip_count,'expected_clip_count',expectedClips, ...
    'centers_hz',[2.2,3.2,3.7,4.8],'quality_factor_each',[4,4,4,4], ...
    'Plant_calls',0,'runner_invoked',false,'TEST_read',false,'VAL_read',false, ...
    'inertia_reconstruction_enabled',false,'frozen_replay_status_preserved','FAIL_FIXED_FROZEN_REPLAY');
fid=fopen(outPath,'w');assert(fid>=0,'StaticN4:ParityWrite','Cannot create parity result.');
cleanup=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(audit,'PrettyPrint',true) newline],'char');clear cleanup;
fprintf('STATIC_N4_HELPER_PARITY=%s\n',outPath);
assert(pass,'StaticN4:ParityFailed','MATLAB helper does not match the frozen N4 recurrence.');
end

function y=ternary(c,a,b)
if c,y=a;else,y=b;end
end
