function report=audit_mlp15_ghp7_balance_parity_v1()
% Plant-free parity check for the GHP7-balanced MLP15 export.
auditDir=fileparts(mfilename('fullpath'));taskRoot=fileparts(auditDir);
researchRoot=fileparts(taskRoot);
runtimeRoot=fullfile(researchRoot,'pilot_runner_mlp15_c5_full72_v1', ...
    'candidate_runner_work','matlab','runtime');
addpath(runtimeRoot);
runDir=fullfile(taskRoot,'runs','C5_MLP15_GHP7_BALANCE_SEED2026102001');
weightsPath=fullfile(runDir,'mlp15_attitude_weights_v1.mat');
vectorPath=fullfile(runDir,'parity_vector_v1.mat');
weights=load(weightsPath);vector=load(vectorPath);
raw=mlp15_attitude_forward_v1(vector.input_normalized_window.',weights);
expectedRaw=double(vector.expected_model_output_raw_rad_s2(:));
dmax=[45;45;4.7124];
clipped=min(max(raw,-dmax),dmax);
expectedClipped=double(vector.expected_runtime_output_clipped_rad_s2(:));
rawError=max(abs(raw-expectedRaw));
clippedError=max(abs(clipped-expectedClipped));
report=struct('schema','DL1018_MLP15_C5_GHP7_BALANCE_MATLAB_PARITY_V1', ...
    'status','PASS','max_abs_error_raw_rad_s2',rawError, ...
    'max_abs_error_runtime_clipped_rad_s2',clippedError, ...
    'tolerance_rad_s2',1e-5,'input_shape',[13,15], ...
    'plant_called',false,'TEST48_read',false, ...
    'expected_raw_field','expected_model_output_raw_rad_s2', ...
    'expected_clipped_field','expected_runtime_output_clipped_rad_s2');
assert(rawError<=report.tolerance_rad_s2,'DLMLP:ParityRaw', ...
    'MATLAB/PyTorch raw MLP15 output exceeds tolerance.');
assert(clippedError<=report.tolerance_rad_s2,'DLMLP:ParityClip', ...
    'MATLAB/PyTorch clipped MLP15 output exceeds tolerance.');
outPath=fullfile(auditDir,'MATLAB_PARITY_GHP7_BALANCE_v1.json');
fid=fopen(outPath,'w');assert(fid>=0,'DLMLP:ParityReport','Cannot write parity report.');
cleanup=onCleanup(@()fclose(fid));
fwrite(fid,[jsonencode(report,'PrettyPrint',true) newline],'char');
clear cleanup
end
