function run_morph_dev2_screen12(releasePath,releaseSha,attemptDir)
% Two preregistered morphology screen12s, baseline then candidate, no retry.
entry=fileparts(mfilename('fullpath'));
root=entry;
releasePath=char(releasePath); releaseSha=lower(char(releaseSha)); attemptDir=char(attemptDir);
assert(strcmp(sha256_file(releasePath),releaseSha),'MORPHDEV2:ReleaseSHA','Release SHA differs.');
release=jsondecode(fileread(releasePath));
assert(strcmp(release.schema,'PAIRED_MORPH_DEV2_SCREEN12_ROOT_RELEASE_V1')&&logical(release.approved)&& ...
    strcmp(release.scope,'MORPH_DEV2_SCREEN12')&& ...
    double(release.max_runner_calls)==24&&double(release.max_transitions)==480000&&double(release.max_new_bytes)==10*1024^3&& ...
    double(release.minimum_free_bytes)==30*1024^3&& ...
    ~logical(release.training_authorized)&&~logical(release.TEST_authorized)&& ...
    ~logical(release.retry_authorized)&& ...
    isequal(string(release.scene_ids(:)).', ...
        ["DL1018_VAL_T1_C00_W07","DL1018_VAL_T1_C02_W09","DL1018_VAL_T1_C05_W12","DL1018_VAL_T1_C08_W15","DL1018_VAL_T2_C00_W10","DL1018_VAL_T2_C02_W12","DL1018_VAL_T2_C05_W15","DL1018_VAL_T2_C06_W00","DL1018_VAL_T3_C00_W13","DL1018_VAL_T3_C02_W15","DL1018_VAL_T3_C03_W00","DL1018_VAL_T3_C12_W09"])&& ...
    isequal(string(release.arm_order(:)).',["baseline","candidate"]), ...
    'MORPHDEV2:Release','Root release is absent or does not approve exactly this screen12 scope.');
lockPath=char(release.source_lock_path);
assert(strcmp(sha256_file(lockPath),lower(char(release.source_lock_sha256))), ...
    'MORPHDEV2:SourceLockSHA','Final source-lock SHA differs.');
lock=jsondecode(fileread(lockPath));
assert(strcmp(lock.schema,'SOURCE_LOCK_MORPH_DEV2_SCREEN12_V1')&& ...
    strcmp(lock.status,'FROZEN_INPUTS')&&~logical(lock.executed)&& ...
    ~logical(lock.closed_loop_runs_authorized)&& ...
    strcmp(lock.manifest.sha256,release.manifest_sha256)&& ...
    numel(lock.sources)==39&&numel(lock.inputs)==17&& ...
    strcmp(sha256_file(lock.taskbook.path),lock.taskbook.sha256)&& ...
    strcmp(sha256_file(lock.wrapper.path),lock.wrapper.sha256)&& ...
    strcmp(sha256_file(lock.launcher.path),lock.launcher.sha256)&& ...
    strcmp(sha256_file(lock.checker.path),lock.checker.sha256)&& ...
    strcmp(sha256_file(lock.state.path),lock.state.sha256)&& ...
    strcmpi(lock.wrapper.path,fullfile(entry,'run_morph_dev2_screen12.m'))&& ...
    strcmpi(lock.manifest.path,fullfile(entry,'manifest','SCREEN12_PREPARED_MANIFEST.json')), ...
    'MORPHDEV2:Lock','Frozen screen12 entry/input identity differs.');
manifest=jsondecode(fileread(lock.manifest.path));
assert(strcmp(sha256_file(lock.manifest.path),lock.manifest.sha256)&& ...
    strcmp(manifest.schema,'MORPH_DEV2_SCREEN12_PREPARED_MANIFEST_V1')&& ...
    manifest.plant_calls==0&&manifest.training_runs==0&&~manifest.TEST_accessed, ...
    'MORPHDEV2:Manifest','No-Plant manifest differs.');expectedAttempt=fullfile(entry,'attempts',char(release.attempt_id));
assert(isfolder(attemptDir)&&same_path(attemptDir,expectedAttempt)&& ...
    ~isfile(fullfile(attemptDir,'batch_status.json'))&& ...
    ~isfile(fullfile(attemptDir,'runner_invocation.json')), ...
    'MORPHDEV2:Attempt','Attempt already has terminal/runner marker.');
verify_control_files(releasePath,releaseSha,lockPath,release,lock);
verify_files(lock);
assert(strcmp(version('-release'),'2025b'),'MORPHDEV2:MATLABRelease','Expected R2025b.');
restoredefaultpath;
addpath(fullfile(root,'matlab','runtime'));
activate_paired_runner();
modelPath=find_input(lock,'model_mat');
snapshotPath=find_input(lock,'c5_snapshot_mat');
modelPack=load(modelPath,'model');
snapshot=load(snapshotPath,'cfg','opts','W0','modelIdentity');
assert(isequal(fieldnames(modelPack),{'model'})&&numel(fieldnames(snapshot))==4&& ...
    all(isfield(snapshot,{'cfg','opts','W0','modelIdentity'})), ...
    'MORPHDEV2:MATVariables','Only the two allowlisted MAT variable sets may be read.');
model=modelPack.model;
cfg=bind_paired_fixed_j0(snapshot.cfg);
assert(strcmp(char(snapshot.cfg.controller_morphology_mode),'fixed')&& ...
    double(cfg.plant.dt)==.001&&isequaln(rmfield(cfg,'attitude_replacement'),snapshot.cfg)&& ...
    strcmp(char(model.model_id),'DSSM14')&&strcmp(char(model.architecture),'DSSM')&& ...
    double(model.seed)==2026102001&&double(model.selected_step)==60000&& ...
    double(model.input_dim)==14&&double(model.window)==32&& ...
    isequal(size(model.output_W),[33,3])&&isequal(double(model.output_W),double(snapshot.W0)), ...
    'MORPHDEV2:ModelCfg','C5 snapshot cfg or DSSM14 model differs.');
identity=manifest.c5; identity.scenes=lock.diagnostic_scenes;
assert(strcmp(paired_sha256_double(double(model.output_W)),identity.W0_sha256)&& ...
    strcmp(hash_normalizer_arrays(model),identity.normalizer_arrays_sha256)&& ...
    strcmp(snapshot.modelIdentity.W0_sha256,identity.W0_sha256)&& ...
    strcmp(snapshot.modelIdentity.normalizer_arrays_sha256,identity.normalizer_arrays_sha256), ...
    'MORPHDEV2:ModelIdentity','W0/normalizer identity differs.');
[cfgSha,~]=json_sha256(cfg);
assert(strcmp(cfgSha,identity.cfg_sha256)&& ...
    strcmp(cfg.attitude_replacement.J0_controller_fixed_sha256,identity.J0_controller_fixed_sha256), ...
    'MORPHDEV2:CfgJ0','C5 cfg or controller J0 differs.');
fixedPlant=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
fixedController=controller_parameters(cfg,fixedPlant,'fixed');
assert(isequal(double(fixedController.inertia),double(cfg.attitude_replacement.J0_controller_fixed_kgm2)), ...
    'MORPHDEV2:J0','Fixed controller inertia differs.');
[baseline,candidateOpts]=make_paired_c5_options(cfg,model);
c5opts=rmfield(baseline,{'paired_arm','paired_position_method_id','rbf_attitude_initial_weight'});
assert(isequaln(c5opts,snapshot.opts)&& ...
    strcmp(json_sha256(c5opts),identity.c5_options_sha256)&& ...
    strcmp(json_sha256(baseline),identity.baseline_options_sha256)&& ...
    strcmp(json_sha256(candidateOpts),identity.candidate_options_sha256), ...
    'MORPHDEV2:Options','C5 or paired effective options differ.');
flags={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled'};
commonBase=rmfield(baseline,[flags,{'paired_arm'}]);
commonCandidate=rmfield(candidateOpts,[flags,{'paired_arm'}]);
assert(isequaln(commonBase,commonCandidate)&& ...
    strcmp(json_sha256(commonBase),identity.common_options_sha256)&& ...
    strcmp(paired_sha256_double(zeros(size(cfg.rbf.position.centers,2),3)),identity.rbf_position_initial_weight_sha256)&& ...
    strcmp(paired_sha256_double(double(baseline.rbf_attitude_initial_weight)),identity.rbf_attitude_initial_weight_sha256), ...
    'MORPHDEV2:CommonOptions','Common options or zero RBF initial weights differ.');
ids={'DL1018_VAL_T1_C00_W07','DL1018_VAL_T1_C02_W09','DL1018_VAL_T1_C05_W12','DL1018_VAL_T1_C08_W15','DL1018_VAL_T2_C00_W10','DL1018_VAL_T2_C02_W12','DL1018_VAL_T2_C05_W15','DL1018_VAL_T2_C06_W00','DL1018_VAL_T3_C00_W13','DL1018_VAL_T3_C02_W15','DL1018_VAL_T3_C03_W00','DL1018_VAL_T3_C12_W09'};
seeds=[2026111807,2026111841,2026111892,2026111943,2026112810,2026112844,2026112895,2026112896,2026113813,2026113847,2026113848,2026114001];
arms={'baseline','candidate'};
results=repmat(struct('scene_id','','arm','','status','NOT_RUN','reason','', ...
    'score',struct(),'delta_score',struct(),'wall_seconds',NaN,'run_dir',''),1,24);
for i=1:12
    for a=1:2, j=2*(i-1)+a; results(j).scene_id=ids{i}; results(j).arm=arms{a}; end
end
runnerCalls=0; confirmedPlantRuns=0; confirmedTransitions=0;
unknownPlantInvocations=0; pairCompleted=false(1,12); pairSafetyPass=false(1,12);
batchStart=utc_now(); batchTimer=tic;
try
    assert(isequal(string(ids),string({identity.scenes(1:12).scene_id}))&& ...
        isequal(double([identity.scenes(1:12).seed]),seeds), ...
        'MORPHDEV2:SceneIdentity','Fixed screen12 scene IDs/seeds differ from preflight.');
    for i=1:12
        out=make_paired_screen12_scene(ids{i},cfg);
        assert(istable(out.spec)&&height(out.spec)==1,'MORPHDEV2:Spec','Expected one spec row.');
        spec=table2struct(out.spec); scene=out.scene; metadata=out.metadata;
        sceneHashes=struct('spec_sha256',json_sha256(spec), ...
            'scene_sha256',json_sha256(scene),'metadata_sha256',json_sha256(metadata));
        frozen=identity.scenes(i);
        assert(strcmp(char(string(spec.scene_id)),ids{i})&&double(spec.seed)==seeds(i)&& ...
            strcmp(sceneHashes.spec_sha256,frozen.spec_sha256)&& ...
            strcmp(sceneHashes.scene_sha256,frozen.scene_sha256)&& ...
            strcmp(sceneHashes.metadata_sha256,frozen.metadata_sha256)&& ...
            isequal(size(scene.time),[20001,1])&&isequal(scene.time,(0:.001:20).'), ...
            'MORPHDEV2:SceneSHA','Regenerated screen12 scene differs from preflight.');
        scores=cell(1,2); armDirs=cell(1,2);
        for a=1:2
            j=2*(i-1)+a;
            assert(runnerCalls<24,'MORPHDEV2:Budget','24-call screen12 budget exhausted.');
            assert(get_free_bytes()>=double(release.minimum_free_bytes), ...
                'MORPHDEV2:Disk','C drive free space below 30 GiB.');
            newBytes=tree_bytes(attemptDir);
            assert(newBytes<double(release.max_new_bytes),'MORPHDEV2:Budget','New outputs reached 10 GiB.');
            if runnerCalls>=2
                firstPairBytes=first_pair_bytes(attemptDir);
                assert(newBytes+(24-runnerCalls)*ceil(firstPairBytes/2)<=double(release.max_new_bytes), ...
                    'MORPHDEV2:BudgetForecast','First-pair bytes predict budget exhaustion.');
            end
            verify_control_files(releasePath,releaseSha,lockPath,release,lock);
            verify_files(lock);
            assert(strcmp(json_sha256(scene),sceneHashes.scene_sha256)&& ...
                strcmp(json_sha256(cfg),cfgSha),'MORPHDEV2:Immutable','Scene/cfg changed before runner.');
            if a==1,opts=baseline;else,opts=candidateOpts;end
            effectiveSha=json_sha256(opts);
            if a==1,expectedOpts=identity.baseline_options_sha256;
            else,expectedOpts=identity.candidate_options_sha256;end
            assert(strcmp(effectiveSha,expectedOpts),'MORPHDEV2:Options','Effective options changed.');
            armDir=fullfile(attemptDir,sprintf('%02d_%s_%s',i,ids{i},arms{a}));
            assert(~isfolder(armDir),'MORPHDEV2:NoOverwrite','Arm directory exists.');
            mkdir(armDir); armDirs{a}=armDir;
            baseRecord=struct('release_sha256',releaseSha, ...
                'source_lock_sha256',lower(char(release.source_lock_sha256)), ...
                'manifest_sha256',lock.manifest.sha256, ...
                'runner_sha256',source_sha(lock,'matlab/runtime/run_paired_observer_closed_loop.m'), ...
                'scene_id',ids{i},'seed',seeds(i),'arm',arms{a}, ...
                'scene_sha256',sceneHashes.scene_sha256,'spec_sha256',sceneHashes.spec_sha256, ...
                'metadata_sha256',sceneHashes.metadata_sha256,'cfg_sha256',cfgSha, ...
                'common_options_sha256',identity.common_options_sha256, ...
                'effective_options_sha256',effectiveSha,'W0_sha256',identity.W0_sha256, ...
                'normalizer_arrays_sha256',identity.normalizer_arrays_sha256, ...
                'rbf_position_initial_weight_sha256',identity.rbf_position_initial_weight_sha256, ...
                'rbf_attitude_initial_weight_sha256',identity.rbf_attitude_initial_weight_sha256, ...
                'batch_stdout_path',fullfile(attemptDir,'stdout.log'), ...
                'batch_stderr_path',fullfile(attemptDir,'stderr.log'));
            startRecord=baseRecord; startRecord.started_utc=utc_now();
            startRecord.status='STARTED_BEFORE_RUNNER_INVOCATION';
            write_json_new(fullfile(armDir,'run_start.json'),startRecord);
            marker=baseRecord; marker.recorded_utc=utc_now();
            marker.kind='RUNNER_INVOCATION';
            marker.first_plant_step_claimed=false;
            write_json_new(fullfile(armDir,'runner_invocation.json'),marker);
            runnerCalls=runnerCalls+1;
            countedLog=false;
            wall=tic;
            try
                rng(seeds(i),'twister');
                log=run_paired_observer_closed_loop(scene,'B2-RBF-Full-SPLIT',cfg,opts);
                assert(isfield(log,'last_transition')&& ...
                    isnumeric(log.last_transition)&&isscalar(log.last_transition)&& ...
                    isfinite(log.last_transition)&&log.last_transition>=0&& ...
                    log.last_transition==floor(log.last_transition), ...
                    'MORPHDEV2:TransitionCount','Returned log has invalid transition count.');
                confirmedTransitions=confirmedTransitions+double(log.last_transition);
                if log.last_transition>0,confirmedPlantRuns=confirmedPlantRuns+1;end
                countedLog=true;
                wallSeconds=toc(wall);
                rawPath=fullfile(armDir,'run_raw.mat');
                assert(java.io.File(rawPath).createNewFile(),'MORPHDEV2:NoOverwrite','Raw path exists.');
                save(rawPath,'log','-v7.3');
                rawSha=sha256_file(rawPath);
                assert(tree_bytes(attemptDir)<=double(release.max_new_bytes), ...
                    'MORPHDEV2:Budget','New outputs exceeded 10 GiB after raw save.');
                assert(strcmp(json_sha256(scene),sceneHashes.scene_sha256)&& ...
                    strcmp(json_sha256(cfg),cfgSha)&&strcmp(json_sha256(opts),effectiveSha), ...
                    'MORPHDEV2:Immutable','Runner mutated scene/cfg/options.');
                verify_control_files(releasePath,releaseSha,lockPath,release,lock);
                verify_files(lock);
                audit=baseRecord; audit.time_size=size(scene.time);
                audit.scene_sha256_after=json_sha256(scene);
                audit.same_scene_payload_sha256=sceneHashes.scene_sha256;
                write_json_new(fullfile(armDir,'scene_audit.json'),audit);
                [score,gate]=score_log(log,scene,a==2);
                scores{a}=score;
                results(j).score=score; results(j).wall_seconds=wallSeconds;
                safetyReasons={};
                if ~logical(gate.passed),safetyReasons{end+1}='Full stable run contract failed.';end
                if a==2
                    if score.motor_saturation_count~=0,safetyReasons{end+1}='Candidate motor saturation count is nonzero.';end
                    if score.generalized_clip_count~=0,safetyReasons{end+1}='Candidate generalized clipping count is nonzero.';end
                    results(j).delta_score=score_delta(scores{1},score);
                end
                safetyGate=struct('passed',isempty(safetyReasons),'requirements', {safetyReasons}, ...
                    'reason',strjoin(safetyReasons,' '));
                status=baseRecord;
                if safetyGate.passed,status.status='COMPLETED_SCREEN12';
                elseif ~logical(gate.passed),status.status='FAILED_ENGINEERING';
                else,status.status='FAILED_SAFETY_GATE';end
                status.ended_utc=utc_now(); status.last_transition=double(log.last_transition);
                status.runner_status=char(log.status); status.safety_stop_reason=char(log.safety_stop_reason);
                status.wall_seconds=wallSeconds; status.raw_path=rawPath;
                status.raw_sha256=rawSha; status.raw_bytes=dir(rawPath).bytes;
                status.score=score; status.engineering_gate=gate; status.safety_gate=safetyGate;
                status.performance_metrics_are_nongating=true;
                write_json_new(fullfile(armDir,'run_status.json'),status);
                results(j).status=status.status; results(j).reason=safetyGate.reason;
                results(j).run_dir=armDir;
                clear log
                if a==2
                    delta=results(j).delta_score;
                    performance=struct('delta_definition','candidate_minus_baseline', ...
                        'q_rmse_improved',delta.q_rmse_m<0,'q_rmse_worsened',delta.q_rmse_m>0, ...
                        'q_early_improved',delta.q_early_rmse_m<0,'q_early_worsened',delta.q_early_rmse_m>0, ...
                        'q_late_improved',delta.q_late_rmse_m<0,'q_late_worsened',delta.q_late_rmse_m>0, ...
                        'so3_rmse_improved',delta.so3_rmse_rad<0,'so3_rmse_worsened',delta.so3_rmse_rad>0, ...
                        'so3_early_improved',delta.so3_early_rmse_rad<0,'so3_early_worsened',delta.so3_early_rmse_rad>0, ...
                        'so3_late_improved',delta.so3_late_rmse_rad<0,'so3_late_worsened',delta.so3_late_rmse_rad>0);
                    pairAudit=struct('schema','MORPH_DEV2_SCREEN12_PAIR_AUDIT_V1', ...
                        'scope','MORPH_DEV2_SCREEN12','scene_id',ids{i}, ...
                        'baseline',scores{1},'candidate',score,'delta_candidate_minus_baseline',delta, ...
                        'same_scene_sha256',sceneHashes.scene_sha256,'status','RECORDED', ...
                        'candidate_engineering_gate',gate,'safety_gate',safetyGate, ...
                        'performance_assessment',performance, ...
                        'performance_metrics_are_nongating',true);
                    write_json_new(fullfile(attemptDir,sprintf('pair_%02d_audit.json',i)),pairAudit);
                    pairCompleted(i)=true; pairSafetyPass(i)=safetyGate.passed;
                end
                assert(safetyGate.passed,'MORPHDEV2:SafetyGate','%s',safetyGate.reason);
            catch armError
                if ~countedLog,unknownPlantInvocations=unknownPlantInvocations+1;end
                if ~isfile(fullfile(armDir,'run_status.json'))
                    status=baseRecord; status.status='FAILED_ENGINEERING'; status.ended_utc=utc_now();
                    status.reason=getReport(armError,'extended','hyperlinks','off');
                    status.last_transition='unknown_if_no_returned_log';
                    if exist('log','var')&&isstruct(log)&&isfield(log,'last_transition')
                        status.last_transition=double(log.last_transition);
                    end
                    status.wall_seconds=toc(wall);
                    if isfile(fullfile(armDir,'run_raw.mat'))
                        status.raw_path=fullfile(armDir,'run_raw.mat');
                        status.raw_sha256=sha256_file(status.raw_path);
                        status.raw_bytes=dir(status.raw_path).bytes;
                    end
                    if ~isempty(scores{a})
                        status.score=scores{a};
                        results(j).score=scores{a};
                    end
                    results(j).wall_seconds=status.wall_seconds;
                    write_json_new(fullfile(armDir,'run_status.json'),status);
                end
                if ~isfile(fullfile(armDir,'scene_audit.json'))
                    audit=baseRecord; audit.status='FAILED_BEFORE_SCORE_GATE';
                    audit.scene_sha256_after=json_sha256(scene);
                    write_json_new(fullfile(armDir,'scene_audit.json'),audit);
                end
                pairPath=fullfile(attemptDir,sprintf('pair_%02d_audit.json',i));
                if ~isfile(pairPath)
                    failedPair=struct('scene_id',ids{i},'baseline',scores{1}, ...
                        'candidate',scores{2},'same_scene_sha256',sceneHashes.scene_sha256, ...
                        'status','INCOMPLETE','performance_metrics_are_nongating',true, ...
                        'failure_reason',armError.message);
                    write_json_new(pairPath,failedPair);
                end
                if strcmp(results(j).status,'NOT_RUN'),results(j).status='FAILED';end
                if isempty(results(j).reason),results(j).reason=armError.message;end
                results(j).run_dir=armDir;
                rethrow(armError);
            end
        end
    end
    assert(all(pairCompleted)&&all(pairSafetyPass), ...
        'MORPHDEV2:Incomplete','Both screen12 pairs must complete their engineering and safety gates.');
    batchStatus='MORPH_DEV2_SCREEN12_COMPLETE'; failureReason='';
catch batchError
    batchStatus='STOPPED_ON_FAILURE';
    failureReason=getReport(batchError,'extended','hyperlinks','off');
end
summary=struct('schema','MORPH_DEV2_SCREEN12_BATCH_STATUS_V1','scope','MORPH_DEV2_SCREEN12', ...
    'status',batchStatus, ...
    'started_utc',batchStart,'ended_utc',utc_now(), ...
    'release_sha256',releaseSha,'source_lock_sha256',char(release.source_lock_sha256), ...
    'manifest_sha256',lock.manifest.sha256, ...
    'runner_invocation_count',runnerCalls, ...
    'confirmed_plant_runs',confirmedPlantRuns, ...
    'confirmed_transitions',confirmedTransitions, ...
    'unknown_plant_invocations',unknownPlantInvocations, ...
    'training_run_count',0,'TEST_accessed',false,'new_bytes',0, ...
    'batch_wall_seconds',toc(batchTimer),'pair_completed',pairCompleted, ...
    'pair_safety_pass',pairSafetyPass,'performance_is_nongating',true,'results',results, ...
    'failure_reason',failureReason,'artifact_errors',{{}});
artifactErrors={};
try,write_results_csv(fullfile(attemptDir,'results.csv'),results);
catch artifactError,artifactErrors{end+1}=getReport(artifactError,'extended','hyperlinks','off');end
if ~isempty(artifactErrors)
    batchStatus='STOPPED_ON_FAILURE'; summary.status=batchStatus;
    summary.failure_reason=strjoin(artifactErrors,' | ');
end
summary.artifact_errors=artifactErrors;
try,write_screen12_report(fullfile(attemptDir,'report.md'),summary);
catch artifactError,artifactErrors{end+1}=getReport(artifactError,'extended','hyperlinks','off');end
if ~isempty(artifactErrors)
    batchStatus='STOPPED_ON_FAILURE'; summary.status=batchStatus;
    summary.failure_reason=strjoin(artifactErrors,' | ');
end
summary.artifact_errors=artifactErrors; summary.batch_wall_seconds=toc(batchTimer);
summary.new_bytes=tree_bytes(attemptDir);
for k=1:4
    statusBytes=numel(unicode2native([jsonencode(summary) newline],'UTF-8'));
    summary.new_bytes=tree_bytes(attemptDir)+statusBytes;
end
write_json_new(fullfile(attemptDir,'batch_status.json'),summary);
fprintf('MORPH_DEV2_SCREEN12_BATCH_JSON:%s\n',jsonencode(summary));
assert(strcmp(batchStatus,'MORPH_DEV2_SCREEN12_COMPLETE'), ...
    'MORPHDEV2:BatchFailed','Screen12 stopped; see batch_status.json.');
end

function verify_control_files(releasePath,releaseSha,lockPath,release,lock)
assert(strcmp(sha256_file(releasePath),releaseSha)&& ...
    strcmp(sha256_file(lockPath),lower(char(release.source_lock_sha256)))&& ...
    strcmp(sha256_file(lock.manifest.path),lock.manifest.sha256), ...
    'MORPHDEV2:ControlSHA','Release, source lock, or manifest identity changed.');
end
function verify_files(lock)
for item=reshape(lock.sources,1,[])
    assert(strcmp(sha256_file(item.path),item.sha256),'MORPHDEV2:SourceSHA','Source changed: %s.',item.path);
end
for item=reshape(lock.inputs,1,[])
    assert(strcmp(sha256_file(item.path),item.sha256),'MORPHDEV2:InputSHA','Input changed: %s.',item.path);
end
for item={lock.wrapper,lock.launcher,lock.checker,lock.taskbook,lock.state,lock.scene_builder,lock.manifest_generator,lock.builder}
    record=item{1};
    assert(strcmp(sha256_file(record.path),record.sha256),'MORPHDEV2:EntrySHA','Entry changed: %s.',record.path);
end
for item=reshape(lock.scene_inputs,1,[])
    assert(strcmp(sha256_file(item.path),item.sha256),'MORPHDEV2:SceneInputSHA','Scene input changed: %s.',item.path);
end
end
function path=find_input(lock,name)
items=lock.inputs(strcmp({lock.inputs.role},name));
assert(numel(items)==1,'MORPHDEV2:Input','Missing unique input role %s.',name);
path=char(items.path);
end

function hash=source_sha(lock,relative)
items=lock.sources(strcmp({lock.sources.relative_path},relative));
assert(numel(items)==1,'MORPHDEV2:Source','Missing source %s.',relative);
hash=char(items.sha256);
end

function [score,gate]=score_log(log,scene,isCandidate)
n=20000;
assert(isequal(size(log.time),[n+1,1])&&isequal(size(log.state),[n+1,12])&& ...
    isequal(size(log.reference.position),[n+1,3])&& ...
    isequal(size(log.transition_time),[n,1])&& ...
    isequal(size(log.filtered_attitude_reference),[n,3])&& ...
    isequal(log.time,scene.time)&&isequal(log.transition_time,scene.time(1:n))&& ...
    strcmp(char(log.status),'STABLE')&&isempty(char(log.safety_stop_reason))&& ...
    double(log.last_transition)==n, ...
    'MORPHDEV2:FullRun','Full 20,001-state/20,000-transition stable run required.');
for name={'state','motor_command','requested_generalized','controller_clipped_generalized', ...
        'allocated_generalized','realized_generalized','filtered_attitude_reference'}
    value=log.(name{1});
    assert(isnumeric(value)&&all(isfinite(value(:))),'MORPHDEV2:Finite','Enabled log field nonfinite: %s.',name{1});
end
for name={'position','velocity','acceleration','yaw','yaw_rate','yaw_acceleration'}
    value=log.reference.(name{1});
    assert(isnumeric(value)&&all(isfinite(value(:))),'MORPHDEV2:Reference','Reference nonfinite: %s.',name{1});
end
assert(isnumeric(log.controller_call_time_s)&&numel(log.controller_call_time_s)==n&& ...
    all(isfinite(log.controller_call_time_s(:))), ...
    'MORPHDEV2:ControllerTime','Controller call timing must be finite for all transitions.');
e=double(log.state(:,1:3))-double(log.reference.position);
eNorm=sqrt(sum(e.^2,2)); axisRmse=sqrt(mean(e.^2,1)); q=sqrt(mean(eNorm.^2));
peak=max(eNorm); stateTime=double(log.time);
earlyState=stateTime<2.2; lateState=stateTime>=2.2;
qEarly=sqrt(mean(sum(e(earlyState,:).^2,2)));
qLate=sqrt(mean(sum(e(lateState,:).^2,2)));
qEarlyAxis=sqrt(mean(e(earlyState,:).^2,1)); qLateAxis=sqrt(mean(e(lateState,:).^2,1));
qEarlyPeak=max(eNorm(earlyState)); qLatePeak=max(eNorm(lateState));
theta=zeros(n,1);
for k=1:n
    actual=rotation_zyx(double(log.state(k,7:9).'));
    desired=rotation_zyx(double(log.filtered_attitude_reference(k,:).'));
    x=(trace(desired.'*actual)-1)/2;
    theta(k)=acos(max(min(x,1),-1));
end
so3=sqrt(mean(theta.^2)); so3Peak=max(theta);
transitionTime=double(log.transition_time);
earlyTransition=transitionTime<2.2; lateTransition=transitionTime>=2.2;
so3Early=sqrt(mean(theta(earlyTransition).^2)); so3Late=sqrt(mean(theta(lateTransition).^2));
so3EarlyPeak=max(theta(earlyTransition)); so3LatePeak=max(theta(lateTransition));
assert(all(isfinite([axisRmse,q,peak,so3,so3Peak]))&& ...
    isequal(size(log.motor_saturated,1),n)&& ...
    isequal(size(log.generalized_clipped,1),n)&&numel(log.tilt_limited)==n&& ...
    nnz(earlyState)==2200&&nnz(lateState)==17801&& ...
    nnz(earlyTransition)==2200&&nnz(lateTransition)==17800, ...
    'MORPHDEV2:Score','Scoring shape, time split, or finite contract differs.');
motorCount=nnz(any(log.motor_saturated,2));
clipCount=nnz(any(log.generalized_clipped,2));
tiltCount=nnz(log.tilt_limited);
score=struct('q_rmse_m',q,'q_axis_rmse_m',axisRmse,'q_peak_m',peak, ...
    'q_early_rmse_m',qEarly,'q_early_axis_rmse_m',qEarlyAxis,'q_early_peak_m',qEarlyPeak, ...
    'q_late_rmse_m',qLate,'q_late_axis_rmse_m',qLateAxis,'q_late_peak_m',qLatePeak, ...
    'so3_rmse_rad',so3,'so3_peak_rad',so3Peak, ...
    'so3_early_rmse_rad',so3Early,'so3_early_peak_rad',so3EarlyPeak, ...
    'so3_late_rmse_rad',so3Late,'so3_late_peak_rad',so3LatePeak, ...
    'q_early_state_points',nnz(earlyState),'q_late_state_points',nnz(lateState), ...
    'so3_early_transitions',nnz(earlyTransition),'so3_late_transitions',nnz(lateTransition), ...
    'motor_saturation_count',motorCount,'generalized_clip_count',clipCount, ...
    'tilt_limited_count',tiltCount,'state_points',n+1,'transitions',n, ...
    'controller_call_time_s_mean',mean(double(log.controller_call_time_s)), ...
    'controller_call_time_excludes_candidate_post_allocator_commit',true);
traceErrors={};
if isCandidate
    required={'phys_attitude_trace','attitude_fusion_rbf_output_enabled', ...
        'attitude_fusion_rbf_update_enabled','rbf_output_held','rbf_weight_norm', ...
        'rbf_weight_max','rbf_weight_derivative_norm','attitude_rbf_estimate_acceleration_rads2', ...
        'attitude_rbf_compensation_torque_Nm','attitude_event_flag'};
    missing=required(~isfield(log,required));
    if ~isempty(missing)
        traceErrors{end+1}=['Missing candidate trace fields: ' strjoin(missing,', ')];
    elseif ~iscell(log.phys_attitude_trace)||numel(log.phys_attitude_trace)~=n|| ...
            ~is_scalar_false(log.attitude_fusion_rbf_output_enabled)|| ...
            ~is_scalar_false(log.attitude_fusion_rbf_update_enabled)|| ...
            numel(log.attitude_event_flag)~=n|| ...
            ~zero_axis_history(log.rbf_output_held,n)|| ...
            ~zero_axis_history(log.attitude_rbf_estimate_acceleration_rads2,n)|| ...
            ~zero_axis_history(log.attitude_rbf_compensation_torque_Nm,n)|| ...
            ~zero_scalar_history(log.rbf_weight_norm,n)|| ...
            ~zero_scalar_history(log.rbf_weight_max,n)|| ...
            ~zero_scalar_history(log.rbf_weight_derivative_norm,n)
        traceErrors{end+1}='Candidate attitude RBF was active or its trace shape differed.';
    else
        for k=1:n
            tr=log.phys_attitude_trace{k};
            traceFields={'sample_index','prepare','commit','morph_command','omega_body', ...
                'is_attitude_event','event_delta_s','rbf_output_enabled','rbf_update_enabled'};
            prepareFields={'time_s','observer','tau_comp_Nm','estimateTorque_Nm'};
            commitFields={'time_s','tau_cmd_clipped_Nm'};
            valid=isstruct(tr)&&isscalar(tr)&&all(isfield(tr,traceFields))&& ...
                isstruct(tr.prepare)&&all(isfield(tr.prepare,prepareFields))&& ...
                isstruct(tr.commit)&&all(isfield(tr.commit,commitFields))&& ...
                isstruct(tr.prepare.observer)&&all(isfield(tr.prepare.observer,{'updated','delta_s'}))&& ...
                isscalar(tr.sample_index)&&isscalar(tr.prepare.time_s)&&isscalar(tr.commit.time_s)&& ...
                isscalar(tr.is_attitude_event)&&isscalar(tr.rbf_output_enabled)&& ...
                isscalar(tr.rbf_update_enabled)&&isscalar(tr.event_delta_s)&& ...
                isscalar(tr.prepare.observer.updated)&&finite_struct(tr);
            if valid
                valid=tr.sample_index==k&&tr.prepare.time_s==log.transition_time(k)&& ...
                    tr.commit.time_s==log.transition_time(k)&& ...
                    isequal(double(tr.morph_command(:)),double(scene.arms.command(k,:).'))&& ...
                    isequal(double(tr.omega_body(:)),double(log.state(k,10:12).'))&& ...
                    isequal(double(tr.commit.tau_cmd_clipped_Nm(:)), ...
                        double(log.controller_clipped_generalized(k,2:4).'))&& ...
                    isequal(double(tr.prepare.estimateTorque_Nm(:)),-double(tr.prepare.tau_comp_Nm(:)))&& ...
                    logical(tr.is_attitude_event)==logical(log.attitude_event_flag(k))&& ...
                    logical(tr.prepare.observer.updated)==logical(tr.is_attitude_event)&& ...
                    ~logical(tr.rbf_output_enabled)&&~logical(tr.rbf_update_enabled);
                if valid&&tr.prepare.observer.updated
                    valid=tr.is_attitude_event&&tr.prepare.observer.delta_s>0&& ...
                        abs(tr.prepare.observer.delta_s-tr.event_delta_s)<1e-10;
                end
            end
            if ~valid
                traceErrors{end+1}=sprintf('Candidate helper time/command/omega/RBF lineage differs at transition %d.',k);
                break
            end
        end
    end
end
gate=struct('passed',isempty(traceErrors),'status','STABLE','safety_stop_reason','', ...
    'candidate_trace_checked',isCandidate,'trace_errors',{traceErrors});
end

function tf=is_scalar_false(value)
tf=(islogical(value)||isnumeric(value))&&isscalar(value)&& ...
    isfinite(double(value))&&~logical(value);
end

function tf=zero_axis_history(value,n)
tf=isnumeric(value)&&isequal(size(value),[n,3])&& ...
    all(isfinite(double(value(:))))&&all(value(:)==0);
end

function tf=zero_scalar_history(value,n)
tf=isnumeric(value)&&isequal(size(value),[n,1])&& ...
    all(isfinite(double(value(:))))&&all(value(:)==0);
end

function ok=finite_struct(value)
ok=true;
if isnumeric(value)
    ok=all(isfinite(value(:)));
elseif isstruct(value)
    for v=reshape(value,1,[])
        names=fieldnames(v);
        for k=1:numel(names)
            if ~finite_struct(v.(names{k})),ok=false;return;end
        end
    end
elseif iscell(value)
    for k=1:numel(value)
        if ~finite_struct(value{k}),ok=false;return;end
    end
end
end

function R=rotation_zyx(e)
r=e(1); p=e(2); y=e(3);
cr=cos(r);sr=sin(r);cp=cos(p);sp=sin(p);cy=cos(y);sy=sin(y);
R=[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr; ...
   sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr; ...
   -sp,cp*sr,cp*cr];
end

function bytes=first_pair_bytes(attemptDir)
dirs=dir(fullfile(attemptDir,'01_*'));
assert(numel(dirs)==2,'MORPHDEV2:BudgetForecast','Expected completed first pair.');
bytes=0;
for k=1:2,bytes=bytes+tree_bytes(fullfile(attemptDir,dirs(k).name));end
end

function tf=same_path(a,b)
tf=strcmpi(char(java.io.File(a).getCanonicalPath()), ...
    char(java.io.File(b).getCanonicalPath()));
end

function bytes=tree_bytes(path)
entries=dir(fullfile(path,'**','*'));
files=entries(~[entries.isdir]);
bytes=sum(double([files.bytes]));
end

function [hash,nbytes]=json_sha256(value)
bytes=unicode2native(jsonencode(value),'UTF-8'); nbytes=numel(bytes);
md=java.security.MessageDigest.getInstance('SHA-256');md.update(uint8(bytes(:)));
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function hash=sha256_file(path)
fid=fopen(path,'r');assert(fid>=0,'MORPHDEV2:Read','Cannot read %s.',path);
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
md=java.security.MessageDigest.getInstance('SHA-256');
while true
    bytes=fread(fid,8*1024*1024,'*uint8');
    if isempty(bytes),break;end
    md.update(bytes);
end
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function hash=hash_normalizer_arrays(model)
md=java.security.MessageDigest.getInstance('SHA-256');
for names={'input_mu','input_sigma'}
    field=names{1};a=reshape(double(model.(field)),1,[]);
    assert(numel(a)==14&&all(isfinite(a)),'MORPHDEV2:Normalizer','Invalid normalizer.');
    header=[field char(0) '((1, 14), ''float64'')' char(0)];
    md.update(typecast(uint8(unicode2native(header,'UTF-8')),'int8'));
    md.update(typecast(a(:),'int8'));
end
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function bytes=get_free_bytes()
drive=java.io.File('C:\'); bytes=double(drive.getUsableSpace());
end

function t=utc_now()
t=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end

function write_json_new(path,value)
write_text_new(path,[jsonencode(value) newline]);
end

function write_text_new(path,value)
file=java.io.File(path);
assert(file.createNewFile(),'MORPHDEV2:NoOverwrite','File already exists: %s.',path);
fid=fopen(path,'w');assert(fid>=0,'MORPHDEV2:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,unicode2native(value,'UTF-8'),'uint8');
end

function write_results_csv(path,results)
columns={'q_rmse_m','q_axis_x_rmse_m','q_axis_y_rmse_m','q_axis_z_rmse_m','q_peak_m', ...
    'q_early_rmse_m','q_early_axis_x_rmse_m','q_early_axis_y_rmse_m','q_early_axis_z_rmse_m','q_early_peak_m', ...
    'q_late_rmse_m','q_late_axis_x_rmse_m','q_late_axis_y_rmse_m','q_late_axis_z_rmse_m','q_late_peak_m', ...
    'so3_rmse_rad','so3_peak_rad','so3_early_rmse_rad','so3_early_peak_rad', ...
    'so3_late_rmse_rad','so3_late_peak_rad','motor_saturation_count','generalized_clip_count', ...
    'tilt_limited_count','controller_call_time_s_mean','q_early_state_points','q_late_state_points', ...
    'so3_early_transitions','so3_late_transitions'};
deltaColumns={'delta_q_rmse_m','delta_q_axis_x_rmse_m','delta_q_axis_y_rmse_m','delta_q_axis_z_rmse_m', ...
    'delta_q_early_rmse_m','delta_q_early_axis_x_rmse_m','delta_q_early_axis_y_rmse_m','delta_q_early_axis_z_rmse_m', ...
    'delta_q_early_peak_m','delta_q_late_rmse_m','delta_q_late_axis_x_rmse_m', ...
    'delta_q_late_axis_y_rmse_m','delta_q_late_axis_z_rmse_m','delta_q_late_peak_m', ...
    'delta_so3_rmse_rad','delta_so3_peak_rad','delta_so3_early_rmse_rad','delta_so3_early_peak_rad', ...
    'delta_so3_late_rmse_rad','delta_so3_late_peak_rad', ...
    'delta_motor_saturation_count','delta_generalized_clip_count','delta_tilt_limited_count', ...
    'delta_controller_call_time_s_mean','delta_q_early_state_points','delta_q_late_state_points', ...
    'delta_so3_early_transitions','delta_so3_late_transitions','delta_state_points','delta_transitions'};
header=[{'scene_id','arm','status','wall_seconds'},columns,deltaColumns,{'reason'}];
lines={strjoin(header,',')};
for k=1:numel(results)
    r=results(k);
    values={csv_text(r.scene_id),csv_text(r.arm),csv_text(r.status),csv_metric(r,'wall_seconds')};
    for c=1:numel(columns)
        name=columns{c}; idx=0;
        if contains(name,'axis_x_'),idx=1;elseif contains(name,'axis_y_'),idx=2;elseif contains(name,'axis_z_'),idx=3;end
        field=name;
        if idx>0
            field=extractBefore(name,'_axis_');
            if startsWith(name,'q_axis_'),field='q_axis_rmse_m';
            elseif startsWith(name,'q_early_axis_'),field='q_early_axis_rmse_m';
            else,field='q_late_axis_rmse_m';end
        end
        values{end+1}=csv_metric(r.score,field,idx); %#ok<AGROW>
    end
    for c=1:numel(deltaColumns)
        name=deltaColumns{c}; field=extractAfter(name,'delta_'); idx=0;
        if contains(name,'axis_x_'),idx=1;elseif contains(name,'axis_y_'),idx=2;elseif contains(name,'axis_z_'),idx=3;end
        if idx>0
            if startsWith(name,'delta_q_early_axis_'),field='q_early_axis_rmse_m';
            elseif startsWith(name,'delta_q_late_axis_'),field='q_late_axis_rmse_m';
            else,field='q_axis_rmse_m';end
        end
        values{end+1}=csv_metric(r.delta_score,field,idx); %#ok<AGROW>
    end
    values{end+1}=csv_text(r.reason);
    lines{end+1}=strjoin(values,','); %#ok<AGROW>
end
write_text_new(path,[strjoin(lines,newline) newline]);
end

function delta=score_delta(baseline,candidate)
delta=struct(); names=fieldnames(baseline);
for k=1:numel(names)
    name=names{k}; a=baseline.(name); b=candidate.(name);
    if isnumeric(a)&&isnumeric(b),delta.(name)=double(b)-double(a);end
end
delta.definition='candidate_minus_baseline';
end

function value=csv_metric(record,name,index)
value='';
if ~isstruct(record)||~isfield(record,name),return;end
number=record.(name);
if isempty(number),return;end
if index>0
    if numel(number)<index,return;end
    number=number(index);
elseif ~isscalar(number)
    value=csv_text(strjoin(arrayfun(@(x)sprintf('%.17g',double(x)),number(:).','UniformOutput',false),';'));
    return
end
value=sprintf('%.17g',double(number));
end

function value=csv_text(value)
value=char(string(value));
if contains(value,'"'),value=strrep(value,'"','""');end
if contains(value,',')||contains(value,'"')||contains(value,newline)
    value=['"' value '"'];
end
end

function write_screen12_report(path,summary)
lines={sprintf('# MORPH_DEV2_SCREEN12: %s',summary.status), ...
    sprintf('Runner calls: %d / 24; confirmed runs: %d; transitions: %d; unknown invocations: %d.', ...
        summary.runner_invocation_count,summary.confirmed_plant_runs, ...
        summary.confirmed_transitions,summary.unknown_plant_invocations), ...
    'Performance changes are descriptive and do not gate the next preregistered scene.'};
for i=1:12
    baseline=summary.results(2*i-1); candidate=summary.results(2*i);
    if ~isempty(fieldnames(candidate.delta_score))
        d=candidate.delta_score; s0=baseline.score; s1=candidate.score;
        lines{end+1}=sprintf(['%s: Q %.17g -> %.17g (d %.17g), early d %.17g, late d %.17g m; ' ...
            'SO3 %.17g -> %.17g (d %.17g), early d %.17g, late d %.17g rad; candidate %s.'], ...
            candidate.scene_id,s0.q_rmse_m,s1.q_rmse_m,d.q_rmse_m, ...
            d.q_early_rmse_m,d.q_late_rmse_m,s0.so3_rmse_rad,s1.so3_rmse_rad, ...
            d.so3_rmse_rad,d.so3_early_rmse_rad,d.so3_late_rmse_rad,candidate.status); %#ok<AGROW>
    else
        lines{end+1}=sprintf('%s: pair incomplete; baseline %s, candidate %s.', ...
            candidate.scene_id,baseline.status,candidate.status); %#ok<AGROW>
    end
end
if ~isempty(summary.failure_reason)
    lines{end+1}=['Failure: ' strrep(summary.failure_reason,newline,' ')]; %#ok<AGROW>
end
write_text_new(path,[strjoin(lines,newline) newline]);
end
