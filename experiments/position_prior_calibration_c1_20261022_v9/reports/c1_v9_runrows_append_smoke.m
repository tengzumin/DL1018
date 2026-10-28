function result=c1_v9_runrows_append_smoke()
% No Plant: reproduce the empty-struct assignment error and verify v9 append.
row=struct('scene_id','DL1018_VAL_T2_C00_W10','condition','B','status','STABLE', ...
    'raw_sha256','abc','reused_prior_run',true,'actual_run_release','v8');
failedAsExpected=false;
try
    broken=struct([]); broken(end+1)=row; %#ok<NASGU>
catch ME
    failedAsExpected=strcmp(ME.identifier,'MATLAB:heterogeneousStrucAssignment');
end
assert(failedAsExpected,'C1:SmokeRootCause','MATLAB did not reproduce the original empty-struct append failure.');
rows=struct([]); rows=append_run_row(rows,row);
row.condition='ON1'; row.raw_sha256='def'; row.reused_prior_run=false; row.actual_run_release='v9';
rows=append_run_row(rows,row);
assert(numel(rows)==2&&isequal(fieldnames(rows),fieldnames(row))&& ...
    strcmp(rows(1).condition,'B')&&strcmp(rows(2).condition,'ON1')&& ...
    rows(1).reused_prior_run&&~rows(2).reused_prior_run, ...
    'C1:SmokeAppend','The v9 first and second append/schema check failed.');
result=struct('status','PASS_NO_PLANT','original_error_reproduced',failedAsExpected, ...
    'append_rows',numel(rows),'schema_field_count',numel(fieldnames(rows)), ...
    'conditions',{ {rows.condition} },'release_tags',{ {rows.actual_run_release} });
end
function rows=append_run_row(rows,row)
if isempty(rows), rows=row; else, rows(end+1)=row; end
end
