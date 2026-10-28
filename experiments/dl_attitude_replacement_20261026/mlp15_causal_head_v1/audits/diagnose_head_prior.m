function report=diagnose_head_prior()
% Recorded-state prior ablation. No rollout, no new labels, no future updates.
here=fileparts(mfilename('fullpath'));study=fileparts(here);
out=fullfile(here,'FIXED_STATE_PRIOR_DIAGNOSIS.json');assert(~isfile(out));
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));
release=jsondecode(fileread(fullfile(study,'RELEASE.json')));model=load(release.model_path);
scale=double(model.target_rms(:));rows=cell(6,1);
for s=1:6
    id=manifest.records(s).scene_id;path=fullfile(study,'runs',id,'raw_run.mat');raw=load(path,'log');L=raw.log;
    events=find(~cellfun(@isempty,L.mlp15_attitude_trace));N=numel(events);
    W=zeros(33,3,2);P=10*eye(33);lastPhi=zeros(33,1);lastBase=zeros(3,1);
    predictions=zeros(3,2);errors=zeros(N,3,2);mature=false(N,1);priorBeta=0;
    clipping=zeros(1,2);projections=zeros(1,2);maxNorm=zeros(1,2);maxReplay=0;
    for i=1:N
        z=L.mlp15_attitude_trace{events(i)};d=z.causal_head;
        base=double(d.base_residual_rad_s2(:));phi=double(d.phi(:));current=zeros(3,2);
        priors=[base,zeros(3,1)];
        for j=1:2
            y=priors(:,j)+scale.*(W(:,:,j).'*phi);
            clipping(j)=clipping(j)+any(abs(y)>[45;45;4.7124]);
            current(:,j)=double(z.beta)*min(max(y,-[45;45;4.7124]),[45;45;4.7124]);
            if j==1,maxReplay=max(maxReplay,max(abs(y-double(z.raw_residual_rad_s2(:)))));end
        end
        if i>1&&priorBeta>=1&&z.beta>=1
            mature(i)=true;observed=double(d.observation_residual_rad_s2(:));
            priorP=P/.999;K=(priorP*lastPhi)/(1+lastPhi.'*priorP*lastPhi);
            for j=1:2
                errors(i,:,j)=(observed-predictions(:,j)).';
                prior=zeros(3,1);if j==1,prior=lastBase;end
                next=W(:,:,j)+K*(observed./scale-prior-W(:,:,j).'*lastPhi).';
                value=norm(next,'fro');
                if value>20,next=next*(20/value);projections(j)=projections(j)+1;end
                W(:,:,j)=next;maxNorm(j)=max(maxNorm(j),norm(next,'fro'));
            end
            A=eye(33)-K*lastPhi.';P=A*priorP*A.'+K*K.';P=(P+P.')/2;
            [~,flag]=chol(P);assert(flag==0);
        end
        predictions=current;lastPhi=phi;lastBase=base./scale;priorBeta=z.beta;
    end
    assert(maxReplay<1e-7);rmse=zeros(1,2);axisRMSE=zeros(2,3);
    for j=1:2
        e=errors(mature,:,j);rmse(j)=sqrt(mean(sum(e.^2,2)));axisRMSE(j,:)=sqrt(mean(e.^2,1));
    end
    rows{s}=struct('scene_id',id,'raw_sha256',hash_file(path), ...
        'recorded_prior_RMSE_rad_s2',rmse(1),'zero_prior_RMSE_rad_s2',rmse(2), ...
        'zero_prior_reduction_fraction',1-rmse(2)/rmse(1), ...
        'axis_RMSE_recorded_then_zero_rad_s2',axisRMSE,'head_weight_max_norm',maxNorm, ...
        'weight_projection_count',projections,'dmax_clipped_event_count',clipping, ...
        'recorded_replay_max_abs_error_rad_s2',maxReplay);
end
rows=[rows{:}];windless=endsWith(string({rows.scene_id}),'W15');
pooledOld=sqrt(mean([rows.recorded_prior_RMSE_rad_s2].^2));
pooledNew=sqrt(mean([rows.zero_prior_RMSE_rad_s2].^2));
passed=pooledNew<pooledOld&&all([rows(windless).zero_prior_reduction_fraction]>=.10)&& ...
    all(arrayfun(@(r)r.dmax_clipped_event_count(2)<=r.dmax_clipped_event_count(1),rows));
report=struct('schema','FIXED_STATE_PRIOR_DIAGNOSIS_V1','screen_gate_passed',passed, ...
    'Plant_calls',0,'TEST_read',false,'pooled_recorded_RMSE_rad_s2',pooledOld, ...
    'pooled_zero_prior_RMSE_rad_s2',pooledNew,'rows',rows, ...
    'interpretation','Recorded-state capacity/prediction diagnostic only. No zero-prior closed-loop result exists yet.', ...
    'taskbook_sha256',hash_file(fullfile(here,'PRIOR_DIAGNOSIS_TASKBOOK.md')), ...
    'source_script_sha256',hash_file([mfilename('fullpath') '.m']));
fid=fopen(out,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));disp(report);
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
