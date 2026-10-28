function report=check_matlab_eventwise_parity_v1()
% TRAIN24-only eventwise parity; no Plant loop is entered.
here=fileparts(mfilename('fullpath'));studyRoot=fileparts(here);
entry=fullfile(studyRoot,'candidate_runner_work','matlab','runtime','activate_paired_runner.m');
assert(isfile(entry),'PositionDCPenaltyParity:Runner','Isolated runner is missing.');
addpath(fileparts(entry),'-begin');runnerRoot=activate_paired_runner();
inputPath=fullfile(studyRoot,'MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat');
modelPath=fullfile(runnerRoot,'matlab','models','position_balanced_full24.mat');
d=load(inputPath);m=load(modelPath);
assert(isequal(size(d.x14),[14 1999 24])&&isequal(size(d.base_applied_mps2),[3 1999 24]), ...
    'PositionDCPenaltyParity:Shape','Input tensor shape changed.');
assert(abs(d.event_time_s(1,1)-.01)<2e-6,'PositionDCPenaltyParity:FirstEvent','First event must be 0.01 s.');
assert(all(all(~logical(d.ready_mask(:,1:31))))&&all(all(logical(d.ready_mask(:,32:end)))), ...
    'PositionDCPenaltyParity:Warmup','First-ready index must be zero-based 31.');
model=struct('input_mean',double(m.input_mean(:)),'input_std',double(m.input_std(:)), ...
    'gru_weight_ih_l0',double(m.gru_weight_ih_l0),'gru_weight_hh_l0',double(m.gru_weight_hh_l0), ...
    'gru_bias_ih_l0',double(m.gru_bias_ih_l0(:)),'gru_bias_hh_l0',double(m.gru_bias_hh_l0(:)), ...
    'head_weight',double(m.head_weight),'head_bias',double(m.head_bias(:)));
maxRaw=0;maxDelta=0;maxAction=0;maxBeta=0;
for s=1:24
    hidden=zeros(32,1);rawScene=zeros(3,1999);deltaScene=zeros(3,1999);actionScene=zeros(3,1999);
    for k=1:1999
        [hidden,raw]=position_residual_gru_step_v1(hidden,double(d.x14(:,k,s)),model);
        ready=logical(d.ready_mask(s,k));beta=min(max(double(d.event_time_s(s,k))/1.8,0),1);
        if ready,delta=max(min(raw,.5),-.5);else,delta=zeros(3,1);end
        if ready,action=min(max(double(d.base_applied_mps2(:,k,s))+beta*delta,-3),3);else,action=zeros(3,1);end
        rawScene(:,k)=raw;deltaScene(:,k)=delta;actionScene(:,k)=action;
        maxBeta=max(maxBeta,abs(beta-double(d.expected_beta(s,k))));
    end
    er=double(d.expected_raw_mps2(:,:,s));ed=double(d.expected_delta_mps2(:,:,s));ea=double(d.expected_action_mps2(:,:,s));
    maxRaw=max(maxRaw,max(abs(rawScene(:)-er(:))));
    maxDelta=max(maxDelta,max(abs(deltaScene(:)-ed(:))));
    maxAction=max(maxAction,max(abs(actionScene(:)-ea(:))));
    assert(all(deltaScene(:,1:31)==0,'all')&&all(actionScene(:,1:31)==0,'all'), ...
        'PositionDCPenaltyParity:WarmupOutput','Warmup delta/action must be exactly zero.');
end
fprintf('DC_PENALTY_PARITY raw=%.9g delta=%.9g action=%.9g beta=%.9g\n',maxRaw,maxDelta,maxAction,maxBeta);
assert(maxRaw<2e-5&&maxDelta<2e-5&&maxAction<2e-5&&maxBeta<2e-7, ...
    'PositionDCPenaltyParity:Mismatch','MATLAB/Python eventwise mismatch exceeds tolerance.');
report=struct('schema','POSITION_TEACHER_DC_PENALTY_MATLAB_EVENTWISE_PARITY_V1', ...
    'status','PASS_TRAIN24_EVENTWISE_PARITY','scope','offline eventwise replay only; no Plant step', ...
    'study_id','position_teacher_dc_penalty_full24_preflight_v1','scene_count',24,'events_per_scene',1999, ...
    'first_event_time_s',double(d.event_time_s(1,1)),'first_ready_zero_based_index',31, ...
    'first_ready_event_time_s',double(d.event_time_s(1,32)), ...
    'warmup_hidden_updates_from_event0',true,'hidden_reset_each_scene',true, ...
    'beta_formula','clip(event_time_s/1.8,0,1)','delta_clip_mps2',.5,'action_clip_mps2',3, ...
    'max_abs_raw_error',maxRaw,'max_abs_delta_error',maxDelta,'max_abs_action_error',maxAction, ...
    'max_abs_beta_error',maxBeta,'plant_called',false);
out=fullfile(here,'MATLAB_EVENTWISE_PARITY_RESULT_v1.json');
fid=fopen(out,'w','n','UTF-8');assert(fid>=0);clean=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));clear clean;
end
