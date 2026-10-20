function report=raw_sample_parity(root)
% Re-export one accepted teacher episode per task and teacher role; Plant=0.
if nargin<1||isempty(root),root=pwd;end
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','teacher_reuse_model_screen_v1');
addpath(genpath(fullfile(root,'matlab')));
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'TEACHER:Root','Unexpected project root.');
M=readtable(fullfile(out,'manifests','teacher_reuse_manifest.csv'),'TextType','string');
tasks=["HELIX","FIG8_3D","SQUARE"];roles=["B","POS_OFF"];rows=struct([]);
for ti=1:numel(tasks)
    for ri=1:numel(roles)
        q=M(M.split=="train"&M.task==tasks(ti)&M.role==roles(ri),:);
        assert(height(q)>0,'TEACHER:Sample','No accepted teacher sample for %s/%s.',tasks(ti),roles(ri));
        q=sortrows(q,'scene_id');q=q(1,:);rawPath=fullfile(root,strrep(char(q.raw_path),'/',filesep));
        eventPath=fullfile(root,strrep(char(q.position_event_path),'/',filesep));
        src=load(rawPath,'log','scene');
        [E,meta]=export_position_events_dl1018(src.log,src.scene,cfg,char(q.role),char(upper(q.split)),q);
        xReplay=zeros(height(E),14);
        for j=1:14,xReplay(:,j)=double(E.(sprintf('x14_%d',j)));end
        yReplay=[double(E.target_raw_1),double(E.target_raw_2),double(E.target_raw_3)];
        yClipReplay=[double(E.target_clip_1),double(E.target_clip_2),double(E.target_clip_3)];
        xStored=read_event_matrix(eventPath,'/x14',14,height(E));
        yStored=read_event_matrix(eventPath,'/target_raw',3,height(E));
        yClipStored=read_event_matrix(eventPath,'/target_clip',3,height(E));
        timeStored=double(h5read(eventPath,'/event_time_s'));timeStored=timeStored(:);
        plantStored=double(h5read(eventPath,'/plant_index'));plantStored=plantStored(:);
        readyStored=logical(h5read(eventPath,'/ready'));readyStored=readyStored(:);
        timeReplay=double(E.event_time_s);plantReplay=double(E.plant_index);readyReplay=logical(E.ready);
        r=struct('scene_id',char(q.scene_id),'task',char(q.task),'role',char(q.role), ...
            'x14_max_abs',max(abs(xReplay-xStored),[],'all'), ...
            'target_raw_max_abs_mps2',max(abs(yReplay-yStored),[],'all'), ...
            'target_clip_max_abs_mps2',max(abs(yClipReplay-yClipStored),[],'all'), ...
            'event_time_max_abs_s',max(abs(timeReplay-timeStored)), ...
            'plant_index_max_abs',max(abs(plantReplay-plantStored)), ...
            'ready_mismatch_count',nnz(readyReplay~=readyStored), ...
            'label_closure_max_abs_mps2',double(meta.max_label_closure_mps2), ...
            'plant_starts',0,'raw_file',char(q.raw_path),'event_file',char(q.position_event_path));
        rows=[rows;r]; %#ok<AGROW>
    end
end
pass=all(arrayfun(@(x)x.x14_max_abs<=1e-12&&x.target_raw_max_abs_mps2<=1e-12&& ...
    x.target_clip_max_abs_mps2<=1e-12&&x.event_time_max_abs_s<=1e-12&& ...
    x.plant_index_max_abs==0&&x.ready_mismatch_count==0&&x.label_closure_max_abs_mps2<=1e-9,rows));
report=struct('status',iff(pass,'PASS_SIX_RAW_REEXPORT_PARITY','FAIL_SIX_RAW_REEXPORT_PARITY'), ...
    'sample_count',numel(rows),'task_role_coverage','one B and one POS_OFF per task', ...
    'plant_starts',0,'rows',rows,'method','load accepted raw MAT; re-run the canonical event exporter; compare X14, target, event clock and readiness against accepted H5');
f=fopen(fullfile(out,'reports','raw_sample_parity.json'),'w');assert(f>0,'TEACHER:Write','Cannot write parity report.');
fwrite(f,jsonencode(report,'PrettyPrint',true),'char');fclose(f);
fprintf('RAW_SAMPLE_PARITY %s: %d samples, Plant=0.\n',report.status,numel(rows));
assert(pass,'TEACHER:RawParity','Raw MAT to accepted H5 re-export parity did not pass.');
end

function X=read_event_matrix(path,key,width,n)
X=double(h5read(path,key));
if isequal(size(X),[width,n]),X=X.';end
assert(isequal(size(X),[n,width]),'TEACHER:H5Shape','Unexpected H5 matrix dimensions at %s.',key);
end

function y=iff(c,a,b),if c,y=a;else,y=b;end,end
