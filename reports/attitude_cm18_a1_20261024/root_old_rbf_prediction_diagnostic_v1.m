function receipt=root_old_rbf_prediction_diagnostic_v1()
% Independent arithmetic on the same four qualified records; no state step.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'matlab','core'),'-begin');
addpath(fullfile(root,'experiments','attitude_cm18_a1_20261024','matlab'),'-begin');
base=fullfile(root,'reports','attitude_cm18_a1_20261024','data_preparation_v1');
m=jsondecode(fileread(fullfile(base,'events_screen4_v1','DATASET_MANIFEST_v1.json')));
model=jsondecode(fileread(fullfile(root,'experiments','attitude_cm18_a1_20261024','deployment_v1','deployment_parameters_v1.json')));
rows=cell(4,1);
for s=1:4
    c=load(fullfile(root,m.rows(s).cache_path));
    raw=load(fullfile(root,c.input_identity.raw_run_path),'log');
    start=load(fullfile(root,c.input_identity.run_start_path),'runStart');
    cfg=start.runStart.cfg;
    [J0,~,~]=arm_mass_properties(cfg.plant.arm_initial(:),cfg.plant,zeros(4,1));
    k=double(c.plant_index(:));
    cold=(J0\double(raw.log.attitude_compensation_applied_torque_Nm(k,:)).').';
    pred=zeros(1999,3);
    for e=1:1999,pred(e,:)=cm18_a1_forward_v1(c.X18(e,:),model.parameters);end
    v=cell(7,1);
    for phase=-1:5
        mask=true(1999,1);if phase>=0,mask=double(c.phase_code(:))==phase;end
        n=nnz(mask);r=struct('phase_code',phase,'events',n);
        if n>0
            r.old_applied_estimate_minus_label_axis_rmse_rad_s2=sqrt(mean((cold(mask,:)-c.target_raw(mask,:)).^2,1));
            r.new_raw_prediction_minus_old_label_axis_rmse_rad_s2=sqrt(mean((pred(mask,:)-c.target_raw(mask,:)).^2,1));
        end
        v{phase+2}=r;
    end
    rows{s}=struct('scene_id',c.scene_id,'split',c.split,'phase',{v});
end
receipt=struct('schema','ROOT_CM18_OLD_RBF_PREDICTION_DIAGNOSTIC_V1','status','PASS', ...
    'rows',{rows},'new_Plant_calls',0,'optimizer_steps',0, ...
    'interpretation','Old applied compensation and new raw predictor versus the same old-behavior physical label. Not a new-action or closed-loop comparison; beta/clipping differ and are not hidden.');
out=fullfile(root,'reports','attitude_cm18_a1_20261024','ROOT_OLD_RBF_PREDICTION_DIAGNOSTIC_v1.json');
assert(~isfile(out));f=fopen(out,'w');assert(f>=0);fwrite(f,jsonencode(receipt),'char');fclose(f);
end
