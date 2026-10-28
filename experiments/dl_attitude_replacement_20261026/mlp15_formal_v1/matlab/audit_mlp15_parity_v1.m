function report=audit_mlp15_parity_v1(weightsPath,parityPath,reportPath)
% Plant-free MATLAB parity check for the frozen MLP15 export.
if nargin<1||isempty(weightsPath)
    root=fileparts(fileparts(mfilename('fullpath')));
    weightsPath=fullfile(root,'run_v1','mlp15_attitude_weights_v1.mat');
end
if nargin<2||isempty(parityPath)
    root=fileparts(fileparts(mfilename('fullpath')));
    parityPath=fullfile(root,'run_v1','parity_vector_v1.mat');
end
if nargin<3||isempty(reportPath)
    root=fileparts(fileparts(mfilename('fullpath')));
    reportPath=fullfile(root,'run_v1','MATLAB_PARITY_AUDIT_v1.json');
end
model=load(weightsPath);
vector=load(parityPath);
residual=mlp15_attitude_forward_v1(vector.input_normalized_window.',model);
expected=double(vector.expected_teacher_action_rad_s2(:));
maxError=max(abs(residual-expected));
report=struct('schema','DL1018_MLP15_MATLAB_PARITY_AUDIT_V1', ...
    'status','PASS','max_abs_error_rad_s2',maxError,'tolerance_rad_s2',1e-5, ...
    'plant_called',false,'test_data_read',false);
assert(maxError<=report.tolerance_rad_s2,'DLMLP:Parity', ...
    'MATLAB/PyTorch MLP15 parity exceeds tolerance.');
fid=fopen(reportPath,'w');assert(fid>=0,'DLMLP:Report','Cannot write parity report.');
cleanup=onCleanup(@()fclose(fid));
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');
fwrite(fid,newline,'char');
clear cleanup;
end
