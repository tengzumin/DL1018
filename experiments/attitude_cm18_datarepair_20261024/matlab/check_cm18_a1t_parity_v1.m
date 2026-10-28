function result = check_cm18_a1t_parity_v1(repoRoot, deploymentPath, fixturePath, expectedDeploymentSha256, expectedFixtureSha256, expectedForwardSha256)
%CHECK_CM18_A1T_PARITY_V1 Check exported A1T weights with the frozen pure A1 forward.
% This is a read-only NumPy/MATLAB numerical parity check. It does not call an
% engine, Plant, training code, or any historical controller.

assert(nargin == 6, 'Pass repoRoot, deploymentPath, fixturePath, and three expected SHA256 values.');
repoRoot = char(repoRoot);
deploymentPath = local_resolve(repoRoot, deploymentPath);
fixturePath = local_resolve(repoRoot, fixturePath);
assert(isfile(deploymentPath) && isfile(fixturePath), 'Deployment or fixture file is missing.');

forwardRel = fullfile('experiments', 'attitude_cm18_a1_20261024', 'matlab', 'cm18_a1_forward_v1.m');
expectedForwardPath = fullfile(repoRoot, forwardRel);
actualForwardPath = which('cm18_a1_forward_v1');
assert(~isempty(actualForwardPath) && strcmpi(actualForwardPath, expectedForwardPath), ...
    'MATLAB resolved a different cm18_a1_forward_v1 source.');
forwardSha = local_sha256(actualForwardPath);
deploymentSha = local_sha256(deploymentPath);
fixtureSha = local_sha256(fixturePath);
assert(strcmpi(forwardSha, char(expectedForwardSha256)), 'Frozen MATLAB forward SHA mismatch.');
assert(strcmpi(deploymentSha, char(expectedDeploymentSha256)), 'Deployment parameter JSON SHA mismatch.');
assert(strcmpi(fixtureSha, char(expectedFixtureSha256)), 'Parity fixture JSON SHA mismatch.');

pjson = jsondecode(fileread(deploymentPath));
fixture = jsondecode(fileread(fixturePath));
assert(strcmp(pjson.schema, 'CM18_A1T_DEPLOYMENT_PARAMETERS_V1'), 'Unexpected A1T deployment schema.');
assert(strcmp(pjson.artifact_class, 'DO_NOT_GIT_UPLOAD'), 'Deployment export lacks the data-artifact marker.');
assert(strcmp(fixture.schema, 'CM18_A1T_MATLAB_PARITY_FIXTURE_V1'), 'Unexpected A1T parity fixture schema.');
assert(strcmp(fixture.status, 'PYTHON_PARITY_PASS_MATLAB_PARITY_PENDING'), ...
    'Fixture is not a completed Python parity fixture.');
assert(strcmpi(fixture.identity.deployment_parameters_sha256, deploymentSha), ...
    'Fixture is not bound to this deployment parameter JSON.');
assert(strcmpi(fixture.identity.matlab_forward_sha256, forwardSha), ...
    'Fixture MATLAB source identity differs from the resolved forward function.');
assert(fixture.case_count == 11 && numel(fixture.cases) == 11, ...
    'Expected exactly eleven fixed B/C5/synthetic parity rows.');
assert(strcmp(fixture.identity.B_cache.scene_id, 'DL1018_VAL_T2_C04_W14') && ...
       strcmp(fixture.identity.C5_cache.scene_id, 'DL1018_VAL_T2_C04_W14'), ...
       'Fixture does not use the fixed paired scene ID.');
assert(isequal(double(fixture.identity.indices_zero_based(:).'), [0 500 1000 1500 1998]), ...
    'Fixture event indices differ from the fixed selection.');

p = pjson.parameters;
required = {'W1','b1','W2','b2','W3','b3','input_mean','input_std','train_axis_rms_rad_s2'};
assert(all(isfield(p, required)), 'Deployment parameter fields are incomplete.');
assert(isequal(size(double(p.W1)), [32 18]) && numel(p.b1) == 32, 'W1/b1 shape mismatch.');
assert(isequal(size(double(p.W2)), [32 32]) && numel(p.b2) == 32, 'W2/b2 shape mismatch.');
assert(isequal(size(double(p.W3)), [24 32]) && numel(p.b3) == 24, 'W3/b3 shape mismatch.');
assert(numel(p.input_mean) == 18 && numel(p.input_std) == 18 && ...
       numel(p.train_axis_rms_rad_s2) == 3, 'Deployment normalizer shape mismatch.');

% The shared function is resolved explicitly above; no engine path is added here.
tol = double(fixture.tolerance_abs);
assert(isfinite(tol) && tol > 0 && tol <= 2e-12, 'Unexpected parity tolerance.');
maxErrors = struct('coefficients_3x8', 0, 'basis_8', 0, ...
    'normalized_output', 0, 'physical_output_rad_s2', 0);
sourceCounts = struct('B', 0, 'C5', 0, 'SYNTHETIC', 0);
	nonzeroBasisCounts = struct('B', 0, 'C5', 0, 'SYNTHETIC', 0);
zeroCaseCount = 0;

for k = 1:numel(fixture.cases)
    if iscell(fixture.cases)
        item = fixture.cases{k};
    else
        item = fixture.cases(k);
    end
    raw = reshape(double(item.raw_features_18), 1, []);
    assert(numel(raw) == 18 && all(isfinite(raw)), 'Raw feature row must be finite and length 18.');
    assert(isfield(sourceCounts, char(item.source_group)), 'Unexpected fixture source group.');
    sourceCounts.(char(item.source_group)) = sourceCounts.(char(item.source_group)) + 1;
    [physical, normalized, coefficients, basis] = cm18_a1_forward_v1(raw, p);
    if any(basis ~= 0)
        nonzeroBasisCounts.(char(item.source_group)) = nonzeroBasisCounts.(char(item.source_group)) + 1;
    end
    assert(isequal(size(physical), [1 3]) && isequal(size(normalized), [1 3]) && ...
           isequal(size(coefficients), [3 8]) && isequal(size(basis), [1 8]), ...
           'CM18 MATLAB forward output contract shape mismatch.');
    expected = item.expected;
    expectedPhysical = reshape(double(expected.physical_output_rad_s2), 1, []);
    expectedNormalized = reshape(double(expected.normalized_output), 1, []);
    expectedBasis = reshape(double(expected.basis_8), 1, []);
    expectedCoefficients = double(expected.coefficients_3x8);
    assert(isequal(size(expectedPhysical), [1 3]) && isequal(size(expectedNormalized), [1 3]) && ...
           isequal(size(expectedBasis), [1 8]) && isequal(size(expectedCoefficients), [3 8]), ...
           'Expected fixture output shape mismatch.');
    assert(all(isfinite(physical(:))) && all(isfinite(normalized(:))) && ...
           all(isfinite(coefficients(:))) && all(isfinite(basis(:))) && ...
           all(isfinite(expectedPhysical(:))) && all(isfinite(expectedNormalized(:))) && ...
           all(isfinite(expectedCoefficients(:))) && all(isfinite(expectedBasis(:))), ...
           'Non-finite output or expected fixture value.');
    e = struct();
    e.coefficients_3x8 = max(abs(coefficients(:) - expectedCoefficients(:)));
    e.basis_8 = max(abs(basis(:) - expectedBasis(:)));
    e.normalized_output = max(abs(normalized(:) - expectedNormalized(:)));
    e.physical_output_rad_s2 = max(abs(physical(:) - expectedPhysical(:)));
    names = fieldnames(e);
    for j = 1:numel(names)
        name = names{j};
        assert(isfinite(e.(name)) && e.(name) <= tol, ...
            'Python/MATLAB parity tolerance exceeded for %s.', name);
        maxErrors.(name) = max(maxErrors.(name), e.(name));
    end
    if item.synthetic_zero_basis
        zeroCaseCount = zeroCaseCount + 1;
        assert(strcmp(item.source_group, 'SYNTHETIC') && all(raw(8:15) == 0), ...
            'Synthetic zero-basis fixture must set raw u and z to zero.');
        assert(all(basis == 0) && all(normalized == 0) && ...
               isequal(physical, zeros(1,3)) && isequal(expectedPhysical, zeros(1,3)), ...
               'Zero-basis output must be exactly zero.');
    end
end
assert(sourceCounts.B == 5 && sourceCounts.C5 == 5 && sourceCounts.SYNTHETIC == 1 && zeroCaseCount == 1, ...
    'Fixture source-group counts differ from the fixed 5+5+1 design.');
assert(nonzeroBasisCounts.B >= 1 && nonzeroBasisCounts.C5 >= 1, ...
    'Both real B and C5 fixture groups must include nonzero basis inputs.');

result = struct('schema', 'CM18_A1T_MATLAB_PARITY_RESULT_V1', ...
    'status', 'PASS', 'deployment_sha256', deploymentSha, ...
    'fixture_sha256', fixtureSha, 'matlab_forward_sha256', forwardSha, ...
    'selected_step', fixture.identity.selected_step, ...
    'checkpoint_sha256', fixture.identity.checkpoint_sha256, ...
    'canonical_normalizer_float64_sha256', fixture.identity.canonical_normalizer_float64_sha256, ...
    'case_count', numel(fixture.cases), 'source_counts', sourceCounts, ...
    'nonzero_basis_counts', nonzeroBasisCounts, ...
    'max_abs_errors', maxErrors, 'tolerance_abs', tol, ...
    'zero_basis_exact_zero', true, 'engine_calls', 0, 'Plant_calls', 0, ...
    'optimizer_steps', 0, 'TEST_accessed', false);
end

function path = local_resolve(repoRoot, candidate)
candidate = char(candidate);
if isfile(candidate)
    path = candidate;
else
    path = fullfile(repoRoot, candidate);
end
end

function hex = local_sha256(path)
fid = fopen(path, 'rb');
assert(fid >= 0, 'Cannot open file for SHA256: %s', path);
closer = onCleanup(@() fclose(fid));
bytes = fread(fid, Inf, '*uint8');
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(bytes(:), 'int8'));
digest = typecast(md.digest(), 'uint8');
hex = lower(reshape(dec2hex(digest, 2).', 1, []));
end
