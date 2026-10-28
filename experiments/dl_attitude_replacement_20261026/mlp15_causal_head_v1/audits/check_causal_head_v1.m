function report=check_causal_head_v1()
% Check the actual MATLAB deployment step against an independent NumPy sequence.
here=fileparts(mfilename('fullpath'));study=fileparts(here);research=fileparts(study);
outPath=fullfile(here,'NO_PLANT_CHECK.json');assert(~isfile(outPath));
runner=fullfile(study,'candidate_runner_work');runtime=fullfile(runner,'matlab','runtime');
addpath(runtime);activate_paired_runner();
modelPath=fullfile(research,'mlp15_c5_teacher_full72_v1','runs', ...
    'C5_MLP15_FULL72_SEED2026102001','mlp15_attitude_weights_v1.mat');model=load(modelPath);
fixturePath=fullfile(here,'HEAD_FIXTURE.mat');F=load(fixturePath);
parent=fullfile(research,'mlp15_dev72_v2','candidate_runner_work');
files=dir(fullfile(runner,'matlab','**','*.m'));changed=cell(0,1);
for i=1:numel(files)
    path=fullfile(files(i).folder,files(i).name);relative=erase(path,[runner filesep]);
    if ~strcmpi(hash_file(path),hash_file(fullfile(parent,relative)))
        changed{end+1,1}=relative; %#ok<AGROW>
    end
end
expected={'matlab/runtime/mlp15_attitude_forward_v1.m';'matlab/runtime/mlp15_attitude_step_v1.m'; ...
    'matlab/runtime/run_mlp15_dev72_closed_loop.m'};
assert(isequal(sort(replace(string(changed),'\','/')),sort(string(expected))));
for name={'mlp15_attitude_forward_v1','mlp15_attitude_step_v1'}
    assert(isempty(checkcode(fullfile(runtime,[name{1} '.m']),'-id')), ...
        'HeadCheck:Analyzer','New model-step diagnostics.');
end
old=checkcode(fullfile(parent,'matlab','runtime','run_mlp15_dev72_closed_loop.m'),'-id');
new=checkcode(fullfile(runtime,'run_mlp15_dev72_closed_loop.m'),'-id');
oldText=string({old.message});newText=string({new.message});
% ALIGN diagnostics embed matching-END line numbers, shifted by the insertion.
oldAlign=string({old.id})=="ALIGN";newAlign=string({new.id})=="ALIGN";
oldText(oldAlign)=regexprep(oldText(oldAlign),'\d+','#');
newText(newAlign)=regexprep(newText(newAlign),'\d+','#');
assert(isequal(sort(string({old.id})+":"+oldText), ...
    sort(string({new.id})+":"+newText)), ...
    'HeadCheck:RuntimeDiagnostics','Runtime gained diagnostics beyond its parent.');
[memory,~]=mlp15_attitude_step_v1('init',struct,struct,model);
[disabled,~]=mlp15_attitude_step_v1('init',struct,struct,model);
maxRaw=0;maxTorque=0;maxWeight=0;maxObserved=0;maxFrozen=0;projections=0;updates=0;
alternative=struct;count=size(F.features,2);
for i=1:count
    k=F.sample_indices(i);
    input=struct('feature',F.features(:,i),'J0',F.J0,'beta',F.beta(i), ...
        'dmax',[45;45;4.7124],'head_enabled',true,'sample_index',k,'time_s',F.time_all(k));
    if i>1
        prior=F.sample_indices(i-1);
        input.omega_history=F.omega(prior:k,:);input.torque_history=F.issued_torque(prior:k-1,:);
        input.history_time=F.time_all(prior:k);input.history_sample_indices=(prior:k).';
    end
    beforeMemory=memory;
    [memory,z]=mlp15_attitude_step_v1('step',memory,input,model);
    off=input;off.head_enabled=false;[disabled,zoff]=mlp15_attitude_step_v1('step',disabled,off,model);
    maxRaw=max(maxRaw,max(abs(z.raw_residual_rad_s2-F.expected_raw(:,i))));
    maxTorque=max(maxTorque,max(abs(z.estimateTorque_Nm-F.expected_torque(:,i))));
    maxFrozen=max(maxFrozen,max(abs(zoff.raw_residual_rad_s2-F.expected_base(:,i))));
    maxObserved=max(maxObserved,max(abs(z.head.observation_residual_rad_s2-F.expected_observed(:,i))));
    maxWeight=max(maxWeight,max(abs(z.head.weight_before-F.expected_weight_before(:,:,i)),[],'all'));
    maxWeight=max(maxWeight,max(abs(z.head.weight_after-F.expected_weight_after(:,:,i)),[],'all'));
    assert(z.head.update_executed==logical(F.expected_updated(i))&& ...
        z.head.projection_active==logical(F.expected_projection(i)));
    projections=projections+z.head.projection_active;updates=updates+z.head.update_executed;
    if i==240
        changedInput=input;changedInput.torque_history(end,1)=changedInput.torque_history(end,1)+.005;
        [alternative,changedOut]=mlp15_attitude_step_v1('step',beforeMemory,changedInput,model);
        assert(isequal(z.raw_residual_rad_s2,changedOut.raw_residual_rad_s2)&& ...
            norm(alternative.head_weight-memory.head_weight,'fro')>1e-10, ...
            'HeadCheck:CurrentOutput','Current output used the current observation update.');
    elseif i==241
        [~,changedNext]=mlp15_attitude_step_v1('step',alternative,input,model);
        assert(norm(changedNext.raw_residual_rad_s2-z.raw_residual_rad_s2)>1e-10);
    end
end
covarianceError=max(abs(memory.head_covariance-F.expected_covariance_final),[],'all');
assert(maxRaw<1e-6&&maxTorque<1e-8&&maxWeight<1e-7&&maxFrozen<1e-7&& ...
    maxObserved<1e-8&&covarianceError<1e-7&&projections>0&&updates>0, ...
    'HeadCheck:Parity','NumPy/MATLAB causal head parity failed.');
% Invalid intervals and changing J0 are rejected by the real step.
invalid=input;invalid.history_time(end)=invalid.history_time(end)+.001;
assert_rejected(disabled,invalid,model,'DLMLP:HistoryCausality');
report=struct('status','PASS_NO_PLANT_CAUSAL_HEAD','Plant_calls',0,'TEST_read',false, ...
    'model_sha256',hash_file(modelPath),'fixture_sha256',hash_file(fixturePath), ...
    'changed_runtime_files',{changed},'synthetic_events',count,'max_raw_error_rad_s2',maxRaw, ...
    'max_frozen_model_error_rad_s2',maxFrozen,'max_torque_error_Nm',maxTorque, ...
    'max_weight_error',maxWeight,'max_observation_error_rad_s2',maxObserved, ...
    'max_covariance_error',covarianceError,'projection_events',projections,'update_events',updates, ...
    'current_observation_cannot_change_current_output',true,'invalid_history_rejected',true, ...
    'source_script_sha256',hash_file([mfilename('fullpath') '.m']));
fid=fopen(outPath,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));disp(report);
end

function assert_rejected(memory,input,model,expected)
% Use an actual prior valid event state; disabled keeps no feature history.
memory.previous_sample_index=input.history_sample_indices(1);
memory.previous_time_s=input.history_time(1);memory.previous_beta=1;
memory.fixed_J0=input.J0;
try
    mlp15_attitude_step_v1('step',memory,input,model);
catch ME
    assert(strcmp(ME.identifier,expected),'HeadCheck:WrongError','Unexpected validation error.');return;
end
error('HeadCheck:MissingError','Invalid history was accepted.');
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
