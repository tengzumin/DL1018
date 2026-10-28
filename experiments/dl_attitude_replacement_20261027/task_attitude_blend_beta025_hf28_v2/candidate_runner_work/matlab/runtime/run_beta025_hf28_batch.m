function ledger=run_beta025_hf28_batch()
% Exact sequential HF28 batch. Existing attempt folders are never rerun.
entry=fileparts(mfilename('fullpath'));studyRoot=fileparts(fileparts(fileparts(entry)));
runtime=fullfile(studyRoot,'candidate_runner_work','matlab','runtime');
addpath(runtime,'-begin');
[release,manifest]=validate_beta025_hf28_release(studyRoot);
freeBytes=java.io.File(studyRoot).getFreeSpace();
assert(freeBytes>=30*1024^3,'HF28:DiskFloor','Free disk is below 30 GiB; no new attempt may start.');
pairPath=fullfile(studyRoot,'audits','HF28_SCENE_PAIR_PREFLIGHT_v1.json');
assert(isfile(pairPath),'HF28:PairAudit','The locked read-only scene-pair preflight receipt is missing.');
report=jsondecode(fileread(pairPath));
assert(strcmp(char(report.status),'PASS_SCENE_ONLY')&&double(report.scene_count)==28&& ...
    ~logical(report.TEST_read)&&~logical(report.baseline_metrics_recomputed)&& ...
    strcmpi(char(report.manifest_sha256),sha256_file(fullfile(studyRoot,'HF28_EXECUTION_MANIFEST_v1.json')))&& ...
    all([report.results.B_identity_match])&&all([report.results.C5_scene_binding_match])&& ...
    all([report.results.scene_fields_match]), ...
    'HF28:PairAudit','Locked scene-pair preflight failed or is stale; no Plant calls were made.');
runsRoot=char(java.io.File(char(release.output_root)).getCanonicalPath());
if ~isfolder(runsRoot),mkdir(runsRoot);end
lockPath=fullfile(runsRoot,'HF28_BATCH_RUNNING.lock');
lockFile=java.io.File(lockPath);
assert(lockFile.createNewFile(),'HF28:BatchLock','Another HF28 batch is active or a prior lock needs review.');
lockCleanup=onCleanup(@()delete_batch_lock(lockPath));
write_json(lockPath,struct('schema','DL1018_HF28_BATCH_LOCK_V1', ...
    'created_utc',utc_now(),'release_sha256',sha256_file(fullfile(studyRoot,'RELEASE.json'))));
ledgerPath=fullfile(runsRoot,'HF28_BATCH_LEDGER_v1.json');
ids=cellstr(string({manifest.scenes.scene_id}));
rows=repmat(struct('scene_id','','state','','Plant_calls',0,'attempt_dir',''),28,1);
for i=1:28
    id=ids{i};attemptDir=fullfile(runsRoot,id,'attempt_01');
    if isfolder(attemptDir)||isfile(attemptDir)
        statusPath=fullfile(attemptDir,'run_status.json');
        if isfile(statusPath)
            old=jsondecode(fileread(statusPath));rows(i).state=char(old.state);
            rows(i).Plant_calls=double(old.Plant_calls);
        else
            rows(i).state='INCOMPLETE_EXISTING_ATTEMPT_NO_RETRY';
        end
        rows(i).scene_id=id;rows(i).attempt_dir=attemptDir;
        ledger=make_ledger(rows,i,release,report);write_json(ledgerPath,ledger);continue;
    end
    freeBytes=java.io.File(studyRoot).getFreeSpace();
    if freeBytes<30*1024^3||directory_bytes(runsRoot)>=5*1024^3
        rows(i).scene_id=id;rows(i).state='RESOURCE_STOP_BEFORE_ATTEMPT';
        rows(i).attempt_dir=attemptDir;ledger=make_ledger(rows,i,release,report);
        ledger.resource_stop=true;write_json(ledgerPath,ledger);break;
    end
    try
        run_beta025_hf28_attempt(id);
        status=jsondecode(fileread(fullfile(attemptDir,'run_status.json')));
        rows(i).scene_id=id;rows(i).state=char(status.state);
        rows(i).Plant_calls=double(status.Plant_calls);rows(i).attempt_dir=attemptDir;
    catch ME
        rows(i).scene_id=id;rows(i).state='ABORTED_FATAL_PRECONDITION';
        rows(i).attempt_dir=attemptDir;
        ledger=make_ledger(rows,i,release,report);ledger.fatal_error=struct( ...
            'identifier',char(ME.identifier),'message',char(ME.message));
        write_json(ledgerPath,ledger);rethrow(ME);
    end
    ledger=make_ledger(rows,i,release,report);write_json(ledgerPath,ledger);
    assert(directory_bytes(runsRoot)<=5*1024^3,'HF28:OutputBudget', ...
        'Candidate output exceeded 5 GiB; batch stopped without deleting files.');
end
clear lockCleanup;
end
function ledger=make_ledger(rows,lastIndex,release,report)
ledger=struct('schema','DL1018_TASK_ATTITUDE_BLEND_BETA025_HF28_BATCH_LEDGER_V1', ...
    'updated_utc',utc_now(),'candidate',char(release.candidate), ...
    'planned_scenes',28,'processed_scenes',lastIndex, ...
    'authorized_Plant_calls',double(release.authorized_Plant_calls), ...
    'started_Plant_calls',numel(dir(fullfile(char(release.output_root),'**','attempt_started.marker'))), ...
    'pair_preflight_status',char(report.status),'pair_preflight_manifest_sha256',char(report.manifest_sha256), ...
    'TEST_read',false,'results',rows(1:lastIndex));
end
function n=directory_bytes(root)
if ~isfolder(root),n=0;return;end
files=dir(fullfile(root,'**','*'));files=files(~[files.isdir]);n=sum([files.bytes]);
end
function h=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'HF28:Read','Cannot hash %s.',path);
cleanup=onCleanup(@()fclose(fid));md=java.security.MessageDigest.getInstance('SHA-256');
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end;md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));clear cleanup;
end
function write_json(path,value)
fid=fopen(path,'w','n','UTF-8');assert(fid>=0,'HF28:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid));fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));clear cleanup;
end
function delete_batch_lock(lockPath)
lockFile=java.io.File(lockPath);if lockFile.isFile,lockFile.delete();end
end
function value=utc_now()
value=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end
