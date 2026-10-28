function out = build_gate_inspection_scenes(action, varargin)
%BUILD_GATE_INSPECTION_SCENES Independent no-Plant GH48 / GHP6 scene builder.
% Actions: MANIFEST, PILOT [arm_mode,R_task], HOLDOUT [selected_comparator,arm_mode,R_task].
% HOLDOUT payloads are generated only by an explicit call after comparator selection.
% Battery is a configured point mass with no envelope; rotor disks use the
% configured .0635 m physical radius estimate, never inertia_equivalent_radius.

    root = project_root();
    core = fullfile(root,'matlab','core');
    addpath(core);
    assert_locked_sources(root);
    action = upper(char(string(action)));

    switch action
        case 'MANIFEST'
            out = manifest_v1();
        case 'PILOT'
            [armMode,Rtask,cfg] = parse_build_args(varargin,false);
            rows = manifest_rows('GHP6');
            out = build_payloads(rows,armMode,Rtask,cfg);
        case 'HOLDOUT'
            [armMode,Rtask,cfg] = parse_build_args(varargin,true);
            rows = manifest_rows('GH48');
            out = build_payloads(rows,armMode,Rtask,cfg);
        case 'SELF_CHECK'
            out = run_self_checks();
        otherwise
            error('GateScene:Action','Action must be MANIFEST, PILOT, or HOLDOUT.');
    end
end

function root = project_root()
    p = mfilename('fullpath');
    for k = 1:5, p = fileparts(p); end
    root = p;
    assert(isfolder(fullfile(root,'matlab','core')),'GateScene:ProjectRoot', ...
        'Could not resolve DL1018 project root from this builder.');
end

function [armMode,Rtask,cfg] = parse_build_args(args,requireComparator)
    armMode = 'ACTIVE';
    Rtask = [];
    cfg = [];
    if requireComparator
        assert(~isempty(args),'GateScene:ComparatorRequired', ...
            'HOLDOUT requires the pilot-selected FIXED_MIN or FIXED_BOUND15 comparator.');
        comparator = upper(char(string(args{1})));
        assert(ismember(comparator,{'FIXED_MIN','FIXED_BOUND15'}), ...
            'GateScene:ComparatorInvalid','Unsupported pilot-selected comparator.');
        args = args(2:end);
    end
    if ~isempty(args), armMode = upper(char(string(args{1}))); end
    if numel(args)>1, Rtask = args{2}; end
    if numel(args)>2, cfg = args{3}; end
    if isempty(cfg), cfg = default_config(); end
    assert(isstruct(cfg)&&isfield(cfg,'plant')&&isfield(cfg.plant,'dt')&& ...
        abs(double(cfg.plant.dt)-.001)<1e-12, ...
        'GateScene:Cfg','cfg must be a valid locked 1 kHz configuration.');
    assert(ismember(armMode,{'ACTIVE','FIXED_MIN','FIXED_BOUND15','FIXED_WIDE'}), ...
        'GateScene:ArmMode','Unsupported gate_geometry_arm.');
    if ~isempty(Rtask)
        assert(isequal(size(Rtask),[3 3 20001]) && all(isfinite(Rtask(:))), ...
            'GateScene:RTask','R_task must be finite 3x3x20001.');
    end
end

function out = manifest_v1()
    holdout = manifest_rows('GH48');
    pilot = manifest_rows('GHP6');
    allRows = [holdout;pilot];
    ids = string({allRows.scene_id});
    seeds = [allRows.seed];
    assert(numel(holdout)==48 && numel(pilot)==6, ...
        'GateScene:ManifestCount','Manifest counts must be GH48 and GHP6.');
    assert(numel(unique(ids))==54 && numel(unique(seeds))==54 && ...
        all(seeds>=0 & seeds<2^31), ...
        'GateScene:ManifestIdentity','IDs/seeds must be unique and below 2^31.');
    out = struct('contract_id','DL1018_GATE_INSPECTION_HOLDOUT_V1', ...
        'status','DRAFT_UNAUDITED_ID_SEED_ONLY', ...
        'holdout',holdout,'pilot',pilot,'plant_calls',0, ...
        'external_lock_collision_audit','PENDING_ROOT_READ_ONLY_ID_SEED_AUDIT');
end

function rows = manifest_rows(role)
    rows = repmat(struct('scene_id','','role','','profile',0,'wind_index',0,'seed',0),0,1);
    for g = 1:3
        if strcmp(role,'GH48'), winds = 0:15; else, winds = [0 12]; end
        for w = winds
            if strcmp(role,'GH48')
                sceneId = sprintf('DL1018_GH48_G%d_W%02d',g,w);
                seed = 2100000000 + 1000*(g-1) + w;
            else
                sceneId = sprintf('DL1018_GHP6_G%d_W%02d',g,w);
                seed = 2050000000 + 1000*(g-1) + w;
            end
            rows(end+1,1) = struct('scene_id',sceneId,'role',role, ...
                'profile',g,'wind_index',w,'seed',seed); %#ok<AGROW>
        end
    end
end

function payloads = build_payloads(rows,armMode,Rtask,cfg)
    if nargin<4||isempty(cfg), cfg=default_config(); end
    t = (0:cfg.plant.dt:20).';
    assert(numel(t)==20001 && abs(t(2)-t(1)-.001)<1e-14, ...
        'GateScene:Timeline','Expected 20,001 samples at 1 ms.');
    payloads = cell(numel(rows),1);
    for i = 1:numel(rows)
        payloads{i} = build_one(rows(i),t,cfg,armMode,Rtask);
    end
end

function scene = build_one(row,t,cfg,armMode,Rtask)
    ref = gate_reference(t,row.profile);
    [wind,windSpec] = gate_wind(t,row,cfg);
    arms = gate_arms(t,cfg,armMode);
    scene = struct('reference_contract_id','DL1018_GATE_INSPECTION_HOLDOUT_V1', ...
        'scene_id',row.scene_id,'time',t, ...
        'initial_state',[ref.position(1,:).';ref.velocity(1,:).';0;0;0;0;0;0], ...
        'reference',ref,'arms',arms,'environment_wind_I',wind, ...
        'gate_geometry_arm',armMode,'R_task',Rtask, ...
        'R_task_sha256',numeric_sha256(Rtask), ...
        'R_task_status',ternary(isempty(Rtask),'PENDING_LOCKED_C5_BINDER','INJECTED_LOCKED_C5'), ...
        'metadata',struct('role',row.role,'profile',row.profile,'wind_index',row.wind_index, ...
            'seed',row.seed,'wind_spec',windSpec, ...
            'geometry_scope','configured-component proxy; battery is point-mass only; rotor radius is 5-inch estimate'));
    assert(scene.initial_state(1)==-1.5 && scene.initial_state(3)==1.2 && ...
        all(scene.initial_state(4:12)==0), ...
        'GateScene:InitialState','Initial state must equal the reference start with zero rates.');
    assert(isequal(size(scene.environment_wind_I),[20001 3]) && ...
        isequal(size(scene.arms.command),[20001 4]) && ...
        isequal(size(scene.arms.rho_true),[20001 4]) && ...
        isequal(size(scene.arms.rho_hat),[20001 4]) && ...
        isequal(size(scene.arms.rhoDot_true),[20001 4]) && ...
        isequal(size(scene.arms.rhoDot_hat),[20001 4]), ...
        'GateScene:PayloadShape','Scene arrays do not match the frozen interface.');
end

function ref = gate_reference(t,g)
    t = double(t(:));
    x = zeros(size(t)); vx = x; ax = x;
    q = zeros(size(t)); qp = q; qpp = q;
    forward = t<=6;
    u = t(forward)/6;
    q(forward) = smooth5(u);
    qp(forward) = smooth5_d1(u);
    qpp(forward) = smooth5_d2(u);
    x(forward) = -1.5 + 3*q(forward);
    vx(forward) = .5*qp(forward);
    ax(forward) = (3/36)*qpp(forward);
    reverse = t>=14;
    u = (t(reverse)-14)/6;
    q(reverse) = smooth5(u);
    qp(reverse) = smooth5_d1(u);
    qpp(reverse) = smooth5_d2(u);
    x(reverse) = 1.5 - 3*q(reverse);
    vx(reverse) = -.5*qp(reverse);
    ax(reverse) = -(3/36)*qpp(reverse);
    plateau = t>6 & t<14;
    x(plateau) = 1.5;

    y=zeros(size(t)); vy=y; ay=y; z=1.2+zeros(size(t)); vz=y; az=y;
    active = t>=8 & t<=12;
    u=(t(active)-8)/4;
    b1=sin(pi*u).^4;
    b1u=4*pi*sin(pi*u).^3.*cos(pi*u);
    b1uu=4*pi^2*sin(pi*u).^2.*(3*cos(pi*u).^2-sin(pi*u).^2);
    b2=sin(2*pi*u).^4;
    b2u=8*pi*sin(2*pi*u).^3.*cos(2*pi*u);
    b2uu=16*pi^2*sin(2*pi*u).^2.*(3*cos(2*pi*u).^2-sin(2*pi*u).^2);
    switch g
        case 1
            y(active)=.45*b1; vy(active)=.45*b1u/4; ay(active)=.45*b1uu/16;
        case 2
            y(active)=.35*b2; vy(active)=.35*b2u/4; ay(active)=.35*b2uu/16;
        case 3
            y(active)=.30*b1; vy(active)=.30*b1u/4; ay(active)=.30*b1uu/16;
            z(active)=1.2+.15*b1; vz(active)=.15*b1u/4; az(active)=.15*b1uu/16;
        otherwise
            error('GateScene:Profile','Profile must be G1, G2, or G3.');
    end
    ref=struct('position',[x y z],'velocity',[vx vy vz], ...
        'acceleration',[ax ay az],'yaw',zeros(size(t)), ...
        'yaw_rate',zeros(size(t)),'yaw_acceleration',zeros(size(t)));
end

function y = smooth5(u)
    y = 10*u.^3 - 15*u.^4 + 6*u.^5;
end
function y = smooth5_d1(u)
    y = 30*u.^2 - 60*u.^3 + 30*u.^4;
end
function y = smooth5_d2(u)
    y = 60*u - 180*u.^2 + 120*u.^3;
end

function [wind,spec] = gate_wind(t,row,cfg)
    g=row.profile; w=row.wind_index;
    azIndex=mod(3*(g-1)+5*mod(w,4)+7*w,8);
    azimuth_deg=45*azIndex;
    elevations=[-15 0 15];
    elevation_deg=elevations(1+mod((g-1)+2*w,3));
    az=deg2rad(azimuth_deg); el=deg2rad(elevation_deg);
    direction=[cos(el)*cos(az);cos(el)*sin(az);sin(el)];
    spec=struct('definition_id','DL1018_LOCKED_BIASED_DUAL_SINE_V1', ...
        'azimuth_index',azIndex,'azimuth_deg',azimuth_deg, ...
        'elevation_deg',elevation_deg,'direction_I',direction, ...
        'frequency_hz',[0 0],'amplitude_mps',[0 0], ...
        'phase_rad',[0 0],'rise_time_s',.8,'V0_mps',9, ...
        'rho_air_kg_m3',1.225,'CdBody',1,'CdArm',1, ...
        'source_sha256','88b500b0016225e21cde55fce0fbd6d54d0ffd2b34bed7a58f36d57e25b04f66');
    if w==15
        wind=zeros(numel(t),3);
        return
    end

    % Public discrete frequency/amplitude cells from make_scenes_dl1018,
    % re-declared here; phases are generated only from this new scene seed.
    frequencyCells=cat(3, ...
        [.20 .40;.50 .80;1.00 1.60;2.00 3.00;3.80 5.00], ...
        [.25 .45;.58 .87;1.15 1.75;2.20 3.20;3.70 4.80], ...
        [.30 .50;.65 .95;1.30 1.90;2.40 3.40;3.60 4.60]);
    amplitudeCells=[1.5 1.0;3.5 2.45;4.5 3.5];
    band=floor(w/3)+1; level=mod(w,3)+1;
    frequency=frequencyCells(band,:,g);
    amplitude=amplitudeCells(level,:);
    rs=RandStream('mt19937ar','Seed',double(row.seed));
    phase=2*pi*rand(rs,2,1);
    windCfg=struct('type','biased_dual_sine','direction',direction, ...
        'V0',9,'A1',amplitude(1),'f1',frequency(1),'phi1',phase(1), ...
        'A2',amplitude(2),'f2',frequency(2),'phi2',phase(2), ...
        'rise_time_s',.8,'rho_air',1.225,'CdBody',1,'CdArm',1);
    assert(strcmpi(char(java.io.File(which('wind_velocity_profile')).getCanonicalPath()), ...
        char(java.io.File(fullfile(project_root(),'matlab','core','wind_velocity_profile.m')).getCanonicalPath())), ...
        'GateScene:WindSourcePath','Wind helper resolved outside the locked core source.');
    [windT,detail]=wind_velocity_profile(t,windCfg);
    wind=windT.';
    spec.frequency_hz=frequency; spec.amplitude_mps=amplitude; spec.phase_rad=phase(:).';
    spec.wind_speed_peak_mps=max(abs(detail.speed));
    spec.wind_speed_rms_mps=sqrt(mean(detail.speed.^2));
    assert(all(isfinite(wind),'all') && max(abs(detail.speed))<18, ...
        'GateScene:WindBound','Wind must be finite and below the locked 18 m/s bound.');
end

function arms = gate_arms(t,cfg,mode)
    n=numel(t); command=zeros(n,4);
    switch mode
        case 'ACTIVE'
            command(t>=6 & t<8,:)=1;
            command(t>=13 & t<15,:)=-1;
            rho=.15*ones(n,1);
            q=t>6 & t<8; rho(q)=.15+.05*(t(q)-6);
            rho(t>=8 & t<=13)=.25;
            q=t>13 & t<15; rho(q)=.25-.05*(t(q)-13);
            rho(t>=15)=.15;
        case 'FIXED_MIN'
            rho=.15*ones(n,1);
        case 'FIXED_BOUND15'
            rhoStar=sqrt(2)*(.225-.0635-.015);
            rho=rhoStar*ones(n,1);
        case 'FIXED_WIDE'
            rho=.25*ones(n,1);
        otherwise
            error('GateScene:ArmMode','Unknown arm mode.');
    end
    rhoDot=.05*command;
    rhoHat=.15*ones(n,1);
    rhoHat(1)=rho(1);
    dt=t(2)-t(1);
    for k=1:n-1
        rhoHat(k+1)=min(max(rhoHat(k)+dt*rhoDot(k,1),.15),.25);
    end
    if ~strcmp(mode,'ACTIVE')
        rhoHat=rho;
        rhoDot(:)=0;
    end
    arms=struct('command',repmat(command(:,1),1,4), ...
        'rho_true',repmat(rho,1,4),'rho_hat',repmat(rhoHat,1,4), ...
        'rhoDot_true',repmat(rhoDot(:,1),1,4), ...
        'rhoDot_hat',repmat(rhoDot(:,1),1,4));
    assert(all(arms.rho_true>=.15-1e-12,'all') && ...
        all(arms.rho_true<=.25+1e-12,'all') && ...
        max(abs(arms.rho_hat-arms.rho_true),[],'all')<1e-12, ...
        'GateScene:ArmSchedule','Morphology command and length schedule are inconsistent.');
    if strcmp(mode,'ACTIVE') || strcmp(mode,'FIXED_MIN')
        assert(abs(arms.rho_true(end,1)-.15)<1e-12, ...
            'GateScene:ArmRetraction','ACTIVE/FIXED_MIN must finish at .15 m.');
    end
    if strcmp(mode,'FIXED_BOUND15')
        assert(all(arms.command==0,'all')&&all(arms.rhoDot_true==0,'all')&& ...
            max(abs(arms.rho_true-rhoStar),[],'all')<1e-12, ...
            'GateScene:FixedBound15','FIXED_BOUND15 must be a constant command-free shape.');
    elseif strcmp(mode,'FIXED_MIN')
        assert(all(arms.command==0,'all')&&all(arms.rho_true==.15,'all')&& ...
            all(arms.rhoDot_true==0,'all'),'GateScene:FixedMin','FIXED_MIN must be constant .15 m.');
    elseif strcmp(mode,'FIXED_WIDE')
        assert(all(arms.command==0,'all')&&all(arms.rho_true==.25,'all')&& ...
            all(arms.rhoDot_true==0,'all'),'GateScene:FixedWide','FIXED_WIDE is geometry-only .25 m.');
    end
end

function assert_locked_sources(root)
    core=fullfile(root,'matlab','core');
    expected={ ...
        'default_config.m','685abb7b72a335fdc826673e6431098fe79af88409f17b1b70ce08edb214dc51'; ...
        'distributed_mass_properties.m','db380b506e4bacc37bc398d5726c5ebd25be8ebc08b6c9e76ff59bc78fd45d3a'; ...
        'arm_directions.m','517bbfcd0df9526b189f64bff067a49551f573ad96e682ee005533ab510e686c'; ...
        'wind_velocity_profile.m','88b500b0016225e21cde55fce0fbd6d54d0ffd2b34bed7a58f36d57e25b04f66'};
    for k=1:size(expected,1)
        path=fullfile(core,expected{k,1});
        assert(isfile(path) && strcmpi(file_sha256(path),expected{k,2}), ...
            'GateScene:SourceLock','Locked geometry/wind source changed: %s.',expected{k,1});
    end
    for name={'default_config','wind_velocity_profile'}
        resolved=which(name{1});
        expectedPath=fullfile(core,[name{1} '.m']);
        assert(strcmpi(char(java.io.File(resolved).getCanonicalPath()), ...
            char(java.io.File(expectedPath).getCanonicalPath())), ...
            'GateScene:SourceResolution','Unexpected source resolved for %s.',name{1});
    end
end

function value = file_sha256(path)
    fid=fopen(path,'rb');
    assert(fid>=0,'GateScene:SourceRead','Cannot read locked source: %s.',path);
    bytes=fread(fid,inf,'*uint8'); fclose(fid);
    md=java.security.MessageDigest.getInstance('SHA-256');
    md.update(typecast(bytes(:),'int8'));
    digest=typecast(md.digest(),'uint8');
    value=lower(reshape(dec2hex(digest,2).',1,[]));
end

function value = numeric_sha256(array)
    if isempty(array), value=''; return; end
    bytes=typecast(double(array(:)),'uint8');
    md=java.security.MessageDigest.getInstance('SHA-256');
    md.update(typecast(bytes(:),'int8'));
    digest=typecast(md.digest(),'uint8');
    value=lower(reshape(dec2hex(digest,2).',1,[]));
end

function value = ternary(condition,a,b)
    if condition, value=a; else, value=b; end
end

function report = run_self_checks()
    cfg=default_config(); manifest=manifest_v1();
    assert(manifest.plant_calls==0,'GateScene:NoPlant','Self-check must not invoke Plant.');
    holdout=manifest.holdout; pilotRows=manifest.pilot;
    allRows=[holdout;pilotRows];
    assert(numel(unique(string({allRows.scene_id})))==54 && ...
        numel(unique([allRows.seed]))==54 && max([allRows.seed])<2^31, ...
        'GateScene:UniqueSeedCheck','GH48/GHP6 ID and seed checks failed.');
    assert(strcmp(holdout(1).scene_id,'DL1018_GH48_G1_W00') && ...
        strcmp(holdout(end).scene_id,'DL1018_GH48_G3_W15') && ...
        holdout(48).seed==2100002015 && pilotRows(6).seed==2050002012, ...
        'GateScene:ManifestFormula','Manifest boundary ID/seed formula changed.');

    pilots=build_payloads(pilotRows,'ACTIVE',[]);
    t=pilots{1}.time; dt=cfg.plant.dt;
    assert(numel(t)==20001 && abs(dt-.001)<1e-14 && ...
        abs(t(end)-20)<1e-14 && all(abs(diff(t)-dt)<1e-12), ...
        'GateScene:TimelineCheck','Expected 20 s, dt=1 ms, 20,001 states.');
    maxSpeed=0; maxAcceleration=0; maxTilt=0; maxThrust=0;
    totalThrust=4*cfg.plant.kf*cfg.plant.limits.motor_max^2;
    for g=1:3
        row=struct('scene_id',sprintf('SELF_W15_G%d',g),'role','CHECK', ...
            'profile',g,'wind_index',15,'seed',2100000000+1000*(g-1)+15);
        [zeroWind,~]=gate_wind(t,row,cfg);
        assert(all(zeroWind==0,'all'),'GateScene:W15ZeroWind','W15 must produce all-zero wind.');
        probe=gate_reference(t,g);
        assert(norm(probe.position(1,:)-[-1.5 0 1.2],inf)<1e-12 && ...
            norm(probe.position(end,:)-[-1.5 0 1.2],inf)<1e-12 && ...
            norm(probe.velocity([1 end],:),inf)<1e-12 && ...
            norm(probe.acceleration([1 end],:),inf)<1e-12, ...
            'GateScene:EndpointCheck','Trajectory endpoint position/rates are discontinuous.');
        keys=[0 6 8 12 14 20];
        for b=keys
            k=round(b/dt)+1;
            assert(max(abs(probe.velocity(k,:)))<1e-10 && ...
                max(abs(probe.acceleration(k,:)))<1e-9, ...
                'GateScene:C2Boundary','Piecewise trajectory rates must join continuously at %g s.',b);
            assert(abs(probe.position(k,1)-1.5)<1e-12 || ismember(b,[0 20]), ...
                'GateScene:BoundaryPosition','Longitudinal position is discontinuous at %g s.',b);
        end
        for b=[3 17]
            k=round(b/dt)+1;
            assert(abs(probe.position(k,1))<1e-12 && abs(probe.position(k,2))<1e-12 && ...
                abs(probe.position(k,3)-1.2)<1e-12, ...
                'GateScene:GateReference','Gate reference must be centered at t=%g s.',b);
        end
        a=probe.acceleration; v=probe.velocity;
        tilt=atan2(hypot(a(:,1),a(:,2)),cfg.plant.g+a(:,3));
        thrust=cfg.plant.mass*sqrt(a(:,1).^2+a(:,2).^2+(cfg.plant.g+a(:,3)).^2);
        maxSpeed=max(maxSpeed,max(vecnorm(v,2,2)));
        maxAcceleration=max(maxAcceleration,max(vecnorm(a,2,2)));
        maxTilt=max(maxTilt,max(tilt)); maxThrust=max(maxThrust,max(thrust));
    end
    assert(maxTilt<cfg.control.limits.max_tilt && maxThrust<totalThrust, ...
        'GateScene:NominalLimit','Nominal reference exceeds configured tilt or total-thrust bounds.');
    for i=1:numel(pilots)
        s=pilots{i};
        assert(strcmp(s.reference_contract_id,'DL1018_GATE_INSPECTION_HOLDOUT_V1') && ...
            strcmp(s.R_task_status,'PENDING_LOCKED_C5_BINDER') && ...
            strcmp(s.gate_geometry_arm,'ACTIVE'), ...
            'GateScene:PayloadContract','Pilot payload contract mismatch.');
        assert(s.arms.command(6001,1)==1 && abs(s.arms.rhoDot_true(6001,1)-.05)<1e-12 && ...
            abs(s.arms.rho_true(8001,1)-.25)<1e-12 && s.arms.command(8001,1)==0 && ...
            abs(s.arms.rho_true(13001,1)-.25)<1e-12 && s.arms.command(13001,1)==-1 && ...
            abs(s.arms.rho_true(15001,1)-.15)<1e-12 && s.arms.command(15001,1)==0, ...
            'GateScene:MorphSchedule','ACTIVE schedule must extend 6-8 s, hold 8-13 s, retract 13-15 s.');
    end

    rhoStar=sqrt(2)*(.225-.0635-.015);
    radii=[.15 rhoStar .25]; expected=.225-(radii/sqrt(2)+.0635);
    analytic=[2*(.15/sqrt(2)+.0635),2*(rhoStar/sqrt(2)+.0635), ...
        2*(.25/sqrt(2)+.0635)];
    assert(abs(rhoStar-.207182)<5e-7 && abs(expected(1)-.05543)<5e-5 && ...
        abs(expected(2)-.015)<1e-12 && expected(3)<0 && ...
        abs(analytic(1)-.33913)<5e-5 && abs(analytic(3)-.48060)<5e-5, ...
        'GateScene:AnalyticGeometry','Nominal arm-length boundary arithmetic changed.');
    probe=gate_reference(t,1);
    state=[probe.position probe.velocity zeros(numel(t),6)];
    geometry=cell(3,1);
    for j=1:3
        rho=repmat(radii(j),numel(t),4);
        geometry{j}=check_gate_inspection_geometry(t,state,rho,cfg);
        assert(geometry{j}.pass_bidirectional && ...
            abs(geometry{j}.minimum_clearance_m-expected(j))<5e-5, ...
            'GateScene:GeometryChecker','Synthetic bidirectional proxy mismatch at rho=%.6f.',radii(j));
    end
    assert(geometry{1}.max_abs_cog_offset_body_m<1e-12, ...
        'GateScene:SymmetricCog','Four synchronous equal arms must explicitly yield centered CoG.');
    asymState=state; asymState(:,7:9)=repmat([.08 -.05 .20],numel(t),1);
    asymRho=repmat([.15 .16 .17 .18],numel(t),1);
    rotatedGeometry=check_gate_inspection_geometry(t,asymState,asymRho,cfg);
    assert(rotatedGeometry.pass_bidirectional && ...
        rotatedGeometry.max_abs_cog_offset_body_m>1e-5 && ...
        isfinite(rotatedGeometry.minimum_clearance_m), ...
        'GateScene:RotatedCog','Rotated asymmetric geometry must use its instantaneous CoG offset.');
    assert(geometry{1}.pass_15mm_proxy && geometry{2}.pass_15mm_proxy && ...
        ~geometry{3}.pass_nonnegative_clearance, ...
        'GateScene:GeometryBoundary','Expected .15/.207182 positive and .25 negative gate proxies.');
    report=struct('status','PASS_NO_PLANT_STATIC_SELF_CHECK', ...
        'plant_calls',0,'holdout_payloads_generated',false, ...
        'manifest_status',manifest.status,'holdout_id_seed_count',numel(holdout), ...
        'pilot_id_seed_count',numel(pilotRows),'time_samples',numel(t),'dt_s',dt, ...
        'max_reference_speed_mps',maxSpeed,'max_reference_acceleration_mps2',maxAcceleration, ...
        'max_nominal_tilt_rad',maxTilt,'max_nominal_thrust_N',maxThrust, ...
        'configured_total_thrust_limit_N',totalThrust,'rho_star_m',rhoStar, ...
        'analytic_outer_width_m',analytic,'analytic_side_clearance_m',expected, ...
        'synthetic_geometry_reports',{geometry}, ...
        'rotated_asymmetric_cog_geometry',rotatedGeometry, ...
        'battery_geometry_gap','battery is point mass; no physical battery dimensions configured', ...
        'rotor_geometry_status',cfg.plant.vehicle_envelope.rotor_physical_radius_status);
end

