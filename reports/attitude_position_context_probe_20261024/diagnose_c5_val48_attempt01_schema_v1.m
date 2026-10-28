function report = diagnose_c5_val48_attempt01_schema_v1()
% Read-only schema/stack diagnostic for representative failed VAL48 rows.
% It does not call the exporter, engine, episode, Plant, trainer, or TEST.
scriptPath=[mfilename('fullpath') '.m']; reportDir=fileparts(scriptPath);
repoRoot=fileparts(fileparts(reportDir));
candidatePath=fullfile(reportDir,'C5_MATCHED_VAL_REUSE_CANDIDATES_v1.json');
auditPath=fullfile(repoRoot,'reports','attitude_position_context_probe_20261024', ...
    'certify_and_export_c5_val48_v1.m');
receiptPath=fullfile(repoRoot,'reports','attitude_cm18_datarepair_20261024', ...
    'c5_val48_c5_teacher_v1','C5_VAL48_EVENT_CACHE_MANIFEST_v1.json');
parentPath=fullfile(repoRoot,'reports','paper_continuation_20261023', ...
    'c5_dev72_parent_review','C5_DEV72_RAW_PARENT_REVIEW_v3.json');
screenPath=fullfile(repoRoot,'reports','paper_continuation_20261023', ...
    'c5_axis_coordinate_parent_review','screen12_parent_review','SUMMARY.json');
outPath=fullfile(reportDir,'ROOT_VAL48_ATTEMPT01_SCHEMA_DIAGNOSTIC_v1.json');
assert(~isfile(outPath),'ROOT:Val48DiagnosticExists','Refusing to overwrite diagnostic output.');
M=jsondecode(fileread(candidatePath)); R=jsondecode(fileread(receiptPath));
P=jsondecode(fileread(parentPath)); S=jsondecode(fileread(screenPath));
ids={'DL1018_VAL_T1_C01_W08','DL1018_VAL_T1_C00_W07','DL1018_VAL_T2_C00_W10'};
cases=repmat(struct('scene_id','','reused',false,'raw_path','','run_start_path','', ...
    'run_status_path','','run_status_class','','run_status_fields',{{}}, ...
    'run_status_missing_physical_B_source_sha256',false,'run_start_class','', ...
    'run_start_fields',{{}},'run_start_source_schema_fields',{{}}, ...
    'rbf_event_count',NaN,'weight_before_h5_size',[],'rbf_event_audit_time_h5_size',[], ...
    'parent_rows_class','', ...
    'parent_rows_size',[],'parent_row_class','MISSING','parent_row_fields',{{}}, ...
    'parent_c5_metrics_class','MISSING','parent_lookup_error','','parent_lookup_stack',{{}}),3,1);
for k=1:3
    i=find(strcmp({M.scenes.scene_id},ids{k}),1); row=M.scenes(i); c=row.C5_candidate;
    cases(k).scene_id=ids{k}; cases(k).reused=logical(c.reused);
    cases(k).raw_path=char(c.raw_path); cases(k).run_start_path=char(c.run_start_path);
    cases(k).run_status_path=char(c.run_status_path);
    st=jsondecode(fileread(cases(k).run_status_path));
    cases(k).run_status_class=class(st); cases(k).run_status_fields=fieldnames(st);
    cases(k).run_status_missing_physical_B_source_sha256=~isfield(st,'physical_B_source_sha256');
    q=load(cases(k).run_start_path,'runStart'); z=q.runStart;
    cases(k).run_start_class=class(z); cases(k).run_start_fields=fieldnames(z);
    if isfield(z,'source_identity')&&isstruct(z.source_identity)
        cases(k).run_start_source_schema_fields=fieldnames(z.source_identity);
    elseif isfield(z,'source_paths')
        cases(k).run_start_source_schema_fields={'source_paths','source_sha256'};
    end
    rows=P.rows;
    if cases(k).reused, rows=S.audits; end
    cases(k).parent_rows_class=class(rows); cases(k).parent_rows_size=size(rows);
    try
        rowIds=arrayfun(@(x)char(x.scene_id),rows,'UniformOutput',false);
        idx=find(strcmp(rowIds,ids{k}));
        assert(isscalar(idx),'ROOT:Val48DiagnosticParentIndex','Expected one parent row.');
        pr=rows(idx); cases(k).parent_row_class=class(pr);
        cases(k).parent_row_fields=fieldnames(pr);
        if isfield(pr,'C5_metrics')
            cases(k).parent_c5_metrics_class=class(pr.C5_metrics);
        end
        % Reproduce the pinned v1 find_parent_audit field access to capture its actual stack.
        if isfield(pr,'C5_metrics')
            tmp=char(pr.C5_metrics.sha256); %#ok<NASGU>
            tmp=char(pr.C5_metrics.path); %#ok<NASGU>
        elseif isfield(pr,'raw_sha256')
            tmp=char(pr.raw_sha256); %#ok<NASGU>
            if isfield(pr,'raw_path'), tmp=char(pr.raw_path); end %#ok<NASGU>
        end
    catch ME
        cases(k).parent_lookup_error=[ME.identifier ': ' ME.message];
        if ~isempty(ME.stack)
            cases(k).parent_lookup_stack=arrayfun(@(x)sprintf('%s:%d',x.name,x.line), ...
                ME.stack,'UniformOutput',false);
        end
    end
    % Event audit shape/time are metadata-only and show the initial-weight field convention.
    rawInfo=h5info(cases(k).raw_path,'/log/rbf_event_audit');
    names={rawInfo.Datasets.Name};
    timeDataset=rawInfo.Datasets(strcmp(names,'time'));
    weightDataset=rawInfo.Datasets(strcmp(names,'weight_before'));
    eventCount=h5read(cases(k).raw_path,'/log/rbf_event_count');
    cases(k).rbf_event_count=double(eventCount);
    cases(k).weight_before_h5_size=double(weightDataset.Dataspace.Size);
    cases(k).rbf_event_audit_time_h5_size=double(timeDataset.Dataspace.Size);
end
report=struct('schema','ROOT_C5_VAL48_ATTEMPT01_SCHEMA_DIAGNOSTIC_V1', ...
    'scope','Three representative raw/start/status metadata and exact parent lookup expressions only; no Plant.', ...
    'audit_source_path',auditPath,'audit_source_sha256',sha256_file(auditPath), ...
    'failed_receipt_path',receiptPath,'failed_receipt_sha256',sha256_file(receiptPath), ...
    'parent_audit_path',parentPath,'parent_audit_sha256',sha256_file(parentPath), ...
    'screen12_summary_path',screenPath,'screen12_summary_sha256',sha256_file(screenPath), ...
    'cases',cases);
write_json_no_overwrite(outPath,report); disp(jsonencode(report,'PrettyPrint',true));
end

function sha=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'rb');
assert(fid>=0); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,1024*1024,'*uint8'); if isempty(b), break; end
    md.update(typecast(b,'int8'));
end
sha=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json_no_overwrite(path,value)
assert(~isfile(path)); f=fopen(path,'w','n','UTF-8'); assert(f>=0);
c=onCleanup(@()fclose(f)); %#ok<NASGU>
fwrite(f,jsonencode(value,'PrettyPrint',true),'char');
end
