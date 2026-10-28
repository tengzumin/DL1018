function out=make_paired_screen12_scene(sceneId,cfg)
% Rebuild only the 12 fixed VAL scenes from this isolated CSV and receipt.
assert(isstruct(cfg),'SCREEN12:Config','Expected frozen C5 cfg.');
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
csvPath=fullfile(root,'configs','scene_specs_screen12.csv');
receiptPath=fullfile(root,'configs','scene_specs_screen12_receipt.json');
assert(isfile(csvPath)&&isfile(receiptPath)&& ...
    strcmpi(sha256_file(csvPath),'cf409b72adc2eac7563e90ab8202dc8aea916b710adb2c55b88224aad5024444')&& ...
    strcmpi(sha256_file(receiptPath),'40513239daf0fab1c6f74b93593bb7b17edc10046f22bda983086bdf443d2ddd'), ...
    'SCREEN12:InputSHA','Screen12 VAL CSV or receipt SHA differs.');
receipt=jsondecode(fileread(receiptPath));
expectedIds=["DL1018_VAL_T1_C00_W07","DL1018_VAL_T1_C02_W09", ...
    "DL1018_VAL_T1_C05_W12","DL1018_VAL_T1_C08_W15", ...
    "DL1018_VAL_T2_C00_W10","DL1018_VAL_T2_C02_W12", ...
    "DL1018_VAL_T2_C05_W15","DL1018_VAL_T2_C06_W00", ...
    "DL1018_VAL_T3_C00_W13","DL1018_VAL_T3_C02_W15", ...
    "DL1018_VAL_T3_C03_W00","DL1018_VAL_T3_C12_W09"];
expectedSeeds=[2026111807,2026111841,2026111892,2026111943, ...
    2026112810,2026112844,2026112895,2026112896, ...
    2026113813,2026113847,2026113848,2026114001];
assert(strcmp(receipt.schema,'MORPH_DEV2_SCREEN12_SCENE_SOURCE_RECEIPT_V1')&& ...
    receipt.source_full_csv_sha256_accessed==false&&numel(receipt.rows)==12&& ...
    numel(receipt.lineage.completed_dev_reuse)==2&& ...
    receipt.lineage.completed_dev_reuse(1).rerun==false&& ...
    receipt.lineage.completed_dev_reuse(1).included_in_screen12_macro_average==false&& ...
    receipt.lineage.completed_dev_reuse(2).rerun==false&& ...
    receipt.lineage.completed_dev_reuse(2).included_in_screen12_macro_average==false, ...
    'SCREEN12:Receipt','VAL-only receipt or DEV reuse lineage differs.');
opts=detectImportOptions(csvPath,'VariableNamingRule','preserve');
opts=setvartype(opts,{'scene_id','split','task','class_id'},'string');
rows=readtable(csvPath,opts);
assert(height(rows)==12&&isequal(string(rows.scene_id(:)),expectedIds(:))&& ...
    isequal(string(rows.split(:)),repmat("VAL",12,1))&& ...
    isequal(double(rows.seed(:)),expectedSeeds(:))&& ...
    all([receipt.rows.seed].'==expectedSeeds(:)), ...
    'SCREEN12:Rows','Fixed scene identity, split, or seed differs.');
sourceLines=read_csv_lines(csvPath);
assert(numel(sourceLines)==13, ...
    'SCREEN12:CSV','Expected one header plus exactly twelve raw rows.');
for k=1:12
    expectedLine=char(string(receipt.rows(k).source_line));
    assert(strcmp(sourceLines{k+1},expectedLine)&& ...
        strcmpi(sha256_text(sourceLines{k+1}),char(receipt.rows(k).source_row_sha256))&& ...
        strcmp(char(string(rows.scene_id(k))),char(string(receipt.rows(k).scene_id))), ...
        'SCREEN12:RowSHA','VAL source row mismatch at row %d.',k);
end
ix=find(expectedIds==string(sceneId));
assert(numel(ix)==1,'SCREEN12:SceneId','Scene ID outside the fixed 12-scene VAL cohort.');
specRow=rows(ix,:);
assert(string(specRow.split)=="VAL"&&double(specRow.seed)==expectedSeeds(ix), ...
    'SCREEN12:Spec','Spec split or seed differs.');
[scene,metadata]=construct_scene(specRow,cfg);
scene.reference_contract_id='DL1018_SCENE_REF_FIG8_A2_V2';
metadata.reference_contract_id=scene.reference_contract_id;
out=struct('spec',specRow,'scene',scene,'metadata',metadata);
end

function lines=read_csv_lines(path)
fid=fopen(path,'r');assert(fid>=0,'SCREEN12:Read','Cannot read isolated CSV.');
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
lines={};while true,line=fgetl(fid);if ~ischar(line),break;end;lines{end+1}=line;end
end

function hash=sha256_text(value)
md=java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(uint8(unicode2native(char(value),'UTF-8')),'int8'));
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function [scene,meta]=construct_scene(row,cfg)
t=(0:.001:20).';
ref=make_reference(string(row.task),t);w=double(row.w);
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

function ids=arm_ids(classId)
if classId=="NONE",ids=[];else,ids=double(char(classId))-double('0');end
end

function name=topology(classId)
if classId=="NONE",name='C0';else,name=char(classId);end
end

function hash=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256');
fid=fopen(path,'r');
assert(fid>=0,'PAIRED:SpecRead','Cannot open isolated DEV input.');
cleanup=onCleanup(@()fclose(fid));
while true
    bytes=fread(fid,8*1024*1024,'*uint8');
    if isempty(bytes),break;end
    md.update(bytes);
end
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
