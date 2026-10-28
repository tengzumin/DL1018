function root_audit_train24_snapshots_v1()
% Independent metadata/numeric snapshot readback. No episode or Plant.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
base=fullfile(root,'reports','attitude_cm18_datarepair_20261024');
out=fullfile(base,'ROOT_TRAIN24_SNAPSHOT_READBACK_v1.json');
assert(~isfile(out),'No overwrite');
t=jsondecode(fileread(fullfile(base,'ROOT_C5_MATCHED_TRAIN24_PROTOCOL_TASKBOOK_v1.json')));
p=jsondecode(fileread(fullfile(root,'reports','attitude_position_context_probe_20261024', ...
    'c5_matched_train24_v1','PREPARED_C5_MATCHED_TRAIN24_v1.json')));
assert(strcmp(p.status,'PREPARED_NO_PLANT')&&p.plant_calls==0&&numel(p.snapshot_rows)==24);
c=load(p.C5_snapshot_path,'cfg','opts','W0','modelIdentity','sourceIdentity');
rows=cell(24,1);
for i=1:24
    r=p.snapshot_rows(i); s=p.scene_rows(i); target=t.scene_rows(i);
    assert(strcmp(r.canonical_scene_id,target.canonical_scene_id)&&r.sequence_index==i);
    q=load(r.path,'cfg','opts','W0','c5ModelIdentity','sourceIdentity','snapshotMeta');
    assert(isequaln(q.cfg,c.cfg)&&isequaln(q.opts,c.opts)&&isequaln(q.W0,c.W0));
    assert(isequaln(q.c5ModelIdentity,c.modelIdentity)&&isequaln(q.sourceIdentity,c.sourceIdentity));
    m=q.snapshotMeta;
    assert(strcmp(m.canonical_scene_id,target.canonical_scene_id)&&m.sequence_index==i);
    assert(strcmp(m.source_runtime_scene_id,s.source_runtime_scene_id));
    assert(strcmp(m.raw_sha256,target.raw_sha256)&&strcmp(m.run_start_sha256,target.run_start_sha256));
    raw=load(s.raw_path,'scene');
    assert(strcmp(char(raw.scene.scene_id),s.source_runtime_scene_id));
    z=m.mutable_initial_state;
    assert(isequaln(double(raw.scene.initial_state(:)),double(z.initial_state(:))));
    assert(all(z.attitude_rbf_W_initial==0,'all')&&all(z.position_rbf_W_initial==0,'all'));
    assert(all(z.stage1_position_history_initial==0,'all')&&z.stage1_position_history_fill_initial==0);
    assert(all(z.stage1_pcf_eta_initial==0)&&all(z.delayed_af_integral_initial==0));
    assert(all(z.delayed_prediction_reference_integral_initial==0));
    assert(isequaln(z.stage1_position_head_W0,q.opts.stage1_position_runtime.position_only_search_head.W0));
    assert(q.opts.rbf_attitude_enabled&&q.opts.rbf_attitude_output_enabled&&q.opts.rbf_attitude_update_enabled);
    assert(~q.opts.rbf_position_output_enabled&&~q.opts.rbf_position_update_enabled);
    assert(isequal(double(q.opts.position_coordinate_mask(:)),[1;1;0]));
    assert(~isfield(q.opts,'r2e_first_plant_step_marker'));
    if strcmp(target.task,'T2')
        assert(strcmp(s.source_runtime_scene_id,[target.canonical_scene_id '_ACC_FIX_V1']));
        assert(~isempty(s.source_plant_marker_path)&&~isempty(s.source_plant_marker_sha256));
    end
    rows{i}=struct('scene_id',target.canonical_scene_id,'status','PASS', ...
        'cfg_opts_model_exact',true,'initial_state_exact',true,'declared_mutable_reset_zero',true);
end
result=struct('schema','ROOT_TRAIN24_SNAPSHOT_READBACK_V1','status','PASS_ALL24', ...
    'rows',{rows},'Plant_calls',0,'training_steps',0,'TEST_access',false, ...
    'scope','Snapshot identity/readback and declared reset only; actual runtime reset needs first-flight raw audit.');
fid=fopen(out,'wt'); assert(fid>=0); cleanup=onCleanup(@()fclose(fid));
fwrite(fid,jsonencode(result),'char');
disp('PASS_ALL24');
end
