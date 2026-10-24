root=pwd;
entry=fullfile(root,'experiments','c5_test48_recovery_v1','run_dssm_tail16_v1.m');
issues=checkcode(entry,'-id');
scope=jsondecode(fileread(fullfile(fileparts(mfilename('fullpath')),'RECOVERY208_SCOPE_v1.json')));
assert(iscell(scope.blocks)); tail=scope.blocks{1}; assert(numel(tail.scene_ids)==16);
manifest=jsondecode(fileread(fullfile(root,'reports','paper_continuation_20261023','test_entry_v9','TEST_METHOD_SOURCE_MANIFEST_v4.json')));
k=find(strcmp({manifest.methods.method_id},'CORRECTED_DSSM14_G12_R32')); assert(numel(k)==1);
m=manifest.methods(k); pkg=load(fullfile(root,'experiments','c5_test48_v3','input','TEST_METHOD_CFG_OPTS_v1.mat'),'methodSnapshots');
snap=pkg.methodSnapshots{k}; old=load(char(m.cfg_opts_snapshot_path),'cfg','opts'); a=snap.opts; b=old.opts;
if isfield(a,'r2e_first_plant_step_marker'), a=rmfield(a,'r2e_first_plant_step_marker'); end
if isfield(b,'r2e_first_plant_step_marker'), b=rmfield(b,'r2e_first_plant_step_marker'); end
assert(isequaln(snap.cfg,old.cfg)&&isequaln(a,b));
assert(isequaln(snap.opts.stage1_position_runtime.weight,snap.opts.stage1_position_runtime.model.output_W));
fatal=issues(contains(string({issues.id}),{'SYNER','PARSE'})); assert(isempty(fatal));
r=struct('status','PASS_NOPLANT_SYNTAX_SCOPE_SNAPSHOT','plant_calls',0,'matlab_release',version('-release'),'checkcode_messages',issues,'scope_cell',true,'cfg_opts_exact_excluding_marker_only',true);
fid=fopen(fullfile(fileparts(mfilename('fullpath')),'PARENT_NOPLANT_RESULT_v1.json'),'w','n','UTF-8'); fwrite(fid,jsonencode(r,'PrettyPrint',true),'char'); fclose(fid);
disp(r.status);
