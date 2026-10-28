function audit=audit_c5_r_task_binding_no_plant_v1()
taskRoot=fileparts(mfilename('fullpath'));
projectRoot=fileparts(fileparts(fileparts(taskRoot)));
runtime=fullfile(taskRoot,'candidate_runner_work','matlab','runtime');
runnerRoot=activate_from(runtime);
builderDir=fullfile(taskRoot,'scene_builder_work');
bRunner=fullfile(taskRoot,'b_runner_work');
addpath(builderDir);addpath(bRunner);
assert(nargin('run_gate_holdout_closed_loop')==3&& ...
    nargin('gate_holdout_validate_scene')==3&&nargin('run_b_frozen_gate')==1&& ...
    nargin('validate_b_gate_scene_no_plant')==1&&nargin('build_gate_inspection_scenes')==-2&& ...
    nargin('prepare_gate_candidate_no_plant')==3&&nargin('run_candidate_gate_attempt')==4, ...
    'GATE:Entrypoints','No-Plant entrypoint syntax or arity check failed.');
selfcheck=build_gate_inspection_scenes('SELF_CHECK');
assert(strcmp(selfcheck.status,'PASS_NO_PLANT_STATIC_SELF_CHECK')&& ...
    selfcheck.plant_calls==0&&~selfcheck.holdout_payloads_generated, ...
    'GATE:SelfCheck','Scene builder static self-check failed.');
receiptPath=fullfile(taskRoot,'C5_R_TASK_BINDING_PILOT_RECEIPT_v3.json');
receipt=jsondecode(fileread(receiptPath));
assert(strcmp(receipt.status,'PASS_NO_PLANT_PILOT_PAYLOADS_ONLY')&& ...
    receipt.plant_calls==0&&~receipt.pilot_started&&~receipt.holdout_payloads_generated&& ...
    receipt.scene_count==18&&numel(receipt.scenes)==18, ...
    'GATE:Receipt','Binder receipt is not an 18-payload no-Plant receipt.');
snapshotPath=fullfile(projectRoot,'experiments','position_axis_coordinate_c5_dev72_20261023', ...
    'C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
snapshot=load(snapshotPath,'cfg');
activeCfg=geometry_cfg(snapshot.cfg,'ACTIVE');
Pplant=simulation_parameters(activeCfg,activeCfg.plant.arm_initial,zeros(4,1));
Ptask=controller_parameters(activeCfg,Pplant,'fixed');
assert(strcmpi(json_sha256(activeCfg),receipt.C5_nominal_task.cfg_sha256), ...
    'GATE:CfgSha','Receipt C5 ACTIVE cfg hash differs from locked snapshot.');
refRoot=fileparts(projectRoot);
modelPath=fullfile(refRoot,'REFERENCE_FIX_FULL72_20261021_022342_313', ...
    'corrected_reference_training_v1','corrected_pair_training','models','DSSM14','matlab_model_and_parity.mat');
modelPack=load(modelPath,'model');model=modelPack.model;
armIds={'C5_RBF','C5_RBF_F','C5_00','C5_10','C5_01','C5_11'};
modes={'ACTIVE','FIXED_MIN','FIXED_BOUND15'};
optionHashes=cell(0,1);armSpecs=cell(0,1);
for m=1:numel(modes)
    cfgMode=geometry_cfg(snapshot.cfg,modes{m});
    if strcmp(modes{m},'ACTIVE'),thisArmIds=armIds;else,thisArmIds={'C5_11'};end
    for a=1:numel(thisArmIds)
        spec=gate_attitude_arm_spec(thisArmIds{a});
        armSpecs{end+1,1}=spec; %#ok<AGROW>
        armOpts=make_gate_holdout_options(cfgMode,model,thisArmIds{a},modes{m},struct);
        hashes=gate_holdout_identity_hashes(cfgMode,model,armOpts);
        optionHashes{end+1,1}=hashes.common.position_options_sha256; %#ok<AGROW>
    end
end
assert(all(strcmp(optionHashes,optionHashes{1}))&& ...
    strcmpi(optionHashes{1},receipt.common_position_options_sha256), ...
    'GATE:CommonPosition','Common C5 position options hash differs across arms or receipt.');
rbfF=gate_attitude_arm_spec('C5_RBF_F');
assert(rbfF.rbf_enabled&&rbfF.feedforward_enabled&&~rbfF.observer_enabled&& ...
    armSpecs{1}.rbf_enabled&&armSpecs{1}.feedforward_enabled==false, ...
    'GATE:RbfFeedforward','RBF+F must retain RBF while adding only common physics feedforward.');
csvPath=fullfile(taskRoot,'scene_builder_work','gate_scene_id_seed_manifest_v1_DRAFT.csv');
manifest=readtable(csvPath,'TextType','string');
assert(height(manifest)==54&&sum(manifest.role=="GHP6")==6&&sum(manifest.role=="GH48")==48, ...
    'GATE:Manifest','ID/seed manifest counts differ.');
assert(numel(receipt.scenes)==18,'GATE:PilotCount','Expected 18 geometry-specific pilot payloads.');
rows=repmat(struct('scene_id','','seed',0,'geometry_arm','','payload_sha256','', ...
    'r_task_sha256','','reconstruction_max_abs_error',0,'candidate_validator','PASS', ...
    'b_validator','PASS'),1,18);
taskHashByScene=containers.Map('KeyType','char','ValueType','char');
for i=1:18
    row=receipt.scenes(i);mode=char(row.geometry_arm);
    hit=find(manifest.scene_id==string(row.scene_id));
    assert(numel(hit)==1&&manifest.role(hit)=="GHP6"&&double(manifest.seed(hit))==double(row.seed), ...
        'GATE:PilotIdentity','Pilot ID/seed differs from frozen draft manifest.');
    assert(ismember(mode,modes),'GATE:GeometryMode','Unexpected pilot geometry mode.');
    payloadPath=char(row.payload_path);
    assert(contains(payloadPath,fullfile(taskRoot,'pilot_payloads_bound_c5_v4')), ...
        'GATE:PayloadPath','Pilot payload path escapes isolated task payload directory.');
    vars=whos('-file',payloadPath);
    assert(numel(vars)==1&&strcmp(vars(1).name,'scene'), ...
        'GATE:PayloadVariables','B payload MAT must contain only variable scene.');
    loaded=load(payloadPath,'scene');scene=loaded.scene;
    assert(strcmp(scene.scene_id,char(row.scene_id))&& ...
        abs(double(scene.metadata.seed)-double(row.seed))<1e-9&& ...
        strcmp(scene.gate_geometry_arm,mode), ...
        'GATE:PayloadIdentity','Payload identity or geometry differs from binder receipt.');
    Rt=zeros(3,3,numel(scene.time));
    for k=1:numel(scene.time)
        [~,euler,limited]=baseline_force_to_attitude( ...
            double(scene.reference.acceleration(k,:)).',double(scene.reference.yaw(k)),Ptask);
        assert(~limited,'GATE:TaskTilt','Canonical C5 target unexpectedly clips.');
        Rt(:,:,k)=rotation_zyx(euler);
    end
    err=max(abs(Rt(:)-double(scene.R_task(:))));
    rTaskSha=paired_sha256_double(double(Rt));
    assert(err==0&&strcmpi(rTaskSha,char(row.r_task_sha256))&& ...
        strcmpi(scene.R_task_sha256,char(row.r_task_sha256)), ...
        'GATE:TaskReconstruction','Canonical R_task does not exactly reconstruct from locked C5 cfg.');
    if isKey(taskHashByScene,char(scene.scene_id))
        assert(strcmpi(taskHashByScene(char(scene.scene_id)),rTaskSha), ...
            'GATE:TaskAcrossGeometry','Same pilot scene R_task changed with geometry arm.');
    else
        taskHashByScene(char(scene.scene_id))=rTaskSha;
    end
    cfgMode=geometry_cfg(snapshot.cfg,mode);
    ca=gate_holdout_validate_scene(scene,cfgMode,mode);
    bh=validate_b_gate_scene_no_plant(scene);
    assert(strcmpi(bh,scene.R_task_sha256)&&strcmpi(ca.R_task_sha256,scene.R_task_sha256), ...
        'GATE:ValidatorHash','Candidate/B validators disagree with scene R_task.');
    actualPayloadSha=sha256_file(payloadPath);
    assert(strcmpi(actualPayloadSha,char(row.payload_sha256)), ...
        'GATE:PayloadSHA','Pilot MAT payload SHA differs from receipt.');
    rows(i)=struct('scene_id',char(scene.scene_id),'seed',double(row.seed), ...
        'geometry_arm',mode,'payload_sha256',actualPayloadSha, ...
        'r_task_sha256',char(scene.R_task_sha256),'reconstruction_max_abs_error',err, ...
        'candidate_validator','PASS','b_validator','PASS');
end
assert(taskHashByScene.Count==6,'GATE:UniquePilotCount','Expected six unique pilot IDs.');
preflightJobs=cell(0,1);
for a=1:numel(armIds)
    scenePath=char(receipt.scenes(a).payload_path);
    p=prepare_gate_candidate_no_plant(scenePath,armIds{a},'ACTIVE');
    assert(strcmp(p.opts.gate_attitude_arm,armIds{a})&& ...
        isequaln(p.opts.gate_identity_lock,p.identity), ...
        'GATE:CandidatePrepare','Candidate no-Plant preparation failed for %s.',armIds{a});
    preflightJobs{end+1,1}=struct('scene_id',p.scene.scene_id, ...
        'attitude_arm',armIds{a},'geometry_arm','ACTIVE', ...
        'position_options_sha256',p.identity.common.position_options_sha256); %#ok<AGROW>
end
for modeCell={'FIXED_MIN','FIXED_BOUND15'}
    mode=modeCell{1};
    ix=find(strcmp({receipt.scenes.geometry_arm},mode),1);
    p=prepare_gate_candidate_no_plant(char(receipt.scenes(ix).payload_path),'C5_11',mode);
    assert(strcmp(p.opts.gate_attitude_arm,'C5_11')&& ...
        isequaln(p.opts.gate_identity_lock,p.identity), ...
        'GATE:CandidatePrepare','Candidate no-Plant preparation failed for %s.',mode);
    preflightJobs{end+1,1}=struct('scene_id',p.scene.scene_id, ...
        'attitude_arm','C5_11','geometry_arm',mode, ...
        'position_options_sha256',p.identity.common.position_options_sha256); %#ok<AGROW>
end
releasePath=fullfile(taskRoot,'PILOT_RELEASE_v1.json');
assert(~isfile(releasePath),'GATE:UnexpectedRelease','Pilot release already exists during preflight.');
failClosedPath=fullfile(taskRoot,'pilot_runs','must_not_create_before_release');
assert_rejected(@()run_candidate_gate_attempt(char(receipt.scenes(1).payload_path), ...
    'C5_RBF','ACTIVE',failClosedPath),'GATE:ReleaseMissing');
assert(~isfolder(failClosedPath),'GATE:ReleaseFailClosed','Candidate created output before release.');
bAttempts=fullfile(taskRoot,'b_runner_work','attempts');
assert_rejected(@()run_b_frozen_gate(char(receipt.scenes(1).payload_path)),'HoldoutB:ReleaseMissing');
assert(~isfolder(bAttempts),'GATE:BReleaseFailClosed','B created attempt output before release.');
bad=load(char(receipt.scenes(1).payload_path),'scene');bad=bad.scene;
bad.R_task_sha256=repmat('0',1,64);
badCfg=geometry_cfg(snapshot.cfg,char(receipt.scenes(1).geometry_arm));
assert_rejected(@()gate_holdout_validate_scene(bad,badCfg,char(receipt.scenes(1).geometry_arm)),'GATE:RTaskHash');
assert_rejected(@()validate_b_gate_scene_no_plant(bad),'HoldoutB:RTaskShaMismatch');
audit=struct('schema','DL1018_C5_R_TASK_ROOT_AUDIT_V3', ...
    'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'status','PASS_NO_PLANT_BINDING_AUDIT','plant_calls',0,'training_runs',0, ...
    'pilot_started',false,'pilot_payload_count',18,'holdout_payloads_generated',false, ...
    'tests_data_read',false,'selfcheck_status',selfcheck.status,'selfcheck_plant_calls',selfcheck.plant_calls, ...
    'c5_cfg_sha256',receipt.C5_nominal_task.cfg_sha256, ...
    'c5_g_mps2',double(Ptask.g),'c5_max_tilt_rad',double(Ptask.limits.max_tilt), ...
    'common_position_options_sha256',optionHashes{1},'attitude_arm_ids',{armIds}, ...
    'geometry_arms',{modes},'unique_pilot_scene_count',taskHashByScene.Count, ...
    'scene_count',numel(rows),'candidate_preflight_count',numel(preflightJobs), ...
    'candidate_preflight_jobs',{preflightJobs}, ...
    'candidate_validator_path',which('gate_holdout_validate_scene'), ...
    'b_validator_path',which('validate_b_gate_scene_no_plant'),'pilot_scenes',rows);
outPath=fullfile(taskRoot,'ROOT_C5_R_TASK_NO_PLANT_AUDIT_v3.json');
write_json(outPath,audit);
fprintf('ROOT_R_TASK_AUDIT_PASS scenes=%d geometry_variants=%d exact_reconstruction=true negative_sha_rejected=true plant_calls=0 holdout_payloads=false out=%s', ...
    numel(rows),numel(modes),outPath);
end
function cfg=geometry_cfg(sourceCfg,geometryArm)
cfg=sourceCfg;
if isfield(cfg,'attitude_replacement'),cfg=rmfield(cfg,'attitude_replacement');end
switch upper(char(geometryArm))
    case {'ACTIVE','FIXED_MIN'}
        rho=.15;
    case 'FIXED_BOUND15'
        rho=sqrt(2)*(.225-.0635-.015);
    otherwise
        error('GATE:GeometryCfg','Unsupported geometry mode.');
end
cfg.plant.arm_initial=repmat(rho,4,1);
cfg=bind_paired_fixed_j0(cfg);
end
function root=activate_from(runtime)
addpath(runtime);root=activate_paired_runner();
assert(strcmpi(root,fileparts(fileparts(runtime))),'GATE:RunnerRoot', ...
    'Candidate runner root does not match isolated path.');
end
function R=rotation_zyx(e)
p=e(1);q=e(2);y=e(3);
R=[cos(y)*cos(q),cos(y)*sin(q)*sin(p)-sin(y)*cos(p),cos(y)*sin(q)*cos(p)+sin(y)*sin(p); ...
   sin(y)*cos(q),sin(y)*sin(q)*sin(p)+cos(y)*cos(p),sin(y)*sin(q)*cos(p)-cos(y)*sin(p); ...
   -sin(q),cos(q)*sin(p),cos(q)*cos(p)];
end
function assert_rejected(f,expectedId)
caught=false;
try
    f();
catch ME
    caught=strcmp(ME.identifier,expectedId);
end
assert(caught,'GATE:NegativeCheck','Expected validator to reject bad SHA.');
end
function h=json_sha256(x)
b=unicode2native(jsonencode(x),'UTF-8');
md=java.security.MessageDigest.getInstance('SHA-256');md.update(uint8(b(:)));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=sha256_file(p)
fid=fopen(p,'r');assert(fid>=0,'GATE:FileRead','Cannot open payload file.');
cl=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(b);end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cl;
end
function write_json(p,x)
fid=fopen(p,'w');assert(fid>=0,'GATE:Write','Cannot write audit.');
cl=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(x,'PrettyPrint',true) newline],'char');clear cl;
end