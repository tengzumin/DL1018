function report = audit_mlp15_c5_full72_parity_v1(weightsPath, parityPath, reportPath)
% Plant-free parity for the full72 final MLP15 export.
weights = load(weightsPath);
vector = load(parityPath);
raw = mlp15_attitude_forward_v1(vector.input_normalized_window.', weights);
expectedRaw = double(vector.expected_model_output_raw_rad_s2(:));
dmax = [45; 45; 4.7124];
clipped = min(max(raw, -dmax), dmax);
expectedClipped = double(vector.expected_runtime_output_clipped_rad_s2(:));
rawError = max(abs(raw - expectedRaw));
clippedError = max(abs(clipped - expectedClipped));
report = struct('schema', 'DL1018_MLP15_C5_FULL72_MATLAB_PARITY_V1', ...
    'status', 'PASS', 'max_abs_error_raw_rad_s2', rawError, ...
    'max_abs_error_runtime_clipped_rad_s2', clippedError, ...
    'tolerance_rad_s2', 1e-5, 'input_shape', [13, 15], ...
    'plant_called', false, 'test_data_read', false, ...
    'expected_raw_field', 'expected_model_output_raw_rad_s2', ...
    'expected_clipped_field', 'expected_runtime_output_clipped_rad_s2');
assert(rawError <= report.tolerance_rad_s2, 'DLMLP:ParityRaw', ...
    'MATLAB/PyTorch raw MLP15 output exceeds tolerance.');
assert(clippedError <= report.tolerance_rad_s2, 'DLMLP:ParityClip', ...
    'MATLAB/PyTorch clipped MLP15 output exceeds tolerance.');
fid = fopen(reportPath, 'w');
assert(fid >= 0, 'DLMLP:ParityReport', 'Cannot write parity report.');
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, jsonencode(report, 'PrettyPrint', true), 'char');
fwrite(fid, newline, 'char');
clear cleanup;
end
