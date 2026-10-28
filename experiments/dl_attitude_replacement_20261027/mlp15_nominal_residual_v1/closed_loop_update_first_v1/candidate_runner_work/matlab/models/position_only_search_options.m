function opts=position_only_search_options(cfg,model,headType,gamma,kappa)
% Copy the exact P_A outer controller and replace only its position Head law.
headType=upper(char(headType));W0=double(model.output_W);
assert(isequal(size(W0),[33,3])&&ismember(headType,{'FEATURE','BIAS'}), ...
    'POSSEARCH:Options','Expected selected Final W0 and FEATURE/BIAS.');
opts=controller_options_dl1018(cfg,'P_A',model,[],'online');
p=opts.stage1_position_runtime;
if strcmp(headType,'FEATURE'),p.weight=kappa*W0;else,p.weight=W0;end
p.position_only_search_head=struct('enabled',true,'head_type',headType, ...
    'gamma',double(gamma),'kappa',double(kappa),'W0',W0, ...
    'state_reset_each_episode',true,'encoder_frozen',true);
opts.stage1_position_runtime=p;
end
