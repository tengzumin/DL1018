function result = audit_c524_runtime_reconstruction_v1()
% Independently reconstruct deployed CM18 output, clipping, beta and torque balance.
here=fileparts(mfilename('fullpath')); repoRoot=fileparts(fileparts(here));
reportDir=fullfile(repoRoot,'reports','attitude_cm18_c524_screen12_20261025');
outPath=fullfile(reportDir,'C524_RUNTIME_RECONSTRUCTION_v1.json');
assert(~isfile(outPath),'C524RuntimeAudit:NoOverwrite','Refusing to overwrite runtime audit.');
binding=jsondecode(fileread(fullfile(here,'C524_SCREEN12_BINDING_v1.json')));
modelPack=load(binding.model_path,'model'); model=modelPack.model;
addpath(fileparts(binding.forward_path),'-begin'); clear cm18_a1_forward_v1; rehash;
assert(strcmpi(which('cm18_a1_forward_v1'),binding.forward_path), ...
    'C524RuntimeAudit:ForwardPath','CM18 forward helper resolved outside the pinned source.');
rows=repmat(struct('scene_id','','forward_max_abs_error',0,'clip_max_abs_error',0, ...
    'held_acceleration_max_abs_error',0,'held_torque_max_abs_error',0, ...
    'torque_balance_max_abs_error',0,'c5_rbf_update_transition_count',0, ...
    'c5_rbf_event_count',0,'candidate_rbf_update_count',0),numel(binding.scene_ids),1);
for s=1:numel(binding.scene_ids)
    sceneId=char(binding.scene_ids{s}); audit=jsondecode(fileread(fullfile(reportDir,'scene_audits',[sceneId '_C524_AUDIT_v1.json'])));
    cand=load(audit.candidate_raw_path,'log','runStart'); c=cand.log; n=20000; dt=.001;
    event=logical(c.cm18_event_flag(:)); kEvent=find(event); X=double(c.cm18_event_input_18(event,:));
    observed=double(c.cm18_event_raw_acceleration_rad_s2(event,:));
    clippedLog=double(c.cm18_event_clipped_acceleration_rad_s2(event,:));
    direct=zeros(size(observed)); clip=zeros(size(observed));
    for e=1:numel(kEvent)
        direct(e,:)=cm18_a1_forward_v1(X(e,:),model);
        clip(e,:)=max(min(direct(e,:),double(c.cm18_dmax_rad_s2(:).')), ...
            -double(c.cm18_dmax_rad_s2(:).'));
    end
    eventBeta=min(kEvent*dt/double(c.cm18_beta_rise_time_s),1);
    heldAcc=zeros(n,3); heldTorque=zeros(n,3);
    beta=0; acc=zeros(1,3); tau=zeros(1,3); eventIx=1;
    for k=1:n
        if event(k)
            beta=eventBeta(eventIx); acc=beta*clip(eventIx,:);
            tau=(double(c.cm18_fixed_inertia_J0_kgm2)*acc(:)).'; eventIx=eventIx+1;
        end
        heldAcc(k,:)=acc; heldTorque(k,:)=tau;
    end
    nominal=double(c.attitude_bs_nominal_torque_Nm); requested=double(c.requested_generalized(:,2:4));
    observedTorque=double(c.cm18_compensation_torque_held_Nm);
    heldAcceleration=double(c.cm18_applied_acceleration_held_rad_s2);
    c5=load(audit.c5_rbf_raw_path,'log'); r=c5.log;
    update=logical(r.rbf_update_flag); rbfUpdates=sum(any(update,2));
    if isfield(r,'rbf_event_count'), rbfEventCount=double(r.rbf_event_count); else, rbfEventCount=NaN; end
    rbfCandidateUpdates=sum(any(logical(c.rbf_update_flag),2));
    torqueBalance=nominal-heldTorque;
    values=[max(abs(observed(:)-direct(:))),max(abs(clippedLog(:)-clip(:))), ...
        max(abs(heldAcceleration(:)-heldAcc(:))),max(abs(observedTorque(:)-heldTorque(:))), ...
        max(abs(requested(:)-torqueBalance(:)))];
    assert(numel(kEvent)==1999&&isequal(kEvent(:),(11:10:n).')&& ...
        values(1)<1e-9&&values(2)<1e-9&&values(3)<1e-9&&values(4)<1e-9&&values(5)<1e-9&& ...
        rbfUpdates>0&&rbfCandidateUpdates==0, ...
        'C524RuntimeAudit:Reconstruction','Runtime forward/control reconstruction failed for %s.',sceneId);
    rows(s)=struct('scene_id',sceneId,'forward_max_abs_error',values(1), ...
        'clip_max_abs_error',values(2),'held_acceleration_max_abs_error',values(3), ...
        'held_torque_max_abs_error',values(4),'torque_balance_max_abs_error',values(5), ...
        'c5_rbf_update_transition_count',rbfUpdates,'c5_rbf_event_count',rbfEventCount, ...
        'candidate_rbf_update_count',rbfCandidateUpdates);
end
result=struct('schema','CM18_C5_24_RUNTIME_RECONSTRUCTION_AUDIT_V1','status','PASS', ...
    'created_utc',utc_now(),'binding_sha256',sha256_file(fullfile(here,'C524_SCREEN12_BINDING_v1.json')), ...
    'scene_count',numel(rows),'total_cm18_events',1999*numel(rows), ...
    'max_forward_abs_error',max([rows.forward_max_abs_error]), ...
    'max_clip_abs_error',max([rows.clip_max_abs_error]), ...
    'max_held_acceleration_abs_error',max([rows.held_acceleration_max_abs_error]), ...
    'max_held_torque_abs_error',max([rows.held_torque_max_abs_error]), ...
    'max_tau_bs_minus_compensation_balance_error',max([rows.torque_balance_max_abs_error]), ...
    'matched_C5_RBF_update_transition_count_total',sum([rows.c5_rbf_update_transition_count]), ...
    'candidate_RBF_update_count_total',sum([rows.candidate_rbf_update_count]),'scenes',rows, ...
    'conclusion','The frozen model forward pass, limit, beta schedule, J0 torque, and tau_BS-minus-compensation wiring reproduce the logs; candidate RBF update count is zero while matched C5+RBF updates online.');
write_json_new(outPath,result);
fprintf('C524_RUNTIME_RECONSTRUCTION_PASS; forward=%.3g; torque_balance=%.3g; C5_RBF_updates=%d; candidate_RBF_updates=%d\n', ...
    result.max_forward_abs_error,result.max_tau_bs_minus_compensation_balance_error, ...
    result.matched_C5_RBF_update_transition_count_total,result.candidate_RBF_update_count_total);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r');
assert(fid>=0,'C524RuntimeAudit:Read','Cannot read %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(b); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json_new(path,value)
fid=fopen(path,'w'); assert(fid>=0,'C524RuntimeAudit:Write','Cannot create %s.',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(value),'char');
end
function t=utc_now()
t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end
