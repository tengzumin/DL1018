function report=verify_tcn_teacher_parity_v2(trainingDir)
% Verify exported PyTorch teacher-action output with the MATLAB forward path.
here=fileparts(mfilename('fullpath'));
if nargin<1,trainingDir=fullfile(fileparts(here),'training_v2_teacher_distill');end
addpath(here);
inputPath=fullfile(trainingDir,'parity_vector_v2.mat');
modelPath=fullfile(trainingDir,'tcn_attitude_weights_v2.mat');
assert(isfile(inputPath)&&isfile(modelPath),'DLTCN:ParityFiles','Parity/model files are missing.');
S=load(inputPath,'input_normalized','expected_teacher_rbf_output_rad_s2');
model=load(modelPath);actual=tcn_attitude_forward_v1(S.input_normalized,model);
expected=double(S.expected_teacher_rbf_output_rad_s2(:));
maxAbs=max(abs(actual-expected));
report=struct('schema','DL1018_CAUSAL_TCN_PYTHON_MATLAB_PARITY_V2', ...
    'status','PASS','max_abs_error',maxAbs,'actual_teacher_action_rad_s2',actual(:).', ...
    'expected_teacher_action_rad_s2',expected(:).','tolerance',1e-5, ...
    'test_data_read',false,'plant_called',false);
assert(maxAbs<=report.tolerance,'DLTCN:Parity','Python/MATLAB parity failed: %.17g.',maxAbs);
outPath=fullfile(trainingDir,'MATLAB_PYTHON_PARITY_V2.json');
fid=fopen(outPath,'w');
assert(fid>=0,'DLTCN:ParityOutput','Could not create parity report.');
cleanup=onCleanup(@()fclose(fid));
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');
fwrite(fid,newline,'char');
disp(jsonencode(report));
end
