function result=root_audit_a1r_prepared_v1()
% Independent readback of the actual prepared snapshots; never invokes engine.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
base=fullfile(root,'reports','attitude_cm18_datarepair_20261024');
out=fullfile(base,'ROOT_A1R_PREPARED_SNAPSHOTS_AUDIT_v1.json');
assert(~isfile(out),'Refusing overwrite');
p=jsondecode(fileread(fullfile(base,'a1r_screen12_control_v1','A1R_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json')));
c5=load(p.c5_snapshot_path,'cfg','opts','sceneIdentity');
d=jsondecode(fileread(p.deployment_parameters_path));
assert(numel(p.scene_rows)==12&&p.plant_calls==0&&p.optimizer_steps==0);
allowed={'cm18_attitude_v1','r2e_first_plant_step_marker','rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled'};
for k=1:12
    row=p.scene_rows(k); assert(row.sequence_index==k);
    assert(strcmpi(hashfile(row.prepared_snapshot_path),row.prepared_snapshot_sha256));
    assert(strcmpi(hashfile(row.baseline_C5_raw_path),row.baseline_C5_raw_sha256));
    s=load(row.prepared_snapshot_path); b=load(row.baseline_C5_raw_path,'scene');
    assert(isequaln(s.cfg,c5.cfg)&&isequaln(s.scene,b.scene));
    ix=find(strcmp({c5.sceneIdentity.scene_id},row.scene_id));
    assert(isscalar(ix)&&isequaln(s.sceneIdentity,c5.sceneIdentity(ix)));
    opts=s.opts; old=c5.opts;
    for j=1:numel(allowed)
        if isfield(opts,allowed{j}),opts=rmfield(opts,allowed{j});end
        if isfield(old,allowed{j}),old=rmfield(old,allowed{j});end
    end
    assert(isequaln(opts,old));
    for name={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled'}
        assert(isequal(s.opts.(name{1}),false));
    end
    assert(isequal(s.opts.cm18_attitude_v1.enabled,true));
    names=fieldnames(d.parameters);
    assert(numel(fieldnames(s.opts.cm18_attitude_v1.model))==numel(names));
    for j=1:numel(names)
        a=double(s.opts.cm18_attitude_v1.model.(names{j}));v=double(d.parameters.(names{j}));
        assert(numel(a)==numel(v)&&isequal(a(:),v(:)));
    end
    assert(s.modelIdentity.selected_step==40000);
end
result=struct('schema','ROOT_A1R_PREPARED_SNAPSHOTS_AUDIT_V1','status','PASS', ...
    'scene_count',12,'cfg_and_remaining_opts_exact_C5',true,'scene_exact_baseline',true, ...
    'all_three_RBF_flags_false',true,'model_parameters_exact_export',true, ...
    'Plant_calls',0,'engine_calls',0,'optimizer_steps',0,'TEST_accessed',false);
fid=fopen(out,'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fwrite(fid,jsonencode(result),'char');
end
function h=hashfile(path)
md=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'r');assert(fid>=0);c=onCleanup(@()fclose(fid));
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end,md.update(b);end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
