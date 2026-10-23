function result = check_c4_coordinate_synthetic_v1()
% Cross-language synthetic check only; this does not exercise the closed-loop core.
here=fileparts(mfilename('fullpath'));
fixturePath=fullfile(here,'C4_CROSSLANG_FIXTURE_v1.json');
resultPath=fullfile(here,'C4_CROSSLANG_SYNTHETIC_RESULT_v1.json');
helperPath=fullfile(here,'delayed_prediction_step_candidate.m');
tol=2e-12; maxError=0;
result=struct('schema','C4_CROSSLANG_SYNTHETIC_RESULT_V1','status','FAIL', ...
    'tolerance_abs',tol,'max_abs_error',NaN,'fixture_sha256','','matlab_helper_sha256','', ...
    'checks',{{}},'plant_or_real_data_used',false,'error','');
if isfile(resultPath), error('C4:SyntheticResultExists','Refusing to overwrite %s.',resultPath); end
try
    assert(isfile(fixturePath),'C4:MissingFixture','Missing fixture: %s.',fixturePath);
    addpath(here,'-begin');
    assert(strcmpi(which('delayed_prediction_step_candidate'),helperPath), ...
        'C4:HelperResolution','MATLAB resolved an unexpected prediction helper.');
    result.fixture_sha256=sha256_file(fixturePath);
    result.matlab_helper_sha256=sha256_file(helperPath);
    fixture=jsondecode(fileread(fixturePath));
    frozenHelper='48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d';
    assert(strcmpi(result.matlab_helper_sha256,frozenHelper) && ...
        strcmpi(fixture.matlab_helper_sha256,frozenHelper), ...
        'C4:HelperSHA','Fixture/helper does not match the frozen helper identity.');
    assert(fixture.tolerance_abs==tol && fixture.plant_dt_s==0.001 && fixture.event_period_s==0.01, ...
        'C4:FixtureContract','Unexpected synthetic fixture timing/tolerance.');

    W0=double(fixture.W0); phi320=double(fixture.phi_320(:)); phi330=double(fixture.phi_330(:));
    aReq=double(fixture.a_req_rows_n320_to_n330_N11_by_3);
    aF=double(fixture.a_f_rows_n320_to_n330_N11_by_3);
    v320=double(fixture.v_320_mps(:)); v330=double(fixture.v_330_mps(:));
    sLimit=[7;8;10]; dt=fixture.plant_dt_s;
    assert(isequal(size(W0),[33,3]) && isequal(size(aReq),[11,3]) && isequal(size(aF),[11,3]), ...
        'C4:FixtureShape','Unexpected synthetic fixture array shape.');

    checkNames={'s_eff clip at n=320/330','n=320 has no fabricated previous event', ...
        'n=330 integrates only completed [320,330) rows', ...
        'm=1 selects legacy a_f directly and m=0 selects a_req directly', ...
        'n=330 excludes the current-row sentinel', ...
        'helper raw/applied/gradient/candidate/Wnext match Python kernel', ...
        'outputs use W before the corresponding update'};
    for ic=1:numel(fixture.cases)
        c=fixture.cases(ic); m=double(c.m);
        e320=c.events(1); e330=c.events(2);
        assert(e320.n==320 && e330.n==330 && ~e320.has_previous_input && e330.has_previous_input, ...
            'C4:EventContract','Fixture events must be n=320 and n=330.');
        s320=clip_axis(double(e320.surface(:))-m*double(e320.eta_before(:)),sLimit);
        s330=clip_axis(double(e330.surface(:))-m*double(e330.eta_before(:)),sLimit);
        maxError=max(maxError,check_close('s_eff n=320',s320,e320.s_eff,tol));
        maxError=max(maxError,check_close('s_eff n=330',s330,e330.s_eff,tol));

        out320=delayed_prediction_step_candidate(W0,phi320,s320,320,0.320,[],[],[],[]);
        assert(~out320.has_previous && isempty(out320.previous_raw) && ...
            isempty(out320.previous_residual) && all(out320.prediction_gradient(:)==0), ...
            'C4:FirstEventHistory','n=320 must have no previous-target data.');
        maxError=max(maxError,compare_helper('n=320',out320,e320.expected,tol));
        maxError=max(maxError,check_close('n=320 raw before update',out320.raw,W0.'*phi320,tol));

        if m==1
            predictionRef=aF; expectedRefName='a_f';
        else
            predictionRef=aReq; expectedRefName='a_req';
        end
        assert(strcmp(e330.prediction_reference,expectedRefName), ...
            'C4:ReferenceBranch','Unexpected prediction-reference branch for m=%d.',m);
        integral=zeros(3,1);
        for q=1:10, integral=integral+predictionRef(q,:).'*dt; end
        target=((v330-v320)-integral)/fixture.event_period_s;
        maxError=max(maxError,check_close('completed [320,330) reference integral', ...
            integral,e330.reference_integral_mps,tol));
        maxError=max(maxError,check_close('n=330 causal target',target,e330.target_mps2,tol));
        if m==1
            maxError=max(maxError,check_close('m=1 direct legacy a_f rows',predictionRef,aF,tol));
        else
            maxError=max(maxError,check_close('m=0 direct a_req rows',predictionRef,aReq,tol));
        end
        wrongIntegral=zeros(3,1);
        for q=1:11, wrongIntegral=wrongIntegral+predictionRef(q,:).'*dt; end
        wrongTarget=((v330-v320)-wrongIntegral)/fixture.event_period_s;
        maxError=max(maxError,check_close('current-row sentinel target',wrongTarget, ...
            e330.sentinel_target_if_current_row_were_wrongly_included_mps2,tol));
        assert(norm(target-wrongTarget,inf)>1e-3,'C4:SentinelWeak','Current-row sentinel is not discriminative.');

        maxError=max(maxError,check_close('n=330 W input follows n=320 update', ...
            out320.W_next,e330.W_input,tol));
        out330=delayed_prediction_step_candidate(out320.W_next,phi330,s330,330,0.330, ...
            phi320,target,320,0.320);
        maxError=max(maxError,compare_helper('n=330',out330,e330.expected,tol));
        maxError=max(maxError,check_close('n=330 raw before update', ...
            out330.raw,out320.W_next.'*phi330,tol));
    end
    result.status='PASS_SYNTHETIC_CROSSLANGUAGE_ONLY';
    result.max_abs_error=maxError;
    result.checks=checkNames;
catch ME
    result.max_abs_error=maxError;
    result.error=sprintf('%s: %s',ME.identifier,ME.message);
    write_json(resultPath,result);
    rethrow(ME);
end
write_json(resultPath,result);
fprintf('%s\n',jsonencode(result));
end

function s=clip_axis(x,limit), s=min(max(x,-limit),limit); end

function err=compare_helper(label,out,expected,tol)
err=0;
fields={'raw','applied','beta','previous_raw','previous_residual', ...
    'prediction_gradient','preprojection_candidate','W_next'};
for k=1:numel(fields)
    f=fields{k}; err=max(err,check_close([label ' ' f],out.(f),expected.(f),tol));
end
assert(logical(out.has_previous)==logical(expected.has_previous), ...
    'C4:HelperMismatch','%s has_previous mismatch.',label);
end

function err=check_close(label,actual,expected,tol)
a=double(actual(:)); b=double(expected(:));
assert(numel(a)==numel(b),'C4:ValueShape','%s shape mismatch.',label);
if isempty(a), err=0; return; end
err=max(abs(a-b));
assert(all(isfinite(a)) && all(isfinite(b)) && err<=tol, ...
    'C4:ValueMismatch','%s max abs error %.17g exceeds %.17g.',label,err,tol);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256');
fid=fopen(path,'r'); assert(fid>=0,'C4:ReadFile','Cannot read %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true
    b=fread(fid,8*1024*1024,'*uint8');
    if isempty(b), break; end
    md.update(b);
end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function write_json(path,value)
fid=fopen(path,'w'); assert(fid>=0,'C4:ResultWrite','Cannot create %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(value) newline],'char');
end
