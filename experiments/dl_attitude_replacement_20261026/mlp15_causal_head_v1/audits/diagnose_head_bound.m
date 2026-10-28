function report=diagnose_head_bound(sceneIds)
% Fixed-record replay isolates weight projection; it is not a closed-loop ablation.
here=fileparts(mfilename('fullpath'));study=fileparts(here);
out=fullfile(here,'FIXED_STATE_WEIGHT_BOUND_DIAGNOSIS.json');assert(~isfile(out));
release=jsondecode(fileread(fullfile(study,'RELEASE.json')));model=load(release.model_path);
scale=double(model.target_rms(:));rows=cell(numel(sceneIds),1);
for s=1:numel(sceneIds)
    id=char(sceneIds(s));path=fullfile(study,'runs',id,'raw_run.mat');raw=load(path,'log');L=raw.log;
    events=find(~cellfun(@isempty,L.mlp15_attitude_trace));N=numel(events);
    weights=cat(3,zeros(33,3),zeros(33,3));P=10*eye(33);
    error=zeros(N,3,3);predictions=zeros(3,3);lastPhi=zeros(33,1);lastBase=zeros(3,1);
    bounds=[20 Inf];maxWeight=zeros(1,2);clipCount=zeros(1,2);priorBeta=0;eligible=false(N,1);
    maxReplayDifference=0;
    for i=1:N
        z=L.mlp15_attitude_trace{events(i)};d=z.causal_head;
        base=double(d.base_residual_rad_s2(:));phi=double(d.phi(:));
        current=zeros(3,3);current(:,1)=double(z.beta)*min(max(base,-[45;45;4.7124]),[45;45;4.7124]);
        for j=1:2
            y=base+scale.*(weights(:,:,j).'*phi);
            clipCount(j)=clipCount(j)+any(abs(y)>[45;45;4.7124]);
            current(:,j+1)=double(z.beta)*min(max(y,-[45;45;4.7124]),[45;45;4.7124]);
            if j==1
                maxReplayDifference=max(maxReplayDifference,max(abs(y-double(z.raw_residual_rad_s2(:)))));
            end
        end
        if i>1&&priorBeta>=1&&z.beta>=1
            eligible(i)=true;observed=double(d.observation_residual_rad_s2(:));
            for j=1:3,error(i,:,j)=(observed-predictions(:,j)).';end
            priorP=P/.999;K=(priorP*lastPhi)/(1+lastPhi.'*priorP*lastPhi);
            for j=1:2
                W=weights(:,:,j);W=W+K*(observed./scale-lastBase-W.'*lastPhi).';
                magnitude=norm(W,'fro');
                if magnitude>bounds(j),W=W*(bounds(j)/magnitude);end
                weights(:,:,j)=W;maxWeight(j)=max(maxWeight(j),norm(W,'fro'));
            end
            A=eye(33)-K*lastPhi.';P=A*priorP*A.'+K*K.';P=(P+P.')/2;
        end
        predictions=current;lastPhi=phi;lastBase=base./scale;priorBeta=z.beta;
    end
    assert(maxReplayDifference<1e-7);
    scores=zeros(1,3);axisScores=zeros(3,3);
    for j=1:3
        diff=error(eligible,:,j);scores(j)=sqrt(mean(sum(diff.^2,2)));
        axisScores(j,:)=sqrt(mean(diff.^2,1));
    end
    rows{s}=struct('scene_id',id,'raw_sha256',hash_file(path), ...
        'mature_previous_interval_prediction_vector_RMSE_rad_s2',scores, ...
        'mature_previous_interval_prediction_axis_RMSE_rad_s2',axisScores, ...
        'predictor_order',{{'frozen MLP','recorded bound20 head','unbounded offline head'}}, ...
        'max_head_weight_norm_bound20_and_unbounded',maxWeight, ...
        'dmax_clipped_events_bound20_and_unbounded',clipCount, ...
        'recorded_head_replay_max_abs_difference_rad_s2',maxReplayDifference);
end
report=struct('schema','FIXED_STATE_HEAD_BOUND_DIAGNOSIS_V1','Plant_calls',0,'TEST_read',false, ...
    'interpretation','All methods use the same recorded states and nominal residual labels. Unbounded replay is an offline diagnostic, not deployed or a causal closed-loop claim.', ...
    'rows',[rows{:}],'source_script_sha256',hash_file([mfilename('fullpath') '.m']));
fid=fopen(out,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));disp(report.rows);
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
