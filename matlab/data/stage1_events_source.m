function [T,closureMax]=stage1_events_from_log(log,scene,cfg,row,method,split,validEnd)
% Offline-only labels at the 100 Hz controller events. The model never receives these.
if nargin<7||isempty(validEnd),validEnd=inf;end
idx=find(double(log.rbf_position_event_dt(:))>0 & double(log.transition_time(:))<=validEnd);
assert(~isempty(idx),'POSADV:NoEvents','No valid 100-Hz position events for %s.',row.scene_id);
Pplant0=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));P0=controller_parameters(cfg,Pplant0,'fixed');
X=zeros(numel(idx),14);Y=zeros(numel(idx),3);parts=zeros(numel(idx),12);closure=zeros(numel(idx),1);
time=double(log.transition_time(idx));beta=min(max(time/cfg.rbf.position.beta_rise_time,0),1);
for q=1:numel(idx)
    k=idx(q);x=double(log.state(k,:)).';
    r=struct('position',double(log.reference.position(k,:)).', ...
        'velocity',double(log.reference.velocity(k,:)).','acceleration',double(log.reference.acceleration(k,:)).', ...
        'yaw',double(log.reference.yaw(k)),'yaw_rate',double(log.reference.yaw_rate(k)), ...
        'yaw_acceleration',double(log.reference.yaw_acceleration(k)));
    [~,preview]=position_bs_step(x,r,zeros(3,1),P0);
    [thrust,~,~]=baseline_force_to_attitude(preview.commanded_acceleration,x(9),P0);
    X(q,:)=[preview.error(:);preview.surface(:);x(7:9);thrust/P0.mass;double(scene.arms.command(k,:).')].';
    if startsWith(string(method),'N_')||strcmp(method,'HEAD_FROZEN')
        applied=double(log.stage1_position_applied_acceleration_mps2(k,:)).';
        logged=double(log.stage1_position_feature_14(k,:)).';
        assert(max(abs(logged-X(q,:).'))<=1e-12,'POSADV:FeatureParity','Candidate logged feature differs from offline reconstruction.');
    elseif strcmp(method,'B')
        applied=double(log.position_rbf_estimate_acceleration_mps2(k,:)).';
    else
        applied=zeros(3,1);
    end
    aVirtual=preview.nominal_acceleration-applied;
    Ptrue=simulation_parameters(cfg,scene.arms.rho_true(k,:).',scene.arms.rhoDot_true(k,:).');
    d=vehicle_derivative(x,double(log.realized_generalized(k,:)).', ...
        double(log.wind_force_I(k,:)).',double(log.wind_torque_B(k,:)).',Ptrue);
    aTrue=d(4:6);
    y=aTrue-aVirtual;
    Treq=double(log.controller_clipped_generalized(k,1));Treal=double(log.realized_generalized(k,1));
    Ractual=rot_zyx(x(7:9));Rraw=rot_zyx(double(log.raw_outer_attitude(k,:)).');e3=[0;0;1];
    dWind=double(log.wind_force_I(k,:)).'/Ptrue.mass;
    dAlloc=Ractual*e3*(Treal-Treq)/Ptrue.mass;
    dAtt=(Ractual-Rraw)*e3*Treq/Ptrue.mass;
    dMap=Rraw*e3*Treq/Ptrue.mass-[0;0;Ptrue.g]-aVirtual;
    check=dWind+dAlloc+dAtt+dMap;
    Y(q,:)=y.';parts(q,:)=[dWind;dAlloc;dAtt;dMap].';closure(q)=max(abs(y-check));
end
assert(all(isfinite(X),'all')&&all(isfinite(Y),'all')&&max(closure)<=1e-9, ...
    'POSADV:LabelClosure','Nonfinite data or label decomposition closure exceeds 1e-9 m/s^2.');
closureMax=max(closure);
phase=classify_phase(scene,time,double(row.class_index));
T=table();T.scene_id=repmat(string(row.scene_id),numel(idx),1);T.method=repmat(string(method),numel(idx),1);
T.split=repmat(string(split),numel(idx),1);T.class_index=repmat(double(row.class_index),numel(idx),1);
T.class_id=repmat(string(row.class_id),numel(idx),1);
role=string(method);if startsWith(role,"N_")||role=="HEAD_FROZEN",role="STUDENT";end
T.source_role=repmat(role,numel(idx),1);
T.event_time_s=time;T.beta=beta;T.phase=phase;
T.run_status=repmat(string(log.status),numel(idx),1);
T.complete=repmat(string(log.status)=="STABLE"&&numel(log.transition_time)==20000,numel(idx),1);
T.valid_prefix_end_s=repmat(min(double(log.transition_time(end)),double(validEnd)),numel(idx),1);T.label_closure_max_abs_mps2=closure;
T.safe_prefix_eligible=repmat(startsWith(string(log.status),"SAFE_STOP_")&&~T.complete(1),numel(idx),1);
T.target_raw_1=Y(:,1);T.target_raw_2=Y(:,2);T.target_raw_3=Y(:,3);
T.target_clip_1=max(min(Y(:,1),3),-3);T.target_clip_2=max(min(Y(:,2),3),-3);T.target_clip_3=max(min(Y(:,3),3),-3);
T.d_wind_1=parts(:,1);T.d_wind_2=parts(:,2);T.d_wind_3=parts(:,3);
T.d_alloc_1=parts(:,4);T.d_alloc_2=parts(:,5);T.d_alloc_3=parts(:,6);
T.d_att_1=parts(:,7);T.d_att_2=parts(:,8);T.d_att_3=parts(:,9);
T.d_map_1=parts(:,10);T.d_map_2=parts(:,11);T.d_map_3=parts(:,12);
for j=1:14,T.(sprintf('input_%d',j))=X(:,j);end
end

function phase=classify_phase(scene,t,c)
n=numel(t);phase=repmat("STATIC",n,1);if c==0,return;end
cmd=double(scene.arms.command);rho=double(scene.arms.rho_true);
for i=1:n
    k=max(1,min(size(cmd,1),round(t(i)/median(diff(scene.time)))+1));
    if any(cmd(k,:)>0),phase(i)="EXTEND";
    elseif any(cmd(k,:)<0),phase(i)="RETRACT";
    elseif any(rho(k,:)>.150001),phase(i)="HOLD";
    elseif any(any(abs(cmd(1:k,:))>0)),phase(i)="RECOVERY";
    else,phase(i)="PRE";end
end
end

function R=rot_zyx(e)
phi=e(1);theta=e(2);psi=e(3);cp=cos(phi);sp=sin(phi);ct=cos(theta);st=sin(theta);cy=cos(psi);sy=sin(psi);
R=[cy*ct,cy*st*sp-sy*cp,cy*st*cp+sy*sp;sy*ct,sy*st*sp+cy*cp,sy*st*cp-cy*sp;-st,ct*sp,ct*cp];
end
