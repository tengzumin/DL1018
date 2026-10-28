function audit=verify_train_oof_fold_matlab_parity(studyRoot)
% MATLAB eventwise replay of the six heldout TRAIN scenes; no Plant calls.
if nargin<1||isempty(studyRoot),studyRoot=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));end
runnerRoot=fullfile(studyRoot,'candidate_runner_work');
addpath(fullfile(runnerRoot,'matlab','runtime'));
parityPath=fullfile(studyRoot,'MATLAB_EVENTWISE_PARITY_INPUTS_v1.mat');
weightsPath=fullfile(runnerRoot,'matlab','models','position_dc_oof_holdout_W00_05.mat');
p=load(parityPath);w=load(weightsPath);
meta=jsondecode(fileread(fullfile(studyRoot,'MATLAB_EVENTWISE_PARITY_INPUTS_v1.json')));
assert(isequal(size(p.x14),[14,1999,6])&&isequal(size(p.expected_raw_mps2),[3,1999,6])&& ...
    isequal(size(p.expected_delta_mps2),[3,1999,6])&&isequal(size(p.expected_action_mps2),[3,1999,6]), ...
    'TRAINPair:ParityShape','MATLAB parity input shapes changed.');
model=struct('input_mean',double(w.input_mean(:)),'input_std',double(w.input_std(:)), ...
    'gru_weight_ih_l0',double(w.gru_weight_ih_l0),'gru_weight_hh_l0',double(w.gru_weight_hh_l0), ...
    'gru_bias_ih_l0',double(w.gru_bias_ih_l0(:)),'gru_bias_hh_l0',double(w.gru_bias_hh_l0(:)), ...
    'head_weight',double(w.head_weight),'head_bias',double(w.head_bias(:)));
rawErr=0;deltaErr=0;actionErr=0;sceneMax=zeros(6,3);warmupNonzero=0;firstReady=zeros(6,1);
for s=1:6
    h=zeros(32,1); % hidden state is reset per scene; event 0 still updates it.
    for k=1:1999
        [h,r]=position_residual_gru_step_v1(h,double(p.x14(:,k,s)),model);
        ready=logical(p.ready_mask(s,k));
        beta=min(max(double(p.event_time_s(s,k))/1.8,0),1);
        if ready
            d=min(max(r,-.5),.5);
            a=min(max(double(p.base_applied_mps2(:,k,s))+beta*d,-3),3);
            if firstReady(s)==0,firstReady(s)=k-1;end
        else
            d=zeros(3,1);a=zeros(3,1);
            if any(d~=0),warmupNonzero=warmupNonzero+1;end
        end
        er=max(abs(r-double(p.expected_raw_mps2(:,k,s))));
        ed=max(abs(d-double(p.expected_delta_mps2(:,k,s))));
        ea=max(abs(a-double(p.expected_action_mps2(:,k,s))));
        sceneMax(s,:)=[max(sceneMax(s,1),er),max(sceneMax(s,2),ed),max(sceneMax(s,3),ea)];
    end
end
rawErr=max(sceneMax(:,1));deltaErr=max(sceneMax(:,2));actionErr=max(sceneMax(:,3));
assert(all(firstReady==31)&&warmupNonzero==0&&max([rawErr,deltaErr,actionErr])<2e-6, ...
    'TRAINPair:Parity','MATLAB eventwise replay differs from the locked PyTorch/OOF result.');
audit=struct('schema','POSITION_DC_PENALTY_CV_FOLD_MATLAB_EVENTWISE_PARITY_V1', ...
    'status','PASS','scene_ids',{cellstr(string(meta.scene_ids))},'scene_count',6,'events_per_scene',1999, ...
    'hidden_reset_per_scene',true,'hidden_updates_from_event_zero',true,'first_ready_event_index_zero_based',31, ...
    'warmup_nonzero_output_count',warmupNonzero,'max_abs_raw_delta_error_mps2',rawErr, ...
    'max_abs_clipped_delta_error_mps2',deltaErr,'max_abs_action_error_mps2',actionErr, ...
    'scene_max_abs_errors',sceneMax,'Plant_called',false,'VAL_read',false,'TEST_read',false);
outPath=fullfile(studyRoot,'audits','MATLAB_EVENTWISE_PARITY_v1.json');
write_json_new(outPath,audit);
end
function write_json_new(path,x)
assert(~isfile(path),'TRAINPair:NoOverwrite','Parity output already exists.');
fid=fopen(path,'w');assert(fid>=0,'TRAINPair:Write','Cannot write parity result.');
cleanup=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(x,'PrettyPrint',true) newline],'char');clear cleanup;
end
