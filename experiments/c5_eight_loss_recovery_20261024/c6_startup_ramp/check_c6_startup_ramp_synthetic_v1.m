function result=check_c6_startup_ramp_synthetic_v1()
% Exact synthetic fixture check for the isolated C6 MATLAB/Python helpers.
here=fileparts(mfilename('fullpath'));
fixturePath=fullfile(here,'C6_CROSSLANG_FIXTURE_v1.json');
resultPath=fullfile(here,'C6_CROSSLANG_SYNTHETIC_RESULT_v1.json');
helperPath=fullfile(here,'delayed_prediction_step_candidate.m');
pythonPath=fullfile(here,'delayed_prediction_kernel.py');
assert(isfile(fixturePath)&&~isfile(resultPath),'C6:NoOverwrite', ...
    'Fixture must exist and synthetic result must be absent.');
f=jsondecode(fileread(fixturePath));
assert(strcmp(f.schema,'C6_STARTUP_RAMP_CROSSLANG_FIXTURE_V1')&& ...
    strcmp(f.candidate,'C6_STARTUP_PREDICTION_RAMP')&& ...
    double(f.tolerance_abs)==2e-12&&numel(f.cases)==4&& ...
    strcmpi(f.matlab_helper_sha256,sha256_file(helperPath))&& ...
    strcmpi(f.python_kernel_sha256,sha256_file(pythonPath)), ...
    'C6:FixtureIdentity','Fixture/source identity or contract differs.');
maxError=0; caseRows=struct('name',{},'beta_error',{},'max_abs_error',{});
for k=1:numel(f.cases)
    item=f.cases(k); in=item.input; expected=item.expected;
    if isfield(in,'phi_prev')
        out=delayed_prediction_step_candidate(double(in.W),double(in.phi(:)), ...
            double(in.s_eff(:)),double(in.n),double(in.t_n),double(in.phi_prev(:)), ...
            double(in.y_prev(:)),double(in.previous_index),double(in.previous_time_s));
    else
        out=delayed_prediction_step_candidate(double(in.W),double(in.phi(:)), ...
            double(in.s_eff(:)),double(in.n),double(in.t_n),[],[],[],[]);
    end
    names={'raw','applied','prediction_gradient','preprojection_candidate','W_next'};
    e=0;
    for j=1:numel(names)
        name=names{j}; a=double(out.(name)); b=double(expected.(name));
        assert(isequal(size(a),size(b))&&all(isfinite(a(:)))&&all(isfinite(b(:))), ...
            'C6:FixtureShape','Fixture shape/finite check failed for %s.%s.',item.name,name);
        e=max(e,max(abs(a(:)-b(:))));
    end
    betaError=abs(double(out.beta)-double(expected.beta));
    e=max(e,betaError); maxError=max(maxError,e);
    assert(e<=double(f.tolerance_abs),'C6:CrossLanguageMismatch', ...
        'C6 MATLAB/Python fixture mismatch for %s: %.17g.',item.name,e);
    caseRows(k)=struct('name',char(item.name),'beta_error',betaError,'max_abs_error',e);
end
result=struct('schema','C6_STARTUP_RAMP_CROSSLANG_RESULT_V1', ...
    'status','PASS_SYNTHETIC_CROSSLANGUAGE_ONLY','candidate',char(f.candidate), ...
    'case_count',numel(f.cases),'tolerance_abs',double(f.tolerance_abs), ...
    'max_abs_error',maxError,'fixture_path',fixturePath,'fixture_sha256',sha256_file(fixturePath), ...
    'matlab_helper_path',helperPath,'matlab_helper_sha256',sha256_file(helperPath), ...
    'python_kernel_path',pythonPath,'python_kernel_sha256',sha256_file(pythonPath), ...
    'case_results',caseRows,'plant_calls',0,'training_steps',0,'optimizer_steps',0, ...
    'GPU',0,'plant_or_real_data_used',false,'TEST_accessed',false, ...
    'created_utc',utc_now());
write_json_new(resultPath,result);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256');
fid=fopen(path,'r'); assert(fid>=0,'C6:ReadFile','Cannot read %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true
    b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end
    md.update(b);
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json_new(path,value)
assert(~isfile(path),'C6:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'C6:Write','Cannot create %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char');
end
function t=utc_now()
t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end