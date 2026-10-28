function [physical_output, normalized_output, coefficients, basis, details] = cm18_a2_forward_v1(raw_features, p)
%CM18_A2_FORWARD_V1 Shared CM18 forward with raw-zero alphaBS for yaw only.
% Full-input coefficients supply roll/pitch. The shared network is run again
% after raw columns 4:5 are set to zero; that branch supplies yaw.
required = {'W1','b1','W2','b2','W3','b3','input_mean','input_std', ...
    'train_axis_rms_rad_s2'};
assert(isstruct(p) && all(isfield(p, required)), 'Missing CM18-A2 parameter fields.');
x = reshape(double(raw_features), 1, []);
assert(numel(x) == 18 && all(isfinite(x)), 'raw_features must be finite and length 18.');

W1 = double(p.W1); b1 = reshape(double(p.b1), [], 1);
W2 = double(p.W2); b2 = reshape(double(p.b2), [], 1);
W3 = double(p.W3); b3 = reshape(double(p.b3), [], 1);
mu = reshape(double(p.input_mean), 1, []);
sigma = reshape(double(p.input_std), 1, []);
axis_rms = reshape(double(p.train_axis_rms_rad_s2), 1, []);
assert(isequal(size(W1), [32,18]) && numel(b1) == 32, 'Invalid first layer shape.');
assert(isequal(size(W2), [32,32]) && numel(b2) == 32, 'Invalid second layer shape.');
assert(isequal(size(W3), [24,32]) && numel(b3) == 24, 'Invalid coefficient layer shape.');
assert(numel(mu) == 18 && numel(sigma) == 18 && numel(axis_rms) == 3, 'Invalid scale shape.');
assert(all(isfinite([W1(:);b1;W2(:);b2;W3(:);b3;mu(:);sigma(:);axis_rms(:)])), ...
    'CM18-A2 parameters must be finite.');
assert(all(sigma >= 1e-6) && all(axis_rms > 0), 'Invalid normalization scales.');

[full_coefficients, full_normalized] = local_coefficients(x, W1,b1,W2,b2,W3,b3,mu,sigma);
yaw_raw = x;
yaw_raw(4:5) = 0.0;
[yaw_coefficients, yaw_normalized] = local_coefficients(yaw_raw, W1,b1,W2,b2,W3,b3,mu,sigma);
coefficients = full_coefficients;
coefficients(3,:) = yaw_coefficients(3,:);
basis = [x(12:15) ./ 2, x(8:11)];
normalized_output = (coefficients * basis.').';
physical_output = normalized_output .* axis_rms;
assert(isequal(size(coefficients), [3,8]) && isequal(size(basis), [1,8]), ...
    'CM18-A2 coefficient or basis shape mismatch.');
assert(isequal(size(normalized_output), [1,3]) && isequal(size(physical_output), [1,3]), ...
    'CM18-A2 output must be a 1-by-3 row.');
assert(all(isfinite([full_normalized(:);yaw_normalized(:);coefficients(:);basis(:); ...
    normalized_output(:);physical_output(:)])), 'CM18-A2 output contains non-finite values.');
details = struct('full_coefficients_3x8', full_coefficients, ...
    'yaw_masked_coefficients_3x8', yaw_coefficients, ...
    'full_normalized_features', full_normalized, ...
    'yaw_masked_raw_features', yaw_raw, ...
    'yaw_masked_normalized_features', yaw_normalized);
end

function [coefficients, normalized] = local_coefficients(x,W1,b1,W2,b2,W3,b3,mu,sigma)
normalized = (x - mu) ./ sigma;
h1 = tanh(W1 * normalized.' + b1);
h2 = tanh(W2 * h1 + b2);
flat = (W3 * h2 + b3).';
coefficients = reshape(flat, 8, 3).';
assert(all(isfinite(normalized)) && all(isfinite(coefficients(:))), ...
    'CM18-A2 coefficient branch produced non-finite values.');
end
