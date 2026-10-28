function report=audit_ghp7_force_demand_v2()
% Offline reconstruction of command limits and feedback/compensation demands.
here=fileparts(mfilename('fullpath'));task=fileparts(here);research=fileparts(task);
project=fileparts(fileparts(research));
out=fullfile(here,'GHP7_FORCE_DEMAND_AUDIT_v2.json');
assert(~isfile(out),'Demand:Exists','Preserve the existing audit output.');
currentPath=fullfile(here,'GHP7_BALANCED_SIX_SCENE_RAW_AUDIT_v1.json');
baselinePath=fullfile(research,'MLP15_GHP7_SCORE_RECOMPUTE_AUDIT_v1.json');
current=jsondecode(fileread(currentPath));baseline=jsondecode(fileread(baselinePath));
receiptPath=fullfile(project,'experiments','attitude_physics_inertia_observer_20261025', ...
    'holdout_gate_inspection_v2','C5_R_TASK_BINDING_PILOT_RECEIPT_v5.json');
receipt=jsondecode(fileread(receiptPath));record=receipt.input_records.c5_snapshot_mat;
assert(strcmpi(hash_file(record.path),record.sha256),'Demand:Snapshot','Snapshot identity changed.');
snapshot=load(record.path,'cfg');cfg=snapshot.cfg;
mass=double(cfg.plant.mass);gravity=double(cfg.plant.g);
k1=double(cfg.control.bs.position.k1(:)).';k2=double(cfg.control.bs.position.k2(:)).';
limit=double(cfg.control.limits.max_tilt);
assert(abs(limit-pi/6)<1e-12&&abs(double(cfg.plant.dt)-.001)<1e-12);
sceneId='DL1018_GHP7_G2_W00';
c=current.rows(strcmp({current.rows.scene_id},sceneId));
b=baseline.rows(strcmp({baseline.rows.scene_id},sceneId)&strcmp({baseline.rows.method},'B'));
c5=baseline.rows(strcmp({baseline.rows.scene_id},sceneId)&strcmp({baseline.rows.method},'C5_RBF'));
inputs={c,b,c5};names={'BALANCED_MLP15','B','C5_RBF'};logs=cell(1,3);packs=cell(1,3);rows=cell(1,3);
for i=1:3
    input=inputs{i};sha=hash_file(input.raw_path);
    assert(strcmpi(sha,input.raw_sha256),'Demand:RawHash','Raw identity changed.');
    pack=load(input.raw_path,'log','scene');L=pack.log;n=numel(L.transition_time);
    assert(n==20000&&numel(L.time)==20001&&max(abs(diff(double(L.time))-.001))<1e-10);
    X=double(L.state(1:n,:));t=double(L.transition_time(:));
    refA=double(L.reference.acceleration(1:n,:));refP=double(L.reference.position(1:n,:));
    refV=double(L.reference.velocity(1:n,:));refYaw=double(L.reference.yaw(1:n));
    feedback=(refV-X(:,4:6)).*(k1+k2)+(refP-X(:,1:3)).*(1+k1.*k2);
    nominal=refA+feedback;
    compensation=-double(L.position_compensation_applied_force_N)/mass;
    command=double(L.position_commanded_force_N)/mass;
    errNom=max(abs(nominal-double(L.position_nominal_acceleration_mps2)),[],'all');
    errCmd=max(abs(command-(nominal+compensation)),[],'all');
    assert(errNom<1e-9&&errCmd<1e-9,'Demand:Decomposition','Position force accounting failed.');
    requested=tilt_demand(command,X(:,9),gravity);mask=requested>limit;
    assert(isequal(mask,logical(L.tilt_limited(:))),'Demand:Flag','Reconstructed tilt flags differ.');
    req=double(L.command_filter_acceleration_request_unclamped_rads2);
    applied=double(L.command_filter_acceleration_applied_rads2);
    accelLimit=double(cfg.control.command_filter.acceleration_limit(:)).';
    clipDelta=req-applied;
    filterError=max(abs(applied-min(max(req,-accelLimit),accelLimit)),[],'all');
    assert(filterError<1e-9,'Demand:Filter','Command filter clipping differs from snapshot.');
    filterMask=abs(clipDelta)>1e-10;
    ix=find(mask);[peak,peakIndex]=max(requested);
    row=struct('method',names{i},'raw_path',input.raw_path,'raw_sha256',sha, ...
        'scene_id',sceneId,'sample_dt_s',.001,'transition_count',n, ...
        'nominal_reconstruction_max_abs_mps2',errNom,'command_reconstruction_max_abs_mps2',errCmd, ...
        'tilt_flag_exact_match',true,'tilt_projection_samples',nnz(mask), ...
        'tilt_projection_total_sample_duration_s',nnz(mask)*.001, ...
        'first_tilt_projection_s',t(ix(1)),'last_tilt_projection_s',t(ix(end)), ...
        'maximum_requested_euler_norm_deg',peak*180/pi,'peak_requested_time_s',t(peakIndex), ...
        'reference_only_maximum_requested_euler_norm_deg',max(tilt_demand(refA,refYaw,gravity))*180/pi, ...
        'reference_only_projection_samples',nnz(tilt_demand(refA,refYaw,gravity)>limit), ...
        'BS_nominal_without_compensation_projection_samples',nnz(tilt_demand(nominal,X(:,9),gravity)>limit), ...
        'maximum_actual_physical_tilt_deg',max(acos(max(min(cos(X(:,7)).*cos(X(:,8)),1),-1)))*180/pi, ...
        'command_filter_clipped_samples_any_axis',nnz(any(filterMask,2)), ...
        'command_filter_clipped_axis_counts',sum(filterMask,1), ...
        'command_filter_requested_acceleration_peak_abs_rads2',max(abs(req),[],1), ...
        'command_filter_clip_delta_peak_abs_rads2',max(abs(clipDelta),[],1), ...
        'actual_to_filtered_reference_SO3_rmse_rad',attitude_rmse(X(:,7:9),double(L.filtered_attitude_reference)), ...
        'actual_to_outer_target_SO3_rmse_rad',attitude_rmse(X(:,7:9),double(L.command_filter_target_euler)), ...
        'filter_to_outer_target_SO3_rmse_rad',attitude_rmse(double(L.filtered_attitude_reference),double(L.command_filter_target_euler)), ...
        'peak_reference_acceleration_mps2',refA(peakIndex,:), ...
        'peak_tracking_feedback_acceleration_mps2',feedback(peakIndex,:), ...
        'peak_compensation_acceleration_mps2',compensation(peakIndex,:));
    rows{i}=row;logs{i}=L;packs{i}=pack;
end
for i=2:3
    for field={'time','initial_state','reference','arms','environment_wind_I'}
        f=field{1};assert(isequaln(packs{1}.scene.(f),packs{i}.scene.(f)), ...
            'Demand:Pair','Paired physical scene arrays differ: %s.',f);
    end
end
LC=logs{1};L5=logs{3};n=20000;
deltaTracking=-(double(LC.state(1:n,4:6))-double(L5.state(1:n,4:6))).*(k1+k2) ...
    -(double(LC.state(1:n,1:3))-double(L5.state(1:n,1:3))).*(1+k1.*k2);
deltaComp=-(double(LC.position_compensation_applied_force_N)-double(L5.position_compensation_applied_force_N))/mass;
deltaCommand=(double(LC.position_commanded_force_N)-double(L5.position_commanded_force_N))/mass;
residual=max(abs(deltaCommand-deltaTracking-deltaComp),[],'all');
assert(residual<1e-9,'Demand:PairDecomposition','Paired force difference does not close.');
maskC=logical(LC.tilt_limited);mask5=logical(L5.tilt_limited);
pair=struct('exact_force_delta_max_abs_residual_mps2',residual, ...
    'tracking_feedback_delta_rms_xyz_mps2',sqrt(mean(deltaTracking.^2,1)), ...
    'position_compensation_delta_rms_xyz_mps2',sqrt(mean(deltaComp.^2,1)), ...
    'both_tilt_projection_samples',nnz(maskC&mask5),'candidate_only_projection_samples',nnz(maskC&~mask5), ...
    'C5_only_projection_samples',nnz(mask5&~maskC), ...
    'interpretation','Exact algebraic accounting across recorded closed loops; not a component causal intervention.');
report=struct('schema','DL1018_GHP7_FORCE_DEMAND_AUDIT_V2','status','PASS_OFFLINE_ACCOUNTING', ...
    'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss''Z''')), ...
    'Plant_calls',0,'TEST_read',false,'source_script_sha256',hash_file([mfilename('fullpath') '.m']), ...
    'current_score_audit_sha256',hash_file(currentPath),'baseline_score_audit_sha256',hash_file(baselinePath), ...
    'snapshot_sha256',char(record.sha256),'mass_kg',mass,'gravity_mps2',gravity, ...
    'max_tilt_deg',limit*180/pi,'rows',[rows{:}],'candidate_vs_C5_force_accounting',pair);
fid=fopen(out,'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));clear cleanup;
disp(jsonencode(report,'PrettyPrint',true));
end

function value=tilt_demand(acceleration,yaw,gravity)
sf=acceleration;sf(:,3)=sf(:,3)+gravity;
A=cos(yaw).*sf(:,1)+sin(yaw).*sf(:,2);B=sin(yaw).*sf(:,1)-cos(yaw).*sf(:,2);
value=hypot(atan2(B,hypot(sf(:,3),A)),atan2(A,sf(:,3)));
end

function value=attitude_rmse(a,b)
qa=quaternion_zyx(a);qb=quaternion_zyx(b);
theta=2*acos(min(1,abs(sum(qa.*qb,2))));value=sqrt(mean(theta.^2));
end

function q=quaternion_zyx(e)
c=cos(e/2);s=sin(e/2);
q=[c(:,1).*c(:,2).*c(:,3)+s(:,1).*s(:,2).*s(:,3), ...
    s(:,1).*c(:,2).*c(:,3)-c(:,1).*s(:,2).*s(:,3), ...
    c(:,1).*s(:,2).*c(:,3)+s(:,1).*c(:,2).*s(:,3), ...
    c(:,1).*c(:,2).*s(:,3)-s(:,1).*s(:,2).*c(:,3)];
end

function h=hash_file(path)
fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
