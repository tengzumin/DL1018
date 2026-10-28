function run_dev3_paired(releasePath,releaseSha,attemptDir)
% One released DEV3 attempt: three scenes, baseline then candidate, no retry.
entry=fileparts(mfilename('fullpath'));
root=fileparts(entry);
releasePath=char(releasePath); releaseSha=lower(char(releaseSha)); attemptDir=char(attemptDir);
assert(strcmp(sha256_file(releasePath),releaseSha),'DEV3:ReleaseSHA','Release SHA differs.');
release=jsondecode(fileread(releasePath));
assert(strcmp(release.schema,'PAIRED_DEV3_ROOT_RELEASE_V1')&&logical(release.approved)&& ...
    strcmp(release.scope,'SIX_FRESH_DEV3_PAIRED_RUNS')&& ...
    double(release.max_runner_calls)==6&&double(release.max_new_bytes)==1024^3&& ...
    double(release.minimum_free_bytes)==30*1024^3, ...
    'DEV3:Release','Root release is absent or does not approve exactly this scope.');
lockPath=char(release.source_lock_path);
assert(strcmp(sha256_file(lockPath),lower(char(release.source_lock_sha256))), ...
    'DEV3:SourceLockSHA','Final source-lock SHA differs.');
lock=jsondecode(fileread(lockPath));
assert(strcmp(lock.schema,'SOURCE_LOCK_PAIRED_RUNNER_V1_CANDIDATE')&& ...
    strcmp(lock.status,'NOT_FROZEN')&&~logical(lock.executed)&& ...
    ~logical(lock.closed_loop_runs_authorized)&& ...
    strcmp(lock.preflight_candidate_sha256,release.candidate_input_lock_sha256)&& ...
    strcmp(sha256_file(lock.preflight_candidate_path),lock.preflight_candidate_sha256)&& ...
    strcmp(sha256_file(lock.taskbook.path),lock.taskbook.sha256)&& ...
    strcmp(sha256_file(lock.wrapper.path),lock.wrapper.sha256)&& ...
    strcmp(sha256_file(lock.launcher.path),lock.launcher.sha256)&& ...
    strcmpi(lock.wrapper.path,fullfile(entry,'run_dev3_paired.m')), ...
    'DEV3:Lock','Final entry/input identities differ.');
assert(isfolder(attemptDir)&&strcmp(string(release.attempt_id),string(file_name(attemptDir)))&& ...
    ~isfile(fullfile(attemptDir,'batch_status.json'))&& ...
    ~isfile(fullfile(attemptDir,'runner_invocation.json')), ...
    'DEV3:Attempt','Attempt already has terminal/runner marker.');
candidate=jsondecode(fileread(lock.preflight_candidate_path));
assert(strcmp(candidate.schema,'SOURCE_LOCK_PAIRED_RUNNER_V1_CANDIDATE')&& ...
    strcmp(candidate.status,'NOT_FROZEN')&&~logical(candidate.executed)&& ...
    candidate.result.scenes(1).seed==2026121803&& ...
    candidate.result.scenes(2).seed==2026122847&& ...
    candidate.result.scenes(3).seed==2026123971, ...
    'DEV3:Candidate','Preflight candidate differs.');
verify_files(lock);
assert(strcmp(version('-release'),'2025b'),'DEV3:MATLABRelease','Expected R2025b.');
restoredefaultpath;
addpath(fullfile(root,'matlab','runtime'));
activate_paired_runner();
modelPath=find_input(lock,'model_mat');
snapshotPath=find_input(lock,'c5_snapshot_mat');
modelPack=load(modelPath,'model');
snapshot=load(snapshotPath,'cfg','opts','W0','modelIdentity');
assert(isequal(fieldnames(modelPack),{'model'})&&numel(fieldnames(snapshot))==4&& ...
    all(isfield(snapshot,{'cfg','opts','W0','modelIdentity'})), ...
    'DEV3:MATVariables','Only the two allowlisted MAT variable sets may be read.');
model=modelPack.model;
cfg=bind_paired_fixed_j0(snapshot.cfg);
assert(strcmp(char(snapshot.cfg.controller_morphology_mode),'fixed')&& ...
    double(cfg.plant.dt)==.001&&isequaln(rmfield(cfg,'attitude_replacement'),snapshot.cfg)&& ...
    strcmp(char(model.model_id),'DSSM14')&&strcmp(char(model.architecture),'DSSM')&& ...
    double(model.seed)==2026102001&&double(model.selected_step)==60000&& ...
    double(model.input_dim)==14&&double(model.window)==32&& ...
    isequal(size(model.output_W),[33,3])&&isequal(double(model.output_W),double(snapshot.W0)), ...
    'DEV3:ModelCfg','C5 snapshot cfg or DSSM14 model differs.');
identity=candidate.result;
assert(strcmp(paired_sha256_double(double(model.output_W)),identity.W0_sha256)&& ...
    strcmp(hash_normalizer_arrays(model),identity.normalizer_arrays_sha256)&& ...
    strcmp(snapshot.modelIdentity.W0_sha256,identity.W0_sha256)&& ...
    strcmp(snapshot.modelIdentity.normalizer_arrays_sha256,identity.normalizer_arrays_sha256), ...
    'DEV3:ModelIdentity','W0/normalizer identity differs.');
[cfgSha,~]=json_sha256(cfg);
assert(strcmp(cfgSha,identity.cfg_sha256)&& ...
    strcmp(cfg.attitude_replacement.J0_controller_fixed_sha256,identity.J0_controller_fixed_sha256), ...
    'DEV3:CfgJ0','C5 cfg or controller J0 differs.');
fixedPlant=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));
fixedController=controller_parameters(cfg,fixedPlant,'fixed');
assert(isequal(double(fixedController.inertia),double(cfg.attitude_replacement.J0_controller_fixed_kgm2)), ...
    'DEV3:J0','Fixed controller inertia differs.');
[baseline,candidateOpts]=make_paired_c5_options(cfg,model);
c5opts=rmfield(baseline,{'paired_arm','paired_position_method_id','rbf_attitude_initial_weight'});
assert(isequaln(c5opts,snapshot.opts)&& ...
    strcmp(json_sha256(c5opts),identity.c5_options_sha256)&& ...
    strcmp(json_sha256(baseline),identity.baseline_options_sha256)&& ...
    strcmp(json_sha256(candidateOpts),identity.candidate_options_sha256), ...
    'DEV3:Options','C5 or paired effective options differ.');
flags={'rbf_attitude_enabled','rbf_attitude_output_enabled','rbf_attitude_update_enabled'};
commonBase=rmfield(baseline,[flags,{'paired_arm'}]);
commonCandidate=rmfield(candidateOpts,[flags,{'paired_arm'}]);
assert(isequaln(commonBase,commonCandidate)&& ...
    strcmp(json_sha256(commonBase),identity.common_options_sha256)&& ...
    strcmp(paired_sha256_double(zeros(size(cfg.rbf.position.centers,2),3)),identity.rbf_position_initial_weight_sha256)&& ...
    strcmp(paired_sha256_double(double(baseline.rbf_attitude_initial_weight)),identity.rbf_attitude_initial_weight_sha256), ...
    'DEV3:CommonOptions','Common options or zero RBF initial weights differ.');
ids={'DL1018_DEV_T1_C00_W03','DL1018_DEV_T2_C02_W15','DL1018_DEV_T3_C10_W11'};
seeds=[2026121803,2026122847,2026123971];
arms={'baseline','candidate'};
results=repmat(struct('scene_id','','arm','','status','NOT_RUN','reason','', ...
    'q_rmse_m',NaN,'so3_rmse_rad',NaN,'run_dir',''),1,6);
for i=1:3
    for a=1:2, j=2*(i-1)+a; results(j).scene_id=ids{i}; results(j).arm=arms{a}; end
end
runnerCalls=0; pairPass=false(1,3); improved=false;
batchStart=utc_now();
try
    assert(isequal(string(ids),string({identity.scenes.scene_id}))&& ...
        isequal(double([identity.scenes.seed]),seeds), ...
        'DEV3:SceneIdentity','Fixed scene IDs/seeds differ from preflight.');
    for i=1:3
        out=make_paired_dev_scene(ids{i},cfg);
        assert(istable(out.spec)&&height(out.spec)==1,'DEV3:Spec','Expected one spec row.');
        spec=table2struct(out.spec); scene=out.scene; metadata=out.metadata;
        sceneHashes=struct('spec_sha256',json_sha256(spec), ...
            'scene_sha256',json_sha256(scene),'metadata_sha256',json_sha256(metadata));
        frozen=identity.scenes(i);
        assert(strcmp(char(string(spec.scene_id)),ids{i})&&double(spec.seed)==seeds(i)&& ...
            strcmp(sceneHashes.spec_sha256,frozen.spec_sha256)&& ...
            strcmp(sceneHashes.scene_sha256,frozen.scene_sha256)&& ...
            strcmp(sceneHashes.metadata_sha256,frozen.metadata_sha256)&& ...
            isequal(size(scene.time),[20001,1])&&isequal(scene.time,(0:.001:20).'), ...
            'DEV3:SceneSHA','Regenerated DEV scene differs from preflight.');
        scores=cell(1,2); armDirs=cell(1,2);
        for a=1:2
            j=2*(i-1)+a;
            assert(runnerCalls<6,'DEV3:Budget','Six-call budget exhausted.');
            assert(get_free_bytes()>=double(release.minimum_free_bytes), ...
                'DEV3:Disk','C drive free space below 30 GiB.');
            newBytes=tree_bytes(attemptDir);
            assert(newBytes<double(release.max_new_bytes),'DEV3:Budget','New outputs reached 1 GiB.');
            if runnerCalls>=2
                firstPairBytes=first_pair_bytes(attemptDir);
                assert(newBytes+(6-runnerCalls)*ceil(firstPairBytes/2)<=double(release.max_new_bytes), ...
                    'DEV3:BudgetForecast','First-pair bytes predict budget exhaustion.');
            end
            verify_files(lock);
            assert(strcmp(json_sha256(scene),sceneHashes.scene_sha256)&& ...
                strcmp(json_sha256(cfg),cfgSha),'DEV3:Immutable','Scene/cfg changed before runner.');
            if a==1,opts=baseline;else,opts=candidateOpts;end
            effectiveSha=json_sha256(opts);
            if a==1,expectedOpts=identity.baseline_options_sha256;
            else,expectedOpts=identity.candidate_options_sha256;end
            assert(strcmp(effectiveSha,expectedOpts),'DEV3:Options','Effective options changed.');
            armDir=fullfile(attemptDir,sprintf('%02d_%s_%s',i,ids{i},arms{a}));
            assert(~isfolder(armDir),'DEV3:NoOverwrite','Arm directory exists.');
            mkdir(armDir); armDirs{a}=armDir;
            baseRecord=struct('release_sha256',releaseSha, ...
                'source_lock_sha256',lower(char(release.source_lock_sha256)), ...
                'candidate_input_lock_sha256',lock.preflight_candidate_sha256, ...
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
            wall=tic;
            try
                rng(seeds(i),'twister');
                log=run_paired_observer_closed_loop(scene,'B2-RBF-Full-SPLIT',cfg,opts);
                wallSeconds=toc(wall);
                rawPath=fullfile(armDir,'run_raw.mat');
                assert(java.io.File(rawPath).createNewFile(),'DEV3:NoOverwrite','Raw path exists.');
                save(rawPath,'log','-v7.3');
                rawSha=sha256_file(rawPath);
                [score,gate]=score_log(log,scene,a==2);
                assert(strcmp(json_sha256(scene),sceneHashes.scene_sha256)&& ...
                    strcmp(json_sha256(cfg),cfgSha)&&strcmp(json_sha256(opts),effectiveSha), ...
                    'DEV3:Immutable','Runner mutated scene/cfg/options.');
                verify_files(lock);
                scores{a}=score;
                assert(gate.passed,'DEV3:Gate','Engineering/safety gate failed.');
                if a==2
                    assert(score.motor_saturation_count==0&&score.generalized_clip_count==0&& ...
                        score.tilt_limited_count<=scores{1}.tilt_limited_count&& ...
                        score.q_rmse_m<=scores{1}.q_rmse_m+1e-12&& ...
                        score.so3_rmse_rad<=scores{1}.so3_rmse_rad+1e-12, ...
                        'DEV3:PairGate','Candidate exceeded baseline safety/metric tolerance.');
                end
                audit=baseRecord; audit.time_size=size(scene.time);
                audit.scene_sha256_after=sceneHashes.scene_sha256;
                audit.same_scene_for_both_arms=true;
                write_json_new(fullfile(armDir,'scene_audit.json'),audit);
                status=baseRecord; status.status='COMPLETED';
                status.ended_utc=utc_now(); status.last_transition=double(log.last_transition);
                status.runner_status=char(log.status); status.safety_stop_reason=char(log.safety_stop_reason);
                status.wall_seconds=wallSeconds; status.raw_path=rawPath;
                status.raw_sha256=rawSha; status.raw_bytes=dir(rawPath).bytes;
                status.score=score; status.gate=gate;
                write_json_new(fullfile(armDir,'run_status.json'),status);
                results(j).status='COMPLETED'; results(j).q_rmse_m=score.q_rmse_m;
                results(j).so3_rmse_rad=score.so3_rmse_rad; results(j).run_dir=armDir;
                clear log
                if a==2
                    improved=improved||score.q_rmse_m<scores{1}.q_rmse_m-1e-12|| ...
                        score.so3_rmse_rad<scores{1}.so3_rmse_rad-1e-12;
                    pairPass(i)=true;
                    pairAudit=struct('scene_id',ids{i},'baseline',scores{1},'candidate',score, ...
                        'same_scene_sha256',sceneHashes.scene_sha256,'passed',true);
                    write_json_new(fullfile(attemptDir,sprintf('pair_%02d_audit.json',i)),pairAudit);
                end
            catch armError
                if ~isfile(fullfile(armDir,'run_status.json'))
                    status=baseRecord; status.status='FAILED'; status.ended_utc=utc_now();
                    status.reason=getReport(armError,'extended','hyperlinks','off');
                    status.last_transition='unknown_if_no_returned_log';
                    if exist('log','var')&&isstruct(log)&&isfield(log,'last_transition')
                        status.last_transition=double(log.last_transition);
                    end
                    status.wall_seconds=toc(wall);
                    if isfile(fullfile(armDir,'run_raw.mat'))
                        status.raw_path=fullfile(armDir,'run_raw.mat');
                        status.raw_sha256=sha256_file(status.raw_path);
                    end
                    write_json_new(fullfile(armDir,'run_status.json'),status);
                end
                results(j).status='FAILED'; results(j).reason=armError.message;
                results(j).run_dir=armDir;
                rethrow(armError);
            end
        end
    end
    assert(all(pairPass)&&improved,'DEV3:Screen','Three pairs passed but no strict improvement >1e-12.');
    batchStatus='DEV3_SCREEN_PASS'; failureReason='';
catch batchError
    batchStatus='STOPPED_ON_FAILURE';
    failureReason=getReport(batchError,'extended','hyperlinks','off');
end
summary=struct('schema','PAIRED_DEV3_BATCH_STATUS_V1','status',batchStatus, ...
    'started_utc',batchStart,'ended_utc',utc_now(), ...
    'release_sha256',releaseSha,'source_lock_sha256',char(release.source_lock_sha256), ...
    'candidate_input_lock_sha256',lock.preflight_candidate_sha256, ...
    'runner_invocation_count',runnerCalls,'plant_run_count',runnerCalls, ...
    'training_run_count',0,'new_bytes',tree_bytes(attemptDir), ...
    'pair_pass',pairPass,'strict_improvement',improved,'results',results, ...
    'failure_reason',failureReason);
write_json_new(fullfile(attemptDir,'batch_status.json'),summary);
write_results_csv(fullfile(attemptDir,'results.csv'),results);
write_text_new(fullfile(attemptDir,'report.md'),sprintf( ...
    '# DEV3 attempt\n\nStatus: %s\nRunner invocations: %d / 6\nFailure: %s\n', ...
    batchStatus,runnerCalls,failureReason));
fprintf('PAIRED_DEV3_BATCH_JSON:%s\n',jsonencode(summary));
assert(strcmp(batchStatus,'DEV3_SCREEN_PASS'),'DEV3:BatchFailed','DEV3 stopped; see batch_status.json.');
end

function verify_files(lock)
for item=reshape(lock.sources,1,[])
    assert(strcmp(sha256_file(item.path),item.sha256),'DEV3:SourceSHA','Source changed: %s.',item.path);
end
for item=reshape(lock.inputs,1,[])
    assert(strcmp(sha256_file(item.path),item.sha256),'DEV3:InputSHA','Input changed: %s.',item.path);
end
for item={lock.wrapper,lock.launcher,lock.checker,lock.audit,lock.taskbook}
    record=item{1};
    assert(strcmp(sha256_file(record.path),record.sha256),'DEV3:EntrySHA','Entry changed: %s.',record.path);
end
end

function path=find_input(lock,name)
items=lock.inputs(strcmp({lock.inputs.role},name));
assert(numel(items)==1,'DEV3:Input','Missing unique input role %s.',name);
path=char(items.path);
end

function hash=source_sha(lock,relative)
items=lock.sources(strcmp({lock.sources.relative_path},relative));
assert(numel(items)==1,'DEV3:Source','Missing source %s.',relative);
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
    'DEV3:FullRun','Full 20,001-state/20,000-transition stable run required.');
for name={'state','motor_command','requested_generalized','controller_clipped_generalized', ...
        'allocated_generalized','realized_generalized','filtered_attitude_reference'}
    value=log.(name{1});
    assert(isnumeric(value)&&all(isfinite(value(:))),'DEV3:Finite','Enabled log field nonfinite: %s.',name{1});
end
for name={'position','velocity','acceleration','yaw','yaw_rate','yaw_acceleration'}
    value=log.reference.(name{1});
    assert(isnumeric(value)&&all(isfinite(value(:))),'DEV3:Reference','Reference nonfinite: %s.',name{1});
end
e=double(log.state(:,1:3))-double(log.reference.position);
axisRmse=sqrt(mean(e.^2,1)); q=sqrt(mean(sum(e.^2,2)));
peak=max(sqrt(sum(e.^2,2)));
theta=zeros(n,1);
for k=1:n
    actual=rotation_zyx(double(log.state(k,7:9).'));
    desired=rotation_zyx(double(log.filtered_attitude_reference(k,:).'));
    x=(trace(desired.'*actual)-1)/2;
    theta(k)=acos(max(min(x,1),-1));
end
so3=sqrt(mean(theta.^2)); so3Peak=max(theta);
assert(all(isfinite([axisRmse,q,peak,so3,so3Peak]))&& ...
    isequal(size(log.motor_saturated,1),n)&& ...
    isequal(size(log.generalized_clipped,1),n)&&numel(log.tilt_limited)==n, ...
    'DEV3:Score','Scoring shape or finite contract differs.');
motorCount=nnz(any(log.motor_saturated,2));
clipCount=nnz(any(log.generalized_clipped,2));
tiltCount=nnz(log.tilt_limited);
score=struct('q_rmse_m',q,'q_axis_rmse_m',axisRmse,'q_peak_m',peak, ...
    'so3_rmse_rad',so3,'so3_peak_rad',so3Peak, ...
    'motor_saturation_count',motorCount,'generalized_clip_count',clipCount, ...
    'tilt_limited_count',tiltCount,'state_points',n+1,'transitions',n, ...
    'controller_call_time_s_mean',mean(double(log.controller_call_time_s)), ...
    'controller_call_time_excludes_candidate_post_allocator_commit',true);
if isCandidate
    assert(iscell(log.phys_attitude_trace)&&numel(log.phys_attitude_trace)==n&& ...
        all(~logical(log.attitude_fusion_rbf_output_enabled))&& ...
        all(~logical(log.attitude_fusion_rbf_update_enabled))&& ...
        all(log.rbf_output_held(:)==0)&&all(log.rbf_weight_norm(:)==0)&& ...
        all(log.rbf_weight_max(:)==0)&&all(log.rbf_weight_derivative_norm(:)==0)&& ...
        all(log.attitude_rbf_estimate_acceleration_rads2(:)==0)&& ...
        all(log.attitude_rbf_compensation_torque_Nm(:)==0), ...
        'DEV3:CandidateRBF','Candidate attitude RBF was active.');
    for k=1:n
        tr=log.phys_attitude_trace{k};
        assert(isstruct(tr)&&finite_struct(tr)&&tr.sample_index==k&& ...
            tr.prepare.time_s==log.transition_time(k)&& ...
            tr.commit.time_s==log.transition_time(k)&& ...
            isequal(double(tr.morph_command(:)),double(scene.arms.command(k,:).'))&& ...
            isequal(double(tr.omega_body(:)),double(log.state(k,10:12).'))&& ...
            isequal(double(tr.commit.tau_cmd_clipped_Nm(:)), ...
                double(log.controller_clipped_generalized(k,2:4).'))&& ...
            isequal(double(tr.prepare.estimateTorque_Nm(:)),-double(tr.prepare.tau_comp_Nm(:)))&& ...
            logical(tr.is_attitude_event)==logical(log.attitude_event_flag(k))&& ...
            ~logical(tr.rbf_output_enabled)&&~logical(tr.rbf_update_enabled), ...
            'DEV3:Trace','Candidate helper time/command/omega/RBF lineage differs at %d.',k);
        if tr.prepare.observer.updated
            assert(tr.is_attitude_event&&tr.prepare.observer.delta_s>0&& ...
                abs(tr.prepare.observer.delta_s-tr.event_delta_s)<1e-10, ...
                'DEV3:Event','Candidate event timing differs at %d.',k);
        end
    end
end
gate=struct('passed',true,'status','STABLE','safety_stop_reason','', ...
    'candidate_trace_checked',isCandidate);
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
assert(numel(dirs)==2,'DEV3:BudgetForecast','Expected completed first pair.');
bytes=0;
for k=1:2,bytes=bytes+tree_bytes(fullfile(attemptDir,dirs(k).name));end
end

function name=file_name(path)
[~,name]=fileparts(path);
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
fid=fopen(path,'r');assert(fid>=0,'DEV3:Read','Cannot read %s.',path);
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
    assert(numel(a)==14&&all(isfinite(a)),'DEV3:Normalizer','Invalid normalizer.');
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
assert(file.createNewFile(),'DEV3:NoOverwrite','File already exists: %s.',path);
fid=fopen(path,'w');assert(fid>=0,'DEV3:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,unicode2native(value,'UTF-8'),'uint8');
end

function write_results_csv(path,results)
lines={'scene_id,arm,status,q_rmse_m,so3_rmse_rad,reason'};
for k=1:numel(results)
    r=results(k);
    reason=strrep(char(r.reason),'"','""');
    lines{end+1}=sprintf('%s,%s,%s,%.17g,%.17g,"%s"', ...
        r.scene_id,r.arm,r.status,r.q_rmse_m,r.so3_rmse_rad,reason); %#ok<AGROW>
end
write_text_new(path,[strjoin(lines,newline) newline]);
end
