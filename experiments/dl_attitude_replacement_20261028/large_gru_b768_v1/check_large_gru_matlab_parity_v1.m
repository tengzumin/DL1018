projectRoot='C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018';
runDir=fullfile(projectRoot,'experiments','dl_attitude_replacement_20261028', ...
    'large_gru_b768_v1','runs','GRU13_B768_COSINE_S2026102001');
runtimeDir=fullfile(projectRoot,'experiments','dl_attitude_replacement_20261027', ...
    'mlp15_nominal_residual_v1','closed_loop_update_first_force09_v1', ...
    'candidate_runner_work','matlab','runtime');
addpath(runtimeDir);
fixture=load(fullfile(runDir,'MATLAB_PARITY_FIXTURE_v1.mat'));
model=load(fullfile(runDir,'gru_stream_large_b768_weights_v1.mat'));
required={'input_mean','input_std','target_rms','gru_weight_ih','gru_weight_hh', ...
    'gru_bias_ih','gru_bias_hh','head_weight','head_bias'};
assert(all(isfield(model,required)),'MATLAB parity MAT schema mismatch');
assert(isequal(size(model.gru_weight_ih),[96,13])&& ...
    isequal(size(model.gru_weight_hh),[96,32])&& ...
    isequal(size(model.head_weight),[3,32])&&numel(model.target_rms)==3, ...
    'MATLAB parity model shape mismatch');
assert(isequal(size(fixture.input_features_raw),[1999,13])&& ...
    fixture.event_count==1999,'Expected a 1999-event TRAIN fixture');
assert(max(abs(double(model.input_mean(:))-double(fixture.input_mean(:))))==0&& ...
    max(abs(double(model.input_std(:))-double(fixture.input_std(:))))==0&& ...
    max(abs(double(model.target_rms(:))-double(fixture.target_rms(:))))==0, ...
    'PT/MAT normalizer or feature order differs');
N=fixture.event_count; pred=zeros(N,3); hiddenTrace=zeros(N,32);
memory=[]; [memory,~]=gru_stream_attitude_step_v1('init',memory,[],model);
for k=1:N
    in=struct('feature',double(fixture.input_features_raw(k,:))', ...
        'J0',eye(3),'beta',1,'dmax',1e9*ones(3,1));
    [memory,out]=gru_stream_attitude_step_v1('step',memory,in,model);
    pred(k,:)=double(out.raw_residual_rad_s2(:))';
    hiddenTrace(k,:)=double(out.hidden_after(:))';
end
errPred=max(abs(pred(:)-double(fixture.expected_raw_output_pt(:))));
errHidden=max(abs(hiddenTrace(:)-double(fixture.expected_hidden_after_pt(:))));
if errPred>1e-3, error('MATLAB/PT output parity failed: %.9g',errPred); end
if errHidden>2e-4, error('MATLAB/PT hidden parity failed: %.9g',errHidden); end
% A new episode resets hidden to zero and must repeat the first event exactly.
memory=[]; [memory,~]=gru_stream_attitude_step_v1('init',memory,[],model);
in=struct('feature',double(fixture.input_features_raw(1,:))', ...
    'J0',eye(3),'beta',1,'dmax',1e9*ones(3,1));
[memory,resetOut]=gru_stream_attitude_step_v1('step',memory,in,model);
resetOutputError=max(abs(double(resetOut.raw_residual_rad_s2(:))'-pred(1,:)));
resetHiddenError=max(abs(double(memory.hidden(:))'-hiddenTrace(1,:)));
assert(resetOutputError==0&&resetHiddenError==0,'Scene reset/replay is not deterministic');
% No recurrent call during idle ticks means hidden is held, then resumes at event 2.
held=memory.hidden;
for idleTick=1:17 %#ok<NASGU>
    assert(isequal(memory.hidden,held),'Hidden changed while no event was processed');
end
in=struct('feature',double(fixture.input_features_raw(2,:))', ...
    'J0',eye(3),'beta',1,'dmax',1e9*ones(3,1));
[memory,nextOut]=gru_stream_attitude_step_v1('step',memory,in,model);
holdResumeError=max(abs(double(nextOut.raw_residual_rad_s2(:))'-pred(2,:)));
assert(holdResumeError<=1e-12,'Held hidden state did not resume at next event');
result=struct('status','PASS_MATLAB_PT_STREAM_PARITY', ...
    'train_episode_id',fixture.train_episode_id,'events',N, ...
    'max_abs_output_error',errPred,'max_abs_hidden_error',errHidden, ...
    'scene_reset_output_error',resetOutputError,'scene_reset_hidden_error',resetHiddenError, ...
    'idle_hold_resume_output_error',holdResumeError,'output_tolerance',1e-3, ...
    'hidden_tolerance',2e-4,'Plant_called',false,'training_started',false);
writeJson(fullfile(runDir,'MATLAB_PARITY_RESULT_v1.json'),result);
disp(jsonencode(result));
function writeJson(path,value)
fid=fopen(path,'w'); assert(fid>=0,'Cannot write parity result');
cleanup=onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char'); fwrite(fid,newline,'char');
end
