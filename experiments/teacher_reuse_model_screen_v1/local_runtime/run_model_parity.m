function report=run_model_parity(root)
% Zero-Plant Python/MATLAB inference, state-reset, TCN causality and Head parity.
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','teacher_reuse_model_screen_v1');
local=fullfile(out,'local_runtime');addpath(local,'-begin');
addpath(fullfile(root,'experiments','position_only_closed_loop_search_v1','local_runtime'),'-end');
rehash;
assert(startsWith(which('position_stage1_model_forward_v2'),local,'IgnoreCase',true), ...
    'MODEL:PathIsolation','Teacher-reuse inference adapter did not take precedence.');
ids={'MLP14','KAN14','TCN14','GRU14','DSSM14','MLP20','TCN20','TCN14_L128'};
rows=struct([]);
for ii=1:numel(ids)
    modelId=ids{ii};package=fullfile(out,'models','fast_screen',modelId,'seed2026102001');
    export=jsondecode(fileread(fullfile(package,'export_report.json')));
    assert(ismember(char(export.status),{'EXPORTED_AWAITING_MATLAB_PARITY','MATLAB_PARITY_PASS'})&&export.fixture_count==64, ...
        'MODEL:ExportStatus','Missing 64-window export for %s.',modelId);
    q=load(fullfile(package,'matlab_model_and_parity.mat'));
    model=q.model;N=double(q.fixture_count);maxPhi=0;maxOutput=0;
    for k=1:N
        phi=position_stage1_model_forward_v2(model,q.windows(:,:,k));
        y=double(model.output_W).'*phi;
        maxPhi=max(maxPhi,max(abs(phi-double(q.expected_phi(:,k)))));
        maxOutput=max(maxOutput,max(abs(y-double(q.expected_output(:,k)))));
    end
    assert(maxPhi<=1e-5&&maxOutput<=1e-5,'MODEL:Parity', ...
        '%s parity failed: phi %.4g, output %.4g m/s^2.',modelId,maxPhi,maxOutput);

    % Measure 1024 single-window calls per candidate; this is inference only, Plant=0.
    timings=zeros(1024,1);lastPhi=[];
    for k=1:numel(timings)
        fixture=mod(k-1,N)+1;t=tic;
        lastPhi=position_stage1_model_forward_v2(model,q.windows(:,:,fixture));
        timings(k)=toc(t);
    end
    timings=sort(timings);p99=timings(ceil(.99*numel(timings)));

    tcnCausality=NaN;receptiveField=NaN;
    if strcmp(char(model.architecture),'TCN')
        d=double(model.dilations(:));receptiveField=1+2*sum(d);
        assert(receptiveField>=double(model.window),'MODEL:ReceptiveField', ...
            '%s receptive field %d is shorter than its window %d.',modelId,receptiveField,double(model.window));
        w=double(q.windows(:,:,1));[~,sequencePhi]=position_stage1_model_forward_v2(model,w);
        probes=unique([1,ceil(size(w,2)/2),size(w,2)-1]);tcnCausality=0;
        for ti=probes
            if ti<1||ti>=size(w,2),continue;end
            altered=w;altered(:,ti+1:end)=repmat(((-1).^((1:size(altered,1))'))*3,1,size(altered,2)-ti);
            [~,alteredPhi]=position_stage1_model_forward_v2(model,altered);
            [prefixPhi,~]=position_stage1_model_forward_v2(model,w(:,1:ti));
            tcnCausality=max([tcnCausality;max(abs(sequencePhi(:,ti)-alteredPhi(:,ti))); ...
                max(abs(sequencePhi(:,ti)-prefixPhi))]);
        end
        assert(tcnCausality<=1e-12,'MODEL:TCNCausality','%s future perturbation changed an earlier output.',modelId);
    end

    resetError=NaN;
    if ismember(char(model.architecture),{'GRU','DSSM'})
        a=q.windows(:,:,1);b=q.windows(:,:,2);
        pa=position_stage1_model_forward_v2(model,a);position_stage1_model_forward_v2(model,b);
        pa2=position_stage1_model_forward_v2(model,a);resetError=max(abs(pa-pa2));
        assert(resetError<=1e-12,'MODEL:WindowReset','%s leaks state between independent windows.',modelId);
    end
    z=struct('model_id',modelId,'seed',double(model.seed),'selected_step',double(model.selected_step), ...
        'fixture_count',N,'max_phi_abs_error',maxPhi,'max_output_abs_error_mps2',maxOutput, ...
        'inference_p99_ms',1000*p99,'under_10ms',p99<.01,'receptive_field_events',receptiveField, ...
        'tcn_causality_max_abs_error',tcnCausality,'window_reset_max_abs_error',resetError, ...
        'plant_starts',0);
    if isempty(rows),rows=z;else,rows(end+1,1)=z;end %#ok<AGROW>
    export.status='MATLAB_PARITY_PASS';export.matlab_parity=z;
    fid=fopen(fullfile(package,'export_report.json'),'w');fwrite(fid,jsonencode(export,'PrettyPrint',true),'char');fclose(fid);
    fprintf('MODEL_PARITY %s PASS phi=%.3g output=%.3g p99=%.3fms RF=%g causal=%g reset=%g Plant=0\n', ...
        modelId,maxPhi,maxOutput,z.inference_p99_ms,receptiveField,tcnCausality,resetError);
end

% Exercise the actual shared output-then-update FEATURE Head and PCF coupling contract.
headPath=fullfile(local,'position_only_search_head_step.m');
assert(isfile(headPath),'MODEL:HeadPath','Missing shared position-only Head implementation.');
addpath(fileparts(headPath),'-begin');rehash;
assert(startsWith(which('position_only_search_head_step'),fileparts(headPath),'IgnoreCase',true), ...
    'MODEL:HeadPathIsolation','Unexpected position Head implementation.');
phi=lastPhi;W0=double(q.model.output_W);
state=zeros(33,3);state(1:32,:)=reshape(sin(1:96),32,3)*1e-3;
sEff=[.03;-.02;.01];dt=.01;beta=1;gamma=12;dmax=[3;3;3];
[raw,applied,stateNext]=position_only_search_head_step(phi,W0,state,'FEATURE',gamma,1,sEff,dt,beta,dmax);
rawExpected=state.'*phi;stateExpected=max(min(state+dt*(-gamma*beta*phi*sEff.'-.002*state),60),-60);
headError=max([max(abs(raw-rawExpected),[],'all'), ...
    max(abs(applied-beta*max(min(raw,dmax),-dmax)),[],'all'),max(abs(stateNext-stateExpected),[],'all')]);
assert(headError<=1e-12,'MODEL:HeadParity','Output-then-update Head parity error %.4g.',headError);
loopText=fileread(fullfile(local,'run_dl1018_closed_loop.m'));
assert(contains(loopText,'stage1PositionHistory=zeros(stage1ModelInputDim,stage1ModelContextLength);')&& ...
    contains(loopText,'stage1ModelContextLength=double(stage1PositionRuntime.model.context_length);')&& ...
    contains(loopText,'stage1PositionHistory=[stage1PositionHistory(:,2:end),feature];')&& ...
    contains(loopText,'stage1PositionHeldForceLog')&&contains(loopText,'stage1PositionEventDt'), ...
    'MODEL:RuntimeAudit','Episode history reset, event update, or held Plant input logging is absent.');

protocol=jsondecode(fileread(fullfile(out,'protocol.json')));
report=struct('status','PASS','protocol_status',protocol.status, ...
    'models',rows,'plant_starts',0,'feature_output_then_update_head_max_error',headError, ...
    'history_reset_and_held_input_audit','PASS','notes', ...
    'Each independent window is recomputed from zero state. The standalone parity fixtures advance no Plant.');
report.status='PASS';reportPath=fullfile(out,'reports','zero_plant_model_parity.json');
fid=fopen(reportPath,'w');fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fclose(fid);
fprintf('ZERO_PLANT_MODEL_PARITY PASS models=%d fixtures_per_model=64 Plant=0 Head=%.3g\n',numel(rows),headError);
end
