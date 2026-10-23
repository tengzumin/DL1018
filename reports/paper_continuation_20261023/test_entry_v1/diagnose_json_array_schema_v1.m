function out=diagnose_json_array_schema_v1()
% Read-only inspection of source JSON types; no scene generation or Plant.
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(fileparts(here)));
cp=fullfile(root,'experiments','c5_test48_v1','TEST48_RUN_CONTRACT_v1.json');
mp=fullfile(here,'TEST_METHOD_SOURCE_MANIFEST_v1.json');
c=jsondecode(fileread(cp)); m=jsondecode(fileread(mp));
out=struct('contract_method_order_class',class(c.method_order), ...
    'contract_method_order_size',size(c.method_order),'manifest_methods_class',class(m.methods), ...
    'manifest_methods_size',size(m.methods),'TEST_accessed',false,'Plant_calls',0);
out.contract_method_fieldnames=cell(6,1);
for k=1:6
    if iscell(c.method_order), v=c.method_order{k}; else, v=c.method_order(k); end
    out.contract_method_fieldnames{k}=fieldnames(v);
end
path=fullfile(here,'ACTUAL_JSON_ARRAY_SCHEMA_DIAGNOSIS_v1.json');
assert(~isfile(path),'Preserve original diagnostic result');
fid=fopen(path,'w'); assert(fid>=0); cleanup=onCleanup(@()fclose(fid));
fwrite(fid,[jsonencode(out) newline],'char');
end
