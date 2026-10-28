function receipt=run_cm18_export_v1(mode)
% Export frozen TRAIN/VAL CM18 event caches; default SCREEN4, explicit ALL816.
% Each scene MAT is flat and SciPy-readable; no raw files are copied.
if nargin<1||isempty(mode),mode='SCREEN4';end
mode=upper(char(string(mode)));
assert(ismember(mode,{'SCREEN4','ALL816'}),'CM18:Mode','Mode must be SCREEN4 or ALL816.');
experimentDir=fileparts(mfilename('fullpath'));
repoRoot=fileparts(fileparts(experimentDir));
reportDir=fullfile(repoRoot,'reports','attitude_cm18_a1_20261024','data_preparation_v1');
manifestPath=fullfile(reportDir,'INPUT_MANIFEST_v1.json');
assert(isfile(manifestPath),'CM18:ManifestMissing','Run the reviewed input-manifest preparation first.');
manifest=jsondecode(fileread(manifestPath));manifestSha=sha256_file(manifestPath);
assert(strcmp(manifest.schema,'ATTITUDE_CM18_A1_INPUT_MANIFEST_V1')&& ...
    manifest.scope.train_scenes==768&&manifest.scope.val_scenes==48&& ...
    ~manifest.scope.test_accessed&&~manifest.scope.raw_numeric_arrays_read&& ...
    ~manifest.scope.h5_numeric_arrays_read&&numel(manifest.scenes)==816, ...
    'CM18:ManifestScope','Input manifest schema or scope is invalid.');
assert(isequal(string(manifest.scope.splits(:)),["TRAIN";"VAL"]), ...
    'CM18:ManifestSplits','Manifest must contain only TRAIN and VAL.');

sourceRows=[manifest.reference_sources(:);manifest.new_sources(:)];
sourceVerified=repmat(struct('path','','sha256',''),numel(sourceRows),1);
for q=1:numel(sourceRows)
    p=locked_path(repoRoot,sourceRows(q).path);
    check_hash(p,sourceRows(q).sha256);
    sourceVerified(q)=struct('path',sourceRows(q).path,'sha256',sourceRows(q).sha256);
end
assert(any(strcmp({sourceRows.path},'experiments/attitude_cm18_a1_20261024/run_cm18_export_v1.m')), ...
    'CM18:RunnerNotLocked','Batch source is not recorded in the input manifest.');

scenes=manifest.scenes(:);
screenScenes=select_screen4(scenes);
if strcmp(mode,'SCREEN4')
    selected=screenScenes;
else
    selected=scenes;
end
assert(numel(selected)==(4*strcmp(mode,'SCREEN4')+816*strcmp(mode,'ALL816')), ...
    'CM18:SelectionCount','Unexpected scene selection count.');
assert(numel(unique(string({selected.scene_id})))==numel(selected), ...
    'CM18:DuplicateSelection','Selected scene IDs are not unique.');

screenRows=repmat(struct('scene_id','','split','','cache_path','','cache_sha256','', ...
    'cache_bytes',0,'qualified',false,'input_sha256',struct()),0,1);
screenRowsByScene=screenRows;
if strcmp(mode,'ALL816')
    screenManifestPath=fullfile(reportDir,'events_screen4_v1','DATASET_MANIFEST_v1.json');
    assert(isfile(screenManifestPath),'CM18:Screen4Required', ...
        'ALL816 requires a completed SCREEN4 dataset manifest.');
    screenManifest=jsondecode(fileread(screenManifestPath));
    assert(strcmp(screenManifest.schema,'CM18_A1_DATASET_MANIFEST_V1')&& ...
        strcmp(screenManifest.mode,'SCREEN4')&&strcmp(screenManifest.input_manifest_sha256,manifestSha)&& ...
        numel(screenManifest.rows)==4&&all([screenManifest.rows.qualified])&& ...
        all(strcmp({screenManifest.rows.status},'PASS')), ...
        'CM18:Screen4NotQualified','Existing SCREEN4 dataset must be the same manifest and all four qualified.');
    screenRows=screenManifest.rows(:);
    screenRowsByScene=screenRows;
    for q=1:numel(screenRowsByScene)
        expectedCachePath=make_relative(repoRoot,fullfile(reportDir,'events_screen4_v1', ...
            [screenRowsByScene(q).split,'_',screenRowsByScene(q).scene_id,'.mat']));
        assert(strcmp(screenRowsByScene(q).cache_path,expectedCachePath), ...
            'CM18:Screen4CachePath','SCREEN4 cache path is not canonical for scene %s.',screenRowsByScene(q).scene_id);
        cache=locked_path(repoRoot,screenRowsByScene(q).cache_path);
        assert(strcmpi(sha256_file(cache),screenRowsByScene(q).cache_sha256)&& ...
            dir(cache).bytes==screenRowsByScene(q).cache_bytes, ...
            'CM18:Screen4CacheChanged','SCREEN4 cache identity changed: %s',screenRowsByScene(q).scene_id);
    end
    assert(isequal(sort(string({screenRows.scene_id})),sort(string({screenScenes.scene_id}))), ...
        'CM18:Screen4Selection','SCREEN4 cache scenes do not match frozen selection.');
end

% Conservative estimate includes MAT overhead headroom; caches contain event arrays only.
eventCount=1999;bytesPerScene=2*eventCount*(18+3+1+1+1)*8+128*1024;
estimatedCacheBytes=bytesPerScene*numel(selected);cacheLimit=1024^3;
assert(estimatedCacheBytes<cacheLimit,'CM18:CacheBudget','Estimated event cache exceeds 1 GiB.');
if strcmp(mode,'SCREEN4'),outDir=fullfile(reportDir,'events_screen4_v1');
else,outDir=fullfile(reportDir,'events_all816_v1');end
assert(~isfolder(outDir)&&~isfile(outDir),'CM18:NoOverwrite','Output path already exists: %s',outDir);
[made,msg]=mkdir(outDir);assert(made,'CM18:OutputDirectory','Cannot create output directory: %s',msg);
coreDir=fullfile(repoRoot,'matlab','core');addpath(coreDir,'-begin');

rows=repmat(struct('scene_id','','split','','status','','qualified',false, ...
    'cache_path','','cache_sha256','','cache_bytes',0,'reused_screen4_cache',false, ...
    'input_sha256',struct(),'failure_identifier','','failure_message',''),numel(selected),1);
for q=1:numel(selected)
    item=selected(q);rows(q).scene_id=item.scene_id;rows(q).split=item.split;
    files=item.files(:);fileByRole=struct();
    for f=1:numel(files),fileByRole.(files(f).role)=files(f);end
    try
        assert(all(isfield(fileByRole,{'event_h5','raw_run','run_start'})), ...
            'CM18:InputRoles','Manifest input roles are incomplete.');
        h5Path=locked_path(repoRoot,fileByRole.event_h5.path);
        rawPath=locked_path(repoRoot,fileByRole.raw_run.path);
        startPath=locked_path(repoRoot,fileByRole.run_start.path);
        inputSha=struct('event_h5',verify_input(h5Path,fileByRole.event_h5), ...
            'raw_run',verify_input(rawPath,fileByRole.raw_run), ...
            'run_start',verify_input(startPath,fileByRole.run_start));
        rows(q).input_sha256=inputSha;

        reuseIdx=find(strcmp({screenRowsByScene.scene_id},item.scene_id));
        if strcmp(mode,'ALL816')&&~isempty(reuseIdx)
            assert(numel(reuseIdx)==1,'CM18:DuplicateScreenCache','Duplicate SCREEN4 scene cache.');
            reused=screenRowsByScene(reuseIdx);
            assert(strcmp(inputSha.event_h5,reused.input_sha256.event_h5)&& ...
                strcmp(inputSha.raw_run,reused.input_sha256.raw_run)&& ...
                strcmp(inputSha.run_start,reused.input_sha256.run_start), ...
                'CM18:Screen4InputChanged','SCREEN4 inputs differ from current locked inputs.');
            rows(q).cache_path=reused.cache_path;rows(q).cache_sha256=reused.cache_sha256;
            rows(q).cache_bytes=reused.cache_bytes;rows(q).qualified=true;
            rows(q).status='PASS';rows(q).reused_screen4_cache=true;
        else
            start=load(startPath,'runStart');
            assert(isfield(start,'runStart')&&all(isfield(start.runStart, ...
                {'cfg','run_id','collector_id','model_id','contract_version'})), ...
                'CM18:RunStart','run_start identity fields are incomplete.');
            runStart=start.runStart;
            assert(contains(char(string(runStart.run_id)),item.scene_id)&& ...
                strcmp(char(string(runStart.collector_id)),'B')&&strcmp(char(string(runStart.model_id)),'B')&& ...
                strcmp(char(string(runStart.contract_version)),'DL1018_V311_R2E_PAPER_FINAL')&& ...
                strcmpi(char(string(runStart.cfg.controller_morphology_mode)),'fixed')&& ...
                strcmpi(char(string(runStart.cfg.controller_inertia_derivative_mode)),'full'), ...
                'CM18:RunStartIdentity','run_start scene/collector/model/contract/config mismatch.');
            raw=load(rawPath,'log','scene');
            assert(all(isfield(raw,{'log','scene'})),'CM18:RawVariables','raw_run lacks log or scene.');

            h5ref=struct('scene_id',char(h5readatt(h5Path,'/','scene_id')), ...
                'split',char(h5readatt(h5Path,'/','split')), ...
                'model_id',char(h5readatt(h5Path,'/','model_id')), ...
                'contract_version',char(h5readatt(h5Path,'/','contract_version')), ...
                'plant_index',h5read(h5Path,'/plant_index'),'event_time_s',h5read(h5Path,'/event_time_s'), ...
                'phase_code',h5read(h5Path,'/phase_code'),'x',h5read(h5Path,'/x'), ...
                'target_raw',h5read(h5Path,'/target_raw'));
            assert(strcmp(h5ref.scene_id,item.scene_id)&&strcmpi(h5ref.split,item.split)&& ...
                strcmp(char(string(raw.scene.scene_id)),item.scene_id), ...
                'CM18:ManifestSceneIdentity','Manifest, H5, and raw scene identities differ.');
            [E,meta]=export_cm18_events_v1(raw.log,raw.scene,runStart.cfg,h5ref,item.split);

            % Flat cache contract: event rows align to plant_index 11:10:19991.
            X18=double(E.X18);target_raw=double(E.target_raw);
            event_time_s=double(E.event_time_s(:));phase_code=uint8(E.phase_code(:));
            plant_index=double(E.plant_index(:));scene_id=char(item.scene_id);split=char(item.split);
            input_identity=struct('input_manifest_sha256',manifestSha, ...
                'event_h5_path',fileByRole.event_h5.path,'event_h5_sha256',inputSha.event_h5, ...
                'event_h5_size_bytes',fileByRole.event_h5.size_bytes, ...
                'raw_run_path',fileByRole.raw_run.path,'raw_run_sha256',inputSha.raw_run, ...
                'raw_run_size_bytes',fileByRole.raw_run.size_bytes, ...
                'run_start_path',fileByRole.run_start.path,'run_start_sha256',inputSha.run_start, ...
                'run_start_size_bytes',fileByRole.run_start.size_bytes);
            export_meta=meta; %#ok<NASGU>
            assert(isequal(size(X18),[1999,18])&&isequal(size(target_raw),[1999,3])&& ...
                isequal(size(event_time_s),[1999,1])&&isequal(size(phase_code),[1999,1])&& ...
                isequal(size(plant_index),[1999,1])&&isequal(plant_index,(11:10:19991).'), ...
                'CM18:CacheShape','Flat cache dimensions or event identity are invalid.');
            eventPath=fullfile(outDir,[item.split,'_',item.scene_id,'.mat']);
            assert(~isfile(eventPath),'CM18:NoOverwrite','Cache path already exists: %s',eventPath);
            save(eventPath,'X18','target_raw','event_time_s','phase_code','plant_index', ...
                'scene_id','split','input_identity','export_meta','-v7');
            d=dir(eventPath);rows(q).cache_path=make_relative(repoRoot,eventPath);
            rows(q).cache_sha256=sha256_file(eventPath);rows(q).cache_bytes=d.bytes;
            rows(q).qualified=logical(meta.qualified);
            if meta.qualified,rows(q).status='PASS';else,rows(q).status='FAIL_CLOSURE';end
        end
    catch ME
        rows(q).status='FAIL_INPUT_OR_EXPORT';rows(q).qualified=false;
        rows(q).failure_identifier=ME.identifier;rows(q).failure_message=ME.message;
    end
    partial=struct('schema','CM18_A1_EXPORT_PROGRESS_V1','mode',mode, ...
        'completed_scenes',q,'total_selected_scenes',numel(selected), ...
        'rows',rows(1:q),'output_directory_bytes',directory_bytes(outDir), ...
        'estimated_unique_cache_bytes',estimatedCacheBytes,'cache_limit_bytes',cacheLimit,'TEST_accessed',false);
    write_json(fullfile(outDir,'PROGRESS_v1.json'),partial);
end

dataset=struct('schema','CM18_A1_DATASET_MANIFEST_V1','mode',mode, ...
    'input_manifest_path',make_relative(repoRoot,manifestPath),'input_manifest_sha256',manifestSha, ...
    'scene_count',numel(rows),'qualified_count',nnz([rows.qualified]), ...
    'failed_count',nnz(~[rows.qualified]),'unique_event_cache_bytes',sum([rows.cache_bytes]), ...
    'TEST_accessed',false,'raw_files_copied',false,'rows',rows);
write_json(fullfile(outDir,'DATASET_MANIFEST_v1.json'),dataset);

outputDirectoryBytes=directory_bytes(outDir);
uniqueCacheBytes=sum([rows.cache_bytes]);
for q=1:numel(sourceRows)
    p=locked_path(repoRoot,sourceRows(q).path);check_hash(p,sourceRows(q).sha256);
end
receipt=struct('schema','CM18_A1_EXPORT_RECEIPT_V1','status','PASS', ...
    'mode',mode,'selected_scene_count',numel(selected), ...
    'pass_count',nnz(strcmp({rows.status},'PASS')),'failed_count',nnz(~strcmp({rows.status},'PASS')), ...
    'input_manifest_path',make_relative(repoRoot,manifestPath),'input_manifest_sha256',manifestSha, ...
    'verified_sources',sourceVerified,'rows',rows,'output_directory_bytes',outputDirectoryBytes, ...
    'unique_event_cache_bytes',uniqueCacheBytes,'cache_limit_bytes',cacheLimit, ...
    'raw_files_copied',false,'runner_or_Plant_executed',false,'training_executed',false, ...
    'TEST_accessed',false);
if receipt.failed_count>0,receipt.status='COMPLETED_WITH_FAILURES';end
if uniqueCacheBytes>cacheLimit,receipt.status='CACHE_BUDGET_EXCEEDED';end
write_json(fullfile(outDir,'RECEIPT_v1.json'),receipt);
end

function selected=select_screen4(scenes)
selected=repmat(scenes(1),4,1);pos=0;
for split={'TRAIN','VAL'}
    for condition={'C00','C01'}
        ids=find(arrayfun(@(s)strcmp(s.split,split{1})&&contains(s.scene_id,['_',condition{1},'_']),scenes));
        assert(~isempty(ids),'CM18:ScreenSelection','Missing %s %s scene.',split{1},condition{1});
        [~,order]=sort(string({scenes(ids).scene_id}));
        pos=pos+1;selected(pos)=scenes(ids(order(1)));
    end
end
end

function p=locked_path(root,relative)
relative=char(relative);
assert(~isempty(relative)&&~startsWith(relative,'/')&&~startsWith(relative,'\\')&& ...
    ~contains(lower(relative),'/test/')&&~contains(relative,'..'), ...
    'CM18:UnsafePath','Manifest path is absolute, escapes, or references TEST.');
p=fullfile(root,strrep(relative,'/',filesep));
canonical=char(java.io.File(p).getCanonicalPath());rootCanonical=char(java.io.File(root).getCanonicalPath());
assert(startsWith(lower(canonical),[lower(rootCanonical),filesep])&&isfile(canonical), ...
    'CM18:MissingOrOutsidePath','Locked file is missing or outside repository: %s',relative);
p=canonical;
end

function digest=verify_input(path,record)
info=dir(path);assert(info.bytes==record.size_bytes,'CM18:InputSize','Locked input size changed: %s',path);
digest=sha256_file(path);
assert(strcmpi(digest,record.sha256),'CM18:InputHash','Locked input SHA changed: %s',path);
end

function check_hash(path,expected)
assert(numel(expected)==64&&strcmpi(sha256_file(path),expected), ...
    'CM18:SourceHash','Source SHA mismatch: %s',path);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'r');
assert(fid>=0,'CM18:Read','Cannot read %s.',path);c=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true,b=fread(fid,8*1024*1024,'*uint8');if isempty(b),break;end,md.update(typecast(b(:),'int8'));end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end

function rel=make_relative(root,path)
root=char(java.io.File(root).getCanonicalPath());path=char(java.io.File(path).getCanonicalPath());
assert(startsWith(lower(path),[lower(root),filesep]),'CM18:OutputPath','Output escaped repository.');
rel=strrep(path(numel(root)+2:end),filesep,'/');
end

function bytes=directory_bytes(path)
d=dir(fullfile(path,'**','*'));bytes=0;
for q=1:numel(d),if ~d(q).isdir,bytes=bytes+d(q).bytes;end,end
end

function write_json(path,value)
tmp=[path,'.tmp'];assert(~isfile(tmp),'CM18:TempExists','Temporary receipt exists: %s',tmp);
fid=fopen(tmp,'w');assert(fid>=0,'CM18:Write','Cannot write %s.',tmp);
fwrite(fid,jsonencode(value),'char');fwrite(fid,newline,'char');fclose(fid);
[ok,msg]=movefile(tmp,path,'f');assert(ok,'CM18:Write','Cannot publish %s: %s',path,msg);
end
