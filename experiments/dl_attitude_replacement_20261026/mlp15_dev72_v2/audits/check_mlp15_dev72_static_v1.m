here=fileparts(mfilename('fullpath'));studyRoot=fileparts(here);
runnerRoot=fullfile(studyRoot,'candidate_runner_work');
runtime=fullfile(runnerRoot,'matlab','runtime');
addpath(runtime);
resolvedRoot=activate_paired_runner();
assert(strcmpi(char(java.io.File(resolvedRoot).getCanonicalPath()), ...
    char(java.io.File(runnerRoot).getCanonicalPath())),'STATIC:Root','Unexpected runner root.');
files={fullfile(runtime,'gate_holdout_validate_dev72_scene.m'), ...
    fullfile(runtime,'prepare_mlp15_dev72_no_plant.m'), ...
    fullfile(runtime,'run_mlp15_dev72_attempt.m'), ...
    fullfile(runtime,'run_mlp15_dev72_closed_loop.m'), ...
    fullfile(here,'audit_mlp15_dev72_no_plant_v1.m')};
rows=repmat(struct('path','','count',0,'diagnostics',{{}}),numel(files),1);
for i=1:numel(files)
    d=checkcode(files{i},'-struct');
    rows(i).path=files{i};rows(i).count=numel(d);rows(i).diagnostics=d;
end
pilotRoot=fullfile(fileparts(studyRoot),'pilot_runner_mlp15_v2', ...
    'candidate_runner_work','matlab','runtime');
candidateD=checkcode(fullfile(runtime,'run_mlp15_dev72_closed_loop.m'),'-struct');
baselineD=checkcode(fullfile(pilotRoot,'run_gate_holdout_closed_loop.m'),'-struct');
report=struct('schema','DL1018_MLP15_DEV72_STATIC_AUDIT_V1','status','PASS', ...
    'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'isolated_root',resolvedRoot,'function_resolution',which('run_mlp15_dev72_closed_loop'), ...
    'changed_files',{rows},'closed_loop_candidate_diagnostic_count',numel(candidateD), ...
    'closed_loop_pilot_diagnostic_count',numel(baselineD), ...
    'closed_loop_diagnostic_messages_match',isequal(sort(extract_messages(candidateD)),sort(extract_messages(baselineD))));
report.status='PASS';
for i=1:numel(rows)
    if rows(i).count>0&&~strcmp(rows(i).path,fullfile(runtime,'run_mlp15_dev72_closed_loop.m'))
        report.status='FAIL';
    end
end
if numel(candidateD)~=numel(baselineD)||~report.closed_loop_diagnostic_messages_match,report.status='FAIL';end
out=fullfile(here,'MLP15_DEV72_STATIC_AUDIT_v1.json');
fid=fopen(out,'w');fwrite(fid,[jsonencode(report,'PrettyPrint',true) newline],'char');fclose(fid);
fprintf('MLP15_DEV72_STATIC_AUDIT=%s\n',out);
function messages=extract_messages(d)
if isempty(d),messages=strings(0,1);else,messages=string({d.message}).';end
end
