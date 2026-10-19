function summary=d2_runtime_replay_and_decompose(root)
% Offline, read-only replay of saved DL1018 logs. This function never calls Plant.
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','position_causal_repair_v1');
addpath(genpath(fullfile(root,'matlab')));
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'D2:Root','Unexpected DL1018 root.');
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
B=readtable(fullfile(out,'manifests','BRIDGE6.csv'),'TextType','string');
G=readtable(fullfile(out,'manifests','G06_REPLAY2.csv'),'TextType','string');
runtimeRows={};componentRows=[];eventChecks={};
bridgeScenes=unique(B.scene_id,'stable');

for si=1:numel(bridgeScenes)
    sceneId=char(bridgeScenes(si));
    referenceScene=[];referenceCfg=[];referenceAtt=[];
    roleRows=B(B.scene_id==sceneId,:);
    for ri=1:height(roleRows)
        row=roleRows(ri,:);role=char(row.role);split=lower(char(row.split));
        rawPath=fullfile(root,strrep(char(row.raw_path),'/',filesep));
        folder=fileparts(rawPath);startPath=fullfile(folder,'run_start.mat');
        d=load(rawPath,'log','scene');s=load(startPath,'runStart');log=d.log;scene=d.scene;rs=s.runStart;
        assert(strcmp(char(rs.run_id),char(row.run_id))&&strcmp(char(rs.collector_id),role), ...
            'D2:RunIdentity','run_start does not match attempt-index identity for %s/%s.',sceneId,role);
        cfgEqual=isequaln(rs.cfg,cfg);
        if isempty(referenceScene)
            referenceScene=scene;referenceCfg=rs.cfg;referenceAtt=rs.opts;
            sceneExact=true;cfgPairExact=true;attitudeRbfExact=true;
        else
            sceneExact=scene_equal(referenceScene,scene);
            cfgPairExact=isequaln(referenceCfg,rs.cfg);
            attitudeRbfExact=attitude_options_equal(referenceAtt,rs.opts);
        end
        spec=M(M.scene_id==sceneId,:);assert(height(spec)==1,'D2:SceneSpec','Scene id not unique in frozen scene_specs.csv.');
        [E,meta]=export_position_events_dl1018(log,scene,cfg,role,upper(split),spec);
        h5Path=fullfile(root,'data','events','position',split,sceneId,[role '.h5']);
        xH5=read_matrix(h5Path,'/x14',height(E),14);
        rawH5=read_matrix(h5Path,'/target_raw',height(E),3);
        clipH5=read_matrix(h5Path,'/target_clip',height(E),3);
        readyH5=logical(h5read(h5Path,'/ready'));readyH5=readyH5(:);
        timeH5=double(h5read(h5Path,'/event_time_s'));timeH5=timeH5(:);
        xE=table_matrix(E,'x14_',14);rawE=table_matrix(E,'target_raw_',3);clipE=table_matrix(E,'target_clip_',3);
        eventTick=find(logical(log.position_event_flag(:)));
        xLog=nan(height(E),14);loggedFeatureError=NaN;
        if isfield(log,'stage1_position_feature_14')&&numel(eventTick)==height(E)
            xLog=double(log.stage1_position_feature_14(eventTick,:));
            loggedFeatureError=max(abs(xLog(:)-xE(:)));
        end
        evt=struct('scene_id',sceneId,'role',role,'events',height(E),'ready',nnz(E.ready), ...
            'h5_x14_max_abs',max(abs(xE(:)-xH5(:))),'h5_target_raw_max_abs',max(abs(rawE(:)-rawH5(:))), ...
            'h5_target_clip_max_abs',max(abs(clipE(:)-clipH5(:))),'h5_ready_mismatch',nnz(logical(E.ready(:))~=readyH5), ...
            'h5_time_max_abs_s',max(abs(double(E.event_time_s(:))-timeH5)), ...
            'event_index_is_1_to_N',isequal(double(E.event_index(:)),(1:height(E))'), ...
            'ready_first_ordinal',find(logical(E.ready),1,'first'),'ready_count',nnz(E.ready), ...
            'label_closure_max_mps2',max(double(E.label_closure_max_abs_mps2)), ...
            'raw_log_x14_max_abs',loggedFeatureError);
        eventChecks{end+1,1}=evt; %#ok<AGROW>
        assert(evt.events==1999&&evt.ready==1968&&evt.ready_first_ordinal==32, ...
            'D2:EventContract','Event count/ready boundary changed for %s/%s.',sceneId,role);
        assert(evt.h5_x14_max_abs<=1e-12&&evt.h5_target_raw_max_abs<=1e-12&& ...
            evt.h5_target_clip_max_abs<=1e-12&&evt.h5_ready_mismatch==0&&evt.h5_time_max_abs_s<=1e-12, ...
            'D2:H5Parity','Exported event H5 differs from zero-Plant re-export for %s/%s.',sceneId,role);
        assert(isfinite(evt.label_closure_max_mps2)&&evt.label_closure_max_mps2<=1e-9, ...
            'D2:LabelClosure','Label closure failed for %s/%s.',sceneId,role);
        if strcmp(role,'P_INIT_STUDENT')
            assert(isfinite(loggedFeatureError)&&loggedFeatureError<=1e-12, ...
                'D2:LoggedFeature','Logged X14 differs from exporter for %s.',sceneId);
        end
        if ~isempty(referenceScene)
            % A same-scene triplet must have bit-identical deterministic arrays and config.
            assert(sceneExact&&cfgPairExact&&attitudeRbfExact, ...
                'D2:PairedIdentity','Scene, cfg or attitude-RBF identity changed within %s.',sceneId);
        end
        [parts,closeLabel]=decompose(log,scene,cfg,E,role,sceneId);
        if isempty(componentRows),componentRows=parts;else,componentRows=[componentRows;parts];end %#ok<AGROW>

        if strcmp(role,'P_INIT_STUDENT')
            packagePath=fullfile(root,'models','position','initial','matlab_model_and_parity.mat');
            mp=load(packagePath,'model');model=rs.opts.stage1_position_runtime.model;
            packageModel=mp.model;
            packageModelEqual=model_equal(model,packageModel);
            w0=double(rs.opts.stage1_position_runtime.weight);
            w0Equal=isequaln(w0,double(packageModel.output_W));
            rr=replay_model_and_head(log,rs,cfg,model,w0);
            runtimeRows{end+1,1}=make_row(sceneId,role,char(rs.run_id),char(rs.model_id), ...
                string(rawPath),startPath,cfgEqual,sceneExact,attitudeRbfExact,packageModelEqual,w0Equal, ...
                evt,rr,closeLabel); %#ok<AGROW>
        end
    end
end

% Two G06 Final P_A runs and their exact same-scene B baselines were fixed by scene-id order.
g06Scenes=unique(G.scene_id,'stable');
for si=1:numel(g06Scenes)
    sceneId=char(g06Scenes(si));roleRows=G(G.scene_id==sceneId,:);
    sceneRef=[];cfgRef=[];optsRef=[];
    for ri=1:height(roleRows)
        row=roleRows(ri,:);role=char(row.role);split='dev';
        rawPath=fullfile(root,strrep(char(row.raw_path),'/',filesep));
        folder=fileparts(rawPath);startPath=fullfile(folder,'run_start.mat');
        d=load(rawPath,'log','scene');s=load(startPath,'runStart');log=d.log;scene=d.scene;rs=s.runStart;
        cfgEqual=isequaln(rs.cfg,cfg);
        if isempty(sceneRef),sceneRef=scene;cfgRef=rs.cfg;optsRef=rs.opts;
        else
            assert(scene_equal(sceneRef,scene)&&isequaln(cfgRef,rs.cfg)&&attitude_options_equal(optsRef,rs.opts), ...
                'D2:G06PairIdentity','G06 B/P_A scene or common config mismatch at %s.',sceneId);
        end
        if strcmp(role,'P_A')
            assert(strcmp(char(rs.model_id),'DL1018_POSITION_SELECTED'),'D2:G06FinalModel','G06 P_A model id mismatch.');
            packagePath=fullfile(root,'models','position','selected','matlab_model_and_parity.mat');
            mp=load(packagePath,'model');model=rs.opts.stage1_position_runtime.model;packageModel=mp.model;
            packageModelEqual=model_equal(model,packageModel);
            w0=double(rs.opts.stage1_position_runtime.weight);w0Equal=isequaln(w0,double(packageModel.output_W));
            spec=M(M.scene_id==sceneId,:);[E,meta]=export_position_events_dl1018(log,scene,cfg,role,'DEV',spec); %#ok<ASGLU>
            ev=event_summary_only(E);
            rr=replay_model_and_head(log,rs,cfg,model,w0);
            runtimeRows{end+1,1}=make_row(sceneId,'P_A',char(rs.run_id),char(rs.model_id), ...
                string(rawPath),startPath,cfgEqual,true,attitude_options_equal(optsRef,rs.opts), ...
                packageModelEqual,w0Equal,ev,rr,max(double(E.label_closure_max_abs_mps2))); %#ok<AGROW>
        end
    end
end

RT=struct2table([runtimeRows{:}]);
writetable(RT,fullfile(out,'reports','D2_RUNTIME_REPLAY.csv'));
EC=struct2table([eventChecks{:}]);writetable(EC,fullfile(out,'reports','D2_EVENT_H5_PARITY.csv'));
writetable(componentRows,fullfile(out,'reports','D2_LABEL_COMPONENTS.csv'));
summary=struct('phase','D2_COMPLETE','historical_bridge_runs',18,'g06_replay_runs',2, ...
    'new_plant_starts',0,'new_fits',0,'runtime_records',height(RT),'event_h5_parity_records',height(EC), ...
    'component_event_rows',height(componentRows),'max_event_label_closure_mps2',max(EC.label_closure_max_mps2), ...
    'generated_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
fid=fopen(fullfile(out,'state','D2_MATLAB_SUMMARY.json'),'w');fwrite(fid,jsonencode(summary,'PrettyPrint',true),'char');fclose(fid);
fprintf('D2 offline replay complete: %d actual online runs; %d event parity checks; %d component rows; 0 Plant.\n', ...
    height(RT),height(EC),height(componentRows));
end

function yes=scene_equal(a,b)
yes=isequaln(a.time,b.time)&&isequaln(a.initial_state,b.initial_state)&& ...
    isequaln(a.environment_wind_I,b.environment_wind_I)&& ...
    isequaln(a.reference.position,b.reference.position)&&isequaln(a.reference.velocity,b.reference.velocity)&& ...
    isequaln(a.reference.acceleration,b.reference.acceleration)&&isequaln(a.reference.yaw,b.reference.yaw)&& ...
    isequaln(a.reference.yaw_rate,b.reference.yaw_rate)&&isequaln(a.reference.yaw_acceleration,b.reference.yaw_acceleration)&& ...
    isequaln(a.arms.command,b.arms.command)&&isequaln(a.arms.rho_true,b.arms.rho_true)&& ...
    isequaln(a.arms.rhoDot_true,b.arms.rhoDot_true);
end

function yes=attitude_options_equal(a,b)
names={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled', ...
    'attitude_rbf_frequency_hz','rbf_attitude_gamma_scale'};
yes=true;
for i=1:numel(names),yes=yes&&isfield(a,names{i})&&isfield(b,names{i})&&isequaln(a.(names{i}),b.(names{i}));end
yes=yes&&logical(a.rbf_attitude_enabled)&&logical(a.rbf_attitude_output_enabled)&&logical(a.rbf_attitude_update_enabled);
end

function yes=model_equal(a,b)
names={'input_dim','input_mu','input_sigma','knots','spline_W','linear_W','feature_b','architecture','output_W'};
yes=true;
for i=1:numel(names)
    yes=yes&&isfield(a,names{i})&&isfield(b,names{i});
    if ~yes,return;end
    x=a.(names{i});y=b.(names{i});
    if isnumeric(x)&&isnumeric(y),yes=yes&&isequal(size(x),size(y))&&max(abs(double(x(:))-double(y(:))),[],'omitnan')==0;
    else,yes=yes&&strcmp(char(string(x)),char(string(y)));end
end
end

function rr=replay_model_and_head(log,rs,cfg,model,w0)
n=numel(log.transition_time);valid=logical(log.stage1_position_event_inference_valid(:));
ticks=find(valid);eventTicks=find(logical(log.stage1_position_event(:)));
feature=double(log.stage1_position_feature_14);
phiStored=double(log.stage1_position_event_phi_33);rawStored=double(log.stage1_position_event_raw_acceleration_mps2);
appliedStored=double(log.stage1_position_event_applied_acceleration_mps2);
wBefore=double(log.stage1_position_event_weight_before_33x3);
wAfter=double(log.stage1_position_event_weight_after_33x3);
beta=double(log.stage1_position_event_beta(:));dt=double(log.stage1_position_effective_update_dt_s(:));
surface=double(log.stage1_position_pcf_event_s_original_mps);
eta=double(log.stage1_position_pcf_event_eta_before_mps);
maxPhi=0;maxRaw=0;maxApplied=0;maxWNext=0;maxUpdateRaw=0;maxEta=0;
eventPos=zeros(n,1);eventPos(eventTicks)=1:numel(eventTicks);
for j=1:numel(ticks)
    k=ticks(j);p=eventPos(k);assert(p>=32,'D2:History','Valid event before full 32-event history.');
    window=feature(eventTicks(p-31:p),:).';
    phi=position_stage1_model_forward_v2(model,window);
    maxPhi=max(maxPhi,max(abs(phi-phiStored(k,:).')));
    Wb=wBefore(:,:,j);Wa=wAfter(:,:,j);
    raw=Wb.'*phi;maxUpdateRaw=max(maxUpdateRaw,max(abs(raw-rawStored(k,:).')));
    betaK=beta(k);clipped=max(min(raw,cfg.rbf.position.dmax(:)),-cfg.rbf.position.dmax(:));applied=betaK*clipped;
    maxRaw=max(maxRaw,max(abs(raw-rawStored(k,:).')));maxApplied=max(maxApplied,max(abs(applied-appliedStored(k,:).')));
    [~,appliedNext,Wnext,~,~]=position_stage1_update_head_pcf_v3_5(phi,Wb,surface(k,:).',dt(k), ...
        betaK,cfg.rbf.position.dmax,eta(k,:).',true);
    maxWNext=max(maxWNext,max(abs(Wnext(:)-Wa(:))));
    maxApplied=max(maxApplied,max(abs(appliedNext-appliedStored(k,:).')));
end
chain=0;
for j=2:size(wBefore,3),chain=max(chain,max(abs(wBefore(:,:,j)-wAfter(:,:,j-1)),[],'all'));end
heldExpected=zeros(n,3);cache=zeros(1,3);
for k=1:n
    if valid(k),cache=appliedStored(k,:);end
    heldExpected(k,:)=cache;
end
held=double(log.stage1_position_held_applied_acceleration_mps2);
zoh=max(abs(heldExpected(:)-held(:)));
forceErr=max(abs(double(log.stage1_position_injected_force_I_N(:))- ...
    (cfg.plant.mass*double(log.stage1_position_held_applied_acceleration_mps2(:)))));
t=double(log.transition_time(:));expectedBeta=min(max(t/cfg.rbf.position.beta_rise_time,0),1)* ...
    double(rs.opts.stage1_position_runtime.beta_scale);
betaErr=max(abs(beta(valid)-expectedBeta(valid)));
dtErr=max(abs(dt(valid)-.01));
etaRecorded=double(log.stage1_position_pcf_event_eta_before_mps(valid,:));
etaRaw=double(log.stage1_position_pcf_eta_before_mps(valid,:));
if ~isempty(etaRecorded),maxEta=max(abs(etaRecorded(:)-etaRaw(:)));end
rr=struct('event_count',numel(eventTicks),'valid_inference_events',numel(ticks), ...
    'max_phi_abs_error',maxPhi,'max_raw_abs_error',maxRaw,'max_output_then_update_raw_error',maxUpdateRaw, ...
    'max_applied_abs_error',maxApplied,'max_weight_next_abs_error',maxWNext, ...
    'max_weight_event_chain_abs_error',chain,'max_zoh_abs_error_mps2',zoh, ...
    'max_injected_force_mass_closure_N',forceErr,'max_beta_abs_error',betaErr, ...
    'max_event_dt_abs_error_s',dtErr,'max_eta_event_log_abs_error_mps',maxEta, ...
    'W0_reset_abs_error',max(abs(double(log.stage1_position_event_weight_before_33x3(:,:,1))-w0),[],'all'), ...
    'all_1968_events_replayed',numel(ticks)==1968,'pcf_coordination_enabled', ...
    logical(log.stage1_position_pcf_coordination_enabled));
end

function [T,closure]=decompose(log,scene,cfg,E,role,sceneId)
idx=double(E.plant_index(:));n=numel(idx);mass=double(cfg.plant.mass);g=double(cfg.plant.g);
x=double(log.state(idx,:));RrawEuler=double(log.raw_outer_attitude(idx,:));
RactualEuler=x(:,7:9);wind=double(log.wind_force_I(idx,:));
Treq=double(log.controller_clipped_generalized(idx,1));Treal=double(log.realized_generalized(idx,1));
nom=double(log.position_nominal_acceleration_mps2(idx,:));
applied=double(log.position_compensation_applied_acceleration_mps2(idx,:));
Fcmd=double(log.position_commanded_force_N(idx,:));
dWind=wind/mass;dAlloc=zeros(n,3);dAtt=zeros(n,3);dMap=zeros(n,3);
for j=1:n
    Ra=rot_zyx(RactualEuler(j,:));Rr=rot_zyx(RrawEuler(j,:));e3=[0;0;1];
    dAlloc(j,:)=(Ra*e3*(Treal(j)-Treq(j))/mass).';
    dAtt(j,:)=((Ra-Rr)*e3*Treq(j)/mass).';
    dMap(j,:)=(Rr*e3*Treq(j)/mass-[0;0;g]-(nom(j,:)-applied(j,:)).').';
end
dEff=dWind+dAlloc+dAtt+dMap;
target=table_matrix(E,'target_raw_',3);closure=max(abs(dEff(:)-target(:)));
assert(closure<=1e-9,'D2:ComponentClosure','Four residual components fail closure for %s/%s.',sceneId,role);
time=double(E.event_time_s(:));
positionError=double(E.x14_1(:)); %#ok<NASGU>
pos=double(log.reference.position(idx,:))-x(:,1:3);
surf=double(log.rbf_position_surface(idx,:));
filtered=double(log.filtered_attitude_reference(idx,:));
actualVel=x(:,4:6);
if isfield(log,'stage1_position_event_eta_before_mps')
    eta=double(log.stage1_position_event_eta_before_mps(idx,:));
else,eta=nan(n,3);end
if strcmp(role,'P_INIT_STUDENT')
    raw=double(log.stage1_position_event_raw_acceleration_mps2(idx,:));
else
    raw=double(log.position_rbf_estimate_acceleration_mps2(idx,:));
end
event=logical(log.position_event_flag(idx));
studentEvent=false(n,1);inferenceValid=false(n,1);updateDelta=nan(n,1);
if isfield(log,'stage1_position_event')
    studentEvent=logical(log.stage1_position_event(idx));inferenceValid=logical(log.stage1_position_event_inference_valid(idx));
    updateDelta=double(log.stage1_position_event_weight_delta_fro(idx));
end
phase=string(E.phase(:));sceneS=repmat(string(sceneId),n,1);roleS=repmat(string(role),n,1);
T=table(sceneS,roleS,double(E.event_index(:)),idx,time,phase, ...
    pos(:,1),pos(:,2),pos(:,3),surf(:,1),surf(:,2),surf(:,3), ...
    RactualEuler(:,1),RactualEuler(:,2),RactualEuler(:,3), ...
    RrawEuler(:,1),RrawEuler(:,2),RrawEuler(:,3), ...
    filtered(:,1),filtered(:,2),filtered(:,3),actualVel(:,1),actualVel(:,2),actualVel(:,3), ...
    dWind(:,1),dWind(:,2),dWind(:,3),dAlloc(:,1),dAlloc(:,2),dAlloc(:,3), ...
    dAtt(:,1),dAtt(:,2),dAtt(:,3),dMap(:,1),dMap(:,2),dMap(:,3), ...
    dEff(:,1),dEff(:,2),dEff(:,3),applied(:,1),applied(:,2),applied(:,3), ...
    raw(:,1),raw(:,2),raw(:,3),nom(:,1),nom(:,2),nom(:,3),Fcmd(:,1),Fcmd(:,2),Fcmd(:,3), ...
    eta(:,1),eta(:,2),eta(:,3),double(E.beta(:)),double(E.target_raw_1),double(E.target_raw_2),double(E.target_raw_3), ...
    event,studentEvent,inferenceValid,updateDelta, ...
    'VariableNames',{'scene_id','role','event_index','plant_index','time_s','phase', ...
    'e_pos_x_m','e_pos_y_m','e_pos_z_m','surface_x_mps','surface_y_mps','surface_z_mps', ...
    'att_roll_rad','att_pitch_rad','att_yaw_rad','raw_att_roll_rad','raw_att_pitch_rad','raw_att_yaw_rad', ...
    'filtered_ref_roll_rad','filtered_ref_pitch_rad','filtered_ref_yaw_rad','velocity_x_mps','velocity_y_mps','velocity_z_mps', ...
    'd_wind_x_mps2','d_wind_y_mps2','d_wind_z_mps2','d_allocation_x_mps2','d_allocation_y_mps2','d_allocation_z_mps2', ...
    'd_attitude_realization_x_mps2','d_attitude_realization_y_mps2','d_attitude_realization_z_mps2', ...
    'd_mapping_x_mps2','d_mapping_y_mps2','d_mapping_z_mps2','d_effective_x_mps2','d_effective_y_mps2','d_effective_z_mps2', ...
    'd_applied_x_mps2','d_applied_y_mps2','d_applied_z_mps2','d_raw_x_mps2','d_raw_y_mps2','d_raw_z_mps2', ...
    'a_nom_x_mps2','a_nom_y_mps2','a_nom_z_mps2','F_cmd_x_N','F_cmd_y_N','F_cmd_z_N', ...
    'pcf_eta_x_mps','pcf_eta_y_mps','pcf_eta_z_mps','beta','target_raw_x_mps2','target_raw_y_mps2','target_raw_z_mps2', ...
    'position_event','student_event','inference_valid','head_update_delta_fro'});
end

function r=make_row(sceneId,role,runId,modelId,rawPath,startPath,cfgEqual,sceneEqual,attEqual,modelEqualFlag,w0Equal,evt,rr,closure)
r=struct('scene_id',sceneId,'role',role,'run_id',runId,'model_id',modelId, ...
    'raw_path',char(rawPath),'run_start_path',startPath,'run_start_bytes',dir(startPath).bytes, ...
    'cfg_matches_current',cfgEqual,'scene_identity_exact',sceneEqual,'attitude_rbf_identity_exact',attEqual, ...
    'model_matches_current_package',modelEqualFlag,'W0_matches_package',w0Equal, ...
    'event_count',evt.events,'ready_count',evt.ready,'event_h5_x14_max_abs',evt.h5_x14_max_abs, ...
    'event_h5_target_raw_max_abs',evt.h5_target_raw_max_abs,'event_h5_target_clip_max_abs',evt.h5_target_clip_max_abs, ...
    'event_h5_time_max_abs_s',evt.h5_time_max_abs_s,'max_label_closure_mps2',closure, ...
    'valid_inference_events',rr.valid_inference_events,'max_phi_abs_error',rr.max_phi_abs_error, ...
    'max_raw_abs_error',rr.max_raw_abs_error,'max_applied_abs_error',rr.max_applied_abs_error, ...
    'max_weight_next_abs_error',rr.max_weight_next_abs_error,'max_weight_event_chain_abs_error',rr.max_weight_event_chain_abs_error, ...
    'max_zoh_abs_error_mps2',rr.max_zoh_abs_error_mps2,'max_injected_force_mass_closure_N',rr.max_injected_force_mass_closure_N, ...
    'max_beta_abs_error',rr.max_beta_abs_error,'max_event_dt_abs_error_s',rr.max_event_dt_abs_error_s, ...
    'max_eta_event_log_abs_error_mps',rr.max_eta_event_log_abs_error_mps,'W0_reset_abs_error',rr.W0_reset_abs_error, ...
    'all_1968_events_replayed',rr.all_1968_events_replayed,'pcf_coordination_enabled',rr.pcf_coordination_enabled);
end

function ev=event_summary_only(E)
ev=struct('events',height(E),'ready',nnz(E.ready),'h5_x14_max_abs',NaN,'h5_target_raw_max_abs',NaN, ...
    'h5_target_clip_max_abs',NaN,'h5_ready_mismatch',NaN,'h5_time_max_abs_s',NaN, ...
    'event_index_is_1_to_N',true,'ready_first_ordinal',find(E.ready,1,'first'),'ready_count',nnz(E.ready), ...
    'label_closure_max_mps2',max(double(E.label_closure_max_abs_mps2)),'raw_log_x14_max_abs',NaN);
end

function A=read_matrix(path,name,nRows,nCols)
A=double(h5read(path,name));
if isequal(size(A),[nCols nRows]),A=A.';end
assert(isequal(size(A),[nRows nCols]),'D2:H5MatrixShape','Unexpected %s shape in %s: %s.',name,path,mat2str(size(A)));
end

function X=table_matrix(E,prefix,width)
X=zeros(height(E),width);
for j=1:width,X(:,j)=double(E.(sprintf('%s%d',prefix,j)));end
end

function R=rot_zyx(e)
phi=e(1);theta=e(2);psi=e(3);cp=cos(phi);sp=sin(phi);ct=cos(theta);st=sin(theta);cy=cos(psi);sy=sin(psi);
R=[cy*ct,cy*st*sp-sy*cp,cy*st*cp+sy*sp; ...
    sy*ct,sy*st*sp+cy*cp,sy*st*cp-cy*sp;-st,ct*sp,ct*cp];
end
