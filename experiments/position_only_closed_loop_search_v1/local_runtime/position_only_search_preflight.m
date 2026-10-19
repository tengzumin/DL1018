function report=position_only_search_preflight(root)
% Zero-Plant protocol, path, identity, and legacy-parity checks.
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','position_only_closed_loop_search_v1');
addpath(genpath(fullfile(root,'matlab')));[cfg,~,resolved]=init_dl1018();
assert(strcmp(root,resolved),'POSSEARCH:Root','Unexpected project root.');
local=fullfile(out,'local_runtime');addpath(genpath(local),'-begin');rehash;
assert(startsWith(which('run_episode_dl1018'),local,'IgnoreCase',true)&& ...
    startsWith(which('run_dl1018_closed_loop'),local,'IgnoreCase',true)&& ...
    startsWith(which('position_stage1_model_forward_v2'),local,'IgnoreCase',true)&& ...
    startsWith(which('position_only_search_head_step'),local,'IgnoreCase',true), ...
    'POSSEARCH:PathIsolation','New experiment runtime or Head helper is not active.');
headStep=@position_only_search_head_step;
modelFile=fullfile(root,'models','position','selected','matlab_model_and_parity.mat');
normalizerFile=fullfile(root,'models','position','selected','normalizer.npz');
assert(isfile(modelFile)&&isfile(normalizerFile),'POSSEARCH:ModelFiles','Selected Final package is incomplete.');
z=load(modelFile,'model');model=z.model;assert(isequal(size(model.output_W),[33,3]),'POSSEARCH:W0','Final W0 must be 33x3.');
selection=jsondecode(fileread(fullfile(root,'configs','selected_models.json')));
model.model_id=char(selection.position_selected.selected_model_id);
assert(strcmp(model.model_id,'DL1018_POSITION_SELECTED')&& ...
    strcmp(char(selection.position_selected.selected_origin),'FINAL'), ...
    'POSSEARCH:SelectedIdentity','Selected position model is not the original Final encoder.');
Bopts=controller_options_dl1018(cfg,'B');Fopts=position_only_search_options(cfg,model,'FEATURE',1,1);
Iopts=position_only_search_options(cfg,model,'BIAS',4,.5);
assert(attitude_equal(Bopts,Fopts)&&attitude_equal(Bopts,Iopts), ...
    'POSSEARCH:Attitude','Candidate attitude options differ from B.');
assert(~Fopts.rbf_position_output_enabled&&~Fopts.rbf_position_update_enabled&& ...
    ~Iopts.rbf_position_output_enabled&&~Iopts.rbf_position_update_enabled&& ...
    Bopts.rbf_position_output_enabled&&Bopts.rbf_position_update_enabled, ...
    'POSSEARCH:PositionPath','Only candidate position RBF is disabled; B remains untouched.');
assert(~isfield(Bopts,'stage1_position_runtime')&& ...
    Fopts.stage1_position_runtime.position_only_search_head.enabled&& ...
    Iopts.stage1_position_runtime.position_only_search_head.enabled, ...
    'POSSEARCH:HeadIsolation','B must not enter the new Head.');
assert(Fopts.stage1_position_runtime.update_dt_scale==1&&Fopts.stage1_position_runtime.beta_scale==1&& ...
    cfg.rbf.runtime.position_update_hz==100&&abs(cfg.plant.dt-.001)<1e-12, ...
    'POSSEARCH:Scheduler','Search must retain original dt, beta ramp, and 100-Hz events.');
assert(logical(Fopts.stage1_position_runtime.command_filter_coordination_v3_5.enabled), ...
    'POSSEARCH:PCF','Original PCF coordination must remain active.');

bridge=readtable(fullfile(out,'..','position_causal_repair_v1','manifests','BRIDGE6.csv'),'TextType','string');
paired=readtable(fullfile(out,'..','position_causal_repair_v1','reports','D1_G04_PAIRED_ALL.csv'),'TextType','string');
final=readtable(fullfile(out,'..','position_causal_repair_v1','reports','D3_INITIAL_FINAL_BRIDGE.csv'),'TextType','string');
specs=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
dev=readtable(fullfile(root,'reports','POSITION_DEV.csv'),'TextType','string');devB=dev(dev.method=="B",:);
devPre=jsondecode(fileread(fullfile(root,'experiments','training_data_structure_compare_v2','reports','D6_PREFLIGHT_HISTORY.json')));
assert(height(devB)==24&&numel(unique(devB.scene_id))==24&&strcmp(char(devPre.status),'PASS')&& ...
    double(devPre.dev_scene_count)==24&&double(devPre.baseline_B_rows_reused)==24&&double(devPre.plant_starts)==0, ...
    'POSSEARCH:DevBaseline','Existing D6 zero-Plant identity verification or 24 B rows are missing.');
assert(all(devB.status=="STABLE")&&all(devB.complete)&&all(devB.finite)&&all(devB.transitions==20000), ...
    'POSSEARCH:DevBaselineStatus','DEV B rows must be stable, complete, finite.');
ids=unique(bridge.scene_id,'stable');assert(numel(ids)==6,'POSSEARCH:Bridge','Expected fixed BRIDGE6.');
checks=struct([]);maxFeatureError=0;maxRawError=0;maxAppliedError=0;replayed=0;
episodeHandle=@run_episode_dl1018;episodeInfo=functions(episodeHandle);
assert(startsWith(episodeInfo.file,local,'IgnoreCase',true),'POSSEARCH:EpisodePath','Episode wrapper resolved outside the isolated directory.');
for i=1:numel(ids)
    sceneId=char(ids(i));spec=specs(specs.scene_id==sceneId,:);assert(height(spec)==1,'POSSEARCH:SceneSpec','Missing scene spec.');
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    bm=bridge(bridge.scene_id==sceneId&bridge.role=="B",:);bi=paired(paired.scene_id==sceneId,:);
    fr=final(final.scene_id==sceneId,:);assert(height(bm)==1&&height(bi)==1&&height(fr)==1, ...
        'POSSEARCH:BridgeRows','Nonunique bridge rows for %s.',sceneId);
    assert(parse_bool(bi.B_complete)&&parse_bool(bi.B_finite)&&double(bi.B_transition_count)==20000, ...
        'POSSEARCH:BStatus','B record is not complete, finite, stable for %s.',sceneId);
    bRaw=fullfile(root,strrep(char(bm.raw_path),'/',filesep));assert(isfile(bRaw),'POSSEARCH:BRaw','Missing B raw run.');
    bd=load(bRaw,'scene');assert(scene_equal(scene,bd.scene),'POSSEARCH:BScene','B scene mismatch for %s.',sceneId);
    brs=load_run_start(fullfile(fileparts(bRaw),'run_start.mat'));
    assert(strcmp(brs.run_id,char(bm.run_id))&&isequaln(brs.cfg,cfg)&&attitude_equal(Bopts,brs.opts), ...
        'POSSEARCH:BIdentity','B run/config/attitude identity mismatch for %s.',sceneId);
    fRaw=fullfile(root,strrep(char(fr.raw_path),'/',filesep));assert(isfile(fRaw)&&strcmp(char(fr.status_final),'STABLE')&& ...
        parse_bool(fr.complete_final)&&parse_bool(fr.finite_final)&&double(fr.transitions)==20000, ...
        'POSSEARCH:FinalStatus','Final reference is incomplete for %s.',sceneId);
    fd=load(fRaw,'log','scene');assert(scene_equal(scene,fd.scene),'POSSEARCH:FinalScene','Final scene mismatch for %s.',sceneId);
    frs=load_run_start(fullfile(fileparts(fRaw),'run_start.mat'));
    assert(isequaln(frs.cfg,cfg)&&isequaln(double(frs.opts.stage1_position_runtime.weight),double(model.output_W))&& ...
        strcmp(char(frs.model_id),'DL1018_POSITION_SELECTED'), ...
        'POSSEARCH:FinalIdentity','Final reference model/config identity mismatch for %s.',sceneId);
    lg=fd.log;valid=find(logical(lg.stage1_position_event_inference_valid));
    assert(numel(valid)>1000&&size(lg.stage1_position_event_weight_before_33x3,3)==numel(valid), ...
        'POSSEARCH:EventAudit','Final event audit fields are incomplete for %s.',sceneId);
    W=double(model.output_W);rowRaw=double(lg.stage1_position_event_raw_acceleration_mps2);
    rowApplied=double(lg.stage1_position_event_applied_acceleration_mps2);
    for j=1:numel(valid)
        k=valid(j);phi=double(lg.stage1_position_event_phi_33(k,:)).';
        sEff=double(lg.stage1_position_pcf_event_s_coord_eff_mps(k,:)).';
        dt=double(lg.stage1_position_effective_update_dt_s(k));beta=double(lg.stage1_position_event_beta(k));
        Wbefore=double(lg.stage1_position_event_weight_before_33x3(:,:,j));
        Wafter=double(lg.stage1_position_event_weight_after_33x3(:,:,j));
        assert(max(abs(W(:)-Wbefore(:)))<=1e-10,'POSSEARCH:FinalReplayBefore','Original W state differs for %s event %d.',sceneId,j);
        [raw,applied,Wnext,~,~]=headStep(phi,model.output_W,W,'FEATURE',1,1,sEff,dt,beta,cfg.rbf.position.dmax);
        [rawLegacy,appliedLegacy,Wlegacy]=position_stage1_update_head_pcf_v3_5(phi,W, ...
            double(lg.stage1_position_pcf_event_s_original_mps(k,:)).',dt,beta,cfg.rbf.position.dmax, ...
            double(lg.stage1_position_pcf_event_eta_before_mps(k,:)).',true);
        maxFeatureError=max(maxFeatureError,max(abs(Wnext(:)-Wlegacy(:))));
        maxRawError=max(maxRawError,max(abs(raw(:)-rawLegacy(:))));
        maxAppliedError=max(maxAppliedError,max(abs(applied(:)-appliedLegacy(:))));
        assert(max(abs(raw(:)-rowRaw(k,:).'))<=1e-10&&max(abs(applied(:)-rowApplied(k,:).'))<=1e-10&& ...
            max(abs(Wnext(:)-Wafter(:)))<=1e-10, ...
            'POSSEARCH:FinalStoredReplay','Custom gamma=1/kappa=1 replay diverges from saved Final %s event %d.',sceneId,j);
        W=Wnext;replayed=replayed+1;
    end
    assert(abs(median(double(lg.stage1_position_effective_update_dt_s(valid)))-.01)<1e-12&& ...
        max(abs(double(lg.stage1_position_event_beta(valid))-min(max(double(lg.transition_time(valid))./cfg.rbf.position.beta_rise_time,0),1)))<1e-12, ...
        'POSSEARCH:FinalTiming','Final event timing/beta differs from original schedule for %s.',sceneId);
    z=struct('scene_id',sceneId,'generated_scene_matches_B_and_Final',true,'B_identity_matches',true, ...
        'Final_identity_matches_selected_encoder',true,'Final_event_count',numel(valid), ...
        'Final_Q_m',double(fr.Final_Q_0_20_m),'same_scene_B_Q_m',double(fr.B_Q_0_20_m), ...
        'gamma1_kappa1_reused',true);
    if isempty(checks),checks=z;else,checks(end+1,1)=z;end %#ok<AGROW>
end

% Formula and boundary checks: gamma touches only the error term; leakage and dt remain fixed.
phi=zeros(33,1);phi(1)=.6;phi(end)=.8;W=zeros(33,3);W(2,1)=.25;sEff=[2;-1;.5];dt=.01;beta=.7;
[~,~,w1]=headStep(phi,W,W,'FEATURE',1,1,sEff,dt,beta,cfg.rbf.position.dmax);
[~,~,w4]=headStep(phi,W,W,'FEATURE',4,1,sEff,dt,beta,cfg.rbf.position.dmax);
expected=w4-w1;gradient=dt*(-3*beta*phi*(sEff.'));
assert(max(abs(expected(:)-gradient(:)))<1e-14,'POSSEARCH:Gamma','Gamma did not only scale the error-driven update.');
[~,~,wLeak]=headStep(phi,W,W,'FEATURE',12,1,zeros(3,1),dt,beta,cfg.rbf.position.dmax);
assert(max(abs(wLeak(:)-(W(:)-dt*.002*W(:))))<1e-14,'POSSEARCH:Leak','Gamma changed leakage or dt.');
[~,~,wBound,pBound]=headStep(phi,W,59.9*ones(33,3),'FEATURE',12,1,-10*ones(3,1),dt,1,cfg.rbf.position.dmax);
assert(pBound&&all(abs(wBound(:))<=60),'POSSEARCH:FeatureBound','FEATURE projection bound failed.');
[raw0,app0,b1]=headStep(phi,model.output_W,zeros(3,1),'BIAS',4,.5,sEff,dt,beta,cfg.rbf.position.dmax);
assert(max(abs(raw0(:)-.5*(double(model.output_W).'*phi)))<1e-14&&all(abs(app0)<=cfg.rbf.position.dmax(:)), ...
    'POSSEARCH:BiasOutput','Zero-bias output or common output bound failed.');
[~,~,bBound,pBias]=headStep(phi,model.output_W,2.99*ones(3,1),'BIAS',12,0,-10*ones(3,1),dt,1,cfg.rbf.position.dmax);
assert(pBias&&all(abs(bBound)<=3),'POSSEARCH:BiasBound','BIAS projection bound failed.');
P=struct('mass',cfg.plant.mass,'g',cfg.plant.g,'bs',cfg.control.bs, ...
    'limits',struct('max_tilt',cfg.control.limits.max_tilt));
state=zeros(12,1);state(1)= -1;reference=struct('position',zeros(3,1),'velocity',zeros(3,1),'acceleration',zeros(3,1));
[~,bs]=position_bs_step(state,reference,zeros(3,1),P);
assert(bs.error(1)>0&&bs.surface(1)>0,'POSSEARCH:SignProbe','Expected positive position error/surface probe.');
[rawSign,~,bSign]=headStep(phi,model.output_W,zeros(3,1),'BIAS',4,0,bs.surface,dt,1,cfg.rbf.position.dmax);
[~,appSign]=headStep(phi,model.output_W,bSign,'BIAS',4,0,bs.surface,dt,1,cfg.rbf.position.dmax);
aReq=bs.nominal_acceleration-appSign;
assert(bSign(1)<0&&appSign(1)<0&&aReq(1)>bs.nominal_acceleration(1), ...
    'POSSEARCH:BiasSign','BIAS sign must add acceleration along positive position error through a_req=a_nom-applied.');

report=struct('status','PASS','plant_starts',0,'selected_model_id',char(model.model_id), ...
    'selected_origin','FINAL','encoder_fits',0,'bridge_scene_count',6,'replayed_final_events',replayed, ...
    'max_gamma1_kappa1_state_error_vs_legacy',maxFeatureError,'max_raw_error_vs_legacy',maxRawError, ...
    'max_applied_error_vs_legacy',maxAppliedError,'same_attitude_as_B',true,'B_position_path_unchanged',true, ...
    'position_event_hz',100,'plant_dt_s',cfg.plant.dt,'beta_rise_s',cfg.rbf.position.beta_rise_time, ...
    'PCF_enabled',true,'DEV_B_identity_evidence','D6_PREFLIGHT_HISTORY.json PASS; 24 original B rows stable/complete/finite', ...
    'checks',checks,'bias_sign_probe',struct('e',bs.error,'s',bs.surface, ...
        'a_nom',bs.nominal_acceleration,'applied_bias_only',appSign,'a_req',aReq,'raw_bias_only',rawSign));
if report.plant_starts~=0||max([maxFeatureError,maxRawError,maxAppliedError])>1e-10,error('POSSEARCH:PreflightFail','Zero-Plant preflight failed tolerance.');end
path=fullfile(out,'reports','PREFLIGHT_ZERO_PLANT.json');write_json(path,report);
fprintf('POSITION_SEARCH_PREFLIGHT PASS: Plant=0, Final replay events=%d, max gamma1/kappa1 errors W/raw/applied %.3g/%.3g/%.3g.\n', ...
    replayed,maxFeatureError,maxRawError,maxAppliedError);
end

function yes=attitude_equal(a,b)
names={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled', ...
    'attitude_rbf_frequency_hz','rbf_attitude_gamma_scale'};yes=true;
for i=1:numel(names),yes=yes&&isfield(a,names{i})&&isfield(b,names{i})&&isequaln(a.(names{i}),b.(names{i}));end
end
function yes=scene_equal(a,b)
names={'time','initial_state','environment_wind_I'};yes=true;
for i=1:numel(names),yes=yes&&isequaln(a.(names{i}),b.(names{i}));end
names={'position','velocity','acceleration','yaw','yaw_rate','yaw_acceleration'};
for i=1:numel(names),yes=yes&&isequaln(a.reference.(names{i}),b.reference.(names{i}));end
names={'command','rho_true','rhoDot_true'};
for i=1:numel(names),yes=yes&&isequaln(a.arms.(names{i}),b.arms.(names{i}));end
end
function s=load_run_start(path)
z=load(path);names=fieldnames(z);s=[];
for i=1:numel(names)
    if isstruct(z.(names{i}))&&isfield(z.(names{i}),'run_id'),s=z.(names{i});break;end
end
assert(~isempty(s),'POSSEARCH:RunStart','Could not identify run-start struct at %s.',path);
end
function v=parse_bool(x)
if islogical(x),v=x;elseif isnumeric(x),v=x~=0;else,v=any(strcmpi(char(string(x)),{'true','1'}));end
end
function write_json(path,s)
fid=fopen(path,'w');assert(fid>0,'POSSEARCH:Report','Cannot write %s.',path);fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
end
