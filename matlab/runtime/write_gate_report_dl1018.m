function write_gate_report_dl1018(path,report)
% Persist a single machine-readable Gate result.
assert(isstruct(report)&&isfield(report,'gate_id')&&isfield(report,'status'), ...
    'DL1018:GateReport','A Gate report requires gate_id and status.');
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
temporary=[path '.tmp'];fid=fopen(temporary,'w');
assert(fid>=0,'DL1018:GateReportOpen','Could not create Gate report.');
cleanup=onCleanup(@() fclose(fid));
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fwrite(fid,newline,'char');
clear cleanup;movefile(temporary,path,'f');
end
