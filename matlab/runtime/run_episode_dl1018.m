function log=run_episode_dl1018(scene,method,cfg,opts,rawPath)
% Execute one accepted candidate's Plant episode and persist its raw evidence.
assert(isfield(scene,'scene_id')&&isfield(scene,'time')&& ...
    numel(scene.time)==20001&&abs(scene.time(end)-20)<1e-12, ...
    'DL1018:EpisodeScene','A formal episode must contain 20,001 state times over 20 seconds.');
log=run_dl1018_closed_loop(scene,'B2-RBF-Full-SPLIT',cfg,opts);
log.scene_id=char(scene.scene_id);log.collector=char(method);
if nargin>=5&&~isempty(rawPath)
    assert(~isfile(rawPath),'DL1018:RawOverwrite','Refusing to overwrite an existing raw episode.');
    folder=fileparts(rawPath);if ~isfolder(folder),mkdir(folder);end
    save(rawPath,'log','scene','method','-v7.3');
end
end
