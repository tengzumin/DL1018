function report=student_refine_adapter_preflight(root)
root=char(java.io.File(root).getCanonicalPath());
out=fullfile(root,'experiments','gru14_dssm14_student_refine_v1');
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'STUDENT:Root','Unexpected project root.');
search=fullfile(root,'experiments','position_only_closed_loop_search_v1','local_runtime');
teacher=fullfile(root,'experiments','teacher_reuse_model_screen_v1','local_runtime');
addpath(genpath(search),'-begin');addpath(genpath(teacher),'-begin');rehash;
forwardPath=char(java.io.File(which('position_stage1_model_forward_v2')).getCanonicalPath());
assert(startsWith(forwardPath,[teacher filesep],'IgnoreCase',true), ...
    'STUDENT:ForwardAdapter','GRU/DSSM teacher-reuse adapter was not selected: %s.',forwardPath);
models={'GRU14','DSSM14'};maxPhi=zeros(1,2);maxOutput=zeros(1,2);
for i=1:2
    id=models{i};
    p=fullfile(root,'experiments','teacher_reuse_model_screen_v1','models','official_export',id, ...
        sprintf('seed%.0f',seed_for(id)),'final_step','matlab_model_and_parity.mat');
    q=load(p,'model','windows','expected_phi','expected_output');
    model=q.model;model.model_id=id;
    for k=1:size(q.windows,3)
        phi=position_stage1_model_forward_v2(model,q.windows(:,:,k));
        y=double(model.output_W).'*phi;
        maxPhi(i)=max(maxPhi(i),max(abs(phi-double(q.expected_phi(:,k)))));
        maxOutput(i)=max(maxOutput(i),max(abs(y-double(q.expected_output(:,k)))));
    end
    opts=position_only_search_options(cfg,model,'FEATURE',12,1);
    assert(opts.stage1_position_runtime.update_enabled&& ...
        norm(opts.stage1_position_runtime.weight-double(model.output_W),'fro')==0&& ...
        ~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&&opts.rbf_attitude_update_enabled, ...
        'STUDENT:Controller','Fixed online position/B-attitude isolation failed for %s.',id);
end
assert(all(maxPhi<=1e-5)&&all(maxOutput<=1e-5), ...
    'STUDENT:Parity','Original-package MATLAB fixture parity exceeds 1e-5.');
report=struct('status','RUNTIME_ADAPTER_REPAIR_PREFLIGHT_PASS','plant_starts_this_check',0, ...
    'plant_starts_total_including_logged_engineering_failure',count_plants(out), ...
    'models',{models},'fixture_count_per_model',64,'max_phi_abs_error',maxPhi, ...
    'max_output_abs_error_mps2',maxOutput,'runtime_adapter_path',forwardPath, ...
    'position_options_path',which('position_only_search_options'), ...
    'episode_runtime_path',which('run_episode_dl1018'), ...
    'test_accessed',false,'new_plant_started',false,'checked_at_utc',utc_now());
write_json(fullfile(out,'reports','runtime_adapter_preflight.json'),report);
fprintf('STUDENT_ADAPTER_PREFLIGHT PASS GRU14/DSSM14 fixtures=64/model PlantThisCheck=0\n');
end
function s=seed_for(id)
if strcmp(id,'GRU14'),s=2026102002;else,s=2026102001;end
end
function n=count_plants(out)
d=dir(fullfile(out,'student_raw','**','plant_started.marker'));n=numel(d);
end
function s=utc_now()
s=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
end
function write_json(path,value)
fid=fopen(path,'w');assert(fid>0,'STUDENT:Write','Cannot write %s.',path);
cleanup=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');
end
