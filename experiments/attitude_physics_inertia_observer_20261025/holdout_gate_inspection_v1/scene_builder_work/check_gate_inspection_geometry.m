function report = check_gate_inspection_geometry(time,stateHistory,armLengths,cfg)
%CHECK_GATE_INSPECTION_GEOMETRY No-Plant configured-component gate proxy.
% stateHistory is N-by-12 Plant state [p_CoG,v,eulerZYX,omega]; p_CoG follows
% cfg.plant.state_position_reference. armLengths is N-by-4 true arm length.
% Component support bounds are exact for configured boxes/cylinders, then
% conservatively tested whenever their x-support overlaps the wall slab.
% Battery is only a point mass in distributed_v1 and has no envelope dimensions.

    if nargin<4 || isempty(cfg)
        cfg=default_config();
    end
    t=double(time(:)); X=double(stateHistory); rho=double(armLengths);
    if size(X,1)==12 && size(X,2)==numel(t), X=X.'; end
    assert(numel(t)>=2 && all(isfinite(t)) && all(diff(t)>0), ...
        'GateGeometry:Time','time must be finite and strictly increasing.');
    assert(isequal(size(X),[numel(t) 12]) && all(isfinite(X),'all'), ...
        'GateGeometry:State','stateHistory must be finite N-by-12.');
    assert(isequal(size(rho),[numel(t) 4]) && all(isfinite(rho),'all'), ...
        'GateGeometry:ArmLengths','armLengths must be finite N-by-4.');
    P=cfg.plant;
    assert(strcmp(P.mass_model,'distributed_v1') && ...
        strcmp(P.state_position_reference,'instantaneous_total_cog'), ...
        'GateGeometry:Reference','Checker requires the configured instantaneous total CoG reference.');
    assert(isfield(P,'vehicle_envelope') && ...
        abs(P.vehicle_envelope.rotor_physical_radius-.0635)<1e-12, ...
        'GateGeometry:RotorRadius','Geometry must bind vehicle_envelope.rotor_physical_radius=.0635 m.');
    assert(isfield(P.component_dimensions,'rotor') && ...
        isfield(P.component_dimensions.rotor,'height'), ...
        'GateGeometry:RotorHeight','Configured rotor height is required for disk proxy.');
    wall=struct('x',[-.10 .10],'y',[-.225 .225],'z',[.90 1.50]);
    n=numel(t); nComp=18;
    marginByComponent=nan(n,nComp);
    overlapAny=false(n,1);
    maxCogOffsetBody=0;
    componentNames = {'body','battery_point','arm1','arm2','arm3','arm4', ...
        'motor1','motor2','motor3','motor4','rotor_disk1','rotor_disk2', ...
        'rotor_disk3','rotor_disk4','servo1','servo2','servo3','servo4'};

    for k=1:n
        [cogBody,centers,orientations,kinds,dimensions,radii,heights] = ...
            configured_components(P,rho(k,:).');
        maxCogOffsetBody=max(maxCogOffsetBody,norm(cogBody));
        R=rotation_zyx(X(k,7:9).');
        cogI=X(k,1:3).';
        for j=1:nComp
            centerI=cogI+R*(centers(:,j)-cogBody);
            Rcomponent=R*orientations(:,:,j);
            halfExtent=component_half_extent(Rcomponent,kinds{j}, ...
                dimensions(:,j),radii(j),heights(j));
            lo=centerI-halfExtent; hi=centerI+halfExtent;
            inSlab=(lo(1)<=wall.x(2)+1e-12) && (hi(1)>=wall.x(1)-1e-12);
            if inSlab
                overlapAny(k)=true;
                marginByComponent(k,j)=min([lo(2)-wall.y(1),wall.y(2)-hi(2), ...
                    lo(3)-wall.z(1),wall.z(2)-hi(3)]);
            end
        end
    end

    sampleClearance=nan(n,1);
    for k=1:n
        valid=marginByComponent(k,isfinite(marginByComponent(k,:)));
        if ~isempty(valid), sampleClearance(k)=min(valid); end
    end
    [forward,reverse]=ordered_crossings(X(:,1),t,overlapAny,sampleClearance,wall.x);
    events=[forward;reverse];
    componentMinimum=repmat(struct('name','','clearance_m',NaN,'time_s',NaN),nComp,1);
    for j=1:nComp
        values=marginByComponent(:,j);
        q=find(isfinite(values));
        componentMinimum(j).name=componentNames{j};
        if ~isempty(q)
            [componentMinimum(j).clearance_m,ix]=min(values(q));
            componentMinimum(j).time_s=t(q(ix));
        end
    end
    report=struct('status','GEOMETRY_PROXY_CHECKED', ...
        'clearance_basis','configured-component proxy; exact configured box/cylinder support extents with conservative x-slab overlap test', ...
        'battery_envelope','point mass at body origin; physical battery dimensions are not configured', ...
        'rotor_radius_m',P.vehicle_envelope.rotor_physical_radius, ...
        'rotor_radius_status',P.vehicle_envelope.rotor_physical_radius_status, ...
        'max_abs_cog_offset_body_m',maxCogOffsetBody, ...
        'wall',wall,'events',events,'component_minimum_clearance',componentMinimum, ...
        'minimum_clearance_m',min([forward.minimum_clearance_m,reverse.minimum_clearance_m]), ...
        'pass_bidirectional',forward.complete&&reverse.complete, ...
        'pass_nonnegative_clearance',forward.minimum_clearance_m>=0&&reverse.minimum_clearance_m>=0, ...
        'pass_15mm_proxy',forward.minimum_clearance_m>=.015-1e-12&& ...
            reverse.minimum_clearance_m>=.015-1e-12, ...
        'contact_response_modelled',false,'no_plant_invocations',0);
end

function [cog,centers,Rparts,kinds,dims,radius,height] = configured_components(P,rho)
    m=P.component_masses; d=P.component_dimensions; angles=double(P.arm_angles(:).');
    directions=[cos(angles);sin(angles);zeros(1,4)];
    root=P.arm_root_radius;
    posBody=zeros(3,1); posBattery=zeros(3,1);
    posArm=directions.*(.5*(root+rho(:))).';
    posMotor=directions.*rho(:).';
    posRotor=posMotor;
    posServo=directions.*(root+.5*d.servo.length);
    totalMass=m.body+m.battery+4*(m.arm+m.motor+m.rotor+m.servo);
    assert(abs(totalMass-P.mass)<=1e-12,'GateGeometry:MassBalance', ...
        'Configured component masses do not sum to plant.mass.');
    cog=(m.body*posBody+m.battery*posBattery+m.arm*sum(posArm,2)+ ...
        m.motor*sum(posMotor,2)+m.rotor*sum(posRotor,2)+m.servo*sum(posServo,2))/totalMass;

    centers=zeros(3,18); Rparts=repmat(eye(3),1,1,18);
    kinds=cell(1,18); dims=zeros(3,18); radius=zeros(1,18); height=zeros(1,18);
    centers(:,1)=posBody; kinds{1}='box'; dims(:,1)=[d.body.length;d.body.width;d.body.height];
    centers(:,2)=posBattery; kinds{2}='point';
    for i=1:4
        Rz=[cos(angles(i)) -sin(angles(i)) 0;sin(angles(i)) cos(angles(i)) 0;0 0 1];
        ia=2+i; im=6+i; ir=10+i; is=14+i;
        centers(:,ia)=posArm(:,i); Rparts(:,:,ia)=Rz; kinds{ia}='box';
        dims(:,ia)=[rho(i)-root;d.arm.width;d.arm.height];
        centers(:,im)=posMotor(:,i); kinds{im}='cylinder';
        radius(im)=d.motor.radius; height(im)=d.motor.height;
        centers(:,ir)=posRotor(:,i); kinds{ir}='cylinder';
        radius(ir)=P.vehicle_envelope.rotor_physical_radius; height(ir)=d.rotor.height;
        centers(:,is)=posServo(:,i); Rparts(:,:,is)=Rz; kinds{is}='box';
        dims(:,is)=[d.servo.length;d.servo.width;d.servo.height];
    end
end

function extent = component_half_extent(R,kind,dims,radius,height)
    switch kind
        case 'point'
            extent=zeros(3,1);
        case 'box'
            extent=abs(R)*(dims(:)/2);
        case 'cylinder'
            extent=[radius*hypot(R(1,1),R(1,2))+.5*height*abs(R(1,3)); ...
                radius*hypot(R(2,1),R(2,2))+.5*height*abs(R(2,3)); ...
                radius*hypot(R(3,1),R(3,2))+.5*height*abs(R(3,3))];
        otherwise
            error('GateGeometry:Shape','Unsupported configured component shape %s.',kind);
    end
end

function [forward,reverse] = ordered_crossings(x,t,overlap,clearance,wallX)
    n=numel(t);
    forward=empty_event(1); reverse=empty_event(-1);
    iEnter=find(x(1:end-1)<=wallX(1) & x(2:end)>wallX(1),1,'first');
    if isempty(iEnter), return; end
    iFar=find((1:n-1)'>=iEnter & x(1:end-1)<wallX(2) & ...
        x(2:end)>=wallX(2),1,'first');
    if isempty(iFar), return; end
    forward=event_from_crossings(1,iEnter+1,iFar+1,x,t,overlap,clearance,wallX);
    after=max(iFar+1,1);
    iReturnEnter=find((1:n-1)'>=after & x(1:end-1)>=wallX(2) & ...
        x(2:end)<wallX(2),1,'first');
    if isempty(iReturnEnter), return; end
    iReturnFar=find((1:n-1)'>=iReturnEnter & x(1:end-1)>wallX(1) & ...
        x(2:end)<=wallX(1),1,'first');
    if isempty(iReturnFar), return; end
    reverse=event_from_crossings(-1,iReturnEnter+1,iReturnFar+1, ...
        x,t,overlap,clearance,wallX);
end

function event = event_from_crossings(direction,iEntry,iFar,x,t,overlap,clearance,wallX)
    n=numel(t); event=empty_event(direction);
    if ~any(overlap(iEntry:iFar)), return; end
    first=iEntry; while first>1 && overlap(first-1), first=first-1; end
    last=iFar; while last<n && overlap(last+1), last=last+1; end
    if ~all(overlap(first:last)), return; end
    values=clearance(first:last);
    if any(~isfinite(values)), return; end
    [minimum,ix]=min(values);
    if direction>0, farSide=x(last)>=wallX(2); else, farSide=x(last)<=wallX(1); end
    complete=last<n && ~overlap(last+1) && farSide;
    event=struct('direction',direction,'entry_time_s',t(iEntry), ...
        'far_plane_time_s',t(iFar),'complete',complete, ...
        'start_index',first,'end_index',last, ...
        'minimum_clearance_m',minimum,'minimum_clearance_time_s',t(first+ix-1));
end

function event = empty_event(direction)
    event=struct('direction',direction,'entry_time_s',NaN,'far_plane_time_s',NaN, ...
        'complete',false,'start_index',NaN,'end_index',NaN, ...
        'minimum_clearance_m',-Inf,'minimum_clearance_time_s',NaN);
end

function R=rotation_zyx(eta)
    phi=eta(1); theta=eta(2); psi=eta(3);
    cphi=cos(phi); sphi=sin(phi); ctheta=cos(theta); stheta=sin(theta);
    cpsi=cos(psi); spsi=sin(psi);
    R=[cpsi*ctheta,cpsi*stheta*sphi-spsi*cphi,cpsi*stheta*cphi+spsi*sphi; ...
        spsi*ctheta,spsi*stheta*sphi+cpsi*cphi,spsi*stheta*cphi-cpsi*sphi; ...
        -stheta,ctheta*sphi,ctheta*cphi];
end


