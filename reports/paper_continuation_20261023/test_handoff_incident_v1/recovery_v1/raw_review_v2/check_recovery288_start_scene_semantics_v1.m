function check_recovery288_start_scene_semantics_v1()
% Read-only, no-Plant semantic comparison of frozen scene packs and run_start inputs.
% Loads only shared scenePacks plus scene/sceneMeta/spec from each run_start MAT.
% It does not open raw_run.mat or compute scores and does not reclassify legacy OS gates.

scriptPath = mfilename('fullpath');
scriptDir = fileparts(scriptPath);
root = scriptDir;
for k = 1:5
    root = fileparts(root);
end
outputPath = fullfile(scriptDir, 'SCENE_EQUIVALENCE_NPLANT_RESULT_v1.json');
assert(~isfile(outputPath), 'Refusing to overwrite existing result: %s', outputPath);

indexPath = fullfile(root, 'experiments', 'c5_test48_v3', 'input', 'TEST_INPUT_INDEX_v1.json');
sharedPath = fullfile(root, 'experiments', 'c5_test48_v3', 'input', 'TEST_SCENES_SHARED_v1.mat');
assert(strcmp(sha256_file(indexPath), '90940a818d293c66c34423a63088113557518c5ecdfd528a3f37867f391eef68'), ...
    'Frozen TEST input-index SHA changed');
sharedSha = 'da207d858e8918f27c19fef30d4ad57206e20f1971e743515043d1a88a995d5c';
sharedShaBefore = sha256_file(sharedPath);
assert(strcmp(sharedShaBefore, sharedSha), 'Frozen shared-scene SHA changed');
index = jsondecode(fileread(indexPath));
sceneIds = json_string_array(index.scene_ids);
assert(numel(sceneIds) == 48, 'Expected 48 frozen scene IDs');
assert(strcmp(char(string(index.shared_scenes_mat_sha256)), sharedSha), ...
    'Input index does not bind the frozen shared-scene MAT');

batchShas = {'388e2d32b824bdae420088e397f1408d73d2677c6b75ed98dbefed5b784c29c9', ...
    '60f5ce17f634ab82bfb5a14017575727f6a88e777d613c9f7838ac3b25e91e01', ...
    'd976e2eee317dffcceae99046dd4ce6f5f06eface4c039513cd39769a25870df', ...
    'ff1d61302f459f07ca3c813b165d01deffdb619447d907f6ffa1cca9f76249d7', ...
    '970971971ac88d17639962917ffe7f8ae235c3c7dfc3fb394c716883d981a7e9'};

% Construct the exact 288 run_start path/SHA pairs from the preserved batch metadata.
rows = repmat(blank_row(), 0, 1);
v3B = fullfile(root, 'experiments', 'c5_test48_v3', 'runs', 'BTR', 'METHOD_BATCH_STATUS_v1.json');
assert_source_sha(v3B, '72a2f159fca3b7c56c2415909a9214afb93d2e8df0caae9f656a720870b33389');
b = jsondecode(fileread(v3B));
assert(strcmp(b.schema, 'TEST48_METHOD_BATCH_STATUS_V1') && strcmp(b.method_id, 'B_TRACEABLE') ...
    && strcmp(b.alias, 'BTR') && b.scene_count == 48 && b.completed_scenes == 48 ...
    && numel(b.records) == 48, 'B48 batch metadata differs from the frozen scope');
rows = [rows; rows_from_batch(root, b.records, 'B_TRACEABLE', 'BTR', sceneIds, 1:48, ...
    'V3_REUSED_B48', fullfile(root, 'experiments', 'c5_test48_v3', 'runs', 'BTR'))];

methodIds = {'CORRECTED_DSSM14_G12_R32', 'CORRECTED_KAN14_G12_R32', ...
    'C5_M110', 'C5_FREEZE_TRAINED_W0', 'C5_NO_DELAYED_PREDICTION'};
aliases = {'DSSM', 'KAN', 'C5M110', 'C5FREEZE', 'C5NOPRED'};
for mi = 1:numel(methodIds)
    methodId = methodIds{mi};
    alias = aliases{mi};
    if mi == 1
        % Original DSSM records 1-31 remain tied to their v9 batch; scene 32 is
        % represented only by the parent no-score identity report; 33-48 are the
        % separately receipted recovery tail. This does not infer an OS exit.
        oldPath = fullfile(root, 'experiments', 'c5_test48_v9', 'runs', alias, 'METHOD_BATCH_STATUS_v4.json');
        assert_source_sha(oldPath, batchShas{mi});
        old = jsondecode(fileread(oldPath));
        assert(strcmp(old.schema, 'TEST48V4_METHOD_BATCH_STATUS_V1') && strcmp(old.method_id, methodId) ...
            && strcmp(old.alias, alias) && old.completed_scenes == 31 && numel(old.records) == 31, ...
            'Original DSSM 31-record batch metadata changed');
        rows = [rows; rows_from_batch(root, old.records, methodId, alias, sceneIds, 1:31, ...
            'V9_ORIGINAL_FIRST31_OS_UNKNOWN', fullfile(root, 'experiments', 'c5_test48_v9', 'runs', alias))];

        scene32ReportPath = fullfile(root, 'reports', 'paper_continuation_20261023', ...
            'test_handoff_incident_v1', 'PARENT_SCENE32_IDENTITY_NO_SCORE_v1.json');
        scene32ReportSha = '09fbc3c51cd029cbd79da5adb43ad7a43937efaafdd28fb92608250944d12e15';
        assert(strcmp(sha256_file(scene32ReportPath), scene32ReportSha), 'Scene32 parent report SHA changed');
        scene32Report = jsondecode(fileread(scene32ReportPath));
        assert(strcmp(scene32Report.scene_id, sceneIds{32}) && scene32Report.runIdentity_missing ...
            && strcmp(scene32Report.OS_exit, 'UNKNOWN') ...
            && strcmp(scene32Report.hashes.run_start, 'bfca54164a726f560e90cbb8201bfe73d1e010cabbb54c5d2127ac8f704a159f'), ...
            'Scene32 exception is not the parent-reviewed no-identity/unknown-OS record');
        scene32Start = fullfile(root, 'experiments', 'c5_test48_v9', 'runs', 'DSSM', ...
            sceneIds{32}, 'attempt_01', 'run_start.mat');
        rows(end + 1, 1) = make_row(methodId, 32, sceneIds{32}, scene32Start, ...
            scene32Report.hashes.run_start, 'V9_SCENE32_NUMERIC_IDENTITY_ONLY_OS_UNKNOWN'); %#ok<AGROW>

        tailPath = fullfile(root, 'experiments', 'c5_test48_recovery_v1', 'runs', ...
            'DSSM_TAIL16', 'METHOD_BATCH_STATUS_v1.json');
        assert_source_sha(tailPath, '7e0a2b5552d3baa967c3395a0efb4d5283bbb76238747db8992c749781855ee1');
        tail = jsondecode(fileread(tailPath));
        assert(strcmp(tail.schema, 'RECOVERY208_DSSM_TAIL16_BATCH_STATUS_V1') ...
            && strcmp(tail.method_id, methodId) && strcmp(tail.alias, 'DSSM_TAIL16') ...
            && tail.scene_count == 16 && tail.completed_scenes == 16 && numel(tail.records) == 16, ...
            'DSSM recovery-tail metadata changed');
        rows = [rows; rows_from_tail(root, tail.records, methodId, sceneIds, ...
            fullfile(root, 'experiments', 'c5_test48_recovery_v1', 'runs', 'DSSM_TAIL16'))];
    else
        batchPath = fullfile(root, 'experiments', 'c5_test48_v9', 'runs', alias, 'METHOD_BATCH_STATUS_v4.json');
        assert_source_sha(batchPath, batchShas{mi});
        batch = jsondecode(fileread(batchPath));
        assert(strcmp(batch.schema, 'TEST48V4_METHOD_BATCH_STATUS_V1') ...
            && strcmp(batch.method_id, methodId) && strcmp(batch.alias, alias) ...
            && batch.scene_count == 48 && batch.completed_scenes == 48 && numel(batch.records) == 48, ...
            'Recovery method batch metadata differs from the frozen scope: %s', methodId);
        rows = [rows; rows_from_batch(root, batch.records, methodId, alias, sceneIds, 1:48, ...
            'RECOVERY208_V9_SCIENTIFIC_ENTRY', fullfile(root, 'experiments', 'c5_test48_v9', 'runs', alias))];
    end
end
assert(numel(rows) == 288, 'Expected exactly 288 run_start pairs');
pairs = cell(numel(rows), 1);
for i = 1:numel(rows)
    pairs{i} = [rows(i).method_id '|' rows(i).scene_id];
end
assert(numel(unique(pairs)) == 288, 'Duplicate method/scene pair in the 288-row manifest');

% Load only the frozen shared pack variable. Do not load any run output/raw variable.
sharedData = load(sharedPath, 'scenePacks');
assert(isfield(sharedData, 'scenePacks') && iscell(sharedData.scenePacks) ...
    && numel(sharedData.scenePacks) == 48, 'Frozen scenePacks variable has an unexpected schema');

for i = 1:numel(rows)
    row = rows(i);
    try
        row.start_sha256_before = sha256_file(row.run_start_path);
        assert(strcmp(row.start_sha256_before, row.expected_start_sha256), ...
            'run_start SHA differs from its preserved batch/parent metadata');
        startData = load(row.run_start_path, 'scene', 'sceneMeta', 'spec');
        assert(all(isfield(startData, {'scene', 'sceneMeta', 'spec'})), ...
            'run_start lacks one of scene/sceneMeta/spec');
        expectedPack = sharedData.scenePacks{row.scene_index};
        assert(isstruct(expectedPack) && all(isfield(expectedPack, {'scene', 'metadata', 'spec'})), ...
            'Frozen scene pack lacks scene/metadata/spec');
        row.scene_equal = isequaln(startData.scene, expectedPack.scene);
        row.sceneMeta_equal = isequaln(startData.sceneMeta, expectedPack.metadata);
        row.spec_equal = isequaln(startData.spec, expectedPack.spec);
        ids = {char_scene_id(startData.scene.scene_id), ...
            char_scene_id(expectedPack.scene.scene_id), ...
            char_scene_id(startData.sceneMeta.scene_id), ...
            char_scene_id(expectedPack.metadata.scene_id), ...
            char_scene_id(table_scene_id(startData.spec)), ...
            char_scene_id(table_scene_id(expectedPack.spec))};
        row.scene_id_char_equal = all(strcmp(ids, row.scene_id));
        row.variable_check_pass = row.scene_equal && row.sceneMeta_equal && row.spec_equal ...
            && row.scene_id_char_equal;
    catch err
        row.error_identifier = err.identifier;
        row.error_message = err.message;
    end
    try
        row.start_sha256_after = sha256_file(row.run_start_path);
        row.start_unchanged_during_read = strcmp(row.start_sha256_before, row.start_sha256_after) ...
            && strcmp(row.start_sha256_after, row.expected_start_sha256);
    catch err
        row.start_sha256_after = '';
        row.start_unchanged_during_read = false;
        if isempty(row.error_message)
            row.error_identifier = err.identifier;
            row.error_message = err.message;
        end
    end
    rows(i) = row;
end
sharedShaAfter = sha256_file(sharedPath);
sharedUnchanged = strcmp(sharedShaBefore, sharedShaAfter) && strcmp(sharedShaAfter, sharedSha);
allRowsPass = all([rows.variable_check_pass]) && all([rows.start_unchanged_during_read]) ...
    && all(cellfun(@isempty, {rows.error_message})) && sharedUnchanged;

result = struct();
result.schema = 'RECOVERY288_SCENE_START_SEMANTIC_EQUIVALENCE_NOPLANT_V1';
result.status = ternary(allRowsPass, 'PASS_EXACT_SCENE_START_EQUIVALENCE_NO_PLANT', ...
    'FAIL_SCENE_START_EQUIVALENCE_OR_INPUT_STABILITY');
result.created_utc = char(datetime('now', 'TimeZone', 'UTC', 'Format', "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"));
result.plant_calls = 0;
result.raw_files_opened = false;
result.scoring_performed = false;
result.shared_scenes = struct('path', sharedPath, 'expected_sha256', sharedSha, ...
    'sha256_before', sharedShaBefore, 'sha256_after', sharedShaAfter, 'unchanged', sharedUnchanged);
result.run_start_count = numel(rows);
result.unique_method_scene_pairs = numel(unique(pairs));
result.all_288_pairs_pass = allRowsPass;
result.original_DSSM_natural_OS_exit = 'UNKNOWN';
result.legacy_six_process_OS0_gate = 'UNMET_DO_NOT_RECLASSIFY';
result.rows = rows;
write_json_no_overwrite(outputPath, result);
end

function rows = rows_from_batch(root, records, methodId, alias, sceneIds, indices, source, basePath)
assert(numel(records) == numel(indices), 'Batch record count mismatch for %s', methodId);
rows = repmat(blank_row(), numel(records), 1);
for j = 1:numel(records)
    rec = records(j);
    idx = indices(j);
    assert(rec.batch_index == idx && strcmp(char(string(rec.scene_id)), sceneIds{idx}), ...
        'Batch index/scene order mismatch for %s/%s', methodId, sceneIds{idx});
    expectedPath = fullfile(basePath, sceneIds{idx}, 'attempt_01', 'run_start.mat');
    assert(strcmpi(canonical_path(char(string(rec.run_start_path))), canonical_path(expectedPath)), ...
        'Unexpected run_start path for %s/%s', methodId, sceneIds{idx});
    rows(j) = make_row(methodId, idx, sceneIds{idx}, rec.run_start_path, ...
        rec.run_start_sha256, source);
end
end

function assert_source_sha(path, expectedSha)
assert(strcmp(sha256_file(path), expectedSha), 'Frozen batch/report source SHA changed: %s', path);
end

function rows = rows_from_tail(root, records, methodId, sceneIds, basePath)
assert(numel(records) == 16, 'DSSM tail must have 16 records');
rows = repmat(blank_row(), numel(records), 1);
for j = 1:numel(records)
    rec = records(j);
    idx = j + 32;
    assert(rec.canonical_batch_index == idx && rec.tail_local_index == j ...
        && strcmp(char(string(rec.scene_id)), sceneIds{idx}), ...
        'Tail canonical/local index or scene mismatch at local index %d', j);
    expectedPath = fullfile(basePath, sceneIds{idx}, 'attempt_01', 'run_start.mat');
    assert(strcmpi(canonical_path(char(string(rec.run_start_path))), canonical_path(expectedPath)), ...
        'Unexpected DSSM tail run_start path at canonical index %d', idx);
    rows(j) = make_row(methodId, idx, sceneIds{idx}, rec.run_start_path, ...
        rec.run_start_sha256, 'RECOVERY208_DSSM_TAIL16');
end
end

function row = blank_row()
row = struct('method_id', '', 'scene_index', 0, 'scene_id', '', ...
    'source', '', 'run_start_path', '', 'expected_start_sha256', '', ...
    'start_sha256_before', '', 'start_sha256_after', '', ...
    'scene_equal', false, 'sceneMeta_equal', false, 'spec_equal', false, ...
    'scene_id_char_equal', false, 'variable_check_pass', false, ...
    'start_unchanged_during_read', false, 'error_identifier', '', 'error_message', '');
end

function row = make_row(methodId, sceneIndex, sceneId, path, expectedSha, source)
row = blank_row();
row.method_id = char(string(methodId));
row.scene_index = sceneIndex;
row.scene_id = char(string(sceneId));
row.source = source;
row.run_start_path = char(string(path));
row.expected_start_sha256 = lower(char(string(expectedSha)));
assert(~isempty(regexp(row.expected_start_sha256, '^[0-9a-f]{64}$', 'once')), ...
    'Malformed run_start SHA for %s/%s', row.method_id, row.scene_id);
end

function ids = json_string_array(value)
if iscell(value)
    ids = cellfun(@(x) char(string(x)), value(:), 'UniformOutput', false);
elseif isstring(value)
    ids = cellstr(value(:));
elseif ischar(value)
    if isrow(value)
        ids = {value};
    else
        ids = cellstr(value);
    end
else
    error('Unexpected JSON scene_ids type: %s', class(value));
end
end

function value = char_scene_id(value)
if isstring(value)
    assert(isscalar(value), 'Expected scalar MATLAB string scene_id');
    value = char(value);
elseif ischar(value)
    assert(isrow(value), 'Expected row character scene_id');
else
    error('Unexpected scene_id type: %s', class(value));
end
end

function value = table_scene_id(value)
assert(istable(value) && height(value) == 1 && any(strcmp(value.Properties.VariableNames, 'scene_id')), ...
    'Expected one-row MATLAB table with scene_id variable');
value = value.scene_id;
assert(numel(value) == 1, 'Expected scalar table scene_id');
if iscell(value)
    value = value{1};
end
end

function path = canonical_path(path)
path = char(java.io.File(path).getCanonicalPath());
end

function digest = sha256_file(path)
fid = fopen(path, 'rb');
assert(fid >= 0, 'Cannot open file for SHA-256: %s', path);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes = fread(fid, Inf, '*uint8');
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(bytes(:), 'int8'));
digestBytes = typecast(md.digest(), 'uint8');
digest = lower(reshape(dec2hex(digestBytes, 2).', 1, []));
end

function write_json_no_overwrite(path, value)
assert(~isfile(path), 'Refusing to overwrite existing result: %s', path);
tmpPath = [path '.tmp'];
assert(~isfile(tmpPath), 'Refusing to overwrite existing temporary result: %s', tmpPath);
fid = fopen(tmpPath, 'w');
assert(fid >= 0, 'Cannot create result file: %s', tmpPath);
try
    fwrite(fid, jsonencode(value), 'char');
    fwrite(fid, newline, 'char');
    closeStatus = fclose(fid);
    fid = -1;
    assert(closeStatus == 0, 'Could not finish writing result: %s', tmpPath);
catch err
    if fid >= 0
        fclose(fid);
    end
    rethrow(err);
end
movefile(tmpPath, path);
end

function value = ternary(condition, whenTrue, whenFalse)
if condition
    value = whenTrue;
else
    value = whenFalse;
end
end
