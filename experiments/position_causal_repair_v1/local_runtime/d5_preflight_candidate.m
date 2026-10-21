function result=d5_preflight_candidate(root,candidate)
% Zero-Plant parity/config/runtime-input preflight for one frozen D4 canary.
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','position_causal_repair_v1');
candidate=upper(char(candidate));assert(any(strcmp(candidate,{'C1','C2'})),'D5:Candidate','Candidate must be C1 or C2.');
if strcmp(candidate,'C1'),family='C1_X20_FIXED_INFORMATION';else,family='C2_X14_ADAPTATION_AWARE';end
seed=2026101901;package=fullfile(out,'models',family,['seed' num2str(seed)]);
matPath=fullfile(package,'matlab_model_and_parity.mat');q=load(matPath);
exportPath=fullfile(package,'export_report.json');export=jsondecode(fileread(exportPath));
model=q.model;dim=double(model.input_dim);assert(dim==14+6*strcmp(candidate,'C1'),'D5:InputDim','Candidate input dimension mismatch.');
assert(strcmp(export.status,'EXPORTED_AWAITING_MATLAB_PARITY')&&strcmp(char(model.model_id),[family '_SEED' num2str(seed)]), ...
    'D5:ExportIdentity','Candidate export identity/status mismatch.');
local=fullfile(out,'local_runtime');addpath(genpath(fullfile(root,'matlab')));addpath(genpath(local),'-begin');rehash;
resolvedForward=which('position_stage1_model_forward_v2');resolvedLoop=which('run_dl1018_closed_loop');
assert(startsWith(resolvedForward,local,'IgnoreCase',true)&&startsWith(resolvedLoop,local,'IgnoreCase',true), ...
    'D5:PathIsolation','The candidate-only MATLAB runtime copy did not take precedence.');
maxPhi=0;maxOutput=0;
for k=1:double(q.fixture_count)
    phi=position_stage1_model_forward_v2(model,q.windows(:,:,k));
    y=double(model.output_W).'*phi;
    maxPhi=max(maxPhi,max(abs(phi-double(q.expected_phi(:,k)))));
    maxOutput=max(maxOutput,max(abs(y-double(q.expected_output(:,k)))));
end
assert(maxPhi<=1e-5&&maxOutput<=1e-5,'D5:MatlabParity','Candidate MATLAB forward differs from Python export.');

[cfg,~,resolvedRoot]=init_dl1018();assert(strcmp(root,resolvedRoot),'D5:Root','Unexpected DL1018 root.');
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
B=readtable(fullfile(out,'manifests','BRIDGE6.csv'),'TextType','string');
ids=unique(B.scene_id,'stable');assert(numel(ids)==6,'D5:BridgeCount','Expected exactly six frozen BRIDGE6 scenes.');
maxFeatureError=0;sceneChecks=struct([]);weightResetError=0;
for si=1:numel(ids)
    sceneId=char(ids(si));rows=B(B.scene_id==sceneId,:);assert(height(rows)==3,'D5:Triplet','BRIDGE6 must contain B/POS_OFF/P_INIT triplet.');
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    referenceScene=[];referenceCfg=[];referenceOpts=[];
    for ri=1:height(rows)
        row=rows(ri,:);raw=fullfile(root,strrep(char(row.raw_path),'/',filesep));d=load(raw,'scene');
        start=load(fullfile(fileparts(raw),'run_start.mat'),'runStart');
        assert(strcmp(char(start.runStart.run_id),char(row.run_id)),'D5:RunIdentity','Historical run_start identity mismatch.');
        if isempty(referenceScene)
            referenceScene=d.scene;referenceCfg=start.runStart.cfg;referenceOpts=start.runStart.opts;
        else
            assert(scene_equal(referenceScene,d.scene),'D5:SceneTriplet','Historical triplet scene mismatch.');
            assert(isequaln(referenceCfg,start.runStart.cfg),'D5:CfgTriplet','Historical triplet cfg mismatch.');
            assert(attitude_equal(referenceOpts,start.runStart.opts),'D5:AttitudeTriplet','Historical attitude setup mismatch.');
        end
    end
    assert(scene_equal(scene,referenceScene),'D5:GeneratedScene','Generated scene differs from frozen historical triplet.');
    assert(isequaln(cfg,referenceCfg),'D5:Cfg','Frozen cfg differs from current runner cfg.');
    opts=controller_options_dl1018(cfg,'P_A',model,[],'online');
    assert(opts.rbf_attitude_enabled&&opts.rbf_attitude_output_enabled&&opts.rbf_attitude_update_enabled, ...
        'D5:Attitude','Original attitude RBF must remain enabled.');
    assert(~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
        opts.stage1_position_runtime.enabled&&opts.stage1_position_runtime.update_enabled&& ...
        isequal(size(opts.stage1_position_runtime.weight),[33,3]),'D5:PositionMode','P_A candidate position mode is invalid.');
    assert(attitude_equal(opts,referenceOpts),'D5:AttitudeIdentity','Candidate changed the original attitude RBF settings.');
    initialWeight=double(opts.stage1_position_runtime.weight);
    freshOpts=controller_options_dl1018(cfg,'P_A',model,[],'online');
    freshWeight=double(freshOpts.stage1_position_runtime.weight);
    weightResetError=max(weightResetError,max(abs(initialWeight(:)-freshWeight(:))));

    initRow=rows(strcmpi(rows.role,'P_INIT_STUDENT'),:);assert(height(initRow)==1,'D5:InitialRow','P_INIT source row missing.');
    raw=fullfile(root,strrep(char(initRow.raw_path),'/',filesep));d=load(raw,'log','scene');
    spec=M(M.scene_id==sceneId,:);assert(height(spec)==1,'D5:SceneSpec','Scene specification missing.');
    [E,~]=export_position_events_dl1018(d.log,d.scene,cfg,'P_INIT_STUDENT','TRAIN',struct('scene_id',sceneId));
    idx=double(E.plant_index(:));x14=zeros(height(E),14);
    for j=1:14,x14(:,j)=double(E.(sprintf('x14_%d',j)));end
    velocity=double(d.log.state(idx,4:6));nominal=double(d.log.position_nominal_acceleration_mps2(idx,:));
    actual=zeros(height(E),dim);
    for j=1:height(E)
        if dim==20,actual(j,:)=[x14(j,:),velocity(j,:),nominal(j,:)];else,actual(j,:)=x14(j,:);end
    end
    if dim==20,expected=[x14,velocity,nominal];else,expected=x14;end
    maxFeatureError=max(maxFeatureError,max(abs(actual(:)-expected(:))));
    z=struct('scene_id',sceneId,'generated_scene_equals_history',true,'cfg_equals_current',true, ...
        'attitude_rbf_identity_exact',true,'source_event_count',height(E), ...
        'feature_dimension',dim,'same_candidate_opts_for_fresh_episode',true);
    if isempty(sceneChecks),sceneChecks=z;else,sceneChecks(end+1,1)=z;end %#ok<AGROW>
end
assert(maxFeatureError<=1e-12&&weightResetError<=1e-12,'D5:FeatureReset','Candidate feature or W0 reset parity failed.');
runtimeText=fileread(fullfile(local,'run_dl1018_closed_loop.m'));
assert(contains(runtimeText,'stage1PositionHistory=zeros(stage1ModelInputDim,32);')&& ...
    contains(runtimeText,'stage1PositionWeight=double(field_or(stage1PositionRuntime,''weight'',zeros(33,3)));')&& ...
    contains(runtimeText,'x(k,4:6).'';stage1Preview.nominal_acceleration(:)'), ...
    'D5:ResetSource','Per-episode history/weight initialization is missing in isolated runtime.');

report=struct('status','PASS','candidate',candidate,'family',family,'seed',seed,'input_dim',dim, ...
    'plant_starts',0,'fixture_count',double(q.fixture_count),'max_phi_abs_error',maxPhi, ...
    'max_output_abs_error',maxOutput,'max_runtime_feature_abs_error',maxFeatureError, ...
    'max_W0_reset_abs_error',weightResetError,'checkpoint_sha256',export.checkpoint_sha256, ...
    'isolated_forward_path',resolvedForward, ...
    'isolated_loop_path',resolvedLoop,'checks',sceneChecks, ...
    'notes','Original B, attitude RBF, PCF update, beta, clip, Plant, and safety path retained; X20 only appends current v_I and nominal acceleration.');
reportPath=fullfile(out,'reports',['D5_PREFLIGHT_' candidate '.json']);
fid=fopen(reportPath,'w');fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fclose(fid);
export.status='MATLAB_PARITY_PASS';export.max_phi_abs_error=maxPhi;export.max_output_abs_error=maxOutput;
export.matlab_forward_path=resolvedForward;
fid=fopen(exportPath,'w');fwrite(fid,jsonencode(export,'PrettyPrint',true),'char');fclose(fid);
fprintf('D5 %s preflight PASS: dim=%d fixtures=%d phi=%.3g output=%.3g feature=%.3g Plant=0\n', ...
    candidate,dim,double(q.fixture_count),maxPhi,maxOutput,maxFeatureError);
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
