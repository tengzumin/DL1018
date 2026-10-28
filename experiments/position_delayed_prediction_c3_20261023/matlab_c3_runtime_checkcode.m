root=fileparts(mfilename('fullpath'));
candidate=fullfile(root,'run_dl1018_closed_loop.m');
issues=checkcode(candidate,'-id');
result=struct('status','MATLAB_NO_PLANT_RUNTIME_CHECKCODE','file',candidate, ...
    'sha256','','message_count',numel(issues),'messages',issues);
fid=fopen(fullfile(root,'runtime_checkcode.json'),'w');
fwrite(fid,jsonencode(result),'char');
fclose(fid);
disp(jsonencode(struct('status',result.status,'message_count',result.message_count)));
