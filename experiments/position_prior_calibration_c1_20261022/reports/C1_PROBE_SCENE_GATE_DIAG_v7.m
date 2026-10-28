% Read-only inspection of the frozen B raw scenes; no controller/Plant is called.
reportDir=fileparts(mfilename('fullpath')); c1Dir=fileparts(reportDir); repoRoot=fileparts(fileparts(c1Dir));
lock=jsondecode(fileread(fullfile(c1Dir,'C1_SOURCE_LOCK_v2.json')));
r2=jsondecode(fileread(lock.r2_lock.path)); manifest=readtable(r2.reuse_manifest.path,'TextType','string','VariableNamingRule','preserve');
sceneIds=string({r2.scenes.scene_id}).'; N=20001;
paths={'time','environment_wind_I','reference.position','reference.velocity','reference.acceleration','reference.yaw','reference.yaw_rate','reference.yaw_acceleration','initial_state','arms.command','arms.rhoDot_hat','arms.rhoDot_true','arms.rho_hat','arms.rho_true'};
expected={[N,1],[N,3],[N,3],[N,3],[N,3],[N,1],[N,1],[N,1],[],[N,4],[N,4],[N,4],[N,4],[N,4]};
emptyField=struct('path','','class','','size',[],'numel',0,'finite',false,'shape_ok',false);
rows=repmat(struct('scene_id','','raw_path','','expected_raw_sha256','','raw_sha256_before','','raw_sha256_after','','raw_bytes_before',0,'raw_bytes_after',0,'raw_datenum_unchanged',false,'scene_id_raw','','scene_id_ok',false,'time_start',NaN,'time_end',NaN,'field_checks',repmat(emptyField,0,1),'all_fields_finite',false,'all_expected_shapes',false,'valid_under_matlab_runtime_contract',false),numel(sceneIds),1);
for i=1:numel(sceneIds)
    sid=sceneIds(i); match=manifest(manifest.scene_id==sid & manifest.role=="B_BASELINE",:);
    assert(height(match)==1,'C1Diag:Manifest','Expected exactly one frozen B row for %s.',sid);
    rawPath=char(match.raw_path); expectedSha=char(match.raw_sha256);
    d0=dir(rawPath); sha0=sha256_file(rawPath); loaded=load(rawPath,'scene');
    d1=dir(rawPath); sha1=sha256_file(rawPath); s=loaded.scene;
    row=struct('scene_id',char(sid),'raw_path',rawPath,'expected_raw_sha256',expectedSha,'raw_sha256_before',sha0,'raw_sha256_after',sha1, ...
      'raw_bytes_before',double(d0.bytes),'raw_bytes_after',double(d1.bytes),'raw_datenum_unchanged',d0.datenum==d1.datenum, ...
      'scene_id_raw','','scene_id_ok',false,'time_start',NaN,'time_end',NaN,'field_checks',repmat(emptyField,numel(paths),1), ...
      'all_fields_finite',false,'all_expected_shapes',false,'valid_under_matlab_runtime_contract',false);
    if isstruct(s)&&isfield(s,'scene_id'), row.scene_id_raw=char(s.scene_id); row.scene_id_ok=strcmp(row.scene_id_raw,char(sid))||strcmp(row.scene_id_raw,[char(sid) '_ACC_FIX_V1']); end
    finiteAll=true; shapeAll=true;
    for j=1:numel(paths)
        p=paths{j}; v=[]; present=true;
        try
            if strcmp(p,'time')||strcmp(p,'environment_wind_I')||strcmp(p,'initial_state'), v=s.(p);
            elseif startsWith(p,'reference.'), v=s.reference.(p(11:end));
            elseif startsWith(p,'arms.'), v=s.arms.(p(6:end));
            else, present=false;
            end
        catch, present=false;
        end
        if present
            dims=size(v); isFinite=(isnumeric(v)||islogical(v))&&all(~isnan(double(v(:)))&~isinf(double(v(:))));
            if strcmp(p,'time'), shapeOk=numel(v)==N; elseif strcmp(p,'initial_state'), shapeOk=numel(v)==12; else, shapeOk=isequal(dims,expected{j}); end
            row.field_checks(j)=struct('path',p,'class',class(v),'size',double(dims),'numel',numel(v),'finite',logical(isFinite),'shape_ok',logical(shapeOk));
        else
            row.field_checks(j)=struct('path',p,'class','<missing>','size',[],'numel',0,'finite',false,'shape_ok',false);
        end
        finiteAll=finiteAll&&row.field_checks(j).finite; shapeAll=shapeAll&&row.field_checks(j).shape_ok;
    end
    if isfield(s,'time')&&numel(s.time)==N, row.time_start=double(s.time(1)); row.time_end=double(s.time(end)); end
    identityOk=strcmpi(sha0,expectedSha)&&strcmpi(sha1,expectedSha)&&d0.bytes==d1.bytes&&d0.datenum==d1.datenum;
    timeOk=isfinite(row.time_start)&&isfinite(row.time_end)&&abs(row.time_start)<=1e-12&&abs(row.time_end-20)<=1e-12;
    row.all_fields_finite=finiteAll; row.all_expected_shapes=shapeAll;
    row.valid_under_matlab_runtime_contract=identityOk&&row.scene_id_ok&&finiteAll&&shapeAll&&timeOk;
    rows(i)=row; fprintf('%s valid=%d scene_id=%s all_shapes=%d all_finite=%d t=[%.17g,%.17g]\n',row.scene_id,row.valid_under_matlab_runtime_contract,row.scene_id_raw,shapeAll,finiteAll,row.time_start,row.time_end);
end
summary=struct('status',ternary(all([rows.valid_under_matlab_runtime_contract]),'PASS_ALL_12','FAIL_ONE_OR_MORE'),'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')),'source_lock_sha256',sha256_file(fullfile(c1Dir,'C1_SOURCE_LOCK_v2.json')),'release_sha256',sha256_file(fullfile(c1Dir,'C1_RELEASE_v7.json')),'runtime_reference',r2.runtimeFiles(1).path,'scene_count',numel(rows),'plant_called',false,'source_raw_modified',false,'rows',rows);
out=fullfile(reportDir,'C1_PROBE_SCENE_GATE_DIAG_v7.json'); assert(~isfile(out),'C1Diag:NoOverwrite','Refuse overwrite: %s',out); write_json(out,summary); fprintf('WROTE %s status=%s\n',out,summary.status);
function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r'); assert(fid>=0); c=onCleanup(@()fclose(fid));
while true, b=fread(fid,1024*1024,'*uint8'); if isempty(b), break; end; md.update(typecast(b(:),'int8')); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
function write_json(path,value)
fid=fopen(path,'w','n','UTF-8'); assert(fid>=0); c=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(value),'char');
end
function out=ternary(c,a,b)
if c,out=a;else,out=b;end
end
