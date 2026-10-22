function [opts, audit] = build_frozen_w0_options(cfg, model)
% Construct the OFF arm by changing exactly one option from the paired ON helper.
% The production runner keeps FEATURE forward/clipping/beta output; with updates
% disabled, its branch skips PCF s_eff coordination in the Head output/update law.
arguments
    cfg (1,1) struct
    model (1,1) struct
end

assert(strcmp(char(model.model_id), 'DSSM14') && ...
    strcmp(char(model.architecture), 'DSSM') && double(model.seed) == 2026102001 && ...
    double(model.selected_step) == 60000 && double(model.input_dim) == 14 && ...
    double(model.window) == 32 && double(model.context_length) == 32, ...
    'FROZENW0:ModelIdentity', 'Unexpected model package identity.');

W0 = double(model.output_W);
assert(isequal(size(W0), [33, 3]), 'FROZENW0:W0Shape', 'Expected W0 to be 33x3.');
assert(strcmpi(hash_bytes(typecast(W0(:), 'uint8')), ...
    '88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53'), ...
    'FROZENW0:W0Identity', 'W0 array content identity changed.');
normalizerIdentity = hash_normalizer_arrays(model);
assert(strcmpi(normalizerIdentity, ...
    '533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0'), ...
    'FROZENW0:NormalizerIdentity', 'Loaded model normalizer arrays changed.');

optsOn = position_only_search_options(cfg, model, 'FEATURE', 12, 1);
opts = optsOn;
opts.stage1_position_runtime.update_enabled = false; % The only experimental difference.
expected = optsOn;
expected.stage1_position_runtime.update_enabled = false;
assert(isequaln(opts, expected), 'FROZENW0:SingleFactor', ...
    'OFF options differ from ON outside update_enabled.');

p = opts.stage1_position_runtime;
h = p.position_only_search_head;
assert(logical(p.enabled) && logical(h.enabled) && strcmpi(char(h.head_type), 'FEATURE') && ...
    double(h.gamma) == 12 && double(h.kappa) == 1 && double(p.beta_scale) == 1 && ...
    isequal(double(p.weight), W0) && isequal(double(h.W0), W0), ...
    'FROZENW0:HeadContract', 'The FEATURE Head, W0, gamma/kappa, or beta contract changed.');
assert(logical(p.command_filter_coordination_v3_5.enabled), ...
    'FROZENW0:PCFDisabled', 'PCF must remain enabled.');
assert(logical(opts.formal_rbf_baseline) && logical(opts.rbf_attitude_enabled) && ...
    logical(opts.rbf_attitude_output_enabled) && logical(opts.rbf_attitude_update_enabled), ...
    'FROZENW0:BaselineAttitude', 'Formal B attitude RBF control changed.');
assert(abs(double(cfg.plant.dt) - 0.001) <= 1e-12 && ...
    double(cfg.rbf.runtime.position_update_hz) == 100, ...
    'FROZENW0:Clocks', 'Expected 1 kHz Plant and 100 Hz position events.');

audit = struct('experimental_difference', 'opts.stage1_position_runtime.update_enabled', ...
    'update_enabled', false, 'head_enabled', true, 'head_type', 'FEATURE', ...
    'gamma', 12, 'kappa', 1, 'beta_scale', 1, 'pcf_enabled', true, ...
    'normalizer_identity_sha256', normalizerIdentity, ...
    'W0_output_W_sha256', hash_bytes(typecast(W0(:), 'uint8')));
end

function h = hash_normalizer_arrays(model)
md = java.security.MessageDigest.getInstance('SHA-256');
for name = {'input_mu', 'input_sigma'}
    field = name{1};
    a = reshape(double(model.(field)), 1, []);
    assert(numel(a) == 14, 'FROZENW0:NormalizerShape', 'Expected fourteen %s values.', field);
    header = [field char(0) '((1, 14), ''float64'')' char(0)];
    md.update(typecast(uint8(unicode2native(header, 'UTF-8')), 'int8'));
    md.update(typecast(a(:), 'int8'));
end
h = lower(reshape(dec2hex(typecast(md.digest(), 'uint8'), 2).', 1, []));
end

function h = hash_bytes(bytes)
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(uint8(bytes(:)), 'int8'));
h = lower(reshape(dec2hex(typecast(md.digest(), 'uint8'), 2).', 1, []));
end
