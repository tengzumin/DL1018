function report=run_official_selected_parity(root,models,reportName)
% Zero-Plant Python/MATLAB parity for official best/final packages.
if nargin<2||isempty(models),models={'MLP14','GRU14'};end
if nargin<3||isempty(reportName),reportName='official_selected_zero_plant_parity.json';end
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','teacher_reuse_model_screen_v1');
local=fullfile(out,'local_runtime');addpath(local,'-begin');rehash;
seeds=[2026102001 2026102002];variants={'best_teacher_val','final_step'};rows=struct([]);
for mi=1:numel(models)
    for si=1:numel(seeds)
        for vi=1:numel(variants)
            modelId=models{mi};seed=seeds(si);variant=variants{vi};
            package=fullfile(out,'models','official_export',modelId,sprintf('seed%d',seed),variant);
            export=jsondecode(fileread(fullfile(package,'export_report.json')));
            assert(strcmp(export.status,'EXPORTED_AWAITING_MATLAB_PARITY')&&export.fixture_count==64, ...
                'OFFICIAL:Export','Missing 64-window export: %s seed %d %s.',modelId,seed,variant);
            q=load(fullfile(package,'matlab_model_and_parity.mat'));model=q.model;N=double(q.fixture_count);
            maxPhi=0;maxOutput=0;
            for k=1:N
                phi=position_stage1_model_forward_v2(model,q.windows(:,:,k));y=double(model.output_W).'*phi;
                maxPhi=max(maxPhi,max(abs(phi-double(q.expected_phi(:,k)))));
                maxOutput=max(maxOutput,max(abs(y-double(q.expected_output(:,k)))));
            end
            assert(maxPhi<=1e-5&&maxOutput<=1e-5,'OFFICIAL:Parity', ...
                '%s seed %d %s parity failed: phi %.4g, output %.4g.',modelId,seed,variant,maxPhi,maxOutput);
            timings=zeros(256,1);
            for k=1:numel(timings)
                t=tic;position_stage1_model_forward_v2(model,q.windows(:,:,mod(k-1,N)+1));timings(k)=toc(t);
            end
            timings=sort(timings);p99=timings(ceil(.99*numel(timings)));
            assert(p99<.01,'OFFICIAL:Latency','%s seed %d %s exceeds 10 ms.',modelId,seed,variant);
            resetError=NaN;
            if strcmp(char(model.architecture),'GRU')
                a=q.windows(:,:,1);b=q.windows(:,:,2);pa=position_stage1_model_forward_v2(model,a);
                position_stage1_model_forward_v2(model,b);pa2=position_stage1_model_forward_v2(model,a);
                resetError=max(abs(pa-pa2));assert(resetError<=1e-12,'OFFICIAL:Reset','GRU state leaked.');
            end
            z=struct('model_id',modelId,'seed',seed,'checkpoint_kind',variant,'selected_step',double(model.selected_step), ...
                'fixture_count',N,'max_phi_abs_error',maxPhi,'max_output_abs_error_mps2',maxOutput, ...
                'inference_p99_ms',1000*p99,'window_reset_max_abs_error',resetError,'plant_starts',0);
            if isempty(rows),rows=z;else,rows(end+1,1)=z;end %#ok<AGROW>
            export.status='MATLAB_PARITY_PASS';export.matlab_parity=z;
            fid=fopen(fullfile(package,'export_report.json'),'w');fwrite(fid,jsonencode(export,'PrettyPrint',true),'char');fclose(fid);
            fprintf('OFFICIAL_PARITY %s seed=%d checkpoint=%s PASS phi=%.3g output=%.3g p99=%.3fms Plant=0\n', ...
                modelId,seed,variant,maxPhi,maxOutput,z.inference_p99_ms);
        end
    end
end
report=struct('status','PASS','packages',rows,'package_count',numel(rows),'plant_starts',0, ...
    'head_contract','FEATURE gamma=12 kappa=1 PCF=true; position RBF disabled; original B attitude RBF unchanged');
path=fullfile(out,'reports',reportName);
fid=fopen(path,'w');fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fclose(fid);
fprintf('OFFICIAL_SELECTED_PARITY PASS packages=%d fixtures_per_package=64 Plant=0\n',numel(rows));
end
