function [physical_output, normalized_output, coefficients, basis] = cm18_a1_forward_v1(raw_features, p)
%CM18_A1_FORWARD_V1 Pure CM18-A1 inference, with no online state or updates.
% Input order: omega_B(3), alpha_BS(3), thrust/mass(1), u(4), z(4), a(3).
% Python flattens the final 3-by-8 coefficient matrix in row-major order;
% reshape(flat,8,3).' preserves that same order in MATLAB.

required = {'W1','b1','W2','b2','W3','b3','input_mean','input_std', ...
    'train_axis_rms_rad_s2'};
assert(isstruct(p) && all(isfield(p, required)), 'Missing CM18-A1 parameter fields.');

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
assert(numel(mu) == 18 && numel(sigma) == 18, 'Invalid input normalizer shape.');
assert(numel(axis_rms) == 3, 'Invalid TRAIN target scale shape.');
assert(all(isfinite(W1(:))) && all(isfinite(b1)) && ...
       all(isfinite(W2(:))) && all(isfinite(b2)) && ...
       all(isfinite(W3(:))) && all(isfinite(b3)) && ...
       all(isfinite(mu)) && all(isfinite(sigma)) && all(isfinite(axis_rms)), ...
       'CM18-A1 parameters must be finite.');
assert(all(sigma >= 1e-6) && all(axis_rms > 0), 'Invalid normalization scales.');

x_norm = (x - mu) ./ sigma;
assert(all(isfinite(x_norm)), 'Normalized input contains non-finite values.');
h1 = tanh(W1 * x_norm.' + b1);
h2 = tanh(W2 * h1 + b2);
flat_coefficients = (W3 * h2 + b3).';
coefficients = reshape(flat_coefficients, 8, 3).';
assert(all(isfinite(coefficients(:))), 'Coefficient matrix contains non-finite values.');

u = x(8:11);
z = x(12:15);
basis = [z ./ 2, u];
assert(all(isfinite(basis)), 'Morphology basis contains non-finite values.');
normalized_output = (coefficients * basis.').';
assert(all(isfinite(normalized_output)), 'Normalized output contains non-finite values.');
physical_output = normalized_output .* axis_rms;
assert(all(isfinite(physical_output)), 'Physical output contains non-finite values.');
end
