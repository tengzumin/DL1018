function log=run_episode_dl1018(scene,method,cfg,opts,rawPath)
% Execute one accepted candidate's Plant episode and persist its raw evidence.
assert(isfield(scene,'scene_id')&&isfield(scene,'time')&& ...
    numel(scene.time)==20001&&abs(scene.time(end)-20)<1e-12, ...
    'DL1018:EpisodeScene','A formal episode must contain 20,001 state times over 20 seconds.');
runtimeDir=fileparts(mfilename('fullpath'));
addpath(runtimeDir,'-begin');rehash;clear run_dl1018_closed_loop
runtimeHandle=@run_dl1018_closed_loop;runtimeInfo=functions(runtimeHandle);
runtimePath=char(java.io.File(runtimeInfo.file).getCanonicalPath());
runtimeRoot=char(java.io.File(runtimeDir).getCanonicalPath());
assert(startsWith(runtimePath,runtimeRoot,'IgnoreCase',true), ...
    'D5:PathIsolation','Episode wrapper resolved %s outside %s.',runtimePath,runtimeRoot);
log=runtimeHandle(scene,'B2-RBF-Full-SPLIT',cfg,opts);
log.scene_id=char(scene.scene_id);log.collector=char(method);
if nargin>=5&&~isempty(rawPath)
    assert(~isfile(rawPath),'DL1018:RawOverwrite','Refusing to overwrite an existing raw episode.');
    folder=fileparts(rawPath);if ~isfolder(folder),mkdir(folder);end
    save(rawPath,'log','scene','method','-v7.3');
end
end
