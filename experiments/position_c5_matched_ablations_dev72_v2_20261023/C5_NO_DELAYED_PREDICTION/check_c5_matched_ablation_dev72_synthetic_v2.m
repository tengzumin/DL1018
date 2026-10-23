function result=check_c5_matched_ablation_dev72_synthetic_v2()
% Cross-language helper check only; it does not call the Plant or closed-loop core.
here=fileparts(mfilename('fullpath')); fixturePath=fullfile(here,'C5_ABLATION_CROSSLANG_FIXTURE_v2.json');
resultPath=fullfile(here,'C5_ABLATION_CROSSLANG_RESULT_DEV72_v2.json'); helperPath=fullfile(here,'delayed_prediction_step_candidate.m');
tol=2e-12; maxError=0;
assert(~isfile(resultPath),'C5Ablation:NoOverwrite','Refusing to overwrite %s.',resultPath);
addpath(here,'-begin'); rehash;
assert(strcmpi(which('delayed_prediction_step_candidate'),helperPath), ...
    'C5Ablation:HelperResolution','Unexpected helper resolution.');
fixture=jsondecode(fileread(fixturePath)); helperSha=sha256_file(helperPath);
contract=jsondecode(fileread(fullfile(here,'C5_ABLATION_DEV72_RUN_CONTRACT_v2.json')));
assert(strcmp(fixture.schema,'C5_MATCHED_ABLATION_CROSSLANG_FIXTURE_V1')&& ...
    strcmp(fixture.mode,contract.variant_id)&& ...
    fixture.tolerance_abs==tol&&strcmpi(fixture.matlab_helper_sha256,helperSha)&& ...
    strcmpi(fixture.python_kernel_sha256,'6615a9d9a6096777429065a598d631ca844f46cf4131032e7ff0a3d3067d9ebc')&& ...
    strcmpi(sha256_file(fixture.python_kernel_path),fixture.python_kernel_sha256)&& ...
    logical(contract.legacy_stage1_update_enabled)&&logical(contract.stage1_update_enabled)&& ...
    logical(contract.actual_weight_update_enabled)==strcmp(contract.variant_id,'C5_NO_DELAYED_PREDICTION')&& ...
    ~logical(contract.actual_prediction_gradient_enabled), ...
    'C5Ablation:FixtureIdentity','Fixture/helper/contract identity mismatch.');
W0=double(fixture.W0); phi320=double(fixture.phi_320(:)); phi330=double(fixture.phi_330(:));
aReq=double(fixture.a_req_rows_n320_to_n330_N11_by_3); aF=double(fixture.a_f_rows_n320_to_n330_N11_by_3);
rF=double(fixture.r_f_rows_n320_to_n330_N11_by_3); mask=double(fixture.mask(:));
assert(isequal(size(W0),[33,3])&&isequal(size(aReq),[11,3])&& ...
    isequal(size(aF),[11,3])&&isequal(size(rF),[11,3])&&isequal(mask,[1;1;0]), ...
    'C5Ablation:FixtureShape','Unexpected fixture shapes or mask.');
maxError=max(maxError,check_close('r_f identity',rF,aReq-aF,tol));
refs=aReq; refs(:,mask==1)=aF(:,mask==1);
maxError=max(maxError,check_close('M110 per-axis reference',refs,fixture.reference_rows_n320_to_n330_N11_by_3,tol));
integral=zeros(3,1); for q=1:10, integral=integral+refs(q,:).'*fixture.plant_dt_s; end
target=((double(fixture.v_330_mps(:))-double(fixture.v_320_mps(:)))-integral)/fixture.event_period_s;
wrongIntegral=zeros(3,1); for q=1:11, wrongIntegral=wrongIntegral+refs(q,:).'*fixture.plant_dt_s; end
wrongTarget=((double(fixture.v_330_mps(:))-double(fixture.v_320_mps(:)))-wrongIntegral)/fixture.event_period_s;
maxError=max(maxError,check_close('[320,330) integral',integral,fixture.reference_integral_320_330_mps,tol));
maxError=max(maxError,check_close('causal n330 target',target,fixture.target_330_mps2,tol));
maxError=max(maxError,check_close('n330 sentinel target',wrongTarget,fixture.sentinel_target_if_row330_included_mps2,tol));
assert(norm(target-wrongTarget,inf)>1e-3,'C5Ablation:SentinelWeak','Current-row sentinel is not discriminative.');

checks={'n=320 has no fabricated history';'n=330 uses only the completed [320,330) target'; ...
    'M110 target uses a_f for X/Y and a_req for Z';'current-row sentinel is excluded'; ...
    'raw/applied outputs are computed from pre-update W';'freeze applies W_next=W_k with actual gradient zero'; ...
    'no-prediction removes only rho*old_gradient';'output and weight projection boundary cases'};
events=as_cell(fixture.events); edgeEvents=as_cell(fixture.boundary_events);
assert(numel(events)==2&&numel(edgeEvents)==2,'C5Ablation:EventShape','Expected two causal and two boundary events.');
limits=[7;8;10];
surface320=double(fixture.surface_320(:)); eta320=double(fixture.eta_320(:));
surface330=double(fixture.surface_330(:)); eta330=double(fixture.eta_330(:));
s320=min(max(surface320-mask.*eta320,-limits),limits);
s330=min(max(surface330-mask.*eta330,-limits),limits);
maxError=max(maxError,check_close('M110 s_eff n320',s320,events{1}.s_eff,tol));
maxError=max(maxError,check_close('M110 s_eff n330',s330,events{2}.s_eff,tol));
maxError=max(maxError,check_events('causal',events,phi320,target,tol,true,fixture.mode));
maxError=max(maxError,check_events('boundary',edgeEvents,[],[],tol,false,fixture.mode));
result=struct('schema','C5_MATCHED_ABLATION_CROSSLANG_RESULT_V1', ...
    'status','PASS_SYNTHETIC_CROSSLANGUAGE_ONLY','variant_id',fixture.mode, ...
    'ablation_mode',fixture.mode,'legacy_stage1_update_enabled',true, ...
    'actual_weight_update_enabled',logical(contract.actual_weight_update_enabled), ...
    'actual_prediction_gradient_enabled',false, ...
    'tolerance_abs',tol,'max_abs_error',maxError,'fixture_sha256',sha256_file(fixturePath), ...
    'matlab_helper_sha256',helperSha,'python_kernel_sha256',fixture.python_kernel_sha256, ...
    'checks',{checks},'plant_calls',0, ...
    'plant_or_real_data_used',false,'training_steps',0,'optimizer_steps',0,'TEST_accessed',false);
write_json_new(resultPath,result); fprintf('%s\n',jsonencode(result));
end

function err=check_events(label,events,phi320,target,tol,isCausal,mode)
err=0; first=[]; second=[];
for k=1:2
    e=events{k}; W=double(e.W_input); phi=double(e.phi(:)); s=double(e.s_eff(:));
    if e.n==320
        assert(~e.has_previous_input&&isempty(e.phi_prev)&&isempty(e.y_prev), ...
            'C5Ablation:FirstEvent','n=320 must not invent a previous sample.');
        out=delayed_prediction_step_candidate(W,phi,s,320,0.320,[],[],[],[]);
        first=out;
    else
        assert(e.n==330&&e.has_previous_input&&e.previous_index==320&&abs(e.previous_time_s-0.320)<1e-15, ...
            'C5Ablation:PreviousIndex','n=330 must use completed event j=320.');
        if isCausal
            err=max(err,check_close('n330 phi previous',e.phi_prev,phi320,tol));
            err=max(err,check_close('n330 target previous',e.y_prev,target,tol));
        end
        out=delayed_prediction_step_candidate(W,phi,s,330,0.330, ...
            double(e.phi_prev(:)),double(e.y_prev(:)),e.previous_index,e.previous_time_s);
        second=out;
    end
    expected=e.expected; err=max(err,compare_out([label ' n=' num2str(e.n)],out,expected,tol));
    err=max(err,check_close('pre-update raw output',out.raw,W.'*phi,tol));
    err=max(err,check_close('pre-update limited applied output',out.applied, ...
        out.beta*min(max(W.'*phi,-3),3),tol));
    baseline=e.baseline_expected;
    assert(all(double(out.prediction_gradient(:))==0), ...
        'C5Ablation:ActualGradient','Ablation must log zero applied prediction gradient.');
    if strcmp(mode,'C5_NO_DELAYED_PREDICTION')
        err=max(err,check_close('only rho*old-gradient removed',out.preprojection_candidate, ...
            double(baseline.preprojection_candidate)+0.01*double(baseline.prediction_gradient),tol));
    elseif strcmp(mode,'C5_FREEZE_TRAINED_W0')
        err=max(err,check_close('freeze actual candidate equals W input',out.preprojection_candidate,W,0));
        err=max(err,check_close('freeze actual Wnext equals W input',out.W_next,W,0));
    else
        error('C5Ablation:Mode','Unexpected fixture mode %s.',mode);
    end
    if ~isCausal&&k==1
        assert(max(abs(double(baseline.applied(:))))>=double(baseline.beta)*3-1e-12&& ...
            max(abs(double(baseline.W_next(:))))==60, ...
            'C5Ablation:BoundaryFixture','Boundary fixture must exercise output limit and joint weight projection.');
    end
end
err=max(err,check_close('event-to-event weight',first.W_next,events{2}.W_input,tol));
if strcmp(mode,'C5_FREEZE_TRAINED_W0')
    err=max(err,check_close('freeze n320 W',first.W_next,events{1}.W_input,0));
    err=max(err,check_close('freeze n330 W',second.W_next,events{2}.W_input,0));
    err=max(err,check_close('freeze event-to-event W',second.W_next,first.W_next,0));
end
end

function err=compare_out(label,out,expected,tol)
err=0; fields={'raw','applied','beta','prediction_gradient','preprojection_candidate','W_next'};
for k=1:numel(fields), f=fields{k}; err=max(err,check_close([label ' ' f],out.(f),expected.(f),tol)); end
assert(logical(out.has_previous)==logical(expected.has_previous), ...
    'C5Ablation:PreviousFlag','%s has_previous mismatch.',label);
if expected.has_previous
    err=max(err,check_close([label ' previous_raw'],out.previous_raw,expected.previous_raw,tol));
    err=max(err,check_close([label ' previous_residual'],out.previous_residual,expected.previous_residual,tol));
else
    assert(isempty(out.previous_raw)&&isempty(out.previous_residual), ...
        'C5Ablation:FirstEventHistory','First event returned fabricated previous values.');
end
end

function items=as_cell(value)
if iscell(value), items=value; return; end
assert(isstruct(value),'C5Ablation:JsonShape','Expected struct/cell from jsondecode.');
items=cell(1,numel(value)); for k=1:numel(value), items{k}=value(k); end
end

function err=check_close(label,actual,expected,tol)
a=double(actual(:)); b=double(expected(:));
assert(numel(a)==numel(b),'C5Ablation:ValueShape','%s shape mismatch.',label);
if isempty(a), err=0; return; end
err=max(abs(a-b)); assert(all(isfinite(a))&&all(isfinite(b))&&err<=tol, ...
    'C5Ablation:ValueMismatch','%s max abs error %.17g exceeds %.17g.',label,err,tol);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r');
assert(fid>=0,'C5Ablation:ReadFile','Cannot read %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(b); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function write_json_new(path,value)
assert(~isfile(path),'C5Ablation:NoOverwrite','Refusing to overwrite %s.',path);
fid=fopen(path,'w'); assert(fid>=0,'C5Ablation:Write','Cannot create %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(value) newline],'char');
end
