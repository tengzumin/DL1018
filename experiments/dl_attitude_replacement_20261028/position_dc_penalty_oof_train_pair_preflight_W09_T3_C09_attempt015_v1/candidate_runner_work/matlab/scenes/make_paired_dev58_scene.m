function out=make_paired_dev58_scene(sceneId,cfg)
% Rebuild only the 58 unpaired DEV/VAL scenes from the isolated CSV and receipt.
assert(isstruct(cfg),'DEV58:Config','Expected frozen C5 cfg.');
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
csvPath=fullfile(root,'configs','scene_specs_dev58.csv');
receiptPath=fullfile(root,'configs','scene_specs_dev58_receipt.json');
assert(isfile(csvPath)&&isfile(receiptPath)&& ...
    strcmpi(sha256_file(csvPath),'3657bf4328391944f4664b6aa1791655ec716d6be1b6e375f5c20316002aebaf')&& ...
    strcmpi(sha256_file(receiptPath),'d10a8a924ae1a7f89657cd4fc9f43ff5249f1df5667b4440ed3c7ce5af47bd44'), ...
    'DEV58:InputSHA','DEV58 CSV or receipt SHA differs.');
receipt=jsondecode(fileread(receiptPath));
assert(strcmp(receipt.schema,'MORPH_DEV2_DEV58_SCENE_SOURCE_RECEIPT_V1')&& ...
    strcmp(receipt.status,'EXACT_58_ROWS_FROM_LOCKED_DEV72_COHORT')&& ...
    strcmpi(receipt.source_sha256,'d116b74dc6d9ce3c21a40fcd48b4153a0adc09e98a6c8d341c0f1b6ba680b4e3')&& ...
    double(receipt.source_rows_located)==72&&logical(receipt.source_scan_stopped_after_final_locked_dev_val_row)&& ...
    ~logical(receipt.TEST_rows_selected_or_persisted)&&numel(receipt.rows)==58&& ...
    numel(receipt.excluded_reuse_ids)==14, ...
    'DEV58:Receipt','DEV58 input receipt or DEV72 reuse lineage differs.');
opts=detectImportOptions(csvPath,'VariableNamingRule','preserve');
opts=setvartype(opts,{'scene_id','split','task','class_id'},'string');
rows=readtable(csvPath,opts);
expectedIds=string({receipt.rows.scene_id}).';
assert(height(rows)==58&&isequal(string(rows.scene_id(:)),expectedIds(:))&& ...
    all(ismember(string(rows.split(:)),["DEV";"VAL"]))&& ...
    all(~contains(string(rows.scene_id(:)),"TEST"))&& ...
    all(double(rows.source_split_code(:))==1)&&all(double(rows.sealed(:))==0), ...
    'DEV58:Rows','Fixed DEV58 scene identity or split differs.');
sourceLines=read_csv_lines(csvPath);
assert(numel(sourceLines)==59, ...
    'DEV58:CSV','Expected one header plus exactly fifty-eight raw rows.');
for k=1:58
    assert(strcmpi(sha256_text(sourceLines{k+1}),char(string(receipt.rows(k).source_row_sha256)))&& ...
        strcmp(char(string(rows.scene_id(k))),char(string(receipt.rows(k).scene_id))), ...
        'DEV58:RowSHA','DEV/VAL source row mismatch at row %d.',k);
end
ix=find(expectedIds==string(sceneId));
assert(numel(ix)==1,'DEV58:SceneId','Scene ID outside the fixed 58-scene DEV/VAL cohort.');
specRow=rows(ix,:);
if startsWith(string(sceneId),"DL1018_DEV_"),expectedSplit="DEV";else,expectedSplit="VAL";end
assert(string(specRow.split)==expectedSplit&&double(specRow.source_split_code)==1&&double(specRow.sealed)==0, ...
    'DEV58:Spec','Spec split differs from scene ID.');
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
