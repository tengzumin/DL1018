function results=d5_run_all_training_candidates(root)
% Sequentially run every preflighted single-seed D4 candidate on BRIDGE6.
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','training_data_structure_compare_v2');
local=fullfile(out,'local_runtime');
families={'MIXED_KAN','TEACHER_KAN','DEEP_KAN','HISTORY_KAN','WIDE_MLP'};
results=cell(size(families));
for k=1:numel(families)
    addpath(genpath(local),'-begin');rehash;
    fprintf('D5 starting frozen BRIDGE6 for %s (%d/%d)\n',families{k},k,numel(families));
    results{k}=d5_run_training_candidate_bridge6(root,families{k});
end
summary=struct('status','CANDIDATE_RUNS_COMPLETE','families',{families},'results',{results}, ...
    'new_plant_starts',sum(cellfun(@(x)double(x.new_plant_starts),results)), ...
    'started_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
fid=fopen(fullfile(out,'reports','D5_BRIDGE6_ALL_RESULTS.json'),'w');
fwrite(fid,jsonencode(summary,'PrettyPrint',true),'char');fclose(fid);
s=jsondecode(fileread(fullfile(out,'state','state.json')));
s.phase='D5_CANARY_ANALYSIS';s.status='IN_PROGRESS';s.active_candidate='';s.active_run_id='';
s.next='D5_COMPARE_BRIDGE6_AND_DECIDE_DEV';
s.new_plant_starts=summary.new_plant_starts;
s.updated_at_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
fid=fopen(fullfile(out,'state','state.json'),'w');fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');fclose(fid);
fprintf('D5 all candidates complete: %d new Plant starts across %d candidate models.\n', ...
    summary.new_plant_starts,numel(families));
end
