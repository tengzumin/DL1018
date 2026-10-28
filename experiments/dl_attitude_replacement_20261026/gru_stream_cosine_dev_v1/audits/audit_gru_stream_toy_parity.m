function report=audit_gru_stream_toy_parity()
% Full-sequence Python-double / MATLAB-double parity for toy GRU weights only.
here=char(java.io.File(fileparts(mfilename('fullpath'))).getCanonicalPath());
fixturePath=fullfile(here,'toy_gru_fixture_v1.mat');
reportPath=fullfile(here,'TOY_MATLAB_PARITY_v1.json');
assert(isfile(fixturePath)&&~isfile(reportPath),'GRUStream:ToyFixture', ...
    'Toy fixture must exist and prior parity output must not be overwritten.');
f=load(fixturePath);
model=struct('input_mean',f.input_mean,'input_std',f.input_std,'target_rms',f.target_rms, ...
    'gru_weight_ih',f.gru_weight_ih,'gru_weight_hh',f.gru_weight_hh, ...
    'gru_bias_ih',f.gru_bias_ih,'gru_bias_hh',f.gru_bias_hh, ...
    'head_weight',f.head_weight,'head_bias',f.head_bias);
X=double(f.input_features_raw);expectedY=double(f.expected_output_raw_rad_s2);
expectedH=double(f.expected_hidden_double);N=size(X,1);
assert(N==1999&&size(X,2)==13&&isequal(size(expectedY),[N 3])&& ...
    isequal(size(expectedH),[N 32]),'GRUStream:ToyShape','Expected all 1999 inputs, outputs, and hidden states.');
J0=double(f.fixed_J0);dmax=double(f.dmax(:));beta=double(f.expected_beta(:));
[memory,~]=gru_stream_attitude_step_v1('init',struct,struct,model);
Y=zeros(N,3);H=zeros(N,32);T=zeros(N,3);carryError=0;
for k=1:N
    in=struct('feature',X(k,:).','J0',J0,'beta',beta(k),'dmax',dmax);
    [memory,out]=gru_stream_attitude_step_v1('step',memory,in,model);
    Y(k,:)=out.raw_residual_rad_s2(:).';H(k,:)=out.hidden_after(:).';
    T(k,:)=out.estimateTorque_Nm(:).';
    if k==1,carryError=max(carryError,max(abs(out.hidden_before(:))));
    else,carryError=max(carryError,max(abs(out.hidden_before(:)-H(k-1,:).')));end
    assert(out.event_count==k,'GRUStream:ToyEventCount','Hidden event counter did not advance once per input.');
end
outputError=max(abs(Y-expectedY),[],'all');hiddenError=max(abs(H-expectedH),[],'all');
torqueError=max(abs(T-double(f.expected_torque_Nm)),[],'all');
assert(outputError<1e-8&&hiddenError<1e-8&&torqueError<1e-10&&carryError==0, ...
    'GRUStream:ToyParity','Toy GRU MATLAB/Python trajectory or output-order parity failed.');
% A second scene must reinitialize h=0 and reproduce the complete trajectory.
[memory2,~]=gru_stream_attitude_step_v1('init',struct,struct,model);
Y2=zeros(N,3);H2=zeros(N,32);
for k=1:N
    [memory2,out2]=gru_stream_attitude_step_v1('step',memory2, ...
        struct('feature',X(k,:).','J0',J0,'beta',beta(k),'dmax',dmax),model);
    Y2(k,:)=out2.raw_residual_rad_s2(:).';H2(k,:)=out2.hidden_after(:).';
end
resetOutputError=max(abs(Y2-Y),[],'all');resetHiddenError=max(abs(H2-H),[],'all');
assert(resetOutputError==0&&resetHiddenError==0,'GRUStream:SceneReset', ...
    'A new scene reset did not reproduce the zero-hidden trajectory.');
% Future inputs cannot alter any output or hidden state before the perturbation.
Xfuture=double(f.future_perturbed_features_raw);firstChanged=double(f.future_perturb_index_zero_based)+1;
[memory3,~]=gru_stream_attitude_step_v1('init',struct,struct,model);
Y3=zeros(N,3);H3=zeros(N,32);
for k=1:N
    [memory3,out3]=gru_stream_attitude_step_v1('step',memory3, ...
        struct('feature',Xfuture(k,:).','J0',J0,'beta',beta(k),'dmax',dmax),model);
    Y3(k,:)=out3.raw_residual_rad_s2(:).';H3(k,:)=out3.hidden_after(:).';
end
prefixY=max(abs(Y3(1:firstChanged-1,:)-Y(1:firstChanged-1,:)),[],'all');
prefixH=max(abs(H3(1:firstChanged-1,:)-H(1:firstChanged-1,:)),[],'all');
assert(prefixY==0&&prefixH==0,'GRUStream:FutureCausality', ...
    'A future feature changed an earlier output or hidden state.');
report=struct('status','PASS_MATLAB_DOUBLE_TOY_GRU_STREAM_PARITY', ...
    'Plant_calls',0,'training_started',false,'TEST_read',false,'toy_weights_only',true, ...
    'event_count',N,'output_max_abs_error',outputError,'hidden_trajectory_max_abs_error',hiddenError, ...
    'applied_torque_order_max_abs_error_Nm',torqueError,'hidden_carry_max_abs_error',carryError, ...
    'scene_reset_output_max_abs_error',resetOutputError, ...
    'scene_reset_hidden_max_abs_error',resetHiddenError, ...
    'future_perturbation_first_changed_index_1based',firstChanged, ...
    'future_prefix_output_max_abs_error',prefixY,'future_prefix_hidden_max_abs_error',prefixH, ...
    'python_fixture_sha256',hash_file(fixturePath), ...
    'audit_script_sha256',hash_file([mfilename('fullpath') '.m']));
write_json(reportPath,report);disp(report);
end
function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0,'GRUStream:Read','Cannot read %s.',path);
cleanup=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cleanup;
end
function write_json(path,value)
fid=fopen(path,'w','n','UTF-8');assert(fid>=0,'GRUStream:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));clear cleanup;
end