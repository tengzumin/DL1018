function result = check_cm18_a2_parity_v1(fixture_path, result_path)
%CHECK_CM18_A2_PARITY_V1 Check one new synthetic fixture result; no Plant.
assert(nargin == 2, 'Pass fixture_path and a new result_path.');
fixture_path = char(java.io.File(char(fixture_path)).getCanonicalPath());
result_path = char(java.io.File(char(result_path)).getCanonicalPath());
assert(exist(fixture_path, 'file') == 2, 'Fixture file does not exist.');
assert(exist(result_path, 'file') == 0, 'Refusing to overwrite MATLAB result.');
fixture = jsondecode(fileread(fixture_path));
assert(strcmp(fixture.schema, 'CM18_A2_PARITY_FIXTURE_V1'), 'Unexpected fixture schema.');
p = fixture.parameters;
tol = double(fixture.tolerance_abs);
[y, yn, c, basis, details] = cm18_a2_forward_v1(fixture.raw_features, p);
e = fixture.expected;
assert(isequal(size(y), [1,3]) && isequal(size(yn), [1,3]), 'A2 output must be 1-by-3.');
assert(isequal(size(c), [3,8]), 'A2 coefficients must be 3-by-8.');
assert(isequal(size(basis), [1,8]), 'A2 morphology basis must be 1-by-8.');
local_close(y, reshape(e.physical_output_rad_s2, 1, 3), tol, 'A2 physical output');
local_close(yn, reshape(e.normalized_output, 1, 3), tol, 'A2 normalized output');
local_close(c, reshape(e.coefficients_3x8, 3, 8), tol, 'A2 merged coefficients');
local_close(basis, reshape(e.basis_8, 1, 8), tol, 'morphology basis');
local_close(details.yaw_masked_raw_features, reshape(e.yaw_masked_raw_features, 1, 18), 0, 'raw zero mask');
local_close(details.yaw_masked_normalized_features, reshape(e.yaw_masked_normalized_features, 1, 18), tol, 'normalized masked features');
a1_expected = reshape(e.a1_full_physical_output_rad_s2, 1, 3);
local_close(y(1:2), a1_expected(1:2), tol, 'A1 roll/pitch parity');

[yp, ~, ~, ~] = cm18_a2_forward_v1(fixture.perturbed_alphaBS_features, p);
perturbed_expected = reshape(e.perturbed_physical_output_rad_s2, 1, 3);
local_close(y(3), perturbed_expected(3), tol, 'perturbed fixture yaw');
local_close(y(3), yp(3), 0, 'yaw alphaBS invariance');
[yz, ~, ~, ~] = cm18_a2_forward_v1(fixture.zero_basis_features, p);
local_close(yz, zeros(1,3), 0, 'zero basis output');

forward_path = which('cm18_a2_forward_v1');
assert(~isempty(forward_path), 'Cannot resolve cm18_a2_forward_v1 source.');
check_path = [mfilename('fullpath'), '.m'];
result = struct('schema', 'CM18_A2_MATLAB_PARITY_RESULT_V1', ...
    'status', 'PASS', 'fixture_schema', fixture.schema, ...
    'yaw_alphaBS_invariance', true, 'zero_basis_exact_zero', true, ...
    'roll_pitch_matches_a1_fixture', true, 'output_shape', [1,3], ...
    'coefficient_shape', [3,8], 'basis_shape', [1,8], ...
    'fixture_path', fixture_path, 'fixture_sha256', sha256_file(fixture_path), ...
    'forward_source_path', forward_path, 'forward_source_sha256', sha256_file(forward_path), ...
    'check_source_path', check_path, 'check_source_sha256', sha256_file(check_path), ...
    'plant_calls', 0, 'optimizer_steps', 0);
fid = fopen(result_path, 'w');
assert(fid >= 0, 'Cannot create new MATLAB result file.');
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, jsonencode(result, 'PrettyPrint', true), 'char');
fwrite(fid, newline, 'char');
end

function local_close(actual, expected, tolerance, label)
actual = double(actual); expected = double(expected);
assert(isequal(size(actual), size(expected)), '%s shape mismatch.', label);
assert(all(isfinite(actual(:))) && all(isfinite(expected(:))), '%s contains non-finite values.', label);
delta = max(abs(actual(:) - expected(:)));
assert(isfinite(delta) && delta <= tolerance, '%s differs by %.17g (tolerance %.17g).', label, delta, tolerance);
end

function value = sha256_file(path)
fid = fopen(path, 'rb');
assert(fid >= 0, 'Cannot read source for SHA256: %s', path);
cleanup = onCleanup(@() fclose(fid));
bytes = fread(fid, Inf, '*uint8');
digest = java.security.MessageDigest.getInstance('SHA-256');
digest.update(typecast(bytes(:), 'int8'));
value = lower(reshape(dec2hex(typecast(digest.digest(), 'uint8'), 2).', 1, []));
end
