function ledger = run_full72_authorized_batch()
% Run the root-authorized full72 candidate calls sequentially and audit each raw.
here = char(java.io.File(fileparts(mfilename('fullpath'))).getCanonicalPath());
study = fileparts(here);
release = jsondecode(fileread(fullfile(study, 'RELEASE.json')));
manifest = jsondecode(fileread(fullfile(study, 'MANIFEST.json')));
decision = jsondecode(fileread(char(release.root_release_decision_path)));
scriptPath = [mfilename('fullpath') '.m'];
assert(strcmp(char(release.status), 'RELEASED') && ...
    strcmp(char(release.study_id), 'gru_stream_cosine_tracking_head_full72_v1') && ...
    double(release.authorized_Plant_calls) == 66 && double(release.Plant_calls) == 0 && ...
    ~logical(release.TEST_read) && strcmp(char(decision.decision), ...
    'APPROVED_FOR_FROZEN_CANDIDATE_DEV72_SCREEN') && ...
    strcmpi(hash_file(char(release.root_release_decision_path)), ...
    char(release.root_release_decision_sha256)) && ...
    strcmpi(hash_file(scriptPath), char(release.batch_runner_sha256)), ...
    'Full72Batch:Release', 'Root approval, release, or batch-runner binding failed.');
assert(strcmp(char(manifest.status), 'PASS_READ_ONLY_VALIDATION_BINDINGS') && ...
    numel(manifest.records) == 72 && ~logical(manifest.TEST_read), ...
    'Full72Batch:Manifest', 'Full72 manifest is not the locked DEV/VAL cohort.');
authorized = cellstr(string(release.authorized_scenes)); authorized = authorized(:);
approved = cellstr(string(decision.authorized_scene_order)); approved = approved(:);
expected = cellstr(string({manifest.records(~[manifest.records.candidate_reuse]).scene_id}));
expected = expected(:);
assert(numel(authorized) == 66 && isequal(authorized, approved) && ...
    isequal(sort(authorized), sort(expected)), ...
    'Full72Batch:SceneList', 'Release scene list differs from the approved 66 new scenes.');

runtime = fullfile(study, 'candidate_runner_work', 'matlab', 'runtime');
addpath(runtime, '-begin'); addpath(here, '-begin'); addpath(study, '-begin');
assert(strcmpi(which('run_gru_stream_tracking_head_full72_attempt'), ...
    fullfile(study, 'run_gru_stream_tracking_head_full72_attempt.m')) && ...
    strcmpi(which('audit_gru_stream_tracking_head_raw'), ...
    fullfile(here, 'audit_gru_stream_tracking_head_raw.m')), ...
    'Full72Batch:WhichPath', 'The isolated driver or raw auditor did not resolve.');
ledgerPath = fullfile(here, 'FULL72_PROGRESS_LEDGER_v1.json');
suffix = 1;
while isfile(ledgerPath)
    suffix = suffix + 1;
    ledgerPath = fullfile(here, sprintf('FULL72_PROGRESS_LEDGER_v%02d.json', suffix));
end
logPath = fullfile(here, 'FULL72_BATCH_R2025b.log');
suffix = 1;
while isfile(logPath)
    suffix = suffix + 1;
    logPath = fullfile(here, sprintf('FULL72_BATCH_R2025b_%02d.log', suffix));
end
diary(logPath);
diary('on');

rows = repmat(struct('scene_id', '', 'state', 'PENDING', 'started_utc', '', ...
    'finished_utc', '', 'attempt_dir', '', 'raw_path', '', 'raw_sha256', '', ...
    'audit_path', '', 'audit_status', '', 'Plant_calls', 0, ...
    'error_identifier', '', 'error_message', ''), 1, numel(authorized));
ledger = struct('schema', 'DL1018_GRU_STREAM_TRACKING_HEAD_FULL72_PROGRESS_LEDGER_V1', ...
    'status', 'RUNNING', 'study_id', char(release.study_id), 'candidate', char(release.candidate), ...
    'release_sha256', hash_file(fullfile(study, 'RELEASE.json')), ...
    'batch_runner_sha256', hash_file(scriptPath), 'started_utc', utc_now(), ...
    'finished_utc', '', 'authorized_calls', numel(authorized), 'Plant_calls_started', 0, ...
    'completed_and_audited', 0, 'failed_or_incomplete', 0, 'TEST_read', false, 'records', rows);
write_ledger(ledgerPath, ledger);

for i = 1:numel(authorized)
    sceneId = authorized{i};
    addpath(runtime, '-begin'); addpath(here, '-begin'); addpath(study, '-begin');
    attemptDir = fullfile(study, 'runs', sceneId);
    statusPath = fullfile(attemptDir, 'run_status.json');
    rawPath = fullfile(attemptDir, 'raw_run.mat');
    auditPath = fullfile(here, [sceneId '_GRU_STREAM_TRACKING_HEAD_FULL72_RAW_AUDIT.json']);
    rows(i).scene_id = sceneId;
    rows(i).attempt_dir = attemptDir;
    rows(i).raw_path = rawPath;
    rows(i).audit_path = auditPath;
    if isfolder(attemptDir)
        markerPath = fullfile(attemptDir, 'attempt_started.marker');
        rows(i).Plant_calls = double(isfile(markerPath));
        rows(i).state = 'SKIPPED_EXISTING_NO_RETRY';
        if isfile(statusPath)
            s = jsondecode(fileread(statusPath));
            rows(i).raw_sha256 = char(field_or(s, 'raw_sha256', ''));
        end
        if isfile(auditPath)
            a = jsondecode(fileread(auditPath));
            rows(i).audit_status = char(field_or(a, 'status', ''));
        end
        if isfile(statusPath) && isfile(rawPath) && isfile(auditPath)
            s = jsondecode(fileread(statusPath));
            a = jsondecode(fileread(auditPath));
            if strcmp(char(field_or(s, 'state', '')), 'COMPLETED') && ...
                strcmp(char(field_or(a, 'status', '')), ...
                'PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY') && ...
                strcmpi(char(field_or(s, 'release_sha256', '')), ledger.release_sha256) && ...
                strcmpi(hash_file(rawPath), char(field_or(s, 'raw_sha256', ''))) && ...
                strcmpi(char(field_or(a, 'release_sha256', '')), ledger.release_sha256)
                rows(i).state = 'PASS_RAW_AUDITED_EXISTING';
            end
        end
        rows(i).error_message = 'Existing attempt directory preserved; automatic retry is disabled.';
    else
        rows(i).state = 'RUNNING';
        rows(i).started_utc = utc_now();
        ledger.records = rows;
        write_ledger(ledgerPath, ledger);
        try
            attemptDir = run_gru_stream_tracking_head_full72_attempt(sceneId);
            addpath(runtime, '-begin'); addpath(here, '-begin'); addpath(study, '-begin');
            rawPath = fullfile(attemptDir, 'raw_run.mat');
            statusPath = fullfile(attemptDir, 'run_status.json');
            audit = audit_gru_stream_tracking_head_raw(sceneId, rawPath);
            rows(i).attempt_dir = attemptDir;
            rows(i).raw_path = rawPath;
            rows(i).raw_sha256 = hash_file(rawPath);
            rows(i).audit_status = char(audit.status);
            rows(i).Plant_calls = 1;
            if strcmp(char(audit.status), 'PASS_INDEPENDENT_GRU_STREAM_TRACKING_HEAD_RAW_REPLAY')
                rows(i).state = 'PASS_RAW_AUDITED';
            else
                rows(i).state = 'AUDIT_FAILED';
                rows(i).error_message = 'Raw auditor returned a non-pass status; no retry.';
            end
        catch ME
            rows(i).state = 'FAILED_OR_AUDIT_FAILED_NO_RETRY';
            rows(i).error_identifier = char(ME.identifier);
            rows(i).error_message = char(ME.message);
            if isfile(statusPath)
                s = jsondecode(fileread(statusPath));
                rows(i).Plant_calls = double(field_or(s, 'Plant_calls', 0));
                rows(i).raw_sha256 = char(field_or(s, 'raw_sha256', ''));
            end
            if isfile(auditPath)
                a = jsondecode(fileread(auditPath));
                rows(i).audit_status = char(field_or(a, 'status', ''));
            end
        end
        rows(i).finished_utc = utc_now();
    end
    ledger.records = rows;
    markers = dir(fullfile(study, 'runs', '**', 'attempt_started.marker'));
    ledger.Plant_calls_started = numel(markers);
    ledger.completed_and_audited = nnz(ismember({rows.state}, ...
        {'PASS_RAW_AUDITED', 'PASS_RAW_AUDITED_EXISTING'}));
    ledger.failed_or_incomplete = nnz(ismember({rows.state}, ...
        {'FAILED_OR_AUDIT_FAILED_NO_RETRY', 'AUDIT_FAILED', 'SKIPPED_EXISTING_NO_RETRY'}));
    write_ledger(ledgerPath, ledger);
    fprintf('FULL72_PROGRESS %d/%d %s state=%s Plant_calls=%d audited=%d failed=%d\n', ...
        i, numel(authorized), sceneId, rows(i).state, ledger.Plant_calls_started, ...
        ledger.completed_and_audited, ledger.failed_or_incomplete);
    drawnow;
end
ledger.finished_utc = utc_now();
if ledger.completed_and_audited == 66 && ledger.Plant_calls_started == 66
    ledger.status = 'PASS_ALL_66_NEW_CANDIDATE_RAW_AUDITS';
else
    ledger.status = 'COMPLETE_WITH_FAILURES_OR_INCOMPLETE_SCENES';
end
write_ledger(ledgerPath, ledger);
diary('off');
end

function write_ledger(path, value)
tmp = [path '.tmp'];
fid = fopen(tmp, 'w', 'n', 'UTF-8');
assert(fid >= 0, 'Full72Batch:LedgerWrite', 'Could not write progress ledger.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(value, 'PrettyPrint', true));
clear cleanup;
movefile(tmp, path, 'f');
end

function h = hash_file(path)
fid = fopen(path, 'rb');
assert(fid >= 0, 'Full72Batch:ReadFile', 'Cannot read %s.', path);
cleanup = onCleanup(@() fclose(fid));
md = java.security.MessageDigest.getInstance('SHA-256');
while true
    bytes = fread(fid, 8 * 1024 * 1024, '*uint8');
    if isempty(bytes), break; end
    md.update(typecast(bytes(:), 'int8'));
end
h = lower(reshape(dec2hex(typecast(md.digest(), 'uint8'), 2).', 1, []));
clear cleanup;
end

function value = field_or(s, name, default)
if isstruct(s) && isfield(s, name), value = s.(name); else, value = default; end
end

function value = utc_now()
value = char(datetime('now', 'TimeZone', 'UTC', ...
    'Format', "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"));
end
