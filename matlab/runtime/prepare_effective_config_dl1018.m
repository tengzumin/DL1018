function configPath=prepare_effective_config_dl1018(sourceRoot,projectRoot)
% One-time migration extractor: read cfg only and save a self-contained copy.
sourceRoot=char(java.io.File(sourceRoot).getCanonicalPath());
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
configPath=fullfile(projectRoot,'configs','effective_config.mat');
if isfile(configPath),return;end
effectiveSource=fullfile(sourceRoot,'RBF-BS0','experiments', ...
    'multitask_retrain_v311','cf_shared_retrain_r2e','configs','R2E_EFFECTIVE_CONFIG.mat');
if isfile(effectiveSource)
    loaded=load(effectiveSource,'cfgEffective');
    assert(isfield(loaded,'cfgEffective')&&isstruct(loaded.cfgEffective), ...
        'DL1018:SourceEffectiveConfig','R2E_EFFECTIVE_CONFIG.mat does not contain cfgEffective.');
    cfg=loaded.cfgEffective;
else
    runStart=fullfile(sourceRoot,'RBF-BS0','experiments','x23_head_v38','runs', ...
        'canary','attempt_6ac495b3-a44c-4564-ac6a-1d76221e4287','run_start.mat');
    assert(isfile(runStart),'DL1018:SourceConfigMissing', ...
        'Neither the R2E effective cfg nor the pinned run_start cfg exists.');
    loaded=load(runStart,'cfg');
    assert(isfield(loaded,'cfg')&&isstruct(loaded.cfg), ...
        'DL1018:SourceConfigInvalid','Pinned run_start does not contain cfg.');
    cfg=loaded.cfg;
end
assert(abs(cfg.plant.mass-.695)<=1e-12&&abs(cfg.plant.dt-.001)<=1e-12&& ...
    strcmpi(cfg.plant.mass_model,'distributed_v1'), ...
    'DL1018:SourcePlantConflict','Source physical cfg conflicts with the pinned contract.');
cfg.name='DL1018_V311_R2E_PAPER_FINAL';
cfg.mass_model='distributed_v1';cfg.plant.mass_model='distributed_v1';
cfg.control.morphology_mode='fixed';cfg.controller_morphology_mode='fixed';
cfg.controller_inertia_derivative_mode='full';
cfg.control.command_filter.acceleration_limit=[Inf;Inf;6];
cfg.rbf.runtime=struct('position_update_hz',100,'attitude_update_hz',100);
text=evalc('disp(cfg)');assert(~contains(text,'DL1009','IgnoreCase',true), ...
    'DL1018:ConfigLegacyPath','Effective cfg contains a legacy path.');
folder=fileparts(configPath);if ~isfolder(folder),mkdir(folder);end
assert(~isfile(configPath),'DL1018:ConfigOverwrite','Refusing to replace an existing effective config.');
save(configPath,'cfg','-v7');
end
