function report=diagnose_shared_basis()
here=fileparts(mfilename('fullpath'));study=fileparts(here);
out=fullfile(here,'SHARED_BASIS_DIAGNOSIS.json');assert(~isfile(out));
manifest=jsondecode(fileread(fullfile(study,'MANIFEST.json')));
release=jsondecode(fileread(fullfile(study,'RELEASE.json')));model=load(release.model_path);
S=double(model.target_rms(:));W0=[double(model.head_weight).';double(model.head_bias(:)).'];
rows=cell(6,1);baseError=0;cancelError=0;
for s=1:6
    id=manifest.records(s).scene_id;path=fullfile(study,'runs',id,'raw_run.mat');raw=load(path,'log');L=raw.log;
    events=find(~cellfun(@isempty,L.mlp15_attitude_trace));N=numel(events);
    weights=zeros(33,3,2);covariances=repmat(10*eye(33),1,1,2);
    previousPhi=zeros(33,2);previousBase=zeros(3,1);predictions=zeros(3,2);priorBeta=0;
    errors=zeros(N,3,2);mature=false(N,1);clipCount=zeros(1,2);projectCount=zeros(1,2);
    featureNorm=zeros(N,1);maxReplay=0;maxWeight=zeros(1,2);
    for i=1:N
        z=L.mlp15_attitude_trace{events(i)};d=z.causal_head;unit=double(d.phi(:));
        assert(unit(end)>0);psi=unit/unit(end);features=[unit,psi];
        base=double(d.base_residual_rad_s2(:));featureNorm(i)=norm(psi);
        baseError=max(baseError,max(abs(base-S.*(W0.'*psi))));
        cancelError=max(cancelError,max(abs(base+S.*((-W0).'*psi))));
        current=zeros(3,2);
        for j=1:2
            y=base+S.*(weights(:,:,j).'*features(:,j));
            clipCount(j)=clipCount(j)+any(abs(y)>[45;45;4.7124]);
            current(:,j)=double(z.beta)*min(max(y,-[45;45;4.7124]),[45;45;4.7124]);
            if j==1,maxReplay=max(maxReplay,max(abs(y-double(z.raw_residual_rad_s2(:)))));end
        end
        if i>1&&priorBeta>=1&&z.beta>=1
            mature(i)=true;observed=double(d.observation_residual_rad_s2(:));
            for j=1:2
                errors(i,:,j)=(observed-predictions(:,j)).';f=previousPhi(:,j);
                P=covariances(:,:,j)/.999;K=(P*f)/(1+f.'*P*f);W=weights(:,:,j);
                W=W+K*(observed./S-previousBase-W.'*f).';magnitude=norm(W,'fro');
                if magnitude>20,W=W*(20/magnitude);projectCount(j)=projectCount(j)+1;end
                A=eye(33)-K*f.';P=A*P*A.'+K*K.';P=(P+P.')/2;
                [~,flag]=chol(P);assert(flag==0);covariances(:,:,j)=P;weights(:,:,j)=W;
                maxWeight(j)=max(maxWeight(j),norm(W,'fro'));
            end
        end
        predictions=current;previousPhi=features;previousBase=base./S;priorBeta=z.beta;
    end
    assert(maxReplay<1e-7);rmse=zeros(1,2);
    for j=1:2,e=errors(mature,:,j);rmse(j)=sqrt(mean(sum(e.^2,2)));end
    rows{s}=struct('scene_id',id,'raw_sha256',hash_file(path), ...
        'normalized_correction_RMSE_rad_s2',rmse(1),'shared_basis_RMSE_rad_s2',rmse(2), ...
        'reduction_fraction',1-rmse(2)/rmse(1),'feature_psi_norm_min_max',[min(featureNorm),max(featureNorm)], ...
        'dmax_clipped_events_normalized_then_shared',clipCount, ...
        'weight_projection_events_normalized_then_shared',projectCount, ...
        'maximum_weight_norm_normalized_then_shared',maxWeight);
end
rows=[rows{:}];old=sqrt(mean([rows.normalized_correction_RMSE_rad_s2].^2));
shared=sqrt(mean([rows.shared_basis_RMSE_rad_s2].^2));
windless=endsWith(string({rows.scene_id}),'W15');quiet=rows(strcmp({rows.scene_id},'DL1018_VAL_T3_C00_W13'));
passed=shared<=.8*old&&all([rows(windless).reduction_fraction]>=-.05)&& ...
    quiet.reduction_fraction>=.8&&all(arrayfun(@(r)r.dmax_clipped_events_normalized_then_shared(2)<= ...
    r.dmax_clipped_events_normalized_then_shared(1),rows));
assert(baseError<1e-9&&cancelError<1e-9);
report=struct('schema','SHARED_HIDDEN_BASIS_DIAGNOSIS_V1','screen_gate_passed',passed, ...
    'Plant_calls',0,'TEST_read',false,'pooled_normalized_correction_RMSE_rad_s2',old, ...
    'pooled_shared_basis_RMSE_rad_s2',shared,'frozen_head_weight_norm',norm(W0,'fro'), ...
    'max_frozen_output_reconstruction_error_rad_s2',baseError,'max_exact_prior_cancellation_error_rad_s2',cancelError, ...
    'rows',rows,'source_script_sha256',hash_file([mfilename('fullpath') '.m']), ...
    'taskbook_sha256',hash_file(fullfile(here,'BASIS_CONSISTENCY_TASKBOOK.md')), ...
    'interpretation','A recorded-state parameterization diagnostic; not a shared-basis closed-loop result.');
fid=fopen(out,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));disp(report);
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
