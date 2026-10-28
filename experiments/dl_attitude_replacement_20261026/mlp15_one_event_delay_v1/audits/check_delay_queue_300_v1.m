% Minimal no-Plant causality check of the actual delayed MLP15 queue snippet.
auditDir = fileparts(mfilename('fullpath'));
experimentRoot = fileparts(auditDir);
devPath = fullfile(experimentRoot, 'candidate_runner_work', 'matlab', ...
    'runtime', 'run_mlp15_dev72_closed_loop.m');
jsonPath = fullfile(auditDir, 'check_delay_queue_300_v1.json');
sourceSha = '';
report = struct('status', 'FAIL_DELAY_QUEUE_300_NO_PLANT', ...
    'event_count', 300, 'executed_event_count', 0, ...
    'first_event_applied_zero', false, ...
    'current_generated_independence_pass', false, ...
    'non_event_hold_pass', false, ...
    'source_event_index_time_age_pass', false, ...
    'no_second_beta_or_dmax', false, 'plant_calls', 0, ...
    'training_runs', 0, 'source_sha256', '', 'source_path', devPath, ...
    'time_step_s', 0.001, 'rls_scope', ...
    'MLP15 step/RLS was not executed; runtime RLS remains at its existing fixed 10 ms update interval.', ...
    'coverage', ['Evaluated the verbatim actual DEV queue cache segment from ' ...
    'appliedMlp15Torque=previousGeneratedMlp15Torque through the applied-delay-age if/end, ' ...
    'plus the actual dT=heldMlp15Torque line over every 1 ms sample. No Plant or full-function integration.']);
report.prior_failed_attempts = { ...
    'Attempt 1 failed locating the age-if closing end before the event loop; executed_event_count=0; plant_calls=0.', ...
    'Attempt 2 failed binding the pre-event held-torque source line before the event loop; executed_event_count=0; plant_calls=0.'};
executedEventCount = 0;

try
    assert(isfile(devPath), 'QueueCheck:SourceMissing', 'Actual DEV source is missing.');
    sourceSha = sha256_file(devPath);
    sourceText = fileread(devPath);

    startMarker = 'appliedMlp15Torque=previousGeneratedMlp15Torque;';
    ageMarker = 'appliedMlp15DelayAge=t(k)-heldMlp15AppliedSourceTime;';
    startAt = strfind(sourceText, startMarker);
    assert(numel(startAt) == 1, 'QueueCheck:StartMarker', ...
        'Expected one actual queue application marker.');
    ageAt = strfind(sourceText, ageMarker);
    ageAt = ageAt(ageAt > startAt(1));
    assert(numel(ageAt) == 1, 'QueueCheck:AgeMarker', ...
        'Expected one actual delay-age calculation after queue application.');
    afterAge = sourceText(ageAt(1) + numel(ageMarker):end);
    closeAt = strfind(afterAge, 'end');
    assert(~isempty(closeAt), 'QueueCheck:AgeIfEnd', ...
        'Could not find the actual age-if closing end.');
    closeAt = closeAt(1);
    snippetEnd = ageAt(1) + numel(ageMarker) + closeAt + 1;
    eventSnippet = sourceText(startAt(1):snippetEnd);

    heldLine = 'dT=heldMlp15Torque;';
    heldAt = strfind(sourceText, heldLine);
    assert(numel(heldAt) >= 2 && heldAt(1) < startAt(1), ...
        'QueueCheck:HeldMarker', 'Could not bind the actual non-event held-torque line.');
    heldAfter = sourceText(heldAt(1) + numel(heldLine): ...
        min(numel(sourceText), heldAt(1) + numel(heldLine) + 100));
    assert(contains(heldAfter, 'if attitudeEvent'), 'QueueCheck:HeldBranch', ...
        'The selected held-torque statement is not the actual pre-event branch line.');
    heldLine = sourceText(heldAt(1):heldAt(1) + numel(heldLine) - 1);
    assert(contains(eventSnippet, 'previousGeneratedMlp15Sample') && ...
        contains(eventSnippet, 'previousGeneratedMlp15Time=t(k);') && ...
        contains(eventSnippet, ageMarker), 'QueueCheck:SnippetCoverage', ...
        'Extracted source snippet does not cover cache/sample/time/age assignments.');

    eventCount = 300;
    intervalPattern = [7 11 9 14 10 8 13];
    eventIndices = zeros(eventCount, 1);
    eventIndices(1) = 5;
    for j = 2:eventCount
        eventIndices(j) = eventIndices(j-1) + intervalPattern(mod(j-2, numel(intervalPattern)) + 1);
    end
    sampleCount = eventIndices(end) + 4;
    t = (0:sampleCount-1).' * 0.001;

    % Synthetic generated torque already includes beta and componentwise dmax.
    dmax = [0.65; 0.38; 0.21];
    beta = min(0.15 + 0.002 * (1:eventCount), 0.9);
    rawResidual = [1.2*sin((1:eventCount)*0.17); ...
        -0.9*cos((1:eventCount)*0.11); 0.5*sin((1:eventCount)*0.07)];
    generated = zeros(3, eventCount);
    for j = 1:eventCount
        clipped = max(min(rawResidual(:,j), dmax), -dmax);
        generated(:,j) = beta(j) * clipped;
    end

    state = initial_queue_state(sampleCount);
    sourceSamples = zeros(eventCount, 1);
    sourceTimes = nan(eventCount, 1);
    appliedAges = nan(eventCount, 1);
    appliedByEvent = zeros(3, eventCount);
    timeCursor = 1;
    independenceCount = 0;
    nonEventHoldPass = true;
    for k = 1:sampleCount
        % This is the actual line immediately before the actual event branch.
        dT = nan(3, 1);
        heldMlp15Torque = state.heldMlp15Torque;
        eval(heldLine);
        heldAtStart = state.heldMlp15Torque;
        if timeCursor <= eventCount && k == eventIndices(timeCursor)
            preEventState = state;
            actual = execute_actual_event(eventSnippet, k, t(k), ...
                generated(:,timeCursor), preEventState);
            perturbation = [0.137; -0.241; 0.319];
            perturbed = execute_actual_event(eventSnippet, k, t(k), ...
                generated(:,timeCursor) + perturbation, preEventState);
            assert(isequal(actual.applied, perturbed.applied), ...
                'QueueCheck:CurrentGeneratedLeak', ...
                'Changing current generated torque changed current applied torque.');
            assert(isequal(perturbed.generated, generated(:,timeCursor) + perturbation), ...
                'QueueCheck:GeneratedCache', 'Current generated torque was not cached as supplied.');
            independenceCount = independenceCount + 1;

            if timeCursor == 1
                expectedApplied = zeros(3, 1);
                expectedSourceSample = 0;
                expectedSourceTime = NaN;
                expectedAge = NaN;
                assert(isequal(actual.applied, expectedApplied), ...
                    'QueueCheck:FirstEvent', 'First event did not apply zero torque.');
            else
                expectedApplied = generated(:,timeCursor-1);
                expectedSourceSample = eventIndices(timeCursor-1);
                expectedSourceTime = t(expectedSourceSample);
                expectedAge = t(k) - expectedSourceTime;
            end
            assert(isequal(actual.applied, expectedApplied), ...
                'QueueCheck:OneEventDelay', 'Applied torque is not the previous event output.');
            assert(actual.sourceSample == expectedSourceSample && ...
                isequaln(actual.sourceTime, expectedSourceTime) && ...
                isequaln(actual.delayAge, expectedAge), ...
                'QueueCheck:SourceAge', 'Applied source index/time/age is inaccurate.');
            assert(isequal(actual.generated, generated(:,timeCursor)), ...
                'QueueCheck:BetaDmaxRepeat', ...
                'Generated full beta/dmax torque was altered while caching.');
            appliedByEvent(:,timeCursor) = actual.applied;
            sourceSamples(timeCursor) = actual.sourceSample;
            sourceTimes(timeCursor) = actual.sourceTime;
            appliedAges(timeCursor) = actual.delayAge;
            state = actual.state;
            executedEventCount = executedEventCount + 1;
            timeCursor = timeCursor + 1;
        else
            assert(isequal(dT, heldAtStart) && isequal(state.heldMlp15Torque, heldAtStart), ...
                'QueueCheck:NonEventHold', 'Non-event sample changed held applied torque.');
            nonEventHoldPass = nonEventHoldPass && true;
        end
    end
    assert(timeCursor == eventCount + 1, 'QueueCheck:EventCount', ...
        'Not all 300 synthetic events were consumed.');
    assert(sum(state.mlp15GeneratedEventFlag) == eventCount && ...
        isequal(state.mlp15GeneratedTorqueLog(eventIndices,:), generated.') && ...
        isequal(state.mlp15GeneratedSourceSampleLog(eventIndices), eventIndices) && ...
        isequal(state.mlp15GeneratedSourceTimeLog(eventIndices), t(eventIndices)), ...
        'QueueCheck:GeneratedLogs', 'Generated event logs do not match synthetic full torques.');
    assert(~contains(lower(eventSnippet), 'beta') && ...
        ~contains(lower(eventSnippet), 'dmax'), 'QueueCheck:SecondScale', ...
        'Queue snippet unexpectedly applies beta or dmax a second time.');

    firstEventAppliedZero = all(appliedByEvent(:,1) == 0) && ...
        sourceSamples(1) == 0 && isnan(sourceTimes(1)) && isnan(appliedAges(1));
    ages = appliedAges(2:end);
    sourceAgePass = all(sourceSamples(2:end) == eventIndices(1:end-1)) && ...
        all(sourceTimes(2:end) == t(eventIndices(1:end-1))) && ...
        all(abs(ages - (t(eventIndices(2:end))-t(eventIndices(1:end-1)))) < 1e-12);
    noSecondScalePass = ~contains(lower(eventSnippet), 'beta') && ...
        ~contains(lower(eventSnippet), 'dmax') && ...
        isequal(state.mlp15GeneratedTorqueLog(eventIndices,:), generated.');
    assert(firstEventAppliedZero && independenceCount == eventCount && ...
        nonEventHoldPass && sourceAgePass && noSecondScalePass, ...
        'QueueCheck:FinalContract', 'One or more queue contract checks failed.');

    report.status = 'PASS_DELAY_QUEUE_300_NO_PLANT';
    report.executed_event_count = executedEventCount;
    report.first_event_applied_zero = firstEventAppliedZero;
    report.current_generated_independence_pass = independenceCount == eventCount;
    report.non_event_hold_pass = nonEventHoldPass;
    report.source_event_index_time_age_pass = sourceAgePass;
    report.no_second_beta_or_dmax = noSecondScalePass;
    report.source_sha256 = sourceSha;
    report.event_interval_pattern_samples = intervalPattern;
    report.event_interval_min_ms = min(diff(eventIndices));
    report.event_interval_max_ms = max(diff(eventIndices));
    report.actual_applied_age_min_ms = min(ages) * 1000;
    report.actual_applied_age_max_ms = max(ages) * 1000;
    report.extracted_event_snippet_sha256 = sha256_text(eventSnippet);
    report.command = ['& ''C:\Program Files\MATLAB\R2025b\bin\matlab.exe'' ' ...
        '-logfile ''C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\' ...
        'experiments\dl_attitude_replacement_20261026\mlp15_one_event_delay_v1\audits\' ...
        'check_delay_queue_300_v1.log'' -batch "run(''C:/Users/35326/Desktop/postgraduation/0/Mcode/' ...
        'drone_tcn/DL1018/experiments/dl_attitude_replacement_20261026/mlp15_one_event_delay_v1/' ...
        'audits/check_delay_queue_300_v1.m'')"'];
catch err
    report.source_sha256 = sourceSha;
    report.executed_event_count = executedEventCount;
    report.failure_identifier = err.identifier;
    report.failure_message = err.message;
    write_json(jsonPath, report);
    fprintf(2, 'QUEUE_TEST_STATUS=%s\n%s\n', report.status, err.message);
    rethrow(err);
end

write_json(jsonPath, report);
fprintf('QUEUE_TEST_STATUS=%s\n', report.status);
fprintf('event_count=%d source_sha256=%s\n', report.event_count, report.source_sha256);

function state = initial_queue_state(sampleCount)
state = struct('previousGeneratedMlp15Torque', zeros(3,1), ...
    'previousGeneratedMlp15Sample', 0, 'previousGeneratedMlp15Time', NaN, ...
    'heldMlp15Torque', zeros(3,1), 'heldMlp15AppliedSourceSample', 0, ...
    'heldMlp15AppliedSourceTime', NaN, 'dT', zeros(3,1), ...
    'mlp15GeneratedEventFlag', false(sampleCount,1), ...
    'mlp15GeneratedTorqueLog', nan(sampleCount,3), ...
    'mlp15GeneratedSourceSampleLog', nan(sampleCount,1), ...
    'mlp15GeneratedSourceTimeLog', nan(sampleCount,1));
end

function out = execute_actual_event(snippet, k, tk, generated, state)
previousGeneratedMlp15Torque = state.previousGeneratedMlp15Torque;
previousGeneratedMlp15Sample = state.previousGeneratedMlp15Sample;
previousGeneratedMlp15Time = state.previousGeneratedMlp15Time;
heldMlp15Torque = state.heldMlp15Torque;
heldMlp15AppliedSourceSample = state.heldMlp15AppliedSourceSample;
heldMlp15AppliedSourceTime = state.heldMlp15AppliedSourceTime;
dT = state.dT;
mlp15GeneratedEventFlag = state.mlp15GeneratedEventFlag;
mlp15GeneratedTorqueLog = state.mlp15GeneratedTorqueLog;
mlp15GeneratedSourceSampleLog = state.mlp15GeneratedSourceSampleLog;
mlp15GeneratedSourceTimeLog = state.mlp15GeneratedSourceTimeLog;
t = zeros(numel(mlp15GeneratedEventFlag),1);
t(k) = tk;
mlpOut = struct('estimateTorque_Nm', generated(:));
eval(snippet);
out.applied = appliedMlp15Torque;
out.generated = generatedMlp15Torque;
out.sourceSample = heldMlp15AppliedSourceSample;
out.sourceTime = heldMlp15AppliedSourceTime;
out.delayAge = appliedMlp15DelayAge;
out.state = struct('previousGeneratedMlp15Torque', previousGeneratedMlp15Torque, ...
    'previousGeneratedMlp15Sample', previousGeneratedMlp15Sample, ...
    'previousGeneratedMlp15Time', previousGeneratedMlp15Time, ...
    'heldMlp15Torque', heldMlp15Torque, ...
    'heldMlp15AppliedSourceSample', heldMlp15AppliedSourceSample, ...
    'heldMlp15AppliedSourceTime', heldMlp15AppliedSourceTime, 'dT', dT, ...
    'mlp15GeneratedEventFlag', mlp15GeneratedEventFlag, ...
    'mlp15GeneratedTorqueLog', mlp15GeneratedTorqueLog, ...
    'mlp15GeneratedSourceSampleLog', mlp15GeneratedSourceSampleLog, ...
    'mlp15GeneratedSourceTimeLog', mlp15GeneratedSourceTimeLog);
end

function hash = sha256_file(path)
fid = fopen(path, 'rb');
assert(fid >= 0, 'QueueCheck:HashOpen', 'Could not open source file for hashing.');
closer = onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes = fread(fid, Inf, '*uint8');
hash = sha256_bytes(bytes);
end

function hash = sha256_text(value)
hash = sha256_bytes(uint8(value(:)));
end

function hash = sha256_bytes(bytes)
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(uint8(bytes(:)), 'int8'));
digest = typecast(md.digest(), 'uint8');
hash = lower(reshape(dec2hex(digest, 2).', 1, []));
end

function write_json(path, value)
fid = fopen(path, 'w');
assert(fid >= 0, 'QueueCheck:JsonOpen', 'Could not create JSON report.');
closer = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid, '%s\n', jsonencode(value));
end
