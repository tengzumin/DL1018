function prepared=prepare_gate_candidate_no_plant(scenePayloadPath,attitudeArm,geometryArm)
%PREPARE_GATE_CANDIDATE_NO_PLANT Bind a locked C5 arm and validate one pilot payload.
entry=fileparts(mfilename('fullpath'));
taskRoot=fileparts(fileparts(fileparts(entry)));
projectRoot=fileparts(fileparts(fileparts(taskRoot)));
runnerRoot=activate_paired_runner();
addpath(fullfile(taskRoot,'scene_builder_work'));
addpath(fullfile(taskRoot,'b_runner_work'));
scenePayloadPath=char(java.io.File(char(scenePayloadPath)).getCanonicalPath());
pilotDir=char(java.io.File(fullfile(taskRoot,'pilot_payloads_bound_c5_v6')).getCanonicalPath());
assert(startsWith(lower(scenePayloadPath),[lower(pilotDir) filesep])&& ...
    endsWith(lower(scenePayloadPath),'_scene_payload.mat')&& ...
    isempty(regexp(lower(scenePayloadPath),'test|raw|status|score','once')), ...
    'GATE:PilotPayloadPath','Input must be a new pilot scene payload under this isolated task.');
vars=whos('-file',scenePayloadPath);
assert(numel(vars)==1&&strcmp(vars(1).name,'scene'), ...
    'GATE:PayloadVariables','Pilot MAT must contain only variable scene.');
payload=load(scenePayloadPath,'scene');scene=payload.scene;
receiptPath=fullfile(taskRoot,'C5_R_TASK_BINDING_PILOT_RECEIPT_v5.json');
receipt=jsondecode(fileread(receiptPath));
payloadSha=sha256_file(scenePayloadPath);
receiptHit=find(strcmp({receipt.scenes.payload_path},scenePayloadPath));
assert(numel(receiptHit)==1&&strcmpi(payloadSha,receipt.scenes(receiptHit).payload_sha256), ...
    'GATE:PayloadLock','Pilot scene payload SHA is not present in binder receipt.');
assert(strcmpi(char(receipt.scenes(receiptHit).geometry_arm),upper(char(geometryArm)))&& ...
    strcmp(char(scene.scene_id),char(receipt.scenes(receiptHit).scene_id)), ...
    'GATE:PayloadArm','Pilot payload does not match requested scene/geometry arm.');
lockDir=fullfile(projectRoot,'experiments','position_axis_coordinate_c5_dev72_20261023');
lockPath=fullfile(lockDir,'C5_DEV72_INPUT_LOCK_v3.json');
snapshotPath=fullfile(lockDir,'C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
refRoot=fileparts(projectRoot);
modelPath=fullfile(refRoot,'REFERENCE_FIX_FULL72_20261021_022342_313', ...
    'corrected_reference_training_v1','corrected_pair_training','models','DSSM14','matlab_model_and_parity.mat');
inputRecords=receipt.input_records;
verify_record(inputRecords.c5_input_lock,lockPath);
verify_record(inputRecords.c5_snapshot_mat,snapshotPath);
verify_record(inputRecords.model_mat,modelPath);
lock=jsondecode(fileread(lockPath));
modelRecord=lock.shared_input_files(strcmp({lock.shared_input_files.role},'model_mat'));
assert(numel(modelRecord)==1&&strcmpi(char(modelRecord.sha256),inputRecords.model_mat.sha256), ...
    'GATE:C5ModelLock','C5 model hash differs from C5 input lock.');
modelPack=load(modelPath,'model');
snapshot=load(snapshotPath,'cfg','W0');
model=modelPack.model;
assert(strcmp(char(model.model_id),'DSSM14')&&double(model.input_dim)==14&& ...
    double(model.window)==32&&isequal(double(model.output_W),double(snapshot.W0))&& ...
    strcmpi(paired_sha256_double(double(snapshot.W0)),char(lock.candidate_identity.W0_sha256))&& ...
    strcmpi(normalizer_sha(model),char(lock.candidate_identity.normalizer_arrays_sha256)), ...
    'GATE:C5Model','C5 DSSM14, normalizer or W0 identity mismatch.');
cfg=geometry_cfg(snapshot.cfg,geometryArm);
opts=make_gate_holdout_options(cfg,model,attitudeArm,geometryArm,struct);
identity=gate_holdout_identity_hashes(cfg,model,opts);
opts.gate_identity_lock=identity;
sceneAudit=gate_holdout_validate_scene(scene,cfg,geometryArm);
assert(strcmpi(scene.R_task_sha256,receipt.scenes(receiptHit).r_task_sha256)&& ...
    strcmpi(identity.common.position_options_sha256,receipt.common_position_options_sha256), ...
    'GATE:IdentityMismatch','Scene R_task or common position identity differs from locked preparation.');
prepared=struct('scene',scene,'cfg',cfg,'model',model,'opts',opts, ...
    'identity',identity,'scene_audit',sceneAudit,'scene_payload_sha256',payloadSha, ...
    'scene_payload_path',scenePayloadPath,'taskbook_sha256',char(receipt.taskbook_sha256), ...
    'candidate_runner_root',runnerRoot,'attitude_arm',upper(char(attitudeArm)), ...
    'geometry_arm',upper(char(geometryArm)),'c5_input_lock_sha256',char(inputRecords.c5_input_lock.sha256), ...
    'c5_snapshot_sha256',char(inputRecords.c5_snapshot_mat.sha256), ...
    'model_mat_sha256',char(inputRecords.model_mat.sha256));
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
        error('GATE:GeometryCfg','Unsupported pilot geometry arm.');
end
cfg.plant.arm_initial=repmat(rho,4,1);
cfg=bind_paired_fixed_j0(cfg);
end
function verify_record(r,p)
assert(strcmpi(sha256_file(p),char(r.sha256))&& ...
    strcmpi(char(java.io.File(p).getCanonicalPath()),char(java.io.File(char(r.path)).getCanonicalPath())), ...
    'GATE:InputSHA','Locked C5 input identity mismatch: %s',p);
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
fid=fopen(p,'r');assert(fid>=0,'GATE:FileRead','Cannot read %s.',p);
cl=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(b);end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cl;
end