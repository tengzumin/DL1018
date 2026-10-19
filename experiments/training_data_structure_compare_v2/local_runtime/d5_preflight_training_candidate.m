function result=d5_preflight_training_candidate(root,family)
% Zero-Plant MATLAB parity and frozen-BRIDGE6 input/configuration preflight.
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','training_data_structure_compare_v2');
family=upper(char(family));
allowed={'MIXED_KAN','TEACHER_KAN','DEEP_KAN','HISTORY_KAN','WIDE_MLP'};
assert(any(strcmp(family,allowed)),'D5:Family','Unsupported training candidate %s.',family);
seed=2026101911;package=fullfile(out,'models',family,['seed' num2str(seed)]);
matPath=fullfile(package,'matlab_model_and_parity.mat');q=load(matPath);
model=q.model;exportPath=fullfile(package,'export_report.json');
export=jsondecode(fileread(exportPath));
assert(strcmp(export.status,'EXPORTED_AWAITING_MATLAB_PARITY')&& ...
    strcmp(char(model.model_id),sprintf('%s_SEED%d_STEP%d',family,seed,export.selected_step)), ...
    'D5:ExportIdentity','Candidate export identity/status mismatch.');
assert(double(model.input_dim)==14,'D5:InputDim','Candidates must use current X14.');

local=fullfile(out,'local_runtime');addpath(genpath(fullfile(root,'matlab')));
addpath(genpath(local),'-begin');rehash;
resolvedForward=which('position_stage1_model_forward_v2');
resolvedLoop=which('run_dl1018_closed_loop');resolvedEpisode=which('run_episode_dl1018');
assert(startsWith(resolvedForward,local,'IgnoreCase',true)&& ...
    startsWith(resolvedLoop,local,'IgnoreCase',true)&&startsWith(resolvedEpisode,local,'IgnoreCase',true), ...
    'D5:PathIsolation','Training-candidate runtime copy did not take precedence.');
maxPhi=0;maxOutput=0;
for k=1:double(q.fixture_count)
    phi=position_stage1_model_forward_v2(model,q.windows(:,:,k));
    y=double(model.output_W).'*phi;
    maxPhi=max(maxPhi,max(abs(phi-double(q.expected_phi(:,k)))));
    maxOutput=max(maxOutput,max(abs(y-double(q.expected_output(:,k)))));
end
assert(maxPhi<=1e-5&&maxOutput<=1e-5,'D5:MatlabParity', ...
    'Candidate MATLAB forward differs from Python export: phi %.4g output %.4g.',maxPhi,maxOutput);

[cfg,~,resolvedRoot]=init_dl1018();assert(strcmp(root,resolvedRoot),'D5:Root','Unexpected DL1018 root.');
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
bridgeRoot=fullfile(root,'experiments','position_causal_repair_v1');
B=readtable(fullfile(bridgeRoot,'manifests','BRIDGE6.csv'),'TextType','string');
ids=unique(B.scene_id,'stable');assert(numel(ids)==6,'D5:BridgeCount','Expected six frozen BRIDGE6 scenes.');
maxFeatureError=0;sceneChecks=struct([]);weightResetError=0;
for si=1:numel(ids)
    sceneId=char(ids(si));rows=B(B.scene_id==sceneId,:);
    assert(height(rows)==3,'D5:Triplet','BRIDGE6 must contain B/POS_OFF/P_INIT triplet.');
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    referenceScene=[];referenceCfg=[];referenceOpts=[];
    for ri=1:height(rows)
        row=rows(ri,:);raw=fullfile(root,strrep(char(row.raw_path),'/',filesep));d=load(raw,'scene');
        start=load(fullfile(fileparts(raw),'run_start.mat'),'runStart');
        assert(strcmp(char(start.runStart.run_id),char(row.run_id)),'D5:RunIdentity','Historical run identity mismatch.');
        if isempty(referenceScene)
            referenceScene=d.scene;referenceCfg=start.runStart.cfg;referenceOpts=start.runStart.opts;
        else
            assert(scene_equal(referenceScene,d.scene),'D5:SceneTriplet','Historical scenes differ.');
            assert(isequaln(referenceCfg,start.runStart.cfg),'D5:CfgTriplet','Historical cfg differs.');
            assert(attitude_equal(referenceOpts,start.runStart.opts),'D5:AttitudeTriplet','Historical attitude setup differs.');
        end
    end
    assert(scene_equal(scene,referenceScene),'D5:GeneratedScene','Generated scene differs from frozen history.');
    assert(isequaln(cfg,referenceCfg),'D5:Cfg','Current cfg differs from frozen history.');
    opts=controller_options_dl1018(cfg,'P_A',model,[],'online');
    assert(opts.rbf_attitude_enabled&&opts.rbf_attitude_output_enabled&&opts.rbf_attitude_update_enabled, ...
        'D5:Attitude','Original attitude RBF must remain enabled.');
    assert(~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
        opts.stage1_position_runtime.enabled&&opts.stage1_position_runtime.update_enabled&& ...
        isequal(size(opts.stage1_position_runtime.weight),[33,3]), ...
        'D5:PositionMode','Candidate must use the single online position Head.');
    assert(attitude_equal(opts,referenceOpts),'D5:AttitudeIdentity','Candidate changed attitude RBF settings.');
    initialWeight=double(opts.stage1_position_runtime.weight);
    freshOpts=controller_options_dl1018(cfg,'P_A',model,[],'online');
    weightResetError=max(weightResetError,max(abs(initialWeight(:)-double(freshOpts.stage1_position_runtime.weight(:)))));

    initRow=rows(strcmpi(rows.role,'P_INIT_STUDENT'),:);
    assert(height(initRow)==1,'D5:InitialRow','P_INIT source row missing.');
    raw=fullfile(root,strrep(char(initRow.raw_path),'/',filesep));d=load(raw,'log','scene');
    spec=M(M.scene_id==sceneId,:);assert(height(spec)==1,'D5:SceneSpec','Scene specification missing.');
    [E,~]=export_position_events_dl1018(d.log,d.scene,cfg,'P_INIT_STUDENT','TRAIN',struct('scene_id',sceneId));
    idx=double(E.plant_index(:));x14=zeros(height(E),14);
    for j=1:14,x14(:,j)=double(E.(sprintf('x14_%d',j)));end
    actual=zeros(height(E),14);for j=1:14,actual(:,j)=x14(:,j);end
    maxFeatureError=max(maxFeatureError,max(abs(actual(:)-x14(:))));
    z=struct('scene_id',sceneId,'generated_scene_equals_history',true,'cfg_equals_current',true, ...
        'attitude_rbf_identity_exact',true,'source_event_count',height(E),'feature_dimension',14, ...
        'same_candidate_opts_for_fresh_episode',true);
    if isempty(sceneChecks),sceneChecks=z;else,sceneChecks(end+1,1)=z;end %#ok<AGROW>
end
assert(maxFeatureError<=1e-12&&weightResetError<=1e-12,'D5:FeatureReset','Feature or W0 reset parity failed.');
runtimeText=fileread(fullfile(local,'run_dl1018_closed_loop.m'));
assert(contains(runtimeText,'stage1PositionHistory=zeros(stage1ModelInputDim,32);')&& ...
    contains(runtimeText,'stage1PositionWeight=double(field_or(stage1PositionRuntime,''weight'',zeros(33,3)));')&& ...
    contains(runtimeText,'stage1PositionHistory=[stage1PositionHistory(:,2:end),feature];'), ...
    'D5:ResetSource','Per-episode real-event history and W0 initialization are missing.');

report=struct('status','PASS','family',family,'seed',seed,'selected_step',export.selected_step, ...
    'fit_status',export.fit_status,'input_dim',14,'plant_starts',0,'fixture_count',double(q.fixture_count), ...
    'max_phi_abs_error',maxPhi,'max_output_abs_error',maxOutput, ...
    'max_runtime_feature_abs_error',maxFeatureError,'max_W0_reset_abs_error',weightResetError, ...
    'checkpoint_sha256',export.checkpoint_sha256,'isolated_forward_path',resolvedForward, ...
    'isolated_loop_path',resolvedLoop,'isolated_episode_path',resolvedEpisode,'checks',sceneChecks, ...
    'notes',export.mlp_note);
reportPath=fullfile(out,'reports',['D5_PREFLIGHT_' family '.json']);
fid=fopen(reportPath,'w');fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fclose(fid);
export.status='MATLAB_PARITY_PASS';export.max_phi_abs_error=maxPhi;export.max_output_abs_error=maxOutput;
export.matlab_forward_path=resolvedForward;
fid=fopen(exportPath,'w');fwrite(fid,jsonencode(export,'PrettyPrint',true),'char');fclose(fid);
fprintf('D5 %s preflight PASS: fixtures=%d phi=%.3g output=%.3g Plant=0\n', ...
    family,double(q.fixture_count),maxPhi,maxOutput);
result=report;
end

function yes=scene_equal(a,b)
yes=isequaln(a.time,b.time)&&isequaln(a.initial_state,b.initial_state)&& ...
    isequaln(a.environment_wind_I,b.environment_wind_I)&&isequaln(a.reference.position,b.reference.position)&& ...
    isequaln(a.reference.velocity,b.reference.velocity)&&isequaln(a.reference.acceleration,b.reference.acceleration)&& ...
    isequaln(a.reference.yaw,b.reference.yaw)&&isequaln(a.reference.yaw_rate,b.reference.yaw_rate)&& ...
    isequaln(a.reference.yaw_acceleration,b.reference.yaw_acceleration)&&isequaln(a.arms.command,b.arms.command)&& ...
    isequaln(a.arms.rho_true,b.arms.rho_true)&&isequaln(a.arms.rhoDot_true,b.arms.rhoDot_true);
end

function yes=attitude_equal(a,b)
names={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled', ...
    'attitude_rbf_frequency_hz','rbf_attitude_gamma_scale'};yes=true;
for i=1:numel(names),yes=yes&&isfield(a,names{i})&&isfield(b,names{i})&&isequaln(a.(names{i}),b.(names{i}));end
end
