function r=root_yaw_ideal_alpha_sensitivity_v1()
here=fileparts(mfilename('fullpath'));root=fileparts(fileparts(here));old=path;c=onCleanup(@()path(old));addpath(fullfile(root,'matlab','core'),'-begin');
ids={'DL1018_DEV_T1_C15_W14','DL1018_DEV_T3_C15_W14'};rows=cell(2,1);
for q=1:2
 p=fullfile(root,'experiments','attitude_cm18_a1_20261024','screen12_remaining_v1','runs',ids{q},'attempt_01');pack=load(fullfile(p,'run_start.mat'),'runStart');b=load(fullfile(p,'raw_run.mat'),'log','scene');cfg=pack.runStart.cfg;P0=simulation_parameters(cfg,cfg.plant.arm_initial(:),zeros(4,1));Pc=controller_parameters(cfg,P0,'fixed');C0=Pc.allocation.C;J0=Pc.inertia;idx=find(b.log.cm18_event_flag);v=zeros(numel(idx),3);grow=zeros(numel(idx),3);
 for j=1:numel(idx)
  k=idx(j);Pt=simulation_parameters(cfg,b.scene.arms.rho_true(k,:).',b.scene.arms.rhoDot_true(k,:).');A=Pt.allocation.C/C0;G=Pt.inertia\(A(2:4,2:4)*J0);D=eye(3)-G\eye(3);v(j,:)=D(3,:);grow(j,:)=G(3,:);
 end
 rows{q}=struct('scene_id',ids{q},'max_abs_ideal_yaw_dalpha_xyz',max(abs(v),[],1),'max_abs_effectiveG_yaw_row',max(abs(grow),[],1));
end
r=struct('status','PASS_OFFLINE_LOCAL_SENSITIVITY','formula','dc_ideal/dalphaBS = I-G^-1 at fixed state, morphology, thrust and wind, unclipped neighborhood','scope','No Plant/integration/training; not proof of closed-loop causal failure','rows',[rows{:}]);out=fullfile(here,'ROOT_YAW_IDEAL_ALPHA_SENSITIVITY_v1.json');assert(~isfile(out));fid=fopen(out,'w');cleanup=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(r),'char');
end
