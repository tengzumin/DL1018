function out=make_paired_dev_scene(sceneId,cfg)
% Consume only the three-row isolated DEV CSV; never opens the source manifest.
assert(isstruct(cfg),'PAIRED:Spec','Expected frozen cfg.');
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
csvPath=fullfile(root,'configs','scene_specs_dev3.csv');
receiptPath=fullfile(root,'configs','scene_specs_dev3_receipt.json');
assert(isfile(csvPath)&&isfile(receiptPath)&& ...
    strcmpi(sha256_file(csvPath),'bd68a24a0d87764e8d6fabcf5372d8a36a38104a3a246df6523f514548ac7630')&& ...
    strcmpi(sha256_file(receiptPath),'3b4443302cddbf67368922c17234f54041d1f3e36db345b5ec71f5ffc0bf7067'), ...
    'PAIRED:SpecIdentity','DEV-only CSV or extraction receipt changed.');
receipt=jsondecode(fileread(receiptPath));
assert(strcmp(receipt.status,'THREE_EXACT_DEV_ROWS_VERIFIED')&& ...
    strcmpi(receipt.source_sha256,'d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3')&& ...
    strcmpi(receipt.extracted_csv_sha256,sha256_file(csvPath))&&numel(receipt.rows)==3, ...
    'PAIRED:SpecReceipt','DEV extraction provenance differs.');
importOpts=detectImportOptions(csvPath,'VariableNamingRule','preserve');
importOpts=setvartype(importOpts,{'scene_id','split','task','class_id'},'string');
rows=readtable(csvPath,importOpts);
ids=["DL1018_DEV_T1_C00_W03","DL1018_DEV_T2_C02_W15", ...
    "DL1018_DEV_T3_C10_W11"];
tasks=["HELIX","FIG8_3D","SQUARE"];
classes=["NONE","2","34"];
cIds=[0,2,10];
windIds=[3,15,11];
seeds=[2026121803,2026122847,2026123971];
rowHashes=["4546e417fcb2af93f09c83999e6dc0535cf07b58d4f4240e1d751f98ed19a824", ...
    "c8f3dde48b76ae351fe40c30866ff55fa8235e32914a5128e03a1f6b954456f5", ...
    "9f4d08ddc375a4be074c659e04827c49d957518e6098a2a3128788eb87d1452a"];
assert(height(rows)==3&&isequal(string(rows.scene_id(:)),ids(:))&& ...
    isequal(string({receipt.rows.scene_id}),ids)&& ...
    isequal(string({receipt.rows.source_row_sha256}),rowHashes), ...
    'PAIRED:SpecScope','The isolated CSV must contain exactly the three pinned DEV rows.');
ix=find(ids==string(sceneId));
assert(numel(ix)==1,'PAIRED:SceneId','Scene ID is outside the three DEV rows.');
specRow=rows(ix,:);
assert(numel(ix)==1&&string(specRow.split)=="DEV"&& ...
    double(specRow.split_code)==2&&double(specRow.source_split_code)==1&& ...
    double(specRow.sealed)==0&&double(specRow.t)==ix-1&& ...
    string(specRow.task)==tasks(ix)&&double(specRow.c)==cIds(ix)&& ...
    string(specRow.class_id)==classes(ix)&&double(specRow.w)==windIds(ix)&& ...
    double(specRow.seed)==seeds(ix)&&double(receipt.rows(ix).seed)==seeds(ix), ...
    'PAIRED:Spec','Spec identity, task, class, wind or seed differs.');
[scene,metadata]=construct_scene(specRow,cfg);
scene.reference_contract_id='DL1018_SCENE_REF_FIG8_A2_V2';
metadata.reference_contract_id=scene.reference_contract_id;
out=struct('spec',specRow,'scene',scene,'metadata',metadata);
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
