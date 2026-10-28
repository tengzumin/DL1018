function residual=mlp15_attitude_forward_v1(windowNormalized,model)
% Causal 13-by-15 MLP15 inference; flatten event-major, feature-minor.
windowNormalized=double(windowNormalized);
required={'target_rms','fc1_weight','fc1_bias','fc2_weight','fc2_bias', ...
    'head_weight','head_bias'};
assert(isstruct(model)&&all(isfield(model,required))&& ...
    isequal(size(windowNormalized),[13,15])&&all(isfinite(windowNormalized),'all'), ...
    'DLMLP:ForwardInput','Expected a finite normalized 13-by-15 input window and MLP15 weights.');

x=windowNormalized(:);
z=double(model.fc1_weight)*x+double(model.fc1_bias(:));
z=z./(1+exp(-z));
z=double(model.fc2_weight)*z+double(model.fc2_bias(:));
z=z./(1+exp(-z));
residual=double(model.head_weight)*z+double(model.head_bias(:));
residual=residual.*double(model.target_rms(:));
assert(numel(residual)==3&&all(isfinite(residual)), ...
    'DLMLP:ForwardFinite','MLP15 output is invalid.');
residual=residual(:);
end
