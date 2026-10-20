function report=run_x20_extension_parity(root)
% Zero-Plant parity for user-authorized KAN20/GRU20/DSSM20 seed packages.
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','teacher_reuse_model_screen_v1');
local=fullfile(out,'local_runtime');addpath(local,'-begin');rehash;
ids={'KAN20','GRU20','DSSM20'};seeds=[2026102001 2026102002];rows=struct([]);
for mi=1:numel(ids)
    for si=1:numel(seeds)
        modelId=ids{mi};seed=seeds(si);package=fullfile(out,'models','fast_screen',modelId,sprintf('seed%d',seed));
        export=jsondecode(fileread(fullfile(package,'export_report.json')));
        assert(strcmp(export.status,'EXPORTED_AWAITING_MATLAB_PARITY')&&export.fixture_count==64, ...
            'X20:Export','Missing 64-window export for %s seed %d.',modelId,seed);
        q=load(fullfile(package,'matlab_model_and_parity.mat'));model=q.model;N=double(q.fixture_count);
        maxPhi=0;maxOutput=0;
        for k=1:N
            phi=position_stage1_model_forward_v2(model,q.windows(:,:,k));
            y=double(model.output_W).'*phi;
            maxPhi=max(maxPhi,max(abs(phi-double(q.expected_phi(:,k)))));
            maxOutput=max(maxOutput,max(abs(y-double(q.expected_output(:,k)))));
        end
        assert(maxPhi<=1e-5&&maxOutput<=1e-5,'X20:Parity', ...
            '%s seed %d parity failed: phi %.4g, output %.4g m/s^2.',modelId,seed,maxPhi,maxOutput);
        timings=zeros(256,1);
        for k=1:numel(timings)
            fixture=mod(k-1,N)+1;t=tic;
            position_stage1_model_forward_v2(model,q.windows(:,:,fixture));timings(k)=toc(t);
        end
        timings=sort(timings);p99=timings(ceil(.99*numel(timings)));
        assert(p99<.01,'X20:Latency','%s seed %d exceeds 10 ms single-window P99.',modelId,seed);
        resetError=NaN;
        if ismember(char(model.architecture),{'GRU','DSSM'})
            a=q.windows(:,:,1);b=q.windows(:,:,2);pa=position_stage1_model_forward_v2(model,a);
            position_stage1_model_forward_v2(model,b);pa2=position_stage1_model_forward_v2(model,a);
            resetError=max(abs(pa-pa2));assert(resetError<=1e-12,'X20:Reset','%s leaked state.',modelId);
        end
        z=struct('model_id',modelId,'seed',seed,'architecture',char(model.architecture), ...
            'fixture_count',N,'max_phi_abs_error',maxPhi,'max_output_abs_error_mps2',maxOutput, ...
            'inference_p99_ms',1000*p99,'window_reset_max_abs_error',resetError,'plant_starts',0);
        if isempty(rows),rows=z;else,rows(end+1,1)=z;end %#ok<AGROW>
        export.status='MATLAB_PARITY_PASS';export.matlab_parity=z;
        fid=fopen(fullfile(package,'export_report.json'),'w');fwrite(fid,jsonencode(export,'PrettyPrint',true),'char');fclose(fid);
        fprintf('X20_PARITY %s seed=%d PASS phi=%.3g output=%.3g p99=%.3fms Plant=0\n', ...
            modelId,seed,maxPhi,maxOutput,z.inference_p99_ms);
    end
end
report=struct('status','PASS','models',rows,'plant_starts',0, ...
    'head_contract','FEATURE gamma=12 kappa=1 PCF=true; position RBF disabled; original B attitude RBF unchanged');
path=fullfile(out,'reports','x20_extension_zero_plant_parity.json');
fid=fopen(path,'w');fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fclose(fid);
fprintf('X20_ZERO_PLANT_PARITY PASS packages=%d fixtures_per_package=64 Plant=0\n',numel(rows));
end
