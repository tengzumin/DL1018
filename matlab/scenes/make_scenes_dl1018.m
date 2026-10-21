function out=make_scenes_dl1018(action,projectRoot,sceneId)
% Build and retrieve the fixed 888-scene DL1018 design.
if nargin<2||isempty(projectRoot)
    projectRoot=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
end
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
switch upper(char(action))
    case 'BUILD'
        assert_reference_buildable(projectRoot);
        out=build_all(projectRoot);
    case 'GET'
        assert(nargin>=3&&~isempty(sceneId),'DL1018:SceneId','GET requires scene_id.');
        tablePath=fullfile(projectRoot,'configs','scene_specs.csv');
        assert(isfile(tablePath),'DL1018:SceneSpecsMissing','Run G01 before retrieving scenes.');
        M=read_specs(tablePath);idx=find(M.scene_id==string(sceneId));
        assert(numel(idx)==1,'DL1018:UnknownScene','Expected one scene_id: %s.',sceneId);
        [cfg,~,root]=init_dl1018();assert(strcmp(root,projectRoot),'DL1018:RootMismatch','Unexpected root.');
        [scene,metadata]=construct_scene(M(idx,:),cfg);
        metadata.reference_contract_id=reference_contract_id();
        out=struct('scene',scene,'metadata',metadata,'spec',M(idx,:));
    otherwise
        error('DL1018:SceneAction','Action must be BUILD or GET.');
end
end

function report=build_all(projectRoot)
addpath(fullfile(projectRoot,'matlab','runtime'));
[cfg,~,root]=init_dl1018();assert(strcmp(root,projectRoot),'DL1018:RootMismatch','Unexpected root.');
M=build_specs();
tablePath=fullfile(projectRoot,'configs','scene_specs.csv');
if isfile(tablePath)
    existing=read_specs(tablePath);
    assert(tables_equal(existing,M),'DL1018:SceneSpecsConflict', ...
        'Existing scene_specs.csv conflicts with the fixed DL1018 allocation.');
end
assert(height(M)==888&&nnz(M.split=="TRAIN")==768&&nnz(M.split=="VAL")==48&& ...
    nnz(M.split=="DEV")==24&&nnz(M.split=="TEST")==48,'DL1018:SceneCount','Scene split counts differ.');
studentSet=[0 2 4 6 9 11 13 15];
assert(nnz(M.student_train)==384&&nnz(M.student_val)==48&& ...
    all(arrayfun(@(t)nnz(M.student_train&M.t==t)==128,0:2)), ...
    'DL1018:StudentAllocation','Student TRAIN/VAL allocation differs.');
for t=0:2
    for c=0:15
        q=M(M.student_train&M.t==t&M.c==c,:);
        assert(height(q)==8&&numel(unique(q.w))==8,'DL1018:StudentClassBalance', ...
            'Student task/class balance failed at t=%d c=%d.',t,c);
        assert(all(arrayfun(@(band)any(floor(q.w(q.w<15)/3)==band),0:4)), ...
            'DL1018:StudentBandCoverage','Student nonzero band coverage failed at t=%d c=%d.',t,c);
    end
    assert(all(arrayfun(@(w)nnz(M.student_train&M.t==t&M.w==w)==8,0:15)), ...
        'DL1018:StudentTaskWind','Student task/wind balance failed for task %d.',t);
end
assert(all(arrayfun(@(w)nnz(M.student_train&M.w==w)==24,0:15))&& ...
    nnz(M.student_train&M.w>=9&M.w<=14)==144,'DL1018:StudentWindCoverage', ...
    'Student wind-cell balance failed.');

t=(0:.001:20).';refs=cell(3,1);tasks=["HELIX","FIG8_3D","SQUARE"];
referenceStats=repmat(struct('task',"",'max_nominal_tilt_deg',0, ...
    'tilt_limited_samples',0,'max_corner_position_jump_m',0, ...
    'max_corner_speed_mps',0,'max_corner_accel_mps2',0),3,1);
Pp=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));P=controller_parameters(cfg,Pp,'fixed');
for q=1:3
    refs{q}=make_reference(tasks(q),t);
    ref=refs{q};
    assert(isequal(size(ref.position),[20001 3])&&isequal(size(ref.velocity),[20001 3])&& ...
        isequal(size(ref.acceleration),[20001 3])&&all(isfinite([ref.position(:);ref.velocity(:);ref.acceleration(:)])), ...
        'DL1018:ReferenceShape','Reference %s is not finite 20001-by-3.',tasks(q));
    tilt=zeros(numel(t),1);limited=false(numel(t),1);
    for k=1:numel(t)
        x=[ref.position(k,:).';ref.velocity(k,:).';zeros(6,1)];
        r=struct('position',ref.position(k,:).','velocity',ref.velocity(k,:).', ...
            'acceleration',ref.acceleration(k,:).','yaw',0,'yaw_rate',0,'yaw_acceleration',0);
        [~,info]=position_bs_step(x,r,zeros(3,1),P);sf=info.commanded_acceleration+[0;0;P.g];
        tilt(k)=atan2(norm(sf(1:2)),sf(3));[~,~,limited(k)]=baseline_force_to_attitude(info.commanded_acceleration,0,P);
    end
    [jump,maxSpeed,maxAccel]=corner_metrics(tasks(q),ref,t);
    referenceStats(q)=struct('task',tasks(q),'max_nominal_tilt_deg',max(tilt)*180/pi, ...
        'tilt_limited_samples',nnz(limited),'max_corner_position_jump_m',jump, ...
        'max_corner_speed_mps',maxSpeed,'max_corner_accel_mps2',maxAccel);
end

maxWind=0;minHold=inf;minArm=.15;maxArm=.25;minRetractMargin=inf;
for i=1:height(M)
    [scene,meta]=construct_scene(M(i,:),cfg,t,refs);
    assert(isequal(size(scene.environment_wind_I),[20001 3])&& ...
        all(isfinite(scene.environment_wind_I),'all')&& ...
        isequal(size(scene.arms.command),[20001 4])&& ...
        isequal(size(scene.arms.rho_true),[20001 4])&& ...
        isequal(size(scene.arms.rhoDot_true),[20001 4])&& ...
        all(isfinite(scene.arms.rho_true),'all')&& ...
        all(scene.arms.rho_true>=.15-1e-12,'all')&&all(scene.arms.rho_true<=.25+1e-12,'all'), ...
        'DL1018:SceneArrays','Malformed scene arrays for %s.',M.scene_id(i));
    assert(all(ismember(unique(scene.arms.command(:)),[-1 0 1])),'DL1018:ArmCommand', ...
        'Unexpected actuator command for %s.',M.scene_id(i));
    assert(all(abs(scene.arms.rho_true(end,:)-.15)<=1e-12), ...
        'DL1018:ArmRetraction','Arms did not return to minimum by 20 s for %s.',M.scene_id(i));
    maxWind=max(maxWind,meta.wind_speed_peak_mps);
    minArm=min(minArm,min(scene.arms.rho_true,[],'all'));maxArm=max(maxArm,max(scene.arms.rho_true,[],'all'));
    if isfinite(meta.arm_hold_contract_min_s),minHold=min(minHold,meta.arm_hold_contract_min_s);end
    if isfinite(meta.arm_retract_margin_min_s),minRetractMargin=min(minRetractMargin,meta.arm_retract_margin_min_s);end
end
assert(maxWind<18&&minHold>=5-1e-12&&minRetractMargin>=-1e-12&& ...
    all([referenceStats.tilt_limited_samples]==0),'DL1018:ScenePreflight', ...
    'Wind, hold, retraction, or nominal trajectory preflight failed.');
assert(all(M.seed>=0&M.seed<2^31)&&numel(unique(M.seed))==height(M)&& ...
    numel(unique(M.scene_id))==height(M),'DL1018:SceneIdentity','Scene IDs or seeds are not unique.');

if ~isfile(tablePath)
    tempPath=[tablePath '.tmp.csv'];writetable(M,tempPath);movefile(tempPath,tablePath,'f');
end
plan=build_dataset_plan();planPath=fullfile(projectRoot,'configs','dataset_plan.json');
if isfile(planPath)
    current=jsondecode(fileread(planPath));
    assert(isequaln(current,plan),'DL1018:DatasetPlanConflict', ...
        'Existing dataset_plan.json conflicts with the fixed DL1018 plan.');
else
    write_json_dl1018(planPath,plan);
end
report=struct('gate_id','G01_SCENES','status','PASS','contract_version','DL1018_V311_R2E_PAPER_FINAL', ...
    'reference_contract_id',reference_contract_id(), ...
    'upstream_passed',true,'model_id','','actual_counts',struct('scenes_total',height(M), ...
    'train',nnz(M.split=="TRAIN"),'val',nnz(M.split=="VAL"),'dev',nnz(M.split=="DEV"), ...
    'test',nnz(M.split=="TEST"),'student_train',nnz(M.student_train),'student_val',nnz(M.student_val), ...
    'plant_started',0,'engineering_errors',0,'physical_failures',0), ...
    'checks',struct('unique_scene_ids',true,'unique_seeds',true,'student_half_factorial',true, ...
    'test_sealed',true,'shared_external_inputs_by_scene_id',true,'scene_arrays_preflighted',true, ...
    'wind_peak_mps',maxWind,'minimum_arm_hold_s',minHold,'minimum_retraction_margin_s',minRetractMargin, ...
    'arm_length_range_m',[minArm maxArm],'reference_stats',referenceStats), ...
    'max_errors',struct('plant_calls',0),'artifacts',{{'configs/scene_specs.csv', ...
    'configs/dataset_plan.json','reports/G01_SCENES.json'}},'next_gate_allowed',true,'blocking_reason','');
write_gate_report_dl1018(fullfile(projectRoot,'reports','G01_SCENES.json'),report);
end

function M=build_specs()
splits=["TRAIN","VAL","DEV","TEST"];codes=[0 1 1 2];offsets=[0 15 7.5 22.5];
tasks=["HELIX","FIG8_3D","SQUARE"];
classes=["NONE","1","2","3","4","12","13","14","23","24","34","123","124","134","234","1234"];
freqs=cat(3,[.20 .40;.50 .80;1.00 1.60;2.00 3.00;3.80 5.00], ...
    [.25 .45;.58 .87;1.15 1.75;2.20 3.20;3.70 4.80], ...
    [.30 .50;.65 .95;1.30 1.90;2.40 3.40;3.60 4.60]);
amps=[1.5 1.0;3.5 2.45;4.5 3.5];rows=struct([]);dev=[0 0 3;0 1 15;0 4 0;0 5 6;0 7 8;0 10 9;0 11 12;0 15 14; ...
    1 0 4;1 2 15;1 3 1;1 6 7;1 8 8;1 9 10;1 12 13;1 14 14; ...
    2 0 5;2 3 15;2 5 2;2 6 8;2 9 9;2 10 11;2 13 12;2 15 14];
for sp=1:4
    for t=0:2
        for c=0:15
            if sp==1
                wList=0:15;
            elseif sp==2
                wList=mod(c+3*t+7,16);
            elseif sp==3
                wList=dev(dev(:,1)==t&dev(:,2)==c,3);
            else
                wList=mod(c+3*t+11,16);
            end
            if isempty(wList),continue;end
            for w=wList
                rStyle=mod(w,4);sourceCode=codes(sp);band=floor(w/3);level=mod(w,3);
                splitCode=sp-1;
                seed=2026101800+10000*splitCode+1000*t+16*c+w;
                f1=0;f2=0;A1=0;A2=0;phase1=0;phase2=0;
                if w<15
                    rs=RandStream('mt19937ar','Seed',double(seed));
                    phase1=2*pi*rand(rs);phase2=2*pi*rand(rs);
                    frequencySplit=sp;if sp==3,frequencySplit=2;elseif sp==4,frequencySplit=3;end
                    f1=freqs(band+1,1,frequencySplit);f2=freqs(band+1,2,frequencySplit);
                    A1=amps(level+1,1);A2=amps(level+1,2);
                else
                    band=5;level=-1;
                end
                azIndex=mod(3*c+5*t+7*rStyle,8);azimuth=45*azIndex+offsets(sp);
                elevations=[-15 0 15];elevation=elevations(1+mod(c+2*t+rStyle+sourceCode,3));
                schedule=mod(c+t+rStyle+sourceCode,3);target=.15*ones(1,4);start=nan(1,4);retract=nan(1,4);
                active=arm_ids(classes(c+1));targetValues=[.18 .20 .22 .25];
                for q=1:numel(active)
                    a=active(q);targetIndex=1+mod(c+t+rStyle+a+sourceCode,4);
                    assert(isscalar(a)&&a>=1&&a<=4&&isscalar(targetIndex), ...
                        'DL1018:SceneSpecIndex','Invalid target index for class %s: active=%s a=%s c=%s t=%s r=%s source=%s idx=%s.', ...
                        classes(c+1),mat2str(active),mat2str(a),mat2str(c),mat2str(t), ...
                        mat2str(rStyle),mat2str(sourceCode),mat2str(targetIndex));
                    target(a)=targetValues(targetIndex);
                    switch schedule
                        case 0,start(a)=5.2;retract(a)=13.0;
                        case 1,start(a)=5.2+.25*(q-1);retract(a)=13.4+.15*(q-1);
                        case 2,start(a)=6.2;retract(a)=14.0;
                    end
                end
                sid=sprintf('DL1018_%s_T%d_C%02d_W%02d',splits(sp),t+1,c,w);
                isStudentTrain=sp==1&&ismember(mod(w-c-3*t,16),[0 2 4 6 9 11 13 15]);
                isStudentVal=sp==2;
                row=struct('scene_id',string(sid),'split',splits(sp),'split_code',sp-1, ...
                    'source_split_code',sourceCode,'task',tasks(t+1),'t',t,'class_id',classes(c+1), ...
                    'c',c,'w',w,'wind_band',band,'amplitude_level',level,'r_style',rStyle, ...
                    'seed',seed,'f1_hz',f1,'f2_hz',f2,'A1_mps',A1,'A2_mps',A2, ...
                    'phase1_rad',phase1,'phase2_rad',phase2,'azimuth_index',azIndex, ...
                    'azimuth_deg',azimuth,'elevation_deg',elevation,'arm_schedule',schedule, ...
                    'target_a1_m',target(1),'target_a2_m',target(2),'target_a3_m',target(3),'target_a4_m',target(4), ...
                    'start_a1_s',start(1),'start_a2_s',start(2),'start_a3_s',start(3),'start_a4_s',start(4), ...
                    'retract_a1_s',retract(1),'retract_a2_s',retract(2),'retract_a3_s',retract(3),'retract_a4_s',retract(4), ...
                    'student_train',logical(isStudentTrain),'student_val',logical(isStudentVal), ...
                    'sealed',logical(sp==4));
                if isempty(rows),rows=row;else,rows(end+1,1)=row;end %#ok<AGROW>
            end
        end
    end
end
M=struct2table(rows);M.scene_id=string(M.scene_id);M.split=string(M.split);M.task=string(M.task);M.class_id=string(M.class_id);
end

function [scene,meta]=construct_scene(row,cfg,t,refs)
if nargin<3||isempty(t),t=(0:.001:20).';end
if nargin<4||isempty(refs),refs={make_reference("HELIX",t),make_reference("FIG8_3D",t),make_reference("SQUARE",t)};end
ref=refs{double(row.t)+1};w=double(row.w);
if w==15
    wind=zeros(20001,3);speed=zeros(20001,1);
else
    az=deg2rad(double(row.azimuth_deg));el=deg2rad(double(row.elevation_deg));
    wc=struct('type','biased_dual_sine','direction',[cos(el)*cos(az);cos(el)*sin(az);sin(el)], ...
        'V0',9,'A1',double(row.A1_mps),'f1',double(row.f1_hz),'phi1',double(row.phase1_rad), ...
        'A2',double(row.A2_mps),'f2',double(row.f2_hz),'phi2',double(row.phase2_rad), ...
        'rise_time_s',.8,'rho_air',1.225,'CdBody',1,'CdArm',1);
    [windT,detail]=wind_velocity_profile(t,wc);wind=windT.';speed=detail.speed;
end
target=[row.target_a1_m,row.target_a2_m,row.target_a3_m,row.target_a4_m].';
start=[row.start_a1_s,row.start_a2_s,row.start_a3_s,row.start_a4_s].';
retract=[row.retract_a1_s,row.retract_a2_s,row.retract_a3_s,row.retract_a4_s].';
[arms,am]=tcn0916_morphology_scenario(topology(string(row.class_id)),t,double(row.seed), ...
    struct('retract',true,'target_override',target,'start_override',start, ...
    'retract_start_override',retract,'morph_speed_mps',.05,'min_hold_s',5));
arms.rho_hat=repmat(cfg.plant.arm_initial(:).',numel(t),1);arms.rhoDot_hat=zeros(numel(t),4);
scene=struct('scene_id',string(row.scene_id),'time',t,'initial_state',zeros(12,1), ...
    'reference',ref,'arms',arms,'environment_wind_I',wind);
active=arm_ids(string(row.class_id));holds=am.actual_hold_s(active);hold=inf;
margin=inf;if ~isempty(holds),hold=min(holds);margin=min(holds-5);end
meta=struct('scene_id',string(row.scene_id),'wind_speed_rms_mps',sqrt(mean(speed.^2)), ...
    'wind_speed_peak_mps',max(abs(speed)),'wind_input_frequencies_hz',[double(row.f1_hz),double(row.f2_hz)], ...
    'arm_target_lengths_m',am.target_arm_lengths(:).','arm_start_s',am.start_time_s(:).', ...
    'arm_retract_start_s',am.retract_start_time_s(:).','arm_schedule',double(row.arm_schedule), ...
    'arm_hold_contract_min_s',hold,'arm_retract_margin_min_s',margin);
end

function M=read_specs(path)
opts=detectImportOptions(path,'VariableNamingRule','preserve');
opts=setvartype(opts,{'scene_id','split','task','class_id'},'string');M=readtable(path,opts);
end

function tf=tables_equal(a,b)
tf=height(a)==height(b)&&isequal(a.Properties.VariableNames,b.Properties.VariableNames);
if ~tf,return;end
for i=1:width(a)
    x=a{:,i};y=b{:,i};
    if (isnumeric(x)||islogical(x))&&(isnumeric(y)||islogical(y))
        x=double(x);y=double(y);sameShape=isequal(size(x),size(y));
        sameNan=isequal(isnan(x),isnan(y));sameInf=isequal(isinf(x),isinf(y))&& ...
            isequal(sign(x(isinf(x))),sign(y(isinf(y))));
        finite=isfinite(x)&isfinite(y);err=0;
        if any(finite,'all'),err=max(abs(x(finite)-y(finite)));end
        tf=sameShape&&sameNan&&sameInf&&err<=1e-12;
    else
        tf=isequal(string(x),string(y));
    end
    if ~tf
        fprintf(2,'Scene table mismatch in %s: existing class %s, generated class %s.\n', ...
            a.Properties.VariableNames{i},class(x),class(y));
        return;
    end
end
end

function plan=build_dataset_plan()
roles=struct('gate',{},'collector_id',{},'split',{},'scene_count',{},'plant_runs',{},'reuse',{},'status',{});
roles=add_role(roles,'G02_P_TEACHER','B','TRAIN',768,768,false);
roles=add_role(roles,'G02_P_TEACHER','B','VAL',48,48,false);
roles=add_role(roles,'G02_P_TEACHER','POS_OFF','TRAIN',768,768,false);
roles=add_role(roles,'G02_P_TEACHER','POS_OFF','VAL',48,48,false);
roles=add_role(roles,'G04_P_STUDENT','P_INIT_STUDENT','TRAIN',384,384,false);
roles=add_role(roles,'G04_P_STUDENT','P_INIT_STUDENT','VAL',48,48,false);
roles=add_role(roles,'G07_A_TEACHER','P_STAR','TRAIN',768,768,false);
roles=add_role(roles,'G07_A_TEACHER','P_STAR','VAL',48,48,false);
roles=add_role(roles,'G07_A_TEACHER','B','TRAIN',768,0,true);
roles=add_role(roles,'G07_A_TEACHER','B','VAL',48,0,true);
roles=add_role(roles,'G09_A_STUDENT','A_INIT_STUDENT','TRAIN',384,384,false);
roles=add_role(roles,'G09_A_STUDENT','A_INIT_STUDENT','VAL',48,48,false);
for id=["B","P_F","P_A"],roles=add_role(roles,'G06_P_DEV',id,'DEV',24,24,false);end
for id=["PA_F","PA_A"],roles=add_role(roles,'G11_PA_DEV',id,'DEV',24,24,false);end
roles=add_role(roles,'G11_PA_DEV','B','DEV',24,0,true);
roles=add_role(roles,'G11_PA_DEV','P_STAR','DEV',24,0,true);
for id=["B","P_F","P_A","PA_F","PA_A"],roles=add_role(roles,'G12_FINAL_TEST',id,'TEST',48,48,false);end
plan=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','scene_count',888, ...
    'split_counts',struct('TRAIN',768,'VAL',48,'DEV',24,'TEST',48), ...
    'student_train_scene_count',384,'student_val_scene_count',48, ...
    'student_wind_cells',[0 2 4 6 9 11 13 15],'test_status','SEALED', ...
    'b_raw_reused_across_position_and_attitude',true, ...
    'roles',roles,'quota_status','NOT_STARTED','plant_runs_started',0,'hash_or_manifest_audit_performed',false);
end

function roles=add_role(roles,gate,id,split,count,runs,reuse)
roles(end+1)=struct('gate',string(gate),'collector_id',string(id),'split',string(split), ...
    'scene_count',count,'plant_runs',runs,'reuse',logical(reuse),'status',"NOT_STARTED");
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
        puu=[-6*pi^2*sin(th),-16*pi^2*sin(2*th),5.6*pi^2*cos(2*th)];
        v=pu.*ud;a=puu.*(ud.^2)+pu.*udd;
    case 'SQUARE'
        p=zeros(numel(t),3);v=p;a=p;points=[0 0 0;2 0 0;2 2 0;0 2 0;0 0 0];
        seg=min(floor(t/5),3);
        for k=1:numel(t),[p(k,:),v(k,:),a(k,:)]=square_row(t(k),seg(k),points);end
    otherwise,error('DL1018:Task','Unknown task %s.',task);
end
ref=struct('position',p,'velocity',v,'acceleration',a,'yaw',zeros(size(t)), ...
    'yaw_rate',zeros(size(t)),'yaw_acceleration',zeros(size(t)));
end

function [p,v,a]=square_row(t,i,points)
u=min(max((t-5*i)/5,0),1);h=10*u^3-15*u^4+6*u^5;
hd=30*u^2-60*u^3+30*u^4;hdd=60*u-180*u^2+120*u^3;dp=points(i+2,:)-points(i+1,:);
p=points(i+1,:)+dp*h;v=dp*hd/5;a=dp*hdd/25;
end

function assert_reference_buildable(root)
reportPath=fullfile(root,'reports','G01_SCENES.json');
if isfile(reportPath)
    prior=jsondecode(fileread(reportPath));
    assert(isfield(prior,'reference_contract_id')&& ...
        strcmp(char(string(prior.reference_contract_id)),reference_contract_id()), ...
        'DL1018:ReferenceIdentityConflict', ...
        'G01 belongs to another reference contract; use a fresh output root.');
    return;
end
assert(~has_legacy_scene_artifacts(root),'DL1018:LegacySceneEvidence', ...
    'G01 is missing but prior scene or pipeline artifacts exist; use a fresh output root.');
end

function tf=has_legacy_scene_artifacts(root)
tf=false;
paths={fullfile(root,'configs','scene_specs.csv'),fullfile(root,'configs','dataset_plan.json'), ...
    fullfile(root,'reports','G02_P_TEACHER.json'),fullfile(root,'reports','G03_P_INITIAL.json'), ...
    fullfile(root,'reports','G04_P_STUDENT.json'),fullfile(root,'reports','G05_P_FINAL.json'), ...
    fullfile(root,'reports','G06_P_DEV.json'),fullfile(root,'reports','G07_A_TEACHER.json'), ...
    fullfile(root,'reports','G08_A_INITIAL.json'),fullfile(root,'reports','G09_A_STUDENT.json'), ...
    fullfile(root,'reports','G10_A_FINAL.json'),fullfile(root,'reports','G11_PA_DEV.json'), ...
    fullfile(root,'reports','G12_FINAL_TEST.json'),fullfile(root,'reports','G13_FINAL_REPORT.json')};
if any(cellfun(@isfile,paths)),tf=true;return;end
for name={'attempt_index.csv','episode_index.csv'}
    p=fullfile(root,'logs',name{1});
    if isfile(p)
        lines=readlines(p);
        if numel(lines)>1&&any(strlength(strtrim(lines(2:end)))>0),tf=true;return;end
    end
end
for p={fullfile(root,'data','raw'),fullfile(root,'data','events','position'), ...
        fullfile(root,'data','events','attitude')}
    if isfolder(p{1})
        entries=dir(p{1});
        if any(~ismember({entries.name},{'.','..'})),tf=true;return;end
    end
end
modelRoot=fullfile(root,'models');
if isfolder(modelRoot)
    entries=dir(fullfile(modelRoot,'**','*'));
    tf=any(~[entries.isdir]&~ismember({entries.name},{'.','..'}));
end
end

function id=reference_contract_id()
id='DL1018_SCENE_REF_FIG8_A2_V2';
end

function [jump,maxSpeed,maxAccel]=corner_metrics(task,ref,t)
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
if classId=="NONE",name='C0';else,name=char(classId);end
end

function write_json_dl1018(path,value)
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
temporary=[path '.tmp'];fid=fopen(temporary,'w');
assert(fid>=0,'DL1018:JsonWrite','Could not create JSON file: %s.',path);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');
fwrite(fid,newline,'char');clear cleanup;movefile(temporary,path,'f');
end
