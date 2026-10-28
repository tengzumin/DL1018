function result = score_gate_pilot_batch(releasePath,receiptPath,candidateAttemptsRoot,bAttemptsRoot,outputDirectory)
%SCORE_GATE_PILOT_BATCH Score every pre-registered pilot slot without dropping failures.
% The scorer reads only the new isolated pilot attempts named by the root release.

    scorerPath=[mfilename('fullpath') '.m'];
    taskRoot=fileparts(char(java.io.File(char(releasePath)).getCanonicalPath()));
    releasePath=char(java.io.File(char(releasePath)).getCanonicalPath());
    receiptPath=char(java.io.File(char(receiptPath)).getCanonicalPath());
    candidateAttemptsRoot=char(java.io.File(char(candidateAttemptsRoot)).getCanonicalPath());
    bAttemptsRoot=char(java.io.File(char(bAttemptsRoot)).getCanonicalPath());
    outputDirectory=char(java.io.File(char(outputDirectory)).getCanonicalPath());
    require_under(taskRoot,releasePath,'release');
    require_under(taskRoot,receiptPath,'receipt');
    require_under(taskRoot,candidateAttemptsRoot,'candidate attempts');
    require_under(taskRoot,bAttemptsRoot,'B attempts');
    require_under(taskRoot,outputDirectory,'score output');
    assert(~isfolder(outputDirectory)&&~isfile(outputDirectory), ...
        'GateScore:NoOverwrite','Score output directory already exists.');

    release=jsondecode(fileread(releasePath));
    require_under(taskRoot,scorerPath,'scorer');
    receipt=jsondecode(fileread(receiptPath));
    assert(strcmp(char(release.schema),'DL1018_GATE_PILOT_RELEASE_V1')&& ...
        strcmp(char(release.status),'RELEASED')&&double(release.plant_calls_authorized)==54, ...
        'GateScore:Release','Expected the released 54-call pilot manifest.');
    frozenTaskbook=fullfile(taskRoot,'GATE_INSPECTION_HOLDOUT_TASKBOOK_v1_FROZEN_ZH.md');
    assert(isfile(frozenTaskbook)&&strcmpi(sha256_file(frozenTaskbook),char(release.taskbook_sha256))&& ...
        strcmpi(char(receipt.taskbook_sha256),char(release.taskbook_sha256)), ...
        'GateScore:TaskbookSHA','Frozen taskbook, receipt and release identities differ.');
    assert(isfield(release,'pilot_receipt_sha256')&& ...
        strcmpi(sha256_file(receiptPath),char(release.pilot_receipt_sha256)), ...
        'GateScore:ReceiptSHA','Pilot receipt differs from release.');
    assert(isfield(release,'scorer_sha256')&& ...
        strcmpi(sha256_file(scorerPath),char(release.scorer_sha256)), ...
        'GateScore:ScorerSHA','Scorer differs from the frozen release.');

    candidateLockPath=fullfile(taskRoot,'CANDIDATE_SOURCE_LOCK_PILOT_v1.json');
    bLockPath=fullfile(taskRoot,'B_RUNNER_SOURCE_LOCK_PILOT_v1.json');
    assert(strcmpi(sha256_file(candidateLockPath),char(release.candidate_source_lock_sha256))&& ...
        strcmpi(sha256_file(bLockPath),char(release.b_source_lock_sha256)), ...
        'GateScore:SourceLockSHA','Candidate or B source lock differs from release.');
    verify_candidate_lock(jsondecode(fileread(candidateLockPath)),fullfile(taskRoot,'candidate_runner_work'));
    verify_b_lock(jsondecode(fileread(bLockPath)),taskRoot);

    assert(numel(release.pilot_payloads)==18&&numel(release.b_payloads)==6, ...
        'GateScore:PayloadCount','Release must pin 18 candidate payloads and 6 B payloads.');
    arms=cellstr(string(release.candidate_arm_ids(:)));
    assert(isequal(sort(arms),sort({'C5_RBF';'C5_RBF_F';'C5_00';'C5_10';'C5_01';'C5_11'})), ...
        'GateScore:ArmList','Released candidate arm list differs from the registered pilot.');
    verify_release_payloads(release,receipt,taskRoot);
    expected=make_expected_slots(release,arms);
    assert(numel(expected)==54,'GateScore:ExpectedCount','Expected exactly 54 unique slots.');
    keys={expected.key};
    assert(numel(unique(keys))==54,'GateScore:ExpectedDuplicate','Expected run matrix has duplicate slots.');

    snapshotPath=char(receipt.input_records.c5_snapshot_mat.path);
    projectRoot=fileparts(fileparts(fileparts(taskRoot)));
    require_under(projectRoot,snapshotPath,'C5 snapshot');
    assert(strcmpi(sha256_file(snapshotPath),char(receipt.input_records.c5_snapshot_mat.sha256)), ...
        'GateScore:C5SnapshotSHA','Locked C5 cfg snapshot changed.');
    snapshot=load(snapshotPath,'cfg');
    assert(isfield(snapshot,'cfg')&&isstruct(snapshot.cfg)&&isfield(snapshot.cfg,'plant'), ...
        'GateScore:C5Snapshot','Locked C5 snapshot has no plant configuration.');
    cfg=snapshot.cfg;
    addpath(fullfile(taskRoot,'scene_builder_work'));

    [attempts,invalidAttempts]=collect_attempts(candidateAttemptsRoot,'CANDIDATE');
    [bAttempts,invalidB]=collect_attempts(bAttemptsRoot,'B');
    attempts=[attempts(:);bAttempts(:)];
    invalidAttempts=[invalidAttempts(:);invalidB(:)];

    rows=repmat(empty_row(expected(1)),numel(expected),1);
    for i=1:numel(expected)
        e=expected(i); hit=find(strcmp({attempts.key},e.key));
        rows(i)=empty_row(e);
        rows(i).attempt_count=numel(hit);
        if isempty(hit)
            rows(i).score_state='MISSING_ATTEMPT';
        elseif numel(hit)>1
            rows(i).score_state='DUPLICATE_ATTEMPTS';
            rows(i).attempt_dir=strjoin({attempts(hit).attempt_dir},' | ');
            rows(i).failure_reason='More than one attempt matched this frozen slot; none was selected.';
        else
            try
                rows(i)=score_one(e,attempts(hit),release,cfg);
            catch ME
                rows(i).run_state='SCORER_ERROR';rows(i).score_state='SCORER_ERROR';
                rows(i).attempt_dir=attempts(hit).attempt_dir;rows(i).failure_reason=char(ME.message);
            end
        end
    end
    matchedKeys={expected.key};
    unmatched=attempts(~ismember({attempts.key},matchedKeys));
    groupSummary=summarize_groups(rows,arms);
    selectedComparator=select_fixed_comparator(rows);

    result=struct('schema','DL1018_GATE_PILOT_SCORE_V1', ...
        'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
        'taskbook_sha256',char(release.taskbook_sha256), ...
        'release_sha256',sha256_file(releasePath), ...
        'receipt_sha256',sha256_file(receiptPath), ...
        'scorer_sha256',sha256_file(scorerPath), ...
        'expected_slot_count',numel(expected),'attempt_count',numel(attempts), ...
        'missing_slot_count',sum(strcmp({rows.score_state},'MISSING_ATTEMPT')), ...
        'duplicate_slot_count',sum(strcmp({rows.score_state},'DUPLICATE_ATTEMPTS')), ...
        'failed_run_count',sum(strcmp({rows.run_state},'FAILED')), ...
        'incomplete_run_count',sum(~[rows.complete_transitions]), ...
        'application_feasible_count',sum([rows.application_feasible]), ...
        'selected_fixed_comparator',selectedComparator, ...
        'selection_rule','six of six completed stable finite runs without safety stop and with bidirectional passage clearance >=15 mm; among eligible choose lower mean Q8-12, tie within 1e-9 m chooses larger arm length', ...
        'rows',rows,'group_summary',groupSummary, ...
        'unmatched_attempts',unmatched,'invalid_attempt_records',{invalidAttempts}, ...
        'time_samples_are_independent',false,'test_data_read',false);

    mkdir(outputDirectory);
    jsonPath=fullfile(outputDirectory,'pilot_score.json');
    csvPath=fullfile(outputDirectory,'pilot_score.csv');
    result.score_json_path=jsonPath;
    result.score_csv_path=csvPath;
    fid=fopen(jsonPath,'w','n','UTF-8');
    assert(fid>=0,'GateScore:Output','Cannot create score JSON.');
    c=onCleanup(@()fclose(fid));
    fwrite(fid,unicode2native(jsonencode(result,'PrettyPrint',true),'UTF-8'),'uint8');
    clear c;
    writetable(struct2table(rows),csvPath);
    result.score_json_path=jsonPath;
    result.score_csv_path=csvPath;
end

function expected=make_expected_slots(release,arms)
    template=struct('runner','','scene_id','','attitude_arm','','geometry_arm','', ...
        'payload_path','','payload_sha256','','key','');
    expected=repmat(template,0,1);
    for i=1:numel(release.pilot_payloads)
        p=release.pilot_payloads(i); geom=upper(char(p.geometry_arm));
        if strcmp(geom,'ACTIVE'), thisArms=arms; else, thisArms={'C5_11'}; end
        for j=1:numel(thisArms)
            e=template;e.runner='CANDIDATE';e.scene_id=char(p.scene_id);
            e.attitude_arm=thisArms{j};e.geometry_arm=geom;
            e.payload_path=char(p.payload_path);e.payload_sha256=lower(char(p.payload_sha256));
            e.key=slot_key(e.runner,e.scene_id,e.attitude_arm,e.geometry_arm);
            expected(end+1,1)=e; %#ok<AGROW>
        end
    end
    for i=1:numel(release.b_payloads)
        p=release.b_payloads(i);e=template;e.runner='B';e.scene_id=char(p.scene_id);
        e.attitude_arm='B';e.geometry_arm='ACTIVE';
        e.payload_path=char(p.payload_path);e.payload_sha256=lower(char(p.payload_sha256));
        e.key=slot_key(e.runner,e.scene_id,e.attitude_arm,e.geometry_arm);
        expected(end+1,1)=e; %#ok<AGROW>
    end
end

function verify_release_payloads(release,receipt,taskRoot)
    scenes=receipt.scenes;
    assert(numel(scenes)==18,'GateScore:ReceiptCount','Receipt must pin 18 scene payloads.');
    for i=1:numel(release.pilot_payloads)
        p=release.pilot_payloads(i); require_under(taskRoot,char(p.payload_path),'candidate payload');
        j=find(strcmpi({scenes.payload_sha256},char(p.payload_sha256)));
        assert(isscalar(j)&&strcmp(char(scenes(j).scene_id),char(p.scene_id))&& ...
            strcmpi(char(scenes(j).geometry_arm),char(p.geometry_arm))&& ...
            strcmpi(sha256_file(char(p.payload_path)),char(p.payload_sha256)), ...
            'GateScore:CandidatePayload','Candidate payload does not match receipt/release: %s',char(p.scene_id));
    end
    for i=1:numel(release.b_payloads)
        p=release.b_payloads(i); require_under(taskRoot,char(p.payload_path),'B payload');
        j=find(strcmpi({scenes.payload_sha256},char(p.payload_sha256)));
        assert(isscalar(j)&&strcmp(char(scenes(j).scene_id),char(p.scene_id))&& ...
            strcmpi(char(scenes(j).geometry_arm),'ACTIVE')&& ...
            strcmpi(sha256_file(char(p.payload_path)),char(p.payload_sha256)), ...
            'GateScore:PayloadB','B payload does not match receipt/release: %s',char(p.scene_id));
    end
end

function [records,invalid]=collect_attempts(root,runner)
    records=struct('runner',{},'scene_id',{},'attitude_arm',{},'geometry_arm',{}, ...
        'payload_sha256',{},'source_lock_sha256',{},'taskbook_sha256',{},'attempt_dir',{},'key',{},'start',{});
    invalid=struct('attempt_dir',{},'reason',{});
    if ~isfolder(root),return;end
    starts=dir(fullfile(root,'**','run_start.json'));
    for i=1:numel(starts)
        attemptDir=starts(i).folder;startPath=fullfile(attemptDir,starts(i).name);
        try
            st=jsondecode(fileread(startPath));
            sceneId=char(st.scene_id);payloadSha=lower(char(st.scene_payload_sha256));
            if strcmp(runner,'B')
                arm='B';geom='ACTIVE';lockSha=char(st.b_wrapper_source_lock_sha256);
            else
                arm=upper(char(st.attitude_arm));geom=upper(char(st.geometry_arm));
                lockSha=char(st.candidate_source_lock_sha256);
            end
            taskSha=char(st.taskbook_sha256);
            rec=struct('runner',runner,'scene_id',sceneId,'attitude_arm',arm, ...
                'geometry_arm',geom,'payload_sha256',payloadSha, ...
                'source_lock_sha256',lockSha,'taskbook_sha256',taskSha, ...
                'attempt_dir',attemptDir,'key',slot_key(runner,sceneId,arm,geom),'start',st);
            records(end+1,1)=rec; %#ok<AGROW>
        catch ME
            invalid(end+1,1)=struct('attempt_dir',attemptDir,'reason',char(ME.message)); %#ok<AGROW>
        end
    end
end

function row=score_one(e,attempt,release,cfg)
    row=empty_row(e);row.attempt_count=1;row.attempt_dir=attempt.attempt_dir;
    row.run_state='STATUS_MISSING';
    start=attempt.start;
    row.payload_sha256=attempt.payload_sha256;
    if ~strcmpi(attempt.payload_sha256,e.payload_sha256)|| ...
        ~strcmpi(attempt.source_lock_sha256,expected_lock(e.runner,release))|| ...
        ~strcmpi(attempt.taskbook_sha256,char(release.taskbook_sha256))
        row.score_state='IDENTITY_MISMATCH';row.failure_reason='run_start payload, source-lock or taskbook SHA mismatch.';return
    end
    statusPath=fullfile(attempt.attempt_dir,'run_status.json');
    if ~isfile(statusPath),row.score_state='STATUS_MISSING';return;end
    try
        status=jsondecode(fileread(statusPath));
    catch ME
        row.score_state='STATUS_INVALID';row.failure_reason=char(ME.message);return
    end
    row.run_state=char(status.state);
    rawPath=fullfile(attempt.attempt_dir,'raw_run.mat');
    if isfield(status,'raw_output_path')&&~isempty(status.raw_output_path)
        candidateRaw=char(java.io.File(char(status.raw_output_path)).getCanonicalPath());
        require_under(attempt.attempt_dir,candidateRaw,'raw output');rawPath=candidateRaw;
    end
    if ~isfile(rawPath),row.score_state='RAW_MISSING';row.failure_reason='Attempt has no raw MAT.';return;end
    rawSha=sha256_file(rawPath);
    if isfield(status,'raw_output_sha256')&&~isempty(status.raw_output_sha256)&& ...
        ~strcmpi(rawSha,char(status.raw_output_sha256))
        row.score_state='RAW_SHA_MISMATCH';row.failure_reason='Raw MAT SHA differs from run status.';return
    end
    try
        raw=load(rawPath,'log','scene');
    catch ME
        row.score_state='RAW_INVALID';row.failure_reason=char(ME.message);return
    end
    if ~all(isfield(raw,{'log','scene'}))||~isstruct(raw.log)||~isstruct(raw.scene)
        row.score_state='RAW_SCHEMA_INVALID';return
    end
    log=raw.log;scene=raw.scene;
    if ~strcmp(char(scene.scene_id),e.scene_id)|| ...
        ~isfield(scene,'R_task')||~isfield(scene,'R_task_sha256')|| ...
        ~strcmpi(paired_sha256_double(double(scene.R_task)),char(scene.R_task_sha256))|| ...
        ~strcmpi(char(scene.R_task_sha256),char(start.r_task_sha256))
        row.score_state='RAW_IDENTITY_MISMATCH';row.failure_reason='Raw scene or canonical R_task identity mismatch.';return
    end
    row.r_task_sha256=char(scene.R_task_sha256);
    required={'time','transition_time','state','reference','arms','motor_saturated', ...
        'generalized_clipped','tilt_limited','last_transition','status','safety_stop_reason'};
    if ~all(isfield(log,required))||~isfield(log.reference,'position')||~isfield(log.arms,'rho_true')
        row.score_state='TRACE_SCHEMA_INVALID';row.failure_reason='Raw log lacks required scoring traces.';return
    end
    time=double(log.time(:));X=double(log.state);ref=double(log.reference.position);
    if size(X,1)~=numel(time)||size(X,2)~=12||size(ref,1)~=numel(time)||size(ref,2)~=3
        row.score_state='TRACE_SHAPE_INVALID';return
    end
    sceneTime=double(scene.time(:));dt=median(diff(sceneTime));
    if ~isfinite(dt)||dt<=0,row.score_state='TIMELINE_INVALID';return;end
    idx=round((time-sceneTime(1))/dt)+1;
    if any(idx<1|idx>numel(sceneTime))||any(abs(sceneTime(idx)-time)>1e-10)
        row.score_state='TIMELINE_INVALID';return
    end
    transitionTime=double(log.transition_time(:));
    complete=numel(time)==numel(sceneTime)&&numel(transitionTime)==numel(sceneTime)-1&& ...
        double(log.last_transition)==numel(sceneTime)-1&& ...
        max(abs(time-sceneTime))<=1e-10&& ...
        max(abs(transitionTime-sceneTime(1:end-1)))<=1e-10&& ...
        all(isfinite(X(:)))&&all(isfinite(ref(:)));
    if isfield(log,'complete_transitions'),complete=complete&&logical(log.complete_transitions);end
    if isfield(status,'complete_transitions'),complete=complete&&logical(status.complete_transitions);end
    row.complete_transitions=complete;
    row.actual_transition_count=double(log.last_transition);
    row.status_value=char(string(log.status));row.safety_stop_reason=char(string(log.safety_stop_reason));
    finiteTrace=all(isfinite(double(log.motor_saturated(:))))&& ...
        all(isfinite(double(log.generalized_clipped(:))))&&all(isfinite(double(log.tilt_limited(:))));
    row.trace_finite=finiteTrace;
    row.motor_saturation_any=any(logical(log.motor_saturated(:)));
    row.generalized_clip_any=any(logical(log.generalized_clipped(:)));
    row.tilt_limit_any=any(logical(log.tilt_limited(:)));
    if ~finiteTrace,row.failure_reason='Actuator or limit trace contains nonfinite values.';end

    if all(isfinite(X(:)))&&all(isfinite(ref(:)))
        posError=X(:,1:3)-ref;
        row.q0_20_m=sqrt(mean(sum(posError.^2,2)));
        row.rmse_x_m=sqrt(mean(posError(:,1).^2));row.rmse_y_m=sqrt(mean(posError(:,2).^2));
        row.rmse_z_m=sqrt(mean(posError(:,3).^2));
        q8=time>=8-1e-10&time<=12+1e-10;
        if sum(q8)==4001,row.q8_12_m=sqrt(mean(sum(posError(q8,:).^2,2)));end
        if abs(time(end)-20)<=1e-10,row.end_position_error_m=norm(posError(end,:));end
        rho=double(log.arms.rho_true);
        if isequal(size(rho),[numel(time) 4])&&numel(time)>=2&&all(isfinite(rho(:)))
            geom=check_gate_inspection_geometry(time,X,rho,cfg);
            row.geometry_checked=true;row.pass_bidirectional=logical(geom.pass_bidirectional);
            row.pass_15mm_proxy=logical(geom.pass_15mm_proxy);
            row.minimum_clearance_m=double(geom.minimum_clearance_m);
            if isfield(geom,'events')&&numel(geom.events)>=2
                row.forward_clearance_m=double(geom.events(1).minimum_clearance_m);
                row.reverse_clearance_m=double(geom.events(2).minimum_clearance_m);
            end
        end
        Rtask=double(scene.R_task(:,:,idx));n=numel(time);so3=nan(n,1);tilt=nan(n,1);
        for k=1:n
            R=rotation_zyx_local(X(k,7:9).');D=Rtask(:,:,k)'*R;
            so3(k)=acos(max(min((trace(D)-1)/2,1),-1));
            tilt(k)=acos(max(min(R(3,3),1),-1));
        end
        if all(isfinite(so3)),row.so3_rmse_rad=sqrt(mean(so3.^2));end
        row.max_tilt_rad=max(tilt);
        row.max_body_rate_radps=max(sqrt(sum(X(:,10:12).^2,2)));
    end
    row.run_valid=strcmp(row.run_state,'COMPLETED')&&complete&& ...
        strcmp(row.status_value,'STABLE')&&finiteTrace&&all(isfinite(X(:)))&& ...
        isempty(row.safety_stop_reason);
    row.application_feasible=row.run_valid&&~row.motor_saturation_any&& ...
        ~row.generalized_clip_any&&~row.tilt_limit_any&&row.geometry_checked&& ...
        row.pass_bidirectional&&row.pass_15mm_proxy&&row.q0_20_m<=.05&& ...
        row.q8_12_m<=.05&&row.end_position_error_m<=.10;
    if row.run_valid,row.score_state='SCORED_COMPLETE';else,row.score_state='SCORED_FAILED_OR_INCOMPLETE';end
    if isempty(row.failure_reason)&&~row.run_valid
        row.failure_reason='Run status, completion, finite trace or STABLE gate failed.';
    end
end

function row=empty_row(e)
    row=struct('runner',e.runner,'scene_id',e.scene_id,'attitude_arm',e.attitude_arm, ...
        'geometry_arm',e.geometry_arm,'payload_sha256',e.payload_sha256,'r_task_sha256','', ...
        'attempt_dir','','attempt_count',0,'run_state','MISSING','score_state','PENDING', ...
        'complete_transitions',false,'run_valid',false,'application_feasible',false, ...
        'actual_transition_count',NaN,'status_value','','safety_stop_reason','', ...
        'trace_finite',false,'motor_saturation_any',false,'generalized_clip_any',false, ...
        'tilt_limit_any',false,'q0_20_m',NaN,'q8_12_m',NaN,'rmse_x_m',NaN, ...
        'rmse_y_m',NaN,'rmse_z_m',NaN,'so3_rmse_rad',NaN,'max_tilt_rad',NaN, ...
        'max_body_rate_radps',NaN,'end_position_error_m',NaN,'geometry_checked',false, ...
        'pass_bidirectional',false,'pass_15mm_proxy',false,'minimum_clearance_m',NaN, ...
        'forward_clearance_m',NaN,'reverse_clearance_m',NaN,'failure_reason','');
end

function groups=summarize_groups(rows,arms)
    t=struct('runner','','attitude_arm','','geometry_arm','','expected_count',0, ...
        'complete_count',0,'run_valid_count',0,'application_feasible_count',0, ...
        'complete_case_mean_q0_20_m',NaN,'all_expected_mean_q0_20_m',NaN, ...
        'complete_case_mean_q8_12_m',NaN,'all_expected_mean_q8_12_m',NaN, ...
        'complete_case_mean_so3_rmse_rad',NaN,'all_expected_mean_so3_rmse_rad',NaN);
    groups=repmat(t,0,1);groupArms=[{'B'};arms(:);{'C5_11'}];geoms={'ACTIVE','FIXED_MIN','FIXED_BOUND15'};
    for i=1:numel(groupArms)
        for j=1:numel(geoms)
            if i==1&&~strcmp(geoms{j},'ACTIVE'),continue;end
            if i>1&&i<numel(groupArms)&&~strcmp(geoms{j},'ACTIVE'),continue;end
            arm=groupArms{i};if i==numel(groupArms)&&strcmp(geoms{j},'ACTIVE'),continue;end
            if strcmp(arm,'B'),runner='B';else,runner='CANDIDATE';end
            hit=find(strcmp({rows.runner},runner)&strcmp({rows.attitude_arm},arm)&strcmp({rows.geometry_arm},geoms{j}));
            if isempty(hit),continue;end
            g=t;g.runner=runner;g.attitude_arm=arm;g.geometry_arm=geoms{j};
            g.expected_count=numel(hit);g.complete_count=sum([rows(hit).complete_transitions]);
            g.run_valid_count=sum([rows(hit).run_valid]);g.application_feasible_count=sum([rows(hit).application_feasible]);
            completeHit=hit([rows(hit).complete_transitions]);
            g.complete_case_mean_q0_20_m=mean_if_any([rows(completeHit).q0_20_m]);
            g.complete_case_mean_q8_12_m=mean_if_any([rows(completeHit).q8_12_m]);
            g.complete_case_mean_so3_rmse_rad=mean_if_any([rows(completeHit).so3_rmse_rad]);
            if g.complete_count==g.expected_count&&g.expected_count==6
                g.all_expected_mean_q0_20_m=mean([rows(hit).q0_20_m]);
                g.all_expected_mean_q8_12_m=mean([rows(hit).q8_12_m]);
                g.all_expected_mean_so3_rmse_rad=mean([rows(hit).so3_rmse_rad]);
            end
            groups(end+1,1)=g; %#ok<AGROW>
        end
    end
end

function selected=select_fixed_comparator(rows)
    selected='NONE';modes={'FIXED_MIN','FIXED_BOUND15'};eligible=false(1,2);q=nan(1,2);rho=[.15 sqrt(2)*(.225-.0635-.015)];
    for j=1:2
        hit=find(strcmp({rows.runner},'CANDIDATE')&strcmp({rows.attitude_arm},'C5_11')&strcmp({rows.geometry_arm},modes{j}));
        eligible(j)=numel(hit)==6&&all([rows(hit).complete_transitions])&& ...
            all([rows(hit).run_valid])&& ...
            all([rows(hit).geometry_checked])&&all([rows(hit).pass_bidirectional])&& ...
            all([rows(hit).pass_15mm_proxy])&&all(isfinite([rows(hit).q8_12_m]));
        if eligible(j),q(j)=mean([rows(hit).q8_12_m]);end
    end
    valid=find(eligible);
    if isempty(valid),return;end
    if isscalar(valid),selected=modes{valid};return;end
    if abs(q(1)-q(2))<=1e-9
        selected=modes{find(rho==max(rho),1)};
    else
        selected=modes{find(q==min(q),1)};
    end
end

function lockSha=expected_lock(runner,release)
    if strcmp(runner,'B'),lockSha=char(release.b_source_lock_sha256);
    else,lockSha=char(release.candidate_source_lock_sha256);end
end
function key=slot_key(runner,scene,arm,geom)
    key=[upper(char(runner)) '|' char(scene) '|' upper(char(arm)) '|' upper(char(geom))];
end
function require_under(root,path,label)
    root=char(java.io.File(char(root)).getCanonicalPath());path=char(java.io.File(char(path)).getCanonicalPath());
    assert(startsWith(lower(path),[lower(root) filesep]),'GateScore:Path', ...
        '%s path escaped the isolated task root: %s',label,path);
end
function verify_candidate_lock(lock,runnerRoot)
    expected=dir(fullfile(runnerRoot,'matlab','**','*.m'));
    root=char(java.io.File(runnerRoot).getCanonicalPath());prefix=[root filesep];actual=cell(numel(expected),1);
    for i=1:numel(expected)
        p=char(java.io.File(fullfile(expected(i).folder,expected(i).name)).getCanonicalPath());
        assert(startsWith(lower(p),lower(prefix)),'GateScore:CandidateLockPath','Candidate source escaped root.');
        actual{i}=lower(strrep(p(numel(prefix)+1:end),'/','\'));
    end
    locked=lower(strrep(string({lock.files.relative_path}),'/','\'));
    assert(strcmp(char(lock.schema),'DL1018_CANDIDATE_SOURCE_LOCK_V1')&& ...
        strcmpi(char(lock.root),root)&&numel(unique(locked))==numel(locked)&& ...
        isequal(sort(locked(:)),sort(string(actual(:)))), ...
        'GateScore:CandidateLockCoverage','Candidate lock does not cover the source tree exactly once.');
    for i=1:numel(lock.files)
        p=fullfile(root,char(lock.files(i).relative_path));
        assert(isfile(p)&&strcmpi(sha256_file(p),char(lock.files(i).sha256)), ...
            'GateScore:CandidateLockSHA','Candidate source changed: %s',p);
    end
end
function verify_b_lock(lock,taskRoot)
    expected={'b_runner_work\run_b_frozen_gate.m';'b_runner_work\validate_b_gate_scene_no_plant.m'; ...
        'b_runner_work\RUN_B_FROZEN_GATE.ps1';'b_runner_work\verify_no_plant_identity.ps1'; ...
        'b_runner_work\identity_no_plant.json'};
    locked=lower(strrep(string({lock.files.relative_path}),'/','\'));
    assert(strcmp(char(lock.schema),'DL1018_B_SOURCE_LOCK_PILOT_V1')&& ...
        numel(unique(locked))==5&&isequal(sort(locked(:)),sort(lower(string(expected)))), ...
        'GateScore:BLockCoverage','B lock does not cover expected files exactly once.');
    for i=1:numel(lock.files)
        p=fullfile(taskRoot,char(lock.files(i).relative_path));
        assert(isfile(p)&&strcmpi(sha256_file(p),char(lock.files(i).sha256)), ...
            'GateScore:BLockSHA','B wrapper source changed: %s',p);
    end
end
function R=rotation_zyx_local(e)
    p=e(1);q=e(2);y=e(3);
    R=[cos(y)*cos(q),cos(y)*sin(q)*sin(p)-sin(y)*cos(p),cos(y)*sin(q)*cos(p)+sin(y)*sin(p); ...
        sin(y)*cos(q),sin(y)*sin(q)*sin(p)+cos(y)*cos(p),sin(y)*sin(q)*cos(p)-cos(y)*sin(p); ...
        -sin(q),cos(q)*sin(p),cos(q)*cos(p)];
end
function h=paired_sha256_double(a)
    md=java.security.MessageDigest.getInstance('SHA-256');md.update(typecast(double(a(:)),'uint8'));
    h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function m=mean_if_any(x)
    x=x(isfinite(x));if isempty(x),m=NaN;else,m=mean(x);end
end
function h=sha256_file(path)
    fid=fopen(path,'rb');assert(fid>=0,'GateScore:HashOpen','Cannot open file %s.',path);
    c=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
    while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
    h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear c;
end
