function out=make_scenes_v311(action,repoRoot,sceneId)
% Deterministic V3.11 scenes and zero-Plant reference preflight.
if nargin<2||isempty(repoRoot),repoRoot=fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));end
repoRoot=char(repoRoot);expDir=fullfile(repoRoot,'RBF-BS0','experiments','multitask_retrain_v311');
addpath(fullfile(repoRoot,'RBF-BS0','code','code'));
specPath=fullfile(expDir,'configs','scenario_specs.csv');
switch upper(char(action))
    case 'BUILD'
        if isfile(specPath),error('V311:SpecsExist','Refusing to replace frozen scenario_specs.csv.');end
        M=build_specs();report=preflight(repoRoot,M);
        writetable(M,specPath);
        write_report(fullfile(expDir,'reports','SCENE_DESIGN_V311.md'),report,M);
        out=report;
    case 'GET'
        if nargin<3||isempty(sceneId),error('V311:SceneId','GET requires a frozen scene_id.');end
        if ~isfile(specPath),error('V311:MissingSpecs','Run make_scenes_v311(''BUILD'',repoRoot) first.');end
        io=detectImportOptions(specPath,'VariableNamingRule','preserve');
        io=setvartype(io,{'scene_id','split','task','class_id'},'string');
        M=readtable(specPath,io);
        i=find(string(M.scene_id)==string(sceneId));
        if numel(i)~=1,error('V311:UnknownScene','Expected one frozen scene_id: %s',sceneId);end
        [scene,metadata]=construct_scene(repoRoot,M(i,:));
        out=struct('scene',scene,'metadata',metadata);
    otherwise
        error('V311:Action','Action must be BUILD or GET.');
end
end

function M=build_specs()
splits=["TRAIN","VAL","FINAL_TEST"];codes=0:2;offsets=[0,7,11];
tasks=["HELIX","FIG8_3D","SQUARE"];
classes=["NONE","1","2","3","4","12","13","14","23","24","34","123","124","134","234","1234"];
freqs=cat(3,[.20 .40;.50 .80;1.00 1.60;2.00 3.00;3.80 5.00], ...
    [.25 .45;.58 .87;1.15 1.75;2.20 3.20;3.70 4.80], ...
    [.30 .50;.65 .95;1.30 1.90;2.40 3.40;3.60 4.60]);
amps=[1.50 1.00;3.50 2.45;4.50 3.50];rows=struct([]);
for sp=1:3
    split=splits(sp);splitCode=codes(sp);offset=offsets(sp);
    if sp==1,repList=0:3;else,repList=0;end
    for t=0:2
        for c=0:15
            for r=repList
                j=mod(c+5*r+3*t+offset,16);seed=2026110000+100000*splitCode+10000*t+100*c+r;
                band=0;level=0;f1=0;f2=0;A1=0;A2=0;phase1=0;phase2=0;
                azIndex=mod(3*c+5*t+7*r,8);azOffsets=[0,15,22.5];
                azimuth=45*azIndex+azOffsets(splitCode+1);
                elChoices=[-15,0,15];elevation=elChoices(1+mod(c+2*t+r+splitCode,3));
                if j<15
                    band=floor(j/3)+1;level=mod(j,3)+1;
                    f1=freqs(band,1,splitCode+1);f2=freqs(band,2,splitCode+1);
                    A1=amps(level,1);A2=amps(level,2);
                    rs=RandStream('mt19937ar','Seed',double(seed));
                    phase1=2*pi*rand(rs);phase2=2*pi*rand(rs);
                end
                sched=mod(c+t+r+splitCode,3);active=arm_ids(classes(c+1));
                target=.15*ones(1,4);start=nan(1,4);retract=nan(1,4);targetValues=[.18,.20,.22,.25];
                for q=1:numel(active)
                    a=active(q);target(a)=targetValues(1+mod(c+t+r+a+splitCode,4));
                    switch sched
                        case 0,start(a)=5.2;retract(a)=13.0;
                        case 1,start(a)=5.2+.25*(q-1);retract(a)=13.4+.15*(q-1);
                        case 2,start(a)=6.2;retract(a)=14.0;
                    end
                end
                id=sprintf('%s_T%d_C%02d_R%d_W%02d',split,t+1,c,r,j);
                z=struct('scene_id',string(id),'split',split,'split_code',splitCode, ...
                    'task',tasks(t+1),'t',t,'class_id',classes(c+1),'c',c,'r',r,'j',j,'seed',seed, ...
                    'wind_offset',offset,'wind_band',band,'amplitude_level',level, ...
                    'f1_hz',f1,'f2_hz',f2,'A1_mps',A1,'A2_mps',A2, ...
                    'phase1_rad',phase1,'phase2_rad',phase2,'azimuth_index',azIndex, ...
                    'azimuth_deg',azimuth,'elevation_deg',elevation,'arm_schedule',sched, ...
                    'target_a1_m',target(1),'target_a2_m',target(2),'target_a3_m',target(3),'target_a4_m',target(4), ...
                    'start_a1_s',start(1),'start_a2_s',start(2),'start_a3_s',start(3),'start_a4_s',start(4), ...
                    'retract_a1_s',retract(1),'retract_a2_s',retract(2),'retract_a3_s',retract(3),'retract_a4_s',retract(4));
                if isempty(rows),rows=z;else,rows(end+1,1)=z;end %#ok<AGROW>
            end
        end
    end
end
M=struct2table(rows);M.scene_id=string(M.scene_id);M.split=string(M.split);M.task=string(M.task);M.class_id=string(M.class_id);
assert(height(M)==288&&numel(unique(M.scene_id))==288&&nnz(M.split=="TRAIN")==192&& ...
    nnz(M.split=="VAL")==48&&nnz(M.split=="FINAL_TEST")==48,'V311:SceneAllocation','Fixed scene allocation failed.');
for sp=1:3
    expected=[12,3,3];assert(all(arrayfun(@(j)nnz(M.split==splits(sp)&M.j==j)==expected(sp),0:15)), ...
        'V311:WindAllocation','Wind-cell allocation failed for %s.',splits(sp));
end
for t=0:2
    for c=0:15
        tr=M(M.split=="TRAIN"&M.t==t&M.c==c,:);va=M(M.split=="VAL"&M.t==t&M.c==c,:);
        te=M(M.split=="FINAL_TEST"&M.t==t&M.c==c,:);
        assert(height(tr)==4&&numel(unique(tr.j))==4&&height(va)==1&&height(te)==1&& ...
            ~ismember(va.j,tr.j)&&~ismember(te.j,tr.j)&&va.j~=te.j,'V311:PairAllocation','Task/class allocation failed.');
    end
end
assert(max(M.A1_mps+M.A2_mps+9)<18&&max(M.f2_hz)<=5&&all(M.seed<2^31), ...
    'V311:WindBounds','Wind speed, frequency, or seed exceeds the fixed bound.');
end

function report=preflight(repoRoot,M)
cfg=default_config();t=(0:.001:20).';
assert(strcmpi(cfg.plant.mass_model,'distributed_v1')&&abs(cfg.plant.dt-.001)<1e-12, ...
    'V311:PlantConfig','Expected distributed_v1 Plant at 1 kHz.');
P0=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));P=controller_parameters(cfg,P0,'fixed');
tasks=["HELIX","FIG8_3D","SQUARE"];
stats=repmat(struct('task',"",'max_nominal_tilt_deg',0,'tilt_limited_samples',0, ...
    'max_corner_position_jump_m',0,'max_corner_speed_mps',0,'max_corner_accel_mps2',0),3,1);
maxWind=0;minHold=inf;
for q=1:numel(tasks)
    ref=make_reference(tasks(q),t);
    assert(isequal(size(ref.position),[20001,3])&&isequal(size(ref.velocity),[20001,3])&& ...
        isequal(size(ref.acceleration),[20001,3])&&all(isfinite([ref.position(:);ref.velocity(:);ref.acceleration(:)])), ...
        'V311:ReferenceShape','%s reference must be finite 20001-by-3.',tasks(q));
    tilt=zeros(numel(t),1);limited=false(numel(t),1);
    for k=1:numel(t)
        x=[ref.position(k,:).';ref.velocity(k,:).';zeros(6,1)];
        r=struct('position',ref.position(k,:).','velocity',ref.velocity(k,:).', ...
            'acceleration',ref.acceleration(k,:).','yaw',0,'yaw_rate',0,'yaw_acceleration',0);
        [~,info]=position_bs_step(x,r,zeros(3,1),P);sf=info.commanded_acceleration+[0;0;P.g];
        tilt(k)=atan2(norm(sf(1:2)),sf(3));[~,~,limited(k)]=baseline_force_to_attitude(info.commanded_acceleration,0,P);
    end
    [jump,speed,accel]=corner_metrics(tasks(q),ref);
    stats(q)=struct('task',tasks(q),'max_nominal_tilt_deg',max(tilt)*180/pi, ...
        'tilt_limited_samples',nnz(limited),'max_corner_position_jump_m',jump, ...
        'max_corner_speed_mps',speed,'max_corner_accel_mps2',accel); %#ok<AGROW>
end
for i=1:height(M)
    [scene,meta]=construct_scene(repoRoot,M(i,:));
    assert(isequal(size(scene.environment_wind_I),[20001,3])&&all(isfinite(scene.environment_wind_I),'all')&& ...
        isequal(size(scene.arms.command),[20001,4])&&isequal(size(scene.arms.rho_true),[20001,4])&& ...
        isequal(size(scene.arms.rhoDot_true),[20001,4])&&all(isfinite(scene.arms.rho_true),'all'), ...
        'V311:SceneArrays','Malformed scene arrays for %s.',M.scene_id(i));
    maxWind=max(maxWind,meta.wind_speed_peak_mps);
    if isfinite(meta.arm_hold_contract_min_s),minHold=min(minHold,meta.arm_hold_contract_min_s);end
end
assert(maxWind<18&&minHold>=5-1e-12&&all([stats.tilt_limited_samples]==0), ...
    'V311:PhysicalPreflight','Nominal tilt limit, wind, or morphology timing preflight failed.');
report=struct('status','ZERO_PLANT_PREFLIGHT_PASS','plant_calls',0,'train_scenes',nnz(M.split=="TRAIN"), ...
    'val_scenes',nnz(M.split=="VAL"),'test_scenes',nnz(M.split=="FINAL_TEST"), ...
    'max_wind_speed_peak_mps',maxWind,'minimum_actual_arm_hold_s',minHold,'references',stats);
end

function [scene,meta]=construct_scene(repoRoot,row)
addpath(fullfile(repoRoot,'RBF-BS0','code','code'));cfg=default_config();t=(0:.001:20).';
ref=make_reference(string(row.task),t);
if row.j==15
    wind=zeros(20001,3);speed=zeros(20001,1);
else
    az=deg2rad(double(row.azimuth_deg));el=deg2rad(double(row.elevation_deg));
    wc=struct('type','biased_dual_sine','direction',[cos(el)*cos(az);cos(el)*sin(az);sin(el)], ...
        'V0',9,'A1',double(row.A1_mps),'f1',double(row.f1_hz),'phi1',double(row.phase1_rad), ...
        'A2',double(row.A2_mps),'f2',double(row.f2_hz),'phi2',double(row.phase2_rad), ...
        'rise_time_s',.8,'rho_air',1.225,'CdBody',1,'CdArm',1);
    [w,detail]=wind_velocity_profile(t,wc);wind=w.';speed=detail.speed;
end
target=[row.target_a1_m,row.target_a2_m,row.target_a3_m,row.target_a4_m].';
start=[row.start_a1_s,row.start_a2_s,row.start_a3_s,row.start_a4_s].';
retract=[row.retract_a1_s,row.retract_a2_s,row.retract_a3_s,row.retract_a4_s].';
if string(row.class_id)=="NONE",start(:)=5.2;retract(:)=13;end
[arms,am]=tcn0916_morphology_scenario(char(topology(string(row.class_id))),t,double(row.seed), ...
    struct('retract',true,'target_override',target,'start_override',start, ...
    'retract_start_override',retract,'morph_speed_mps',.05,'min_hold_s',5));
% Controller-side estimates stay at the frozen nominal morphology.
arms.rho_hat=repmat(cfg.plant.arm_initial(:).',numel(t),1);arms.rhoDot_hat=zeros(numel(t),4);
scene=struct('scene_id',string(row.scene_id),'time',t,'initial_state',zeros(12,1), ...
    'reference',ref,'arms',arms,'environment_wind_I',wind);
active=arm_ids(string(row.class_id));holds=am.actual_hold_s(active);hold=inf;if ~isempty(holds),hold=min(holds);end
el=deg2rad(double(row.elevation_deg));az=deg2rad(double(row.azimuth_deg));
meta=struct('scene_id',string(row.scene_id),'task',string(row.task),'class_id',string(row.class_id), ...
    'wind_speed_rms_mps',sqrt(mean(speed.^2)),'wind_speed_peak_mps',max(abs(speed)), ...
    'wind_input_frequencies_hz',[double(row.f1_hz),double(row.f2_hz)], ...
    'wind_direction_I',[cos(el)*cos(az);cos(el)*sin(az);sin(el)], ...
    'arm_target_lengths_m',am.target_arm_lengths(:).','arm_start_s',am.start_time_s(:).', ...
    'arm_retract_start_s',am.retract_start_time_s(:).','arm_schedule',double(row.arm_schedule), ...
    'arm_hold_contract_min_s',hold,'split',string(row.split),'wind_cell',double(row.j));
end

function ref=make_reference(task,t)
t=double(t(:));s=min(max(t/20,0),1);u=10*s.^3-15*s.^4+6*s.^5;
ud=(30*s.^2-60*s.^3+30*s.^4)/20;udd=(60*s-180*s.^2+120*s.^3)/400;
switch upper(char(task))
    case 'HELIX'
        th=3*pi*u;p=[1.2*(cos(th)-1),1.2*sin(th),2*u];
        pu=[-3.6*pi*sin(th),3.6*pi*cos(th),2+zeros(size(t))];
        puu=[-10.8*pi^2*cos(th),-10.8*pi^2*sin(th),zeros(size(t))];
        v=pu.*ud;a=puu.*(ud.^2)+pu.*udd;
    case 'FIG8_3D'
        th=2*pi*u;p=[1.5*sin(th),sin(2*th),.4*u+.35*(1-cos(2*th))];
        pu=[3*pi*cos(th),4*pi*cos(2*th),.4+1.4*pi*sin(2*th)];
        puu=[-6*pi^2*sin(th),-8*pi^2*sin(2*th),2.8*pi^2*cos(2*th)];
        v=pu.*ud;a=puu.*(ud.^2)+pu.*udd;
    case 'SQUARE'
        p=zeros(numel(t),3);v=p;a=p;points=[0 0 0;2 0 0;2 2 0;0 2 0;0 0 0];
        seg=min(floor(t/5),3);
        for k=1:numel(t),[p(k,:),v(k,:),a(k,:)]=square_row(t(k),seg(k),points);end
    otherwise,error('V311:Task','Unknown task %s.',task);
end
ref=struct('position',p,'velocity',v,'acceleration',a,'yaw',zeros(size(t)), ...
    'yaw_rate',zeros(size(t)),'yaw_acceleration',zeros(size(t)));
end

function [p,v,a]=square_row(t,i,points)
u=min(max((t-5*i)/5,0),1);h=10*u^3-15*u^4+6*u^5;
hd=30*u^2-60*u^3+30*u^4;hdd=60*u-180*u^2+120*u^3;dp=points(i+2,:)-points(i+1,:);
p=points(i+1,:)+dp*h;v=dp*hd/5;a=dp*hdd/25;
end

function [jump,maxSpeed,maxAccel]=corner_metrics(task,ref)
if task=="SQUARE"
    points=[0 0 0;2 0 0;2 2 0;0 2 0;0 0 0];jump=0;maxSpeed=0;maxAccel=0;
    for b=0:4
        tt=5*b;k=round(tt/.001)+1;maxSpeed=max(maxSpeed,norm(ref.velocity(k,:)));
        maxAccel=max(maxAccel,norm(ref.acceleration(k,:)));
        if b>0&&b<4
            [pl,vl,al]=square_row(tt,b-1,points);[pr,vr,ar]=square_row(tt,b,points);
            jump=max(jump,norm(pl-pr));maxSpeed=max([maxSpeed,norm(vl),norm(vr)]);
            maxAccel=max([maxAccel,norm(al),norm(ar)]);
        end
    end
else
    ix=[1,5001,10001,15001,20001];jump=0;
    maxSpeed=max(vecnorm(ref.velocity(ix,:),2,2));maxAccel=max(vecnorm(ref.acceleration(ix,:),2,2));
end
end

function ids=arm_ids(classId)
if classId=="NONE",ids=[];else,ids=double(char(classId))-double('0');end
end
function name=topology(classId)
if classId=="NONE",name="C0";else,name=classId;end
end

function write_report(path,report,M)
f=fopen(path,'w');assert(f>=0,'V311:ReportOpen','Cannot write scene design report.');c=onCleanup(@()fclose(f)); %#ok<NASGU>
fprintf(f,'# V3.11 场景设计与零 Plant 预检\n\n状态：%s；Plant 调用：%d。\n\n',report.status,report.plant_calls);
fprintf(f,'场景规格 %d 行：TRAIN %d、VAL %d、FINAL_TEST %d。配置含 3 个任务、16 类构型、15 个双正弦风单元及 W0；风频不超过 5 Hz，最大风速 %.6f m/s。\n\n', ...
    height(M),report.train_scenes,report.val_scenes,report.test_scenes,report.max_wind_speed_peak_mps);
fprintf(f,'场景时长 20 s、Plant 采样 1 kHz。机臂最小实际保持时间 %.6f s。\n\n',report.minimum_actual_arm_hold_s);
fprintf(f,'| 任务 | 最大名义倾角 | 倾角限制采样数 | 角点位置跳变 | 角点最大速度 | 角点最大加速度 |\n|---|---:|---:|---:|---:|---:|\n');
for q=1:numel(report.references)
    x=report.references(q);fprintf(f,'| %s | %.6f° | %d | %.3g m | %.3g m/s | %.3g m/s² |\n', ...
        char(x.task),x.max_nominal_tilt_deg,x.tilt_limited_samples,x.max_corner_position_jump_m, ...
        x.max_corner_speed_mps,x.max_corner_accel_mps2);
end
fprintf(f,'\n倾角使用原固定 J0/C0、BS 位置控制器和 baseline_force_to_attitude，以零跟踪误差计算；本表不包含 Plant 仿真。\n');
end
