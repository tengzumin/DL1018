function result = check_c524_matlab_parity_v1()
% Check exported final checkpoints against the frozen MATLAB CM18 inference.
here=fileparts(mfilename('fullpath')); root=fileparts(fileparts(here));
modelDir=fullfile(here,'models');
helper=fullfile(root,'experiments','attitude_cm18_a1_20261024','matlab','cm18_a1_forward_v1.m');
fixturePath=fullfile(modelDir,'matlab_parity_fixture.mat');
outputDir=fullfile(root,'reports','attitude_cm18_c524_screen12_20261025','parity');
outputPath=fullfile(outputDir,'CM18_B24_C524_MATLAB_PARITY_v1.json');
assert(isfile(helper)&&isfile(fixturePath)&&isfolder(outputDir)&&~isfile(outputPath), ...
    'C524Parity:Paths','Pinned helper/fixture is absent or output already exists.');
addpath(fileparts(helper),'-begin'); clear cm18_a1_forward_v1; rehash;
assert(strcmpi(which('cm18_a1_forward_v1'),helper),'C524Parity:HelperPath','Wrong CM18 helper resolved.');
f=load(fixturePath,'X18','B24_expected','C5_24_expected');
assert(isequal(size(f.X18),[64,18])&&all(isfinite(f.X18),'all'), ...
    'C524Parity:Fixture','Malformed fixed parity inputs.');
branches={'B24','C5_24'};
rows=repmat(struct('branch','','rows',0,'max_abs_delta_rad_s2',0, ...
    'zero_basis_exact',false,'model_sha256',''),1,numel(branches));
for k=1:numel(branches)
    branch=branches{k}; pack=load(fullfile(modelDir,[branch '_model.mat']),'model');
    assert(isfield(pack,'model'),'C524Parity:Model','MATLAB model struct is missing.');
    expected=f.([branch '_expected']); actual=zeros(size(expected));
    for q=1:size(f.X18,1), actual(q,:)=cm18_a1_forward_v1(f.X18(q,:),pack.model); end
    delta=max(abs(actual(:)-expected(:)));
    assert(delta<=1e-10&&isequal(actual(1,:),[0,0,0]), ...
        'C524Parity:Numerics','MATLAB/Python parity or exact zero-basis check failed for %s.',branch);
    rows(k)=struct('branch',branch,'rows',size(actual,1),'max_abs_delta_rad_s2',delta, ...
        'zero_basis_exact',true,'model_sha256',sha256_file(fullfile(modelDir,[branch '_model.mat'])));
end
result=struct('schema','CM18_B24_C524_MATLAB_PARITY_V1','status','PASS', ...
    'scope','MATLAB pure inference only; no Plant, optimizer, or TEST', ...
    'helper_path',helper,'helper_sha256',sha256_file(helper), ...
    'fixture_path',fixturePath,'fixture_sha256',sha256_file(fixturePath), ...
    'row_count',64,'branches',rows,'created_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')));
assert(~isfile(outputPath),'C524Parity:OutputExists','Parity report already exists.');
fid=fopen(outputPath,'w'); assert(fid>=0,'C524Parity:Output','Cannot create parity report.');
closer=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,[jsonencode(result) newline],'char');
fprintf('MATLAB_CM18_PARITY=PASS; max_delta_B24=%.3g; max_delta_C5_24=%.3g\n', ...
    rows(1).max_abs_delta_rad_s2,rows(2).max_abs_delta_rad_s2);
end

function h=sha256_file(path)
md=java.security.MessageDigest.getInstance('SHA-256'); fid=fopen(path,'r');
assert(fid>=0,'C524Parity:Read','Cannot read %s.',path); closer=onCleanup(@()fclose(fid)); %#ok<NASGU>
while true, b=fread(fid,8*1024*1024,'*uint8'); if isempty(b), break; end, md.update(b); end
h=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
