function result=d3_export_final_components(root)
% Offline decomposition of the six completed D3 Final P_A raw runs; zero Plant.
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','position_causal_repair_v1');
addpath(genpath(fullfile(root,'matlab')));[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'D3:Root','Unexpected DL1018 root.');
M=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
B=readtable(fullfile(out,'manifests','BRIDGE6.csv'),'TextType','string');ids=unique(B.scene_id,'stable');
parts=table();closures=zeros(numel(ids),1);
for i=1:numel(ids)
    sceneId=char(ids(i));rawPath=fullfile(out,'runs','D3_FINAL_INITIAL_BRIDGE',sceneId,'P_A','raw_run.mat');
    d=load(rawPath,'log','scene');log=d.log;scene=d.scene;spec=M(M.scene_id==sceneId,:);
    assert(height(spec)==1,'D3:SceneSpec','Scene spec must be unique for %s.',sceneId);
    E=export_position_events_dl1018(log,scene,cfg,'P_A','TRAIN',spec);idx=double(E.plant_index(:));n=numel(idx);
    mass=double(cfg.plant.mass);g=double(cfg.plant.g);x=double(log.state(idx,:));
    RaEuler=x(:,7:9);RrEuler=double(log.raw_outer_attitude(idx,:));wind=double(log.wind_force_I(idx,:));
    Treq=double(log.controller_clipped_generalized(idx,1));Treal=double(log.realized_generalized(idx,1));
    nom=double(log.position_nominal_acceleration_mps2(idx,:));applied=double(log.position_compensation_applied_acceleration_mps2(idx,:));
    dWind=wind/mass;dAlloc=zeros(n,3);dAtt=zeros(n,3);dMap=zeros(n,3);
    for j=1:n
        Ra=rot_zyx(RaEuler(j,:));Rr=rot_zyx(RrEuler(j,:));e3=[0;0;1];
        dAlloc(j,:)=(Ra*e3*(Treal(j)-Treq(j))/mass).';
        dAtt(j,:)=((Ra-Rr)*e3*Treq(j)/mass).';
        dMap(j,:)=(Rr*e3*Treq(j)/mass-[0;0;g]-(nom(j,:)-applied(j,:)).').';
    end
    dEff=dWind+dAlloc+dAtt+dMap;target=table_matrix(E,'target_raw_',3);
    closures(i)=max(abs(dEff(:)-target(:)));assert(closures(i)<=1e-9,'D3:Closure','Component closure failed for %s.',sceneId);
    t=double(E.event_time_s(:));edges=[0 1.8 5 10 15 20];labels={'T_0_1p8','T_1p8_5','T_5_10','T_10_15','T_15_20'};
    bin=repmat("OUTSIDE",n,1);for b=1:numel(labels),m=t>=edges(b)&t<edges(b+1);bin(m)=labels{b};end
    pe=double(log.reference.position(idx,:))-x(:,1:3);eta=double(log.stage1_position_pcf_event_eta_before_mps(idx,:));
    sceneCol=repmat(string(sceneId),n,1);phase=string(E.phase(:));eventIndex=double(E.event_index(:));
    T=table(sceneCol,eventIndex,idx,t,bin,phase,pe(:,1),pe(:,2),pe(:,3), ...
        dWind(:,1),dWind(:,2),dWind(:,3),dAlloc(:,1),dAlloc(:,2),dAlloc(:,3), ...
        dAtt(:,1),dAtt(:,2),dAtt(:,3),dMap(:,1),dMap(:,2),dMap(:,3), ...
        dEff(:,1),dEff(:,2),dEff(:,3),applied(:,1),applied(:,2),applied(:,3), ...
        target(:,1),target(:,2),target(:,3),eta(:,1),eta(:,2),eta(:,3),double(E.beta(:)), ...
        'VariableNames',{'scene_id','event_index','plant_index','time_s','time_bin','phase', ...
        'e_pos_x_m','e_pos_y_m','e_pos_z_m', ...
        'd_wind_x_mps2','d_wind_y_mps2','d_wind_z_mps2', ...
        'd_allocation_x_mps2','d_allocation_y_mps2','d_allocation_z_mps2', ...
        'd_attitude_realization_x_mps2','d_attitude_realization_y_mps2','d_attitude_realization_z_mps2', ...
        'd_mapping_x_mps2','d_mapping_y_mps2','d_mapping_z_mps2', ...
        'd_effective_x_mps2','d_effective_y_mps2','d_effective_z_mps2', ...
        'd_applied_x_mps2','d_applied_y_mps2','d_applied_z_mps2', ...
        'target_raw_x_mps2','target_raw_y_mps2','target_raw_z_mps2', ...
        'pcf_eta_x_mps','pcf_eta_y_mps','pcf_eta_z_mps','beta'});
    if isempty(parts),parts=T;else,parts=[parts;T];end %#ok<AGROW>
end
path=fullfile(out,'reports','D3_FINAL_LABEL_COMPONENTS.csv');writetable(parts,path);
summary=struct('runs',numel(ids),'event_rows',height(parts),'new_plant_starts',0,'max_closure_abs_mps2',max(closures), ...
    'raw_files_reopened',true,'created_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
fid=fopen(fullfile(out,'reports','D3_COMPONENT_EXPORT.json'),'w');fwrite(fid,jsonencode(summary,'PrettyPrint',true),'char');fclose(fid);
fprintf('D3 components: %d runs, %d event rows, max closure %.3g m/s^2, 0 Plant.\n',numel(ids),height(parts),max(closures));result=summary;
end

function X=table_matrix(E,prefix,width)
X=zeros(height(E),width);for j=1:width,X(:,j)=double(E.(sprintf('%s%d',prefix,j)));end
end

function R=rot_zyx(e)
phi=e(1);theta=e(2);psi=e(3);cp=cos(phi);sp=sin(phi);ct=cos(theta);st=sin(theta);cy=cos(psi);sy=sin(psi);
R=[cy*ct,cy*st*sp-sy*cp,cy*st*cp+sy*sp; ...
    sy*ct,sy*st*sp+cy*cp,sy*st*cp-cy*sp;-st,ct*sp,ct*cp];
end
