function receipt=bind_gate_r_task_from_locked_c5()
%BIND_GATE_R_TASK_FROM_LOCKED_C5 No-Plant C5 target binding; creates pilot payloads only.
entry=fileparts(mfilename('fullpath'));
taskRoot=fileparts(fileparts(fileparts(entry)));
projectRoot=fileparts(fileparts(fileparts(taskRoot)));
assert(isfolder(fullfile(projectRoot,'matlab','core')),'GATE:BindRoot','DL1018 root missing.');
runnerRoot=activate_paired_runner();
builderPath=fullfile(taskRoot,'scene_builder_work','build_gate_inspection_scenes.m');
assert(isfile(builderPath),'GATE:BuilderMissing','Isolated scene builder missing.');
addpath(fileparts(builderPath));
bRunner=fullfile(taskRoot,'b_runner_work');addpath(bRunner);
lockDir=fullfile(projectRoot,'experiments','position_axis_coordinate_c5_dev72_20261023');
lockPath=fullfile(lockDir,'C5_DEV72_INPUT_LOCK_v3.json');
contractPath=fullfile(lockDir,'C5_DEV72_RUN_CONTRACT_v3.json');
preparePath=fullfile(lockDir,'C5_DEV72_PREPARE_RESULT_v3.json');
snapshotPath=fullfile(lockDir,'C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
refRoot=fileparts(projectRoot);
modelPath=fullfile(refRoot,'REFERENCE_FIX_FULL72_20261021_022342_313', ...
    'corrected_reference_training_v1','corrected_pair_training','models','DSSM14','matlab_model_and_parity.mat');
normPath=fullfile(refRoot,'REFERENCE_FIX_FULL72_20261021_022342_313', ...
    'corrected_reference_training_v1','corrected_pair_training','data','normalizer_x14_train_only.npz');
inputRecords=struct( ...
    'c5_input_lock',input_record(lockPath,'82024c01276cc4bfbd9b7772cf5332dee3fdfcbed422969589b68f1c90ed2d75'), ...
    'c5_run_contract',input_record(contractPath,'6ac3cd505dc13fc5b7e6e0cdef966b21225b54d6f847d32177d43f7c678c8150'), ...
    'c5_prepare_result',input_record(preparePath,'ca1fbd9bdf2d7a7b02b15d36ed010fbb1851b4607394c426f6d4d6d408ce3095'), ...
    'c5_snapshot_mat',input_record(snapshotPath,'842ef395569e675db6e139c2684d72b976946915e5e0a58b9b7f24ec10c1d24a'), ...
    'model_mat',input_record(modelPath,'6f3628b10540c617496b2a20f249c4319af79c1a02d5945f1f91f0aead9c9b6e'), ...
    'normalizer_npz',input_record(normPath,'520983e01aa9af38bd3c1aad15b5b8e6a65f5129a32e997e2234951ace198404'));
lock=jsondecode(fileread(lockPath));
assert(strcmp(char(lock.candidate_identity.id),'DSSM14')&& ...
    strcmpi(char(lock.candidate_identity.W0_sha256), ...
    '88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53'), ...
    'GATE:C5Lock','C5 input lock identity mismatch.');
modelRecord=lock.shared_input_files(strcmp({lock.shared_input_files.role},'model_mat'));
normRecord=lock.shared_input_files(strcmp({lock.shared_input_files.role},'normalizer_npz'));
assert(numel(modelRecord)==1&&numel(normRecord)==1&& ...
    strcmpi(char(modelRecord.sha256),inputRecords.model_mat.sha256)&& ...
    strcmpi(char(normRecord.sha256),inputRecords.normalizer_npz.sha256), ...
    'GATE:C5SharedInput','C5 model/normalizer differs from input lock.');
modelPack=load(modelPath,'model');
snapshot=load(snapshotPath,'cfg','opts','W0','modelIdentity');
assert(isequal(fieldnames(modelPack),{'model'})&& ...
    isequal(sort(fieldnames(snapshot)),sort({'cfg';'opts';'W0';'modelIdentity'})), ...
    'GATE:C5MAT','Locked C5 MAT variable set differs.');
model=modelPack.model;
assert(strcmp(char(model.model_id),'DSSM14')&&double(model.input_dim)==14&& ...
    double(model.window)==32&&isequal(double(model.output_W),double(snapshot.W0))&& ...
    strcmpi(paired_sha256_double(double(snapshot.W0)),char(lock.candidate_identity.W0_sha256))&& ...
    strcmpi(normalizer_sha(model),char(lock.candidate_identity.normalizer_arrays_sha256)), ...
    'GATE:C5Model','Locked DSSM14 model, W0 or normalizer identity mismatch.');
activeCfg=geometry_cfg(snapshot.cfg,'ACTIVE');
Pplant=simulation_parameters(activeCfg,activeCfg.plant.arm_initial,zeros(4,1));
Ptask=controller_parameters(activeCfg,Pplant,'fixed');
assert(strcmp(Ptask.morphology_mode,'fixed')&& ...
    isequal(Ptask.inertia,double(activeCfg.attitude_replacement.J0_controller_fixed_kgm2))&& ...
    isfield(Ptask.limits,'max_tilt')&&isfinite(Ptask.limits.max_tilt)&& ...
    isfinite(Ptask.g)&&isfinite(Ptask.mass)&&abs(double(activeCfg.plant.dt)-.001)<1e-12, ...
    'GATE:PTaskCfg','C5 ACTIVE nominal attitude target config is invalid.');
cfgSha=json_sha256(activeCfg);
PtaskRecord=struct('cfg_sha256',cfgSha,'mass_kg',double(Ptask.mass), ...
    'g_mps2',double(Ptask.g),'max_tilt_rad',double(Ptask.limits.max_tilt), ...
    'J0_sha256',char(activeCfg.attitude_replacement.J0_controller_fixed_sha256), ...
    'reference_yaw_source','scene.reference.yaw','acceleration_source','scene.reference.acceleration', ...
    'adapter_path',which('baseline_force_to_attitude'));
sceneBuilderSha=sha256_file(builderPath);
taskbookPath=fullfile(taskRoot,'GATE_INSPECTION_HOLDOUT_TASKBOOK_v2_FROZEN_ZH.md');
taskbookSha=sha256_file(taskbookPath);
modes={'ACTIVE','FIXED_MIN','FIXED_BOUND15'};
payloadSets=cell(size(modes));
for m=1:numel(modes)
    cfgMode=geometry_cfg(snapshot.cfg,modes{m});
    payloadSets{m}=build_gate_inspection_scenes('PILOT',modes{m},[],cfgMode);
    assert(numel(payloadSets{m})==6,'GATE:PilotCount','Each geometry arm requires six pilot payloads.');
end
activeScenes=payloadSets{1};
RtaskById=containers.Map('KeyType','char','ValueType','any');
sceneAuditByKey=containers.Map('KeyType','char','ValueType','char');
for i=1:6
    scene=activeScenes{i};
    N=numel(scene.time);Rtask=zeros(3,3,N);limited=false(N,1);
    for k=1:N
        [~,euler,limited(k)]=baseline_force_to_attitude( ...
            double(scene.reference.acceleration(k,:)).',double(scene.reference.yaw(k)),Ptask);
        Rtask(:,:,k)=rotation_zyx(euler);
    end
    assert(~any(limited),'GATE:PTaskTilt','C5 canonical task target hits max_tilt.');
    RtaskById(char(scene.scene_id))=Rtask;
end
for m=1:numel(modes)
    cfgMode=geometry_cfg(snapshot.cfg,modes{m});
    for i=1:6
        scene=payloadSets{m}{i};
        id=char(scene.scene_id);
        assert(isKey(RtaskById,id),'GATE:PilotIdentity','Pilot scene missing from canonical target map.');
        base=activeScenes{i};
        assert(strcmp(id,char(base.scene_id))&&isequal(scene.time,base.time)&& ...
            isequaln(scene.reference,base.reference)&&isequaln(scene.environment_wind_I,base.environment_wind_I), ...
            'GATE:GeometrySceneMatch','Geometry variant changed reference, wind or scene ID.');
        scene.R_task=RtaskById(id);
        scene.R_task_sha256=paired_sha256_double(scene.R_task);
        scene.R_task_status='INJECTED_LOCKED_C5';
        candidateAudit=gate_holdout_validate_scene(scene,cfgMode,modes{m});
        bHash=validate_b_gate_scene_no_plant(scene);
        assert(strcmpi(bHash,scene.R_task_sha256), ...
            'GATE:BValidator','B wrapper scene validator returned a different R_task hash.');
        payloadSets{m}{i}=scene;
        sceneAuditByKey([id '|' modes{m}])=candidateAudit.scene_payload_sha256;
    end
end
armIds={'C5_RBF','C5_RBF_F','C5_00','C5_10','C5_01','C5_11'};
armIdentity=struct;
positionOptionHashes=cell(0,1);
for m=1:numel(modes)
    cfgMode=geometry_cfg(snapshot.cfg,modes{m});
    if strcmp(modes{m},'ACTIVE'),thisArmIds=armIds;else,thisArmIds={'C5_11'};end
    for a=1:numel(thisArmIds)
        id=thisArmIds{a};
        opts=make_gate_holdout_options(cfgMode,model,id,modes{m},struct);
        hashes=gate_holdout_identity_hashes(cfgMode,model,opts);
        positionOptionHashes{end+1,1}=hashes.common.position_options_sha256; %#ok<AGROW>
        armIdentity.(matlab.lang.makeValidName([modes{m} '_' id]))=hashes;
    end
end
assert(all(strcmp(positionOptionHashes,positionOptionHashes{1})), ...
    'GATE:CommonPosition','Position options hash differs across geometry/method arms.');
outDir=fullfile(taskRoot,'pilot_payloads_bound_c5_v6');
assert(~isfolder(outDir),'GATE:OutputExists','Refusing to overwrite existing pilot payload directory.');
mkdir(outDir);
rows=repmat(struct('scene_id','','seed',0,'geometry_arm','','r_task_sha256','', ...
    'scene_audit_sha256','','b_r_task_sha256','','payload_path','','payload_sha256','', ...
    'limited_samples',0),1,18);
rowIdx=0;
for m=1:numel(modes)
    for i=1:6
        rowIdx=rowIdx+1;scene=payloadSets{m}{i};
        payloadPath=fullfile(outDir,[char(scene.scene_id) '_' modes{m} '_scene_payload.mat']);
        save(payloadPath,'scene','-v7.3');
        rows(rowIdx)=struct('scene_id',char(scene.scene_id),'seed',double(scene.metadata.seed), ...
            'geometry_arm',modes{m},'r_task_sha256',char(scene.R_task_sha256), ...
            'scene_audit_sha256',sceneAuditByKey([char(scene.scene_id) '|' modes{m}]),'b_r_task_sha256',char(scene.R_task_sha256), ...
            'payload_path',payloadPath,'payload_sha256',sha256_file(payloadPath), ...
            'limited_samples',0);
    end
end
receipt=struct('schema','DL1018_GATE_C5_R_TASK_BINDING_V2', ...
    'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'status','PASS_NO_PLANT_PILOT_PAYLOADS_ONLY','plant_calls',0,'training_runs',0, ...
    'pilot_started',false,'holdout_payloads_generated',false,'tests_data_read',false, ...
    'runner_root',runnerRoot,'taskbook_sha256',taskbookSha, ...
    'scene_builder_path',builderPath,'scene_builder_sha256',sceneBuilderSha, ...
    'candidate_validator_path',which('gate_holdout_validate_scene'), ...
    'b_validator_path',which('validate_b_gate_scene_no_plant'), ...
    'input_records',inputRecords,'candidate_id','DSSM14','W0_sha256',char(lock.candidate_identity.W0_sha256), ...
    'normalizer_arrays_sha256',char(lock.candidate_identity.normalizer_arrays_sha256), ...
    'C5_nominal_task',PtaskRecord,'common_position_options_sha256',positionOptionHashes{1}, ...
    'attitude_arm_ids',{armIds},'arm_identity',{armIdentity},'scene_count',numel(rows),'scenes',rows);
receiptPath=fullfile(taskRoot,'C5_R_TASK_BINDING_PILOT_RECEIPT_v5.json');
assert(~isfile(receiptPath),'GATE:ReceiptExists','Refusing to overwrite existing binder receipt.');
write_json(receiptPath,receipt);
fprintf('C5_R_TASK_BINDING_PASS scenes=%d geometry_variants=%d candidate_and_B_validators=PASS plant_calls=0 pilot_started=false holdout_payloads=false receipt=%s', ...
    numel(rows),numel(modes),receiptPath);
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
        error('GATE:GeometryCfg','Unsupported pilot geometry arm %s.',char(geometryArm));
end
cfg.plant.arm_initial=repmat(rho,4,1);
cfg=bind_paired_fixed_j0(cfg);
end
function R=rotation_zyx(e)
p=e(1);q=e(2);y=e(3);
R=[cos(y)*cos(q),cos(y)*sin(q)*sin(p)-sin(y)*cos(p),cos(y)*sin(q)*cos(p)+sin(y)*sin(p); ...
   sin(y)*cos(q),sin(y)*sin(q)*sin(p)+cos(y)*cos(p),sin(y)*sin(q)*cos(p)-cos(y)*sin(p); ...
   -sin(q),cos(q)*sin(p),cos(q)*cos(p)];
end
function r=input_record(p,expected)
assert(isfile(p)&&strcmpi(sha256_file(p),expected),'GATE:InputSHA','Input SHA mismatch: %s',p);
r=struct('path',p,'sha256',lower(expected));
end
function h=json_sha256(x)
b=unicode2native(jsonencode(x),'UTF-8');
md=java.security.MessageDigest.getInstance('SHA-256');md.update(uint8(b(:)));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=normalizer_sha(m)
md=java.security.MessageDigest.getInstance('SHA-256');
for n={'input_mu','input_sigma'}
    f=n{1};a=reshape(double(m.(f)),1,[]);
    hdr=[f char(0) '((1, 14), ''float64'')' char(0)];
    md.update(typecast(uint8(unicode2native(hdr,'UTF-8')),'int8'));
    md.update(typecast(a(:),'int8'));
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function h=sha256_file(p)
fid=fopen(p,'r');assert(fid>=0,'GATE:FileRead','Cannot open file %s.',p);
cl=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(b);end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cl;
end
function write_json(p,x)
fid=fopen(p,'w');assert(fid>=0,'GATE:Write','Cannot write receipt %s.',p);
cl=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(x,'PrettyPrint',true) newline],'char');clear cl;
end