d=fileparts(mfilename('fullpath'));
ids={'T1_B','T1_C5','T3_B','T3_C5'}; attempts=[2,1,1,1]; rows=cell(4,1);
for j=1:4
 a=fullfile(d,'runs',ids{j},sprintf('attempt_%02d',attempts(j)));
 p=load(fullfile(a,'raw_run.mat'),'log','scene','method');
 rs=load(fullfile(a,'run_start.mat'),'runStart');
 snap=load(fullfile(d,['snapshot_' ids{j} '_v1.mat']),'cfg','opts');
 src=load(rs.runStart.input_identity.raw_path,'scene'); L=p.log;
 assert(isequaln(p.scene,src.scene)&&isequaln(rs.runStart.cfg,snap.cfg));
 o=rmfield(rs.runStart.opts,'r2e_first_plant_step_marker'); assert(isequaln(o,snap.opts));
 assert(strcmp(L.status,'STABLE')&&isempty(L.safety_stop_reason)&&size(L.state,1)==20001&&L.last_transition==20000&&all(isfinite(L.state(:))));
 assert(max(abs(L.time(:)-(0:.001:20)'))<1e-12);
 assert(isequaln(L.state(1,:).',p.scene.initial_state(:)));
 assert(isequaln(L.reference,p.scene.reference)&&isequaln(L.arms,p.scene.arms)&&isequaln(L.environment_wind_I,p.scene.environment_wind_I));
 assert(L.rbf_event_count==1999);
 aw=L.rbf_event_audit.weight_before(:,:,1); assert(all(aw(:)==0));
 if contains(ids{j},'C5')
  assert(isequaln(L.stage1_position_weight_initial,o.stage1_position_runtime.weight));
 else
  pw=L.rbf_position_event_audit.weight_before(:,:,1);
  assert(all(pw(:)==0)&&L.rbf_position_event_count==1999);
 end
 err=L.state(:,1:3)-L.reference.position;
 rows{j}=struct('flight_id',ids{j},'attempt',attempts(j),'state_samples',20001,'transitions',20000,'attitude_events',L.rbf_event_count,'initial_identity_pass',true,'exogenous_scene_exact',true,'motor_saturated_steps',sum(any(L.motor_saturated,2)),'generalized_clipped_steps',sum(any(L.generalized_clipped,2)),'position_Q_m',sqrt(mean(sum(err.^2,2))));
end
r=struct('schema','ROOT_MATCHED_ALL4_RAW_AUDIT_V1','status','PASS','rows',[rows{:}],'new_successful_probe_flights',4,'prior_failed_zeroPlant_attempts',1,'training_steps',0,'TEST_accessed',false);
out=fullfile(d,'ROOT_ALL4_RAW_AUDIT_v1.json'); assert(~isfile(out));
fid=fopen(out,'wt'); fprintf(fid,'%s',jsonencode(r)); fclose(fid); disp(jsonencode(r));

