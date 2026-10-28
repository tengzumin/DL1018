function root_check_corrected_b_opts_all256_v1()
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));
probe=fullfile(root,'reports','attitude_position_context_probe_20261024');
j=jsondecode(fileread(fullfile(probe,'ROOT_T2_REFERENCE_DATA_LINEAGE_AUDIT_v1.json')));
index=j.corrected_T2_TRAIN_inventory.index_path;
assert(strcmpi(sha(index),'3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e'));
snapshot=fullfile(probe,'snapshot_T1_B_v1.mat');
assert(strcmpi(sha(snapshot),'75f90093f8658ebb4b00b07e494d84419ac6ddcb2db9fe285da555058329652c'));
b=load(snapshot,'cfg','opts');T=readtable(index,'TextType','string');
T=T(T.split=="TRAIN"&T.task=="FIG8_3D"&T.role=="B",:);
assert(height(T)==256&&numel(unique(T.runtime_scene_id))==256);
rows=cell(256,1);
for k=1:256
 id=char(T.runtime_scene_id(k));path=char(T.run_start_path(k));
 assert(endsWith(id,'_ACC_FIX_V1')&&strcmpi(sha(path),char(T.run_start_sha256(k))));
 s=load(path,'runStart');o=s.runStart.opts;
 if isfield(o,'r2e_first_plant_step_marker'),o=rmfield(o,'r2e_first_plant_step_marker');end
 cfgMatch=isequaln(b.cfg,s.runStart.cfg);optsMatch=isequaln(b.opts,o);
 fields=union(fieldnames(b.opts),fieldnames(o));diffs={};
 for n=1:numel(fields)
  f=fields{n};if ~(isfield(b.opts,f)&&isfield(o,f)&&isequaln(b.opts.(f),o.(f))),diffs{end+1}=f;end
 end
 row=struct;row.scene_id=id;row.cfg_exact=cfgMatch;row.B_opts_exact_except_marker=optsMatch;
 row.different_option_fields=diffs;row.run_start_sha256=char(T.run_start_sha256(k));rows{k}=row;
end
pass=all(cellfun(@(x)x.cfg_exact&&x.B_opts_exact_except_marker,rows));
r=struct;r.schema='ROOT_CORRECTED_T2_TRAIN256_B_CFG_OPTS_AUDIT_V1';r.all256_pass=pass;
r.rows=rows;r.raw_files_read=0;r.Plant_calls=0;r.optimizer_steps=0;r.TEST_accessed=false;
out=fullfile(here,'ROOT_CORRECTED_T2_TRAIN256_B_CFG_OPTS_AUDIT_v1.json');assert(~isfile(out));
fid=fopen(out,'wt');fprintf(fid,'%s',jsonencode(r));fclose(fid);
fprintf('ALL256_CFG_B_OPTS_PASS=%d\n',pass);assert(pass,'One or more corrected teacher cfg/opts differ.');
end
function h=sha(path)
md=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);c=onCleanup(@()fclose(fid));
while true,x=fread(fid,1048576,'*uint8');if isempty(x),break;end;md.update(typecast(x(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
