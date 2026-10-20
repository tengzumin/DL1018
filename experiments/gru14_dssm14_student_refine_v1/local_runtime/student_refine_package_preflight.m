function report=student_refine_package_preflight(root)
% Zero-Plant MATLAB/PyTorch parity check for every distinct exported package.
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','gru14_dssm14_student_refine_v1');
runtime=fullfile(root,'experiments','teacher_reuse_model_screen_v1','local_runtime');
addpath(genpath(runtime),'-begin');rehash;
forwardPath=char(java.io.File(which('position_stage1_model_forward_v2')).getCanonicalPath());
assert(startsWith(forwardPath,[runtime filesep],'IgnoreCase',true),'STUDENT:PackageRuntime','Wrong model adapter: %s',forwardPath);
manifest=readtable(fullfile(out,'manifests','canonical_packages.csv'),'TextType','string');
assert(height(manifest)>=4&&height(manifest)<=16,'STUDENT:PackageCount','Expected 4-16 distinct packages.');
maxPhi=0;maxY=0;fixtureCounts=zeros(height(manifest),1);maxPlantBefore=count_plants(out);
for i=1:height(manifest)
    folder=fullfile(root,strrep(char(manifest.package_path(i)),'/',filesep));
    matPath=fullfile(folder,'matlab_model_and_parity.mat');q=load(matPath,'model','windows','expected_phi','expected_output');
    assert(size(q.windows,1)==14&&size(q.windows,2)==32&&size(q.windows,3)>=64, ...
        'STUDENT:FixtureShape','Fixture contract failed for %s.',char(manifest.package_id(i)));
    erPhi=0;erY=0;
    for k=1:size(q.windows,3)
        phi=position_stage1_model_forward_v2(q.model,double(q.windows(:,:,k)));
        y=double(q.model.output_W).'*phi;
        expectedPhi=double(q.expected_phi(:,k));expectedY=double(q.expected_output(:,k));
        erPhi=max(erPhi,max(abs(phi(:)-expectedPhi(:))));
        erY=max(erY,max(abs(y(:)-expectedY(:))));
    end
    assert(erPhi<=1e-5&&erY<=1e-5,'STUDENT:PackageParity','Parity exceeds tolerance for %s.',char(manifest.package_id(i)));
    fixtureCounts(i)=size(q.windows,3);maxPhi=max(maxPhi,erPhi);maxY=max(maxY,erY);
    fprintf('STUDENT_PACKAGE_PARITY %s fixtures=%d max_phi=%.3g max_output=%.3g Plant=0\n', ...
        char(manifest.package_id(i)),fixtureCounts(i),erPhi,erY);
end
assert(count_plants(out)==maxPlantBefore,'STUDENT:PreflightPlant','Package preflight started Plant.');
report=struct('status','PASS','packages',height(manifest),'fixtures_per_package',fixtureCounts, ...
    'fixture_sources','Teacher and corresponding Student; HELIX, FIG8_3D, SQUARE', ...
    'max_phi_abs_error',maxPhi,'max_output_abs_error_mps2',maxY,'tolerance',1e-5, ...
    'plant_starts_this_stage',0,'plant_starts_total',count_plants(out), ...
    'forward_adapter',forwardPath,'checked_at_utc',utc_now());
write_json(fullfile(out,'reports','export_zero_plant_parity.json'),report);
fprintf('STUDENT_PACKAGE_PARITY_PASS packages=%d fixtures_each>=64 PlantThisStage=0\n',height(manifest));
end
function n=count_plants(out),d=dir(fullfile(out,'**','plant_started.marker'));n=numel(d);end
function s=utc_now(),s=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));end
function write_json(p,s),fid=fopen(p,'w');assert(fid>0);c=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(s,'PrettyPrint',true),'char');end
