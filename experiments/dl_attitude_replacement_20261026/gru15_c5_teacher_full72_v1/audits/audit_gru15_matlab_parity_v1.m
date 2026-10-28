function report=audit_gru15_matlab_parity_v1()
% Read-only Python/MATLAB GRU parity check. Does not call Plant or access TEST.
taskRoot=fileparts(fileparts(mfilename('fullpath')));
runRoot=fullfile(taskRoot,'runs','C5_GRU15_FULL72_SEED2026102001');
weightsPath=fullfile(runRoot,'gru15_attitude_weights_v1.mat');
fixturePath=fullfile(runRoot,'parity_vector_v1.mat');
reportPath=fullfile(taskRoot,'audits','MATLAB_PARITY_GRU15_FULL72_v1.json');
assert(~isfile(reportPath),'DLGRU:AuditExists','Refusing to overwrite parity audit.');
assert(isfile(weightsPath)&&isfile(fixturePath), ...
    'DLGRU:AuditInput','Required GRU15 weights or parity fixture is missing.');
model=load(weightsPath);
fixture=load(fixturePath);
window=double(fixture.input_normalized_window);
expected=double(fixture.expected_model_output_raw_rad_s2(:));
assert(isequal(size(window),[15,13])&&numel(expected)==3&&all(isfinite(window),'all')&& ...
    all(isfinite(expected)), ...
    'DLGRU:Fixture','GRU15 parity fixture has invalid shapes or values.');
direct=gru15_attitude_forward_v1(window.',model);
memory=struct;[memory,~]=gru15_attitude_step_v1('init',memory,struct(),model);
for t=1:15
    rawFeature=double(model.input_mean(:))+double(model.input_std(:)).*window(t,:).';
    in=struct('feature',rawFeature,'J0',eye(3),'beta',1,'dmax',1e9*ones(3,1));
    [memory,out]=gru15_attitude_step_v1('step',memory,in,model);
end
runtime=double(out.raw_residual_rad_s2(:));
directError=max(abs(direct(:)-expected));
runtimeError=max(abs(runtime-expected));
tolerance=1e-5;
assert(directError<=tolerance&&runtimeError<=tolerance, ...
    'DLGRU:Parity','MATLAB/PyTorch GRU parity exceeds tolerance.');
report=struct('schema','DL1018_GRU15_C5_FULL72_MATLAB_PARITY_V1', ...
    'status','PASS','created_utc',char(datetime('now','TimeZone','UTC', ...
    'Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'model_sha256',sha256_file(weightsPath),'fixture_sha256',sha256_file(fixturePath), ...
    'input_shape',[13,15],'sequence_order','oldest_to_current', ...
    'pytorch_gate_order','reset,update,new','max_abs_error_direct_rad_s2',directError, ...
    'max_abs_error_runtime_step_rad_s2',runtimeError,'tolerance_rad_s2',tolerance, ...
    'plant_called',false,'test_data_read',false,'time_varying_inertia_reconstruction_used',false);
fid=fopen(reportPath,'w');assert(fid>=0,'DLGRU:AuditWrite','Cannot create parity report.');
cleanup=onCleanup(@()fclose(fid));
fwrite(fid,[jsonencode(report,'PrettyPrint',true) newline],'char');
clear cleanup;
fprintf('GRU15 MATLAB parity PASS: direct %.9g, runtime step %.9g rad/s^2\n', ...
    directError,runtimeError);
end

function h=sha256_file(path)
fid=fopen(path,'r');assert(fid>=0,'DLGRU:FileRead','Cannot read %s.',path);
cleanup=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true
    bytes=fread(fid,8*1024*1024,'*uint8');if isempty(bytes),break;end
    md.update(bytes);
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
clear cleanup;
end
