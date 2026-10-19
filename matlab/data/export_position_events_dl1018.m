function [E,meta]=export_position_events_dl1018(log,scene,cfg,collector,split,row)
% Export causal X14 windows and physical acceleration residuals from applied force.
assert(all(isfield(log,{'position_event_flag','position_compensation_applied_force_N', ...
    'position_compensation_applied_acceleration_mps2','position_nominal_acceleration_mps2', ...
    'position_commanded_force_N','realized_generalized','wind_force_I','wind_torque_B', ...
    'transition_time','state','reference'})), ...
    'DL1018:PositionLogFields','Canonical position event and applied-force fields are required.');
idx=find(log.position_event_flag(:));time=double(log.transition_time(:));
assert(~isempty(idx)&&numel(time)==size(log.state,1)-1&&all(diff(time)>0), ...
    'DL1018:PositionEvents','Position event schedule or Plant log lengths are invalid.');
Pplant0=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
P0=controller_parameters(cfg,Pplant0,'fixed');
N=numel(idx);X=zeros(N,14);Y=zeros(N,3);parts=zeros(N,12);closure=zeros(N,1);
appliedForce=double(log.position_compensation_applied_force_N(idx,:));
appliedAccel=double(log.position_compensation_applied_acceleration_mps2(idx,:));
assert(max(abs(appliedAccel-appliedForce/P0.mass),[],'all')<=1e-12, ...
    'DL1018:PositionAppliedUnits','Applied force and acceleration logs do not close.');
if isfield(log,'position_event_beta'),beta=double(log.position_event_beta(idx));else,beta=nan(N,1);end
for q=1:N
    k=idx(q);x=double(log.state(k,:)).';
    r=struct('position',double(log.reference.position(k,:)).', ...
        'velocity',double(log.reference.velocity(k,:)).', ...
        'acceleration',double(log.reference.acceleration(k,:)).', ...
        'yaw',double(log.reference.yaw(k)),'yaw_rate',double(log.reference.yaw_rate(k)), ...
        'yaw_acceleration',double(log.reference.yaw_acceleration(k)));
    [~,preview]=position_bs_step(x,r,zeros(3,1),P0);
    [thrust,~,~]=baseline_force_to_attitude(preview.commanded_acceleration,x(9),P0);
    X(q,:)=[preview.error(:);preview.surface(:);x(7:9);thrust/P0.mass; ...
        double(scene.arms.command(k,:).')].';
    if isfield(log,'stage1_position_event')&&logical(log.stage1_position_event(k))
        logged=double(log.stage1_position_feature_14(k,:)).';
        assert(max(abs(logged-X(q,:).'))<=1e-12, ...
            'DL1018:PositionFeatureParity','Logged position KAN feature differs from X14 replay.');
    end
    nominalAccel=double(log.position_nominal_acceleration_mps2(k,:)).';
    applied=double(log.position_compensation_applied_acceleration_mps2(k,:)).';
    forceCmd=double(log.position_commanded_force_N(k,:)).';
    closure(q)=max([abs(nominalAccel-preview.nominal_acceleration(:)); ...
        abs(forceCmd-(P0.mass*nominalAccel-double(appliedForce(q,:)).'))]);
    Ptrue=simulation_parameters(cfg,double(scene.arms.rho_true(k,:)).', ...
        double(scene.arms.rhoDot_true(k,:)).');
    dx=vehicle_derivative(x,double(log.realized_generalized(k,:)).', ...
        double(log.wind_force_I(k,:)).',double(log.wind_torque_B(k,:)).',Ptrue);
    y=dx(4:6)-(preview.nominal_acceleration(:)-applied);
    Treq=double(log.controller_clipped_generalized(k,1));
    Treal=double(log.realized_generalized(k,1));
    Ractual=rot_zyx(x(7:9));Rraw=rot_zyx(double(log.raw_outer_attitude(k,:)).');e3=[0;0;1];
    dWind=double(log.wind_force_I(k,:)).'/Ptrue.mass;
    dAlloc=Ractual*e3*(Treal-Treq)/Ptrue.mass;
    dAtt=(Ractual-Rraw)*e3*Treq/Ptrue.mass;
    dMap=Rraw*e3*Treq/Ptrue.mass-[0;0;Ptrue.g]-(preview.nominal_acceleration(:)-applied);
    check=dWind+dAlloc+dAtt+dMap;
    Y(q,:)=y.';parts(q,:)=[dWind;dAlloc;dAtt;dMap].';
    closure(q)=max(closure(q),max(abs(y-check)));
end
assert(all(isfinite([X(:);Y(:)]))&&max(closure)<=1e-9, ...
    'DL1018:PositionLabelClosure','Position label decomposition or applied-force closure failed.');
phase=classify_phase(scene,time(idx));
E=table();E.scene_id=repmat(string(row.scene_id),N,1);E.split=repmat(string(split),N,1);
E.collector=repmat(string(collector),N,1);E.event_index=(1:N).';E.plant_index=idx;
E.event_time_s=time(idx);E.beta=beta;E.ready=E.event_index>=32;E.phase=phase;
E.phase_code=phase_code(phase);
E.applied_force_x_N=appliedForce(:,1);E.applied_force_y_N=appliedForce(:,2);E.applied_force_z_N=appliedForce(:,3);
E.applied_compensation_1=appliedAccel(:,1);E.applied_compensation_2=appliedAccel(:,2);E.applied_compensation_3=appliedAccel(:,3);
E.target_raw_1=Y(:,1);E.target_raw_2=Y(:,2);E.target_raw_3=Y(:,3);
E.target_clip_1=max(min(Y(:,1),3),-3);E.target_clip_2=max(min(Y(:,2),3),-3);E.target_clip_3=max(min(Y(:,3),3),-3);
E.label_closure_max_abs_mps2=closure;
for j=1:14,E.(sprintf('x14_%d',j))=X(:,j);end
meta=struct('event_count',N,'ready_count',nnz(E.ready), ...
    'max_applied_force_acceleration_error_mps2',max(abs(appliedAccel-appliedForce/P0.mass),[],'all'), ...
    'max_label_closure_mps2',max(closure));
end

function phase=classify_phase(scene,t)
cmd=double(scene.arms.command);rho=double(scene.arms.rho_true);dt=median(diff(double(scene.time(:))));
phase=strings(numel(t),1);
for i=1:numel(t)
    k=max(1,min(size(cmd,1),round(t(i)/dt)+1));
    if ~any(abs(cmd(:))>0)
        phase(i)="STATIC";
    elseif any(cmd(k,:)>0)
        phase(i)="EXTEND";
    elseif any(cmd(k,:)<0)
        phase(i)="RETRACT";
    elseif any(rho(k,:)>.150001)
        phase(i)="HOLD";
    elseif any(any(abs(cmd(1:k,:))>0))&&~any(any(abs(cmd(k:end,:))>0))
        phase(i)="RECOVERY";
    else
        phase(i)="PRE";
    end
end
end

function code=phase_code(phase)
levels=["STATIC","PRE","EXTEND","HOLD","RETRACT","RECOVERY"];
[found,code]=ismember(phase,levels);assert(all(found),'DL1018:PhaseCode','Unknown phase label.');
code=uint8(code-1);
end

function R=rot_zyx(e)
phi=e(1);theta=e(2);psi=e(3);cp=cos(phi);sp=sin(phi);ct=cos(theta);st=sin(theta);cy=cos(psi);sy=sin(psi);
R=[cy*ct,cy*st*sp-sy*cp,cy*st*cp+sy*sp; ...
    sy*ct,sy*st*sp+cy*cp,sy*st*cp-cy*sp;-st,ct*sp,ct*cp];
end
