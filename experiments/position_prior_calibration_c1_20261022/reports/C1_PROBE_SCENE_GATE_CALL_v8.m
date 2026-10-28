% No-Plant smoke: call the actual local valid_scene in run_c1_screen.m.
reportDir=fileparts(mfilename('fullpath')); c1Dir=fileparts(reportDir); repoRoot=fileparts(fileparts(c1Dir));
addpath(c1Dir,'-begin'); runnerPath=fullfile(c1Dir,'run_c1_screen.m'); gate=str2func('run_c1_screen>valid_scene');
lock=jsondecode(fileread(fullfile(c1Dir,'C1_SOURCE_LOCK_v2.json'))); r2=jsondecode(fileread(lock.r2_lock.path));
manifest=readtable(r2.reuse_manifest.path,'TextType','string','VariableNamingRule','preserve'); sceneIds=string({r2.scenes.scene_id}).';
rows=repmat(struct('scene_id','','raw_path','','expected_sha256','','sha_before','','sha_after','','scene_id_raw','','runner_gate_pass',false,'raw_identity_pass',false),numel(sceneIds),1);
for i=1:numel(sceneIds)
    sid=sceneIds(i); rowIndex=manifest.scene_id==sid & manifest.role=="B_BASELINE"; assert(nnz(rowIndex)==1);
    rawPath=char(manifest.raw_path(rowIndex)); expected=char(manifest.raw_sha256(rowIndex)); d0=dir(rawPath); h0=sha256_file(rawPath);
    loaded=load(rawPath,'scene'); d1=dir(rawPath); h1=sha256_file(rawPath); s=loaded.scene;
    gatePass=logical(feval(gate,s,char(sid))); stable=d0.bytes==d1.bytes&&d0.datenum==d1.datenum&&strcmpi(h0,expected)&&strcmpi(h1,expected);
    rows(i)=struct('scene_id',char(sid),'raw_path',rawPath,'expected_sha256',expected,'sha_before',h0,'sha_after',h1, ...
      'scene_id_raw',char(s.scene_id),'runner_gate_pass',gatePass,'raw_identity_pass',stable);
    fprintf('%s actual_runner_gate=%d raw_identity=%d\n',char(sid),gatePass,stable);
end
out=fullfile(reportDir,'C1_PROBE_SCENE_GATE_CALL_v8.json'); assert(~isfile(out),'C1Gate:NoOverwrite','Refuse overwrite.');
summary=struct('status',ternary(all([rows.runner_gate_pass])&&all([rows.raw_identity_pass]),'PASS_ALL_12_ACTUAL_RUNNER_GATE','FAIL'),'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')),'runner_sha256',sha256_file(runnerPath),'source_lock_sha256',sha256_file(fullfile(c1Dir,'C1_SOURCE_LOCK_v2.json')),'scene_count',numel(rows),'plant_called',false,'rows',rows);
write_json(out,summary); fprintf('WROTE %s %s\n',out,summary.status);
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0); cleanup=onCleanup(@()fclose(fid));
while true, b=fread(fid,1024*1024,'*uint8'); if isempty(b), break; end; md.update(typecast(b(:),'int8')); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json(path,value)
fid=fopen(path,'w','n','UTF-8'); assert(fid>=0); cleanup=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(value),'char');
end
function out=ternary(c,a,b)
if c,out=a;else,out=b;end
end
