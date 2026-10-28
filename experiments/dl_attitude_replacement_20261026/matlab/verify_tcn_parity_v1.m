function report=verify_tcn_parity_v1(trainingDir)
% Compare exported best PyTorch weights with the isolated MATLAB forward path.
if nargin<1,trainingDir=fullfile(fileparts(fileparts(mfilename('fullpath'))),'training_v1');end
inputPath=fullfile(trainingDir,'parity_vector_v1.mat');
modelPath=fullfile(trainingDir,'tcn_attitude_weights_v1.mat');
assert(isfile(inputPath)&&isfile(modelPath),'DLTCN:ParityFiles','Parity/model files are missing.');
S=load(inputPath,'input_normalized','expected_residual_rad_s2');
model=load(modelPath);actual=tcn_attitude_forward_v1(S.input_normalized,model);
expected=double(S.expected_residual_rad_s2(:));
delta=abs(actual-expected);maxAbs=max(delta);
report=struct('status','PASS','max_abs_error',maxAbs, ...
    'actual',actual(:).','expected',expected(:).','tolerance',1e-5);
assert(maxAbs<=report.tolerance,'DLTCN:Parity','Python/MATLAB parity failed: %.17g.',maxAbs);
disp(jsonencode(report));
end
