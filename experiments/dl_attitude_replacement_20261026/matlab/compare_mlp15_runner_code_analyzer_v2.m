function report=compare_mlp15_runner_code_analyzer_v2()
% Compare analyzer diagnostics in the edited simulator against its frozen v4 base.
researchRoot=fileparts(fileparts(mfilename('fullpath')));
base=fullfile(researchRoot,'pilot_runner_v4_teacher_distill', ...
    'candidate_runner_work','matlab','runtime','run_gate_holdout_closed_loop.m');
candidate=fullfile(researchRoot,'pilot_runner_mlp15_v2', ...
    'candidate_runner_work','matlab','runtime','run_gate_holdout_closed_loop.m');
a=checkcode(base,'-id');b=checkcode(candidate,'-id');
baseIds=string({a.id});candidateIds=string({b.id});
ids=unique([baseIds(:);candidateIds(:)]);
baseCounts=zeros(numel(ids),1);candidateCounts=baseCounts;
for i=1:numel(ids)
    baseCounts(i)=sum(baseIds==ids(i));
    candidateCounts(i)=sum(candidateIds==ids(i));
end
newCounts=max(candidateCounts-baseCounts,0);
report=struct('schema','DL1018_MLP15_RUNNER_CODE_ANALYZER_COMPARISON_V2', ...
    'status','PASS_NO_NEW_DIAGNOSTIC_IDS_OR_COUNTS', ...
    'base_file',base,'candidate_file',candidate, ...
    'base_diagnostic_count',numel(a),'candidate_diagnostic_count',numel(b), ...
    'diagnostic_ids',{cellstr(ids)},'base_counts',baseCounts.', ...
    'candidate_counts',candidateCounts.','new_count_by_id',newCounts.', ...
    'no_new_diagnostics',all(newCounts==0),'plant_invoked',false,'test_data_read',false);
assert(report.no_new_diagnostics,'DLMLP15:NewAnalyzerDiagnostic', ...
    'MLP15 simulator introduced MATLAB Code Analyzer diagnostics.');
out=fullfile(researchRoot,'MLP15_RUNNER_CODE_ANALYZER_COMPARISON_v2.json');
assert(~isfile(out),'DLMLP15:NoOverwrite','Code analyzer report already exists.');
fid=fopen(out,'w');assert(fid>=0,'DLMLP15:AnalyzerReport','Cannot write analyzer report.');
closer=onCleanup(@()fclose(fid));fwrite(fid,[jsonencode(report,'PrettyPrint',true) newline],'char');clear closer;
end
