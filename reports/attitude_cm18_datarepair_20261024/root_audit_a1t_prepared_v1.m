function result=root_audit_a1t_prepared_v1()
% Independent snapshot readback; no engine or Plant.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
base=fullfile(root,'reports','attitude_cm18_datarepair_20261024');
out=fullfile(base,'ROOT_A1T_PREPARED_SNAPSHOTS_AUDIT_v1.json');assert(~isfile(out));
prepPath=fullfile(base,'a1t_screen12_control_v1','A1T_SCREEN12_CONTROL_PREPARATION_RESULT_v1.json');
p=jsondecode(fileread(prepPath));d=jsondecode(fileread(p.deployment_parameters_path));
assert(numel(p.scene_rows)==12&&p.plant_calls==0&&p.optimizer_steps==0);
assert(strcmpi(p.deployment_parameters_sha256,'dd5375623cf47abed1db1e620a7d00358aff71b5985ead13e88ba05218952b42'));
for k=1:12
    row=p.scene_rows(k);assert(row.sequence_index==k);
    assert(strcmpi(hashfile(row.prepared_snapshot_path),row.prepared_snapshot_sha256));
    assert(strcmpi(hashfile(row.a1r_snapshot_path),row.a1r_snapshot_sha256));
    s=load(row.prepared_snapshot_path);r=load(row.a1r_snapshot_path);
    assert(isequaln(s.cfg,r.cfg)&&isequaln(s.scene,r.scene)&&isequaln(s.sceneIdentity,r.sceneIdentity));
    assert(isequaln(s.sourceIdentity,r.sourceIdentity));
    a=s.opts;b=r.opts;
    a=rmfield(a,'r2e_first_plant_step_marker');b=rmfield(b,'r2e_first_plant_step_marker');
    a.cm18_attitude_v1=rmfield(a.cm18_attitude_v1,'model');
    b.cm18_attitude_v1=rmfield(b.cm18_attitude_v1,'model');
    assert(isequaln(a,b));
    for flag={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled'}
        assert(isequal(s.opts.(flag{1}),false));
    end
    names=fieldnames(d.parameters);
    assert(numel(fieldnames(s.opts.cm18_attitude_v1.model))==numel(names));
    for j=1:numel(names)
        x=double(s.opts.cm18_attitude_v1.model.(names{j}));y=double(d.parameters.(names{j}));
        assert(numel(x)==numel(y)&&isequal(x(:),y(:)));
    end
    assert(s.modelIdentity.selected_step==40000);
end
result=struct('schema','ROOT_A1T_PREPARED_SNAPSHOTS_AUDIT_V1','status','PASS', ...
    'scene_count',12,'cfg_scene_source_exact_A1R',true,'remaining_opts_exact_A1R',true, ...
    'model_parameters_exact_frozen_export',true,'RBF_three_flags_false',true, ...
    'Plant_calls',0,'engine_calls',0,'optimizer_steps',0,'TEST_accessed',false);
fid=fopen(out,'w');assert(fid>=0);c=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(result),'char');
end
function h=hashfile(path)
md=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'r');assert(fid>=0);c=onCleanup(@()fclose(fid));
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end,md.update(b);end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
