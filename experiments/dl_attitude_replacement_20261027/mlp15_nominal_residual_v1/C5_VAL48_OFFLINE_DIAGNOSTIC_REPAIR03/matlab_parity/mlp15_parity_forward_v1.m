function residual = mlp15_parity_forward_v1(windowNormalized, model)
% Standalone MLP15 forward path; this function does not call a Plant or simulator.
required = {'fc1_weight','fc1_bias','fc2_weight','fc2_bias', ...
    'head_weight','head_bias','target_rms'};
assert(isstruct(model) && all(isfield(model,required)), ...
    'DLMLP:ForwardModel','Model is missing an MLP15 weight field.');
assert(isequal(size(windowNormalized),[13,15]) && ...
    all(isfinite(windowNormalized),'all'), ...
    'DLMLP:ForwardInput','Expected a finite normalized 13-by-15 input window.');

x = double(windowNormalized(:));
h = double(model.fc1_weight)*x + double(model.fc1_bias(:));
h = h ./ (1 + exp(-h));
h = double(model.fc2_weight)*h + double(model.fc2_bias(:));
h = h ./ (1 + exp(-h));
residual = (double(model.head_weight)*h + double(model.head_bias(:))) .* ...
    double(model.target_rms(:));
assert(numel(residual)==3 && all(isfinite(residual)), ...
    'DLMLP:ForwardOutput','MLP15 residual output is invalid.');
residual = residual(:);
end