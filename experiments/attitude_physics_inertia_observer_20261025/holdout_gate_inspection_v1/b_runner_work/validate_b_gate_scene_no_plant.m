function rTaskSha256=validate_b_gate_scene_no_plant(scene)
%VALIDATE_B_GATE_SCENE_NO_PLANT Exact B wrapper scene contract, with no Plant access.
N=20001;
assert(isfield(scene,'reference_contract_id')&&isTextScalar(scene.reference_contract_id)&& ...
    strcmp(char(scene.reference_contract_id),'DL1018_GATE_INSPECTION_HOLDOUT_V1'), ...
    'HoldoutB:ReferenceContract','Unexpected or missing reference_contract_id.');
assert(isfield(scene,'time'),'HoldoutB:TimeMissing','Missing scene.time.');
t=scene.time;
assert(isnumeric(t)&&isreal(t)&&~issparse(t)&&isequal(size(t),[N 1])&& ...
    all(isfinite(double(t(:))))&&abs(double(t(1)))<=1e-12&& ...
    abs(double(t(end))-20)<=1e-12&&max(abs(diff(double(t(:)))-.001))<=1e-12, ...
    'HoldoutB:TimeContract','scene.time must be finite 20,001-by-1 samples from 0 to 20 s at 1 ms.');
refFields={'position','velocity','acceleration'};
assert(isfield(scene,'reference')&&isstruct(scene.reference), ...
    'HoldoutB:ReferenceMissing','Missing scene.reference struct.');
for k=1:numel(refFields)
    assertFiniteArray(scene.reference,refFields{k},[N 3],['reference.' refFields{k}]);
end
for name={'yaw','yaw_rate','yaw_acceleration'}
    field=name{1};
    assert(isfield(scene.reference,field),'HoldoutB:ReferenceField','Missing reference.%s.',field);
    value=scene.reference.(field);
    assert(isnumeric(value)&&isreal(value)&&~issparse(value)&&isvector(value)&& ...
        numel(value)==N&&all(isfinite(double(value(:)))), ...
        'HoldoutB:ReferenceShape','reference.%s must contain 20,001 finite values.',field);
end
assert(isfield(scene,'initial_state')&&isnumeric(scene.initial_state)&& ...
    isreal(scene.initial_state)&&~issparse(scene.initial_state)&& ...
    isvector(scene.initial_state)&&numel(scene.initial_state)==12&& ...
    all(isfinite(double(scene.initial_state(:)))), ...
    'HoldoutB:InitialState','initial_state must be a finite real 12-vector.');
armFields={'command','rho_true','rhoDot_true','rho_hat','rhoDot_hat'};
assert(isfield(scene,'arms')&&isstruct(scene.arms), ...
    'HoldoutB:ArmsMissing','Missing scene.arms struct.');
for k=1:numel(armFields)
    assertFiniteArray(scene.arms,armFields{k},[N 4],['arms.' armFields{k}]);
end
assertFiniteArray(scene,'environment_wind_I',[N 3],'environment_wind_I');
assert(isfield(scene,'R_task')&&isnumeric(scene.R_task)&&isreal(scene.R_task)&& ...
    ~issparse(scene.R_task)&&isequal(size(scene.R_task),[3 3 N])&& ...
    all(isfinite(double(scene.R_task(:)))), ...
    'HoldoutB:RTaskShape','R_task must be a finite real 3-by-3-by-20,001 array.');
assert(isfield(scene,'R_task_sha256')&&isTextScalar(scene.R_task_sha256), ...
    'HoldoutB:RTaskShaMissing','Missing scalar R_task_sha256.');
expectedSha=char(scene.R_task_sha256);
assert(~isempty(regexp(expectedSha,'^[0-9A-Fa-f]{64}$','once')), ...
    'HoldoutB:RTaskShaFormat','R_task_sha256 must be 64 hexadecimal characters.');
values=double(scene.R_task(:));
[~,~,endian]=computer;
if endian=='B',values=swapbytes(values);end
rTaskSha256=sha256Bytes(typecast(values,'uint8'));
assert(strcmpi(expectedSha,rTaskSha256), ...
    'HoldoutB:RTaskShaMismatch','R_task_sha256 does not match canonical R_task bytes.');
I=eye(3);
for k=1:N
    R=double(scene.R_task(:,:,k));
    assert(norm(R.'*R-I,'fro')<=1e-8&&abs(det(R)-1)<=1e-8, ...
        'HoldoutB:RTaskSO3','R_task(:,:, %d) is not in SO(3).',k);
end
end
function assertFiniteArray(container,field,expectedSize,label)
assert(isfield(container,field),'HoldoutB:SceneField','Missing %s.',label);
value=container.(field);
assert(isnumeric(value)&&isreal(value)&&~issparse(value)&& ...
    isequal(size(value),expectedSize)&&all(isfinite(double(value(:)))), ...
    'HoldoutB:SceneArray','%s must be finite with size %s.',label,mat2str(expectedSize));
end
function tf=isTextScalar(value)
tf=(ischar(value)&&isrow(value))||(isstring(value)&&isscalar(value));
end
function hex=sha256Bytes(bytes)
md=java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(uint8(bytes(:)),'int8'));
digest=typecast(md.digest(),'uint8');
hex=lower(reshape(dec2hex(digest,2).',1,[]));
end