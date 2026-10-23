function result=check_c5_axis_coordinate_synthetic_v1()
% Cross-language formula/helper check only; this does not exercise the closed-loop core.
here=fileparts(mfilename('fullpath'));
fixturePath=fullfile(here,'C5_CROSSLANG_FIXTURE_v1.json');
resultPath=fullfile(here,'C5_CROSSLANG_SYNTHETIC_RESULT_v1.json');
helperPath=fullfile(here,'delayed_prediction_step_candidate.m');
tol=2e-12; maxError=0;
result=struct('schema','C5_AXIS_COORDINATE_CROSSLANG_RESULT_V1','status','FAIL', ...
    'tolerance_abs',tol,'max_abs_error',NaN,'fixture_sha256','','matlab_helper_sha256','', ...
    'checks',{{}},'plant_or_real_data_used',false,'error','');
if isfile(resultPath), error('C5:SyntheticResultExists','Refusing to overwrite %s.',resultPath); end
try
    assert(isfile(fixturePath),'C5:MissingFixture','Missing fixture: %s.',fixturePath);
    addpath(here,'-begin');
    assert(strcmpi(which('delayed_prediction_step_candidate'),helperPath), ...
        'C5:HelperResolution','MATLAB resolved an unexpected prediction helper.');
    result.fixture_sha256=sha256_file(fixturePath);
    result.matlab_helper_sha256=sha256_file(helperPath);
    fixture=jsondecode(fileread(fixturePath));
    frozenHelper='48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d';
    frozenKernel='6615a9d9a6096777429065a598d631ca844f46cf4131032e7ff0a3d3067d9ebc';
    assert(strcmpi(result.matlab_helper_sha256,frozenHelper)&& ...
        strcmpi(fixture.matlab_helper_sha256,frozenHelper)&& ...
        strcmpi(fixture.python_kernel_sha256,frozenKernel), ...
        'C5:SourceSHA','Fixture/helper/kernel does not match the frozen source identity.');
    assert(strcmp(fixture.schema,'C5_AXIS_COORDINATE_CROSSLANG_FIXTURE_V1')&& ...
        fixture.tolerance_abs==tol&&fixture.plant_dt_s==0.001&&fixture.event_period_s==0.01, ...
        'C5:FixtureContract','Unexpected synthetic fixture schema/timing/tolerance.');
    W0=double(fixture.W0); phi320=double(fixture.phi_320(:)); phi330=double(fixture.phi_330(:));
    aReq=double(fixture.a_req_rows_n320_to_n330_N11_by_3);
    aF=double(fixture.a_f_rows_n320_to_n330_N11_by_3);
    rF=double(fixture.r_f_rows_n320_to_n330_N11_by_3);
    v320=double(fixture.v_320_mps(:)); v330=double(fixture.v_330_mps(:));
    sLimit=[7;8;10]; dt=fixture.plant_dt_s;
    assert(isequal(size(W0),[33,3])&&isequal(size(aReq),[11,3])&& ...
        isequal(size(aF),[11,3])&&isequal(size(rF),[11,3]), ...
        'C5:FixtureShape','Unexpected synthetic fixture array shape.');
    maxError=max(maxError,check_close('r_f definition',rF,aReq-aF,tol));
    cases=as_cell(fixture.cases);
    assert(numel(cases)==3,'C5:CaseCount','Expected exactly M=I, M=0, and M=diag(1,1,0).');
    expectedMasks={[1;1;1],[0;0;0],[1;1;0]};
    expectedIds={'M_I','M_zero','M_110'};
    checks={'M=I reproduces C3 tracking/reference formula', ...
        'M=0 reproduces the C4 tracking/request-reference formula', ...
        'M=diag(1,1,0) mixes each axis independently', ...
        'first n=320 event invents no prior target/history', ...
        'n=330 target integrates only the completed [320,330) rows', ...
        'current-row sentinel is excluded from target', ...
        'helper raw/applied/gradient/preprojection/Wnext match Python', ...
        'event output reads W before the corresponding update'};
    for ic=1:numel(cases)
        c=cases{ic}; mask=double(c.mask(:));
        assert(isequal(mask,expectedMasks{ic})&&strcmp(c.case_id,expectedIds{ic}), ...
            'C5:MaskContract','Mask case order/value changed.');
        events=as_cell(c.events);
        assert(numel(events)==2,'C5:EventCount','Each mask case must contain n=320 and n=330 events.');
        e320=events{1}; e330=events{2};
        assert(e320.n==320&&e330.n==330&&~e320.has_previous_input&&e330.has_previous_input&& ...
            e330.previous_index==320&&abs(e330.previous_time_s-0.320)<1e-15, ...
            'C5:EventContract','Expected n=320 first event and n=330 previous index 320.');
        s320=clip_axis(double(e320.surface(:))-mask.*double(e320.eta_before(:)),sLimit);
        s330=clip_axis(double(e330.surface(:))-mask.*double(e330.eta_before(:)),sLimit);
        maxError=max(maxError,check_close('s_M n=320',s320,e320.s_eff,tol));
        maxError=max(maxError,check_close('s_M n=330',s330,e330.s_eff,tol));

        refRows=aReq;
        refRows(:,mask==1)=aF(:,mask==1); % Direct a_f branch on M=1 axes; direct a_req on M=0 axes.
        maxError=max(maxError,check_close('per-axis prediction reference rows', ...
            refRows,c.prediction_reference_rows_n320_to_n330_N11_by_3,tol));
        integral=zeros(3,1);
        for q=1:10, integral=integral+refRows(q,:).'*dt; end
        target=((v330-v320)-integral)/fixture.event_period_s;
        maxError=max(maxError,check_close('completed [320,330) integral', ...
            integral,c.reference_integral_320_330_mps,tol));
        maxError=max(maxError,check_close('causal target n=330',target,c.target_330_mps2,tol));
        wrongIntegral=zeros(3,1);
        for q=1:11, wrongIntegral=wrongIntegral+refRows(q,:).'*dt; end
        wrongTarget=((v330-v320)-wrongIntegral)/fixture.event_period_s;
        maxError=max(maxError,check_close('current-row sentinel', ...
            wrongTarget,c.sentinel_target_if_row330_included_mps2,tol));
        assert(norm(target-wrongTarget,inf)>1e-3,'C5:SentinelWeak','Current-row sentinel is not discriminative.');

        maxError=max(maxError,check_close('event 320 W input',W0,e320.W_input,tol));
        out320=delayed_prediction_step_candidate(W0,phi320,s320,320,0.320,[],[],[],[]);
        assert(~out320.has_previous&&all(out320.prediction_gradient(:)==0), ...
            'C5:FirstEventHistory','n=320 must have no fabricated previous event.');
        maxError=max(maxError,compare_helper('n=320',out320,e320.expected,tol));
        maxError=max(maxError,check_close('n=320 pre-update output',out320.raw,W0.'*phi320,tol));

        maxError=max(maxError,check_close('event 330 W input follows event 320 update', ...
            out320.W_next,e330.W_input,tol));
        out330=delayed_prediction_step_candidate(out320.W_next,phi330,s330,330,0.330, ...
            phi320,target,320,0.320);
        maxError=max(maxError,compare_helper('n=330',out330,e330.expected,tol));
        maxError=max(maxError,check_close('n=330 pre-update output', ...
            out330.raw,out320.W_next.'*phi330,tol));
    end
    result.status='PASS_SYNTHETIC_CROSSLANGUAGE_ONLY';
    result.max_abs_error=maxError;
    result.checks=checks;
catch ME
    result.max_abs_error=maxError;
    result.error=sprintf('%s: %s',ME.identifier,ME.message);
    write_json(resultPath,result);
    rethrow(ME);
end
write_json(resultPath,result);
fprintf('%s\n',jsonencode(result));
end

function items=as_cell(value)
if iscell(value), items=value; return; end
assert(isstruct(value),'C5:JsonShape','Expected a struct array or cell array from jsondecode.');
items=cell(1,numel(value));
for k=1:numel(value), items{k}=value(k); end
end

function value=clip_axis(x,limit), value=min(max(x,-limit),limit); end

function err=compare_helper(label,out,expected,tol)
err=0;
fields={'raw','applied','beta','prediction_gradient','preprojection_candidate','W_next'};
for k=1:numel(fields)
    f=fields{k}; err=max(err,check_close([label ' ' f],out.(f),expected.(f),tol));
end
assert(logical(out.has_previous)==logical(expected.has_previous), ...
    'C5:HelperMismatch','%s has_previous mismatch.',label);
end

function err=check_close(label,actual,expected,tol)
a=double(actual(:)); b=double(expected(:));
assert(numel(a)==numel(b),'C5:ValueShape','%s shape mismatch.',label);
if isempty(a), err=0; return; end
err=max(abs(a-b));
assert(all(isfinite(a))&&all(isfinite(b))&&err<=tol, ...
    'C5:ValueMismatch','%s max abs error %.17g exceeds %.17g.',label,err,tol);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256');
fid=fopen(path,'r'); assert(fid>=0,'C5:ReadFile','Cannot read %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true
    b=fread(fid,8*1024*1024,'*uint8');
    if isempty(b), break; end
    md.update(b);
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function write_json(path,value)
fid=fopen(path,'w'); assert(fid>=0,'C5:ResultWrite','Cannot create %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(value) newline],'char');
end
