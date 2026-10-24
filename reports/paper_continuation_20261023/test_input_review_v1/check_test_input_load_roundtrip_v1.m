function out=check_test_input_load_roundtrip_v1()
% Read the single frozen input package; never generate scenes or invoke Plant.
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(fileparts(here)));
inputDir=fullfile(root,'experiments','c5_test48_v3','input');
reportDir=fullfile(root,'reports','paper_continuation_20261023','test_entry_v3');
outputPath=fullfile(here,'PARENT_TEST_INPUT_LOAD_ROUNDTRIP_v1.json');
assert(~isfile(outputPath),'Preserve earlier review');
idx=jsondecode(fileread(fullfile(inputDir,'TEST_INPUT_INDEX_v1.json')));
dev=jsondecode(fileread(fullfile(reportDir,'DEV_INPUT_EQUIVALENCE_RESULT_v1.json')));
pack=load(fullfile(inputDir,'TEST_SCENES_SHARED_v1.mat'));
snap=load(fullfile(inputDir,'TEST_METHOD_CFG_OPTS_v1.mat'));
assert(numel(pack.scenePacks)==48 && numel(snap.methodSnapshots)==6);
assert(isequal(pack.sceneSetSha,snap.sceneSetSha) && strcmp(pack.sceneSetSha,idx.scene_set_sha256));
assert(isequal(string(pack.sceneIds(:)),string(idx.scene_ids(:))));
assert(isequal(string(pack.sceneIds(:)),sort(string(pack.sceneIds(:)))));
sceneChecks=cell(48,1);
for k=1:48
    p=pack.scenePacks{k}; id=char(pack.sceneIds(k));
    assert(startsWith(id,'DL1018_TEST_') && strcmp(char(p.scene.scene_id),id));
    assert(strcmp(char(p.spec.scene_id),id));
    digest=sha_bytes(getByteStreamFromArray(p));
    assert(strcmp(digest,char(pack.digests{k})) && strcmp(digest,char(idx.scene_digests(k))));
    assert(numel(p.scene.time)==20001 && isequal(size(p.scene.initial_state),[12 1]));
    sceneChecks{k}=struct('scene_id',id,'serialized_pack_sha256',digest,'load_roundtrip_equal',true);
end
methodChecks=cell(6,1);
for k=1:6
    m=snap.methodSnapshots{k}; expected=dev.six_method_cfg_opts_model_preflight(k);
    assert(strcmp(m.method_id,expected.method_id));
    cfgSha=sha_bytes(getByteStreamFromArray(m.cfg));
    optsSha=sha_bytes(getByteStreamFromArray(m.opts));
    assert(strcmp(cfgSha,expected.cfg_value_sha256) && strcmp(optsSha,expected.opts_value_sha256));
    assert(isequaln(m.modelIdentity,expected.model_identity));
    methodChecks{k}=struct('method_id',m.method_id,'cfg_value_sha256',cfgSha, ...
        'opts_value_sha256',optsSha,'model_identity_matches_DEV_preflight',true);
end
out=struct('status','PASS_FROZEN_TEST48_LOAD_ROUNDTRIP_AND_SIX_CFG_OPTS', ...
    'scene_count',48,'scenes',{sceneChecks},'methods',{methodChecks}, ...
    'TEST_accessed',true,'TEST_outcomes_accessed',false,'Plant_calls',0, ...
    'training_steps',0,'scene_generation_calls',0);
fid=fopen(outputPath,'w'); assert(fid>=0); cleanup=onCleanup(@()fclose(fid));
fwrite(fid,[jsonencode(out) newline],'char');
end
function h=sha_bytes(bytes)
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(uint8(bytes(:)));
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
