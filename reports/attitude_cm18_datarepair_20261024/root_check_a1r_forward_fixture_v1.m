function result=root_check_a1r_forward_fixture_v1()
% Independent audit of the actual fixed A1R weights; no controller/Plant call.
repoRoot=fileparts(fileparts(fileparts(mfilename('fullpath'))));
base=fullfile(repoRoot,'experiments','attitude_cm18_datarepair_20261024');
fixturePath=fullfile(base,'a1r_screen12_control_v1','artifacts','a1r_forward_parity_fixture_v1.json');
modelPath=fullfile(base,'postselection_a1r_v1','deployment_parameters_v1.json');
helperDir=fullfile(repoRoot,'experiments','attitude_cm18_a1_20261024','matlab');
out=fullfile(fileparts(mfilename('fullpath')),'ROOT_A1R_ACTUAL_MATLAB_PARITY_v1.json');
assert(~isfile(out),'Refusing audit overwrite');
assert(strcmp(file_sha(fixturePath),'04f79f473232341e5495ee77d19af09650e56976881b9cccf24901e7c1fae7f5'));
assert(strcmp(file_sha(modelPath),'b3ab7a3d99df639d4cc0a10ec2b6fcd4622388f58c90c25424e472164ef38d23'));
helper=fullfile(helperDir,'cm18_a1_forward_v1.m');
assert(strcmp(file_sha(helper),'1ff450f9be6a5c16fe98cb4f169ef9930f1b806fecfc10ad664c11ce940f42e9'));
addpath(helperDir,'-begin'); assert(strcmpi(which('cm18_a1_forward_v1'),helper));
f=jsondecode(fileread(fixturePath)); m=jsondecode(fileread(modelPath));
assert(strcmp(m.schema,'CM18_A1R_DEPLOYMENT_PARAMETERS_V1')&&m.identity.selected_step==40000);
assert(f.case_count==11&&numel(f.cases)==11);
maxError=zeros(1,4); nonzero=0; synthetic=0;
for k=1:11
    if iscell(f.cases), c=f.cases{k}; else, c=f.cases(k); end
    x=reshape(double(c.raw_features_18),1,18);
    [physical,normalized,coefficients,basis]=cm18_a1_forward_v1(x,m.parameters);
    actual={physical,normalized,coefficients,basis};
    expected={reshape(double(c.expected.physical_output_rad_s2),1,3), ...
        reshape(double(c.expected.normalized_output),1,3),double(c.expected.coefficients_3x8), ...
        reshape(double(c.expected.basis_8),1,8)};
    for j=1:4
        assert(isequal(size(actual{j}),size(expected{j}))&&all(isfinite(actual{j}(:))));
        delta=max(abs(actual{j}(:)-expected{j}(:)));
        assert(isfinite(delta)&&delta<=2e-12); maxError(j)=max(maxError(j),delta);
    end
    if c.synthetic_zero_basis
        synthetic=synthetic+1; assert(all(basis==0)&&isequal(physical,zeros(1,3)));
    else
        nonzero=nonzero+any(basis~=0);
    end
end
assert(nonzero==2&&synthetic==1);
result=struct('status','PASS','case_count',11,'real_nonzero_basis_cases',nonzero, ...
    'max_error_order',{{'physical','normalized','coefficients','basis'}},'max_abs_error',maxError, ...
    'fixture_sha256',file_sha(fixturePath),'model_sha256',file_sha(modelPath), ...
    'helper_sha256',file_sha(helper),'audit_source_sha256',file_sha([mfilename('fullpath') '.m']), ...
    'selected_step',40000,'Plant_calls',0,'engine_calls',0,'optimizer_steps',0,'TEST_accessed',false);
fid=fopen(out,'w'); assert(fid>=0); close=onCleanup(@()fclose(fid));
fwrite(fid,unicode2native(jsonencode(result),'UTF-8'),'uint8');
end

function h=file_sha(path)
fid=fopen(path,'rb'); assert(fid>=0); close=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true
    b=fread(fid,1024*1024,'*uint8'); if isempty(b), break; end
    md.update(typecast(b(:),'int8'));
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
