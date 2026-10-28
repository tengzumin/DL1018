function result = run_comparison(sceneId,windOverride,morphOverride)
%RUN_COMPARISON Regenerate one DL1018 DEV/VAL scene and compare B with C5 M110.
% Presets: DL1018_DEV_T1_C05_W06, DL1018_DEV_T2_C09_W10, DL1018_DEV_T3_C15_W14.
% windOverride accepts wind_velocity_profile fields; morphOverride accepts
% topology, seed, retract, target_override, start_override,
% retract_start_override, morph_speed_mps, and min_hold_s.
% Examples:
% run_comparison('DL1018_DEV_T1_C05_W06');
% run_comparison('DL1018_DEV_T2_C09_W10',struct('V0',8,'A1',2.5,'A2',1.5), ...
%     struct('morph_speed_mps',.06,'min_hold_s',4));
% run_comparison('DL1018_DEV_T3_C15_W14',[], ...
%     struct('topology','1234','target_override',[.23;.24;.22;.25]));

here=fileparts(mfilename('fullpath'));
if nargin<1||isempty(sceneId),sceneId='DL1018_DEV_T1_C05_W06';end
if nargin<2,windOverride=[];end
if nargin<3,morphOverride=[];end

experimentDir=fullfile(here,'experiments','position_axis_coordinate_c5_dev72_20261023');
snapshotPath=fullfile(experimentDir,'C5_DEV72_PREPARED_CFG_OPTS_v3.mat');
assert(isfile(snapshotPath),'C5Comparison:SnapshotMissing', ...
    'Frozen C5 cfg/opts snapshot is missing: %s.',snapshotPath);
pack=load(snapshotPath,'cfg','opts','sourceIdentity','modelIdentity');
cfg=pack.cfg;
addpath(fullfile(here,'matlab','core'),fullfile(here,'matlab','models'), ...
    fullfile(here,'matlab','runtime'),fullfile(here,'matlab','scenes'), ...
    fullfile(here,'matlab','metrics'));
% Build reference, wind, and arm motion in memory from the selected preset.
[scene,sceneParameters]=build_scene_from_id(sceneId,cfg,windOverride,morphOverride);

assert(isfield(pack.opts,'position_delayed_prediction_enabled')&& ...
    logical(pack.opts.position_delayed_prediction_enabled)&& ...
    isequal(double(pack.opts.position_coordinate_mask(:)),[1;1;0]), ...
    'C5Comparison:SnapshotContract','The frozen snapshot is not the expected C5 M110 configuration.');

% Put the frozen C5 runtime and exported model helpers ahead of same-name functions.
activePaths=string(pack.sourceIdentity.active_paths(:));
addpath(fullfile(here,'matlab','core'),fullfile(here,'matlab','models'), ...
    fullfile(here,'matlab','runtime'),fullfile(here,'matlab','scenes'), ...
    fullfile(here,'matlab','metrics'));
for k=1:numel(activePaths)
    assert(isfile(activePaths(k)),'C5Comparison:SourceMissing', ...
        'A frozen C5 dependency is missing: %s.',activePaths(k));
    addpath(fileparts(char(activePaths(k))));
end
modelHelpers=["position_stage1_model_forward_v2.m"; ...
    "position_only_search_head_step.m";"position_only_search_options.m"];
modelHelperPaths=strings(size(modelHelpers));
for k=1:numel(modelHelpers)
    match=activePaths(endsWith(activePaths,modelHelpers(k)));
    assert(numel(match)==1,'C5Comparison:ModelHelperPath', ...
        'Expected one frozen C5 model helper: %s.',modelHelpers(k));
    modelHelperPaths(k)=match;
    addpath(fileparts(char(match)),'-begin');
end
addpath(experimentDir,'-begin');
clear run_episode_dl1018 run_dl1018_closed_loop delayed_prediction_step_candidate
rehash;
assert(same_path(which('run_episode_dl1018'),fullfile(experimentDir,'run_episode_dl1018.m'))&& ...
    same_path(which('run_dl1018_closed_loop'),fullfile(experimentDir,'run_dl1018_closed_loop.m'))&& ...
    same_path(which('delayed_prediction_step_candidate'),fullfile(experimentDir,'delayed_prediction_step_candidate.m'))&& ...
    all(arrayfun(@(k)same_path(which(erase(modelHelpers(k),'.m')),modelHelperPaths(k)),1:numel(modelHelpers))), ...
    'C5Comparison:RuntimePath','A C5 runtime or model helper did not resolve from its frozen source path.');

optsB=controller_options_dl1018(cfg,'B');
optsC5=pack.opts;
fprintf('\n[B] 开始运行场景 %s ...\n',char(sceneId));
logB=run_episode_dl1018(scene,'B',cfg,optsB);
fprintf('[B] %s，已完成 %d 个 transition。\n',char(logB.status),numel(logB.transition_time));
figures=plot_comparison(scene,logB,[],[]);
fprintf('[C5] 开始运行同一场景 ...\n');
logC5=run_episode_dl1018(scene,'C5',cfg,optsC5);
fprintf('[C5] %s，已完成 %d 个 transition。\n',char(logC5.status),numel(logC5.transition_time));

metrics=[measure_run('B',logB,scene);measure_run('C5',logC5,scene)];
figures=plot_comparison(scene,logB,logC5,figures);
fprintf('\nB 与 C5 指标：\n');
disp(metrics);
result=struct('scene_id',char(sceneId),'metrics',metrics,'B',logB,'C5',logC5,'figures',figures);
result.scene=scene;result.scene_parameters=sceneParameters;
end

function [scene,meta]=build_scene_from_id(sceneId,cfg,windOverride,morphOverride)
% Recreate the public DL1018 scenario formulas without reading scene files.
token=regexp(char(sceneId),'^DL1018_(DEV|VAL)_T([1-3])_C(\d{2})_W(\d{2})$','tokens','once');
assert(~isempty(token),'C5Comparison:SceneId', ...
    'Use a DEV/VAL preset such as DL1018_DEV_T1_C05_W06.');
split=token{1};taskIndex=str2double(token{2})-1;classIndex=str2double(token{3});w=str2double(token{4});
assert(classIndex<=15&&w<=15,'C5Comparison:SceneId','Class must be C00-C15 and wind cell W00-W15.');
t=(0:.001:20).';splitCode=1;sourceCode=1;offset=15;
if strcmp(split,'DEV')
    offset=7.5;splitCode=2;
    dev=[0 0 3;0 1 15;0 4 0;0 5 6;0 7 8;0 10 9;0 11 12;0 15 14; ...
        1 0 4;1 2 15;1 3 1;1 6 7;1 8 8;1 9 10;1 12 13;1 14 14; ...
        2 0 5;2 3 15;2 5 2;2 6 8;2 9 9;2 10 11;2 13 12;2 15 14];
    assert(any(dev(:,1)==taskIndex&dev(:,2)==classIndex&dev(:,3)==w), ...
        'C5Comparison:SceneId','That DEV scene ID is not in the official DL1018 DEV preset list.');
else
    assert(w==mod(classIndex+3*taskIndex+7,16), ...
        'C5Comparison:SceneId','That VAL scene ID does not match the official VAL wind-cell rule.');
end
classes={'NONE','1','2','3','4','12','13','14','23','24','34','123','124','134','234','1234'};
taskNames={'HELIX','FIG8_3D','SQUARE'};rStyle=mod(w,4);band=floor(w/3);level=mod(w,3);
seed=2026101800+10000*splitCode+1000*taskIndex+16*classIndex+w;
freqs=cat(3,[.20 .40;.50 .80;1.00 1.60;2.00 3.00;3.80 5.00], ...
    [.25 .45;.58 .87;1.15 1.75;2.20 3.20;3.70 4.80], ...
    [.30 .50;.65 .95;1.30 1.90;2.40 3.40;3.60 4.60]);
amps=[1.5 1.0;3.5 2.45;4.5 3.5];phase1=0;phase2=0;f1=0;f2=0;A1=0;A2=0;
if w<15
    rs=RandStream('mt19937ar','Seed',double(seed));phase1=2*pi*rand(rs);phase2=2*pi*rand(rs);
    f1=freqs(band+1,1,2);f2=freqs(band+1,2,2);A1=amps(level+1,1);A2=amps(level+1,2);
else
    f1=.5;f2=.8;
end
c=classIndex;task=taskIndex;azIndex=mod(3*c+5*task+7*rStyle,8);
azimuth=45*azIndex+offset;elevations=[-15 0 15];
elevation=elevations(1+mod(c+2*task+rStyle+sourceCode,3));
windCfg=struct('type','biased_dual_sine','direction',[cosd(elevation)*cosd(azimuth); ...
    cosd(elevation)*sind(azimuth);sind(elevation)],'V0',9,'A1',A1,'f1',f1, ...
    'phi1',phase1,'A2',A2,'f2',f2,'phi2',phase2,'rise_time_s',.8, ...
    'rho_air',1.225,'CdBody',1,'CdArm',1);
if ~isempty(windOverride)
    assert(isstruct(windOverride)&&isscalar(windOverride),'C5Comparison:WindOverride', ...
        'windOverride must be a scalar struct of wind_velocity_profile options.');
    names=fieldnames(windOverride);for k=1:numel(names),windCfg.(names{k})=windOverride.(names{k});end
end
if w==15&&isempty(windOverride)
    wind=zeros(numel(t),3);windSpeed=zeros(numel(t),1);
else
    [windT,windDetails]=wind_velocity_profile(t,windCfg);wind=windT.';windSpeed=windDetails.speed;
end

classId=classes{classIndex+1};topology=classId;if strcmp(classId,'NONE'),topology='C0';end
target=.15*ones(4,1);start=nan(4,1);retractStart=nan(4,1);
[topologyNames,topologyArms]=tcn0916_topologies();topologyIdx=find(strcmp(topologyNames,topology),1);
assert(~isempty(topologyIdx),'C5Comparison:Topology','Unknown morphology topology %s.',topology);
active=topologyArms{topologyIdx};targetValues=[.18 .20 .22 .25];schedule=mod(c+task+rStyle+sourceCode,3);
for q=1:numel(active)
    arm=active(q);targetIndex=1+mod(c+task+rStyle+arm+sourceCode,4);target(arm)=targetValues(targetIndex);
    switch schedule
        case 0,start(arm)=5.2;retractStart(arm)=13.0;
        case 1,start(arm)=5.2+.25*(q-1);retractStart(arm)=13.4+.15*(q-1);
        case 2,start(arm)=6.2;retractStart(arm)=14.0;
    end
end
morphOpts=struct('retract',true,'target_override',target,'start_override',start, ...
    'retract_start_override',retractStart,'morph_speed_mps',.05,'min_hold_s',5);
if ~isempty(morphOverride)
    assert(isstruct(morphOverride)&&isscalar(morphOverride),'C5Comparison:MorphOverride', ...
        'morphOverride must be a scalar struct.');
    allowed={'topology','seed','retract','target_override','start_override', ...
        'retract_start_override','morph_speed_mps','min_hold_s'};
    provided=fieldnames(morphOverride);unknown=setdiff(provided,allowed);
    if ~isempty(unknown),error('C5Comparison:MorphOverride','Unknown morphOverride field: %s.',unknown{1});end
    if isfield(morphOverride,'topology')
        topology=char(string(morphOverride.topology));
        topologyIdx=find(strcmp(topologyNames,topology),1);
        assert(~isempty(topologyIdx),'C5Comparison:Topology','Unknown morphology topology %s.',topology);
        active=topologyArms{topologyIdx};
        if ~isfield(morphOverride,'target_override')
            target=.15*ones(4,1);start=nan(4,1);retractStart=nan(4,1);
            for q=1:numel(active)
                arm=active(q);target(arm)=targetValues(1+mod(c+task+rStyle+arm+sourceCode,4));
                switch schedule
                    case 0,start(arm)=5.2;retractStart(arm)=13.0;
                    case 1,start(arm)=5.2+.25*(q-1);retractStart(arm)=13.4+.15*(q-1);
                    case 2,start(arm)=6.2;retractStart(arm)=14.0;
                end
            end
            morphOpts.target_override=target;morphOpts.start_override=start;
            morphOpts.retract_start_override=retractStart;
        end
    end
    if isfield(morphOverride,'seed'),seed=double(morphOverride.seed);end
    for k=1:numel(provided)
        key=provided{k};if ismember(key,{'topology','seed'}),continue;end
        morphOpts.(key)=morphOverride.(key);
    end
end
[arms,morphMeta]=tcn0916_morphology_scenario(topology,t,seed,morphOpts);
arms.rho_hat=repmat(cfg.plant.arm_initial(:).',numel(t),1);arms.rhoDot_hat=zeros(numel(t),4);
scene=struct('scene_id',char(sceneId),'time',t,'initial_state',zeros(12,1), ...
    'reference',make_reference(taskNames{taskIndex+1},t),'arms',arms, ...
    'environment_wind_I',wind,'reference_contract_id','DL1018_SCENE_REF_FIG8_A2_V2');
meta=struct('scene_id',char(sceneId),'task',taskNames{taskIndex+1},'topology',topology, ...
    'seed',seed,'wind',windCfg,'wind_speed_rms_mps',sqrt(mean(windSpeed.^2)), ...
    'wind_speed_peak_mps',max(abs(windSpeed)),'morphology',morphMeta);
end

function ref=make_reference(task,t)
t=double(t(:));s=min(max(t/20,0),1);u=10*s.^3-15*s.^4+6*s.^5;
ud=(30*s.^2-60*s.^3+30*s.^4)/20;udd=(60*s-180*s.^2+120*s.^3)/400;
switch upper(char(task))
    case 'HELIX'
        th=3*pi*u;p=[1.2*(cos(th)-1),1.2*sin(th),2*u];
        pu=[-3.6*pi*sin(th),3.6*pi*cos(th),2+zeros(size(t))];
        puu=[-10.8*pi^2*cos(th),-10.8*pi^2*sin(th),zeros(size(t))];
        v=pu.*ud;a=puu.*(ud.^2)+pu.*udd;
    case 'FIG8_3D'
        th=2*pi*u;p=[1.5*sin(th),sin(2*th),.4*u+.35*(1-cos(2*th))];
        pu=[3*pi*cos(th),4*pi*cos(2*th),.4+1.4*pi*sin(2*th)];
        puu=[-6*pi^2*sin(th),-16*pi^2*sin(2*th),5.6*pi^2*cos(2*th)];
        v=pu.*ud;a=puu.*(ud.^2)+pu.*udd;
    case 'SQUARE'
        p=zeros(numel(t),3);v=p;a=p;points=[0 0 0;2 0 0;2 2 0;0 2 0;0 0 0];
        seg=min(floor(t/5),3);
        for k=1:numel(t),[p(k,:),v(k,:),a(k,:)]=square_reference_row(t(k),seg(k),points);end
    otherwise,error('C5Comparison:Task','Unknown scene task %s.',task);
end
ref=struct('position',p,'velocity',v,'acceleration',a,'yaw',zeros(size(t)), ...
    'yaw_rate',zeros(size(t)),'yaw_acceleration',zeros(size(t)));
end

function [p,v,a]=square_reference_row(t,i,points)
u=min(max((t-5*i)/5,0),1);h=10*u^3-15*u^4+6*u^5;
hd=30*u^2-60*u^3+30*u^4;hdd=60*u-180*u^2+120*u^3;dp=points(i+2,:)-points(i+1,:);
p=points(i+1,:)+dp*h;v=dp*hd/5;a=dp*hdd/25;
end

function row=measure_run(model,log,scene)
n=min(numel(log.transition_time),size(log.state,1)-1);
t=double(log.transition_time(1:n));
mask=t>=0&t<20;
positionError=double(log.reference.position(1:n,:))-double(log.state(1:n,1:3));
attitudeError=atan2(sin(double(log.filtered_attitude_reference(1:n,:))-double(log.state(1:n,7:9))), ...
    cos(double(log.filtered_attitude_reference(1:n,:))-double(log.state(1:n,7:9))));
windSpeed=vecnorm(double(scene.environment_wind_I(1:n,:)),2,2);
windForce=vecnorm(double(log.wind_force_I(1:n,:)),2,2);
windTorque=vecnorm(double(log.wind_torque_B(1:n,:)),2,2);
finite=all(isfinite(positionError(:)))&&all(isfinite(attitudeError(:)))&& ...
    all(isfinite(log.state(1:n,:)),'all');
row=table(string(model),string(log.status),logical(strcmpi(log.status,'STABLE')&&n==20000), ...
    logical(finite),double(n),sqrt(mean(sum(positionError(mask,:).^2,2))), ...
    sqrt(mean(positionError(mask,1).^2)),sqrt(mean(positionError(mask,2).^2)), ...
    sqrt(mean(positionError(mask,3).^2)),max(vecnorm(positionError(mask,:),2,2)), ...
    sqrt(mean(sum(attitudeError(mask,:).^2,2))),max(abs(attitudeError(mask,3))), ...
    mean(any(log.motor_saturated(1:n,:),2)),mean(any(log.generalized_clipped(1:n,:),2)), ...
    max(windSpeed),max(windForce),max(windTorque), ...
    'VariableNames',{'model','status','complete','finite','transitions','position_RMSE_m', ...
    'position_X_RMSE_m','position_Y_RMSE_m','position_Z_RMSE_m','position_peak_error_m', ...
    'attitude_RMSE_rad','yaw_peak_abs_rad', ...
    'motor_saturation_fraction','generalized_clip_fraction','wind_speed_peak_mps', ...
    'wind_force_peak_N','wind_torque_peak_Nm'});
end

function figs=plot_comparison(scene,logB,logC5,figs)
% Mirror the reference runner's six visible validation figures.
n=numel(logB.transition_time);if ~isempty(logC5),n=min(n,numel(logC5.transition_time));end
t=double(logB.transition_time(1:n));colors={[.08 .36 .70],[.80 .25 .16]};names={'B','C5'};
hasC5=~isempty(logC5);
if isempty(figs)
    close(findall(groot,'Type','figure','Tag','C5_COMPARISON_FIGURE'));
    figs=prepare_figure([],'B vs C5 对比');
    tabGroup=uitabgroup(figs,'Units','normalized','Position',[0 0 1 1],'TabLocation','top');
    tabTitles={'跟踪','跟踪误差','RMSE','模型输出','控制分配','风扰与变臂'};
    tabs=gobjects(1,numel(tabTitles));
    for k=1:numel(tabTitles),tabs(k)=uitab(tabGroup,'Title',tabTitles{k});end
    setappdata(figs,'C5_COMPARISON_TABS',tabs);
else
    figure(figs);set(figs,'Visible','on');
end

% Position and attitude tracking.
tl=prepare_tab(figs,1,2,3);
axisNames={'X','Y','Z'};
for i=1:3
    ax=nexttile(tl,i);hold(ax,'on');
    plot(ax,t,logB.reference.position(1:n,i),'k--','LineWidth',1.1,'DisplayName','参考');
    plot(ax,t,logB.state(1:n,i),'Color',colors{1},'DisplayName',names{1});
    if hasC5,plot(ax,t,logC5.state(1:n,i),'Color',colors{2},'DisplayName',names{2});end
    grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,[axisNames{i} ' 位置（m）']);
    if i==1,legend(ax,'Location','best');end
    ax=nexttile(tl,i+3);hold(ax,'on');
    plot(ax,t,logB.filtered_attitude_reference(1:n,i)*180/pi,'k--', ...
        'LineWidth',1.1,'DisplayName','参考');
    plot(ax,t,logB.state(1:n,6+i)*180/pi,'Color',colors{1},'DisplayName',names{1});
    if hasC5,plot(ax,t,logC5.state(1:n,6+i)*180/pi,'Color',colors{2},'DisplayName',names{2});end
    grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,[axisNames{i} ' 姿态（deg）']);
    if i==1,legend(ax,'Location','best');end
end
title(tl,'位置与姿态跟踪：参考、B、C5');drawnow;

% Tracking error and axis RMSE.
positionErrorB=logB.reference.position(1:n,:)-logB.state(1:n,1:3);
attitudeErrorB=wrap_error(logB.filtered_attitude_reference(1:n,:)-logB.state(1:n,7:9));
positionRmseB=sqrt(mean(positionErrorB.^2,1));attitudeRmseB=sqrt(mean(attitudeErrorB.^2,1))*180/pi;
tl=prepare_tab(figs,2,2,1);
ax=nexttile(tl,1);hold(ax,'on');plot(ax,t,positionErrorB,'LineWidth',1.0);
if hasC5
    positionErrorC5=logC5.reference.position(1:n,:)-logC5.state(1:n,1:3);
    plot(ax,t,positionErrorC5,'LineWidth',1.0);
end
grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'位置误差（m）');
title(ax,'参考位置 − 实际位置');
if hasC5,legend(ax,{'B-X','B-Y','B-Z','C5-X','C5-Y','C5-Z'},'Location','best');
else,legend(ax,{'B-X','B-Y','B-Z'},'Location','best');end
ax=nexttile(tl,2);hold(ax,'on');plot(ax,t,attitudeErrorB*180/pi,'LineWidth',1.0);
if hasC5
    attitudeErrorC5=wrap_error(logC5.filtered_attitude_reference(1:n,:)-logC5.state(1:n,7:9));
    plot(ax,t,attitudeErrorC5*180/pi,'LineWidth',1.0);
end
grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'姿态误差（deg）');
title(ax,'参考姿态 − 实际姿态');
if hasC5,legend(ax,{'B-横滚','B-俯仰','B-偏航','C5-横滚','C5-俯仰','C5-偏航'},'Location','best');
else,legend(ax,{'B-横滚','B-俯仰','B-偏航'},'Location','best');end
title(tl,'跟踪误差');drawnow;

tl=prepare_tab(figs,3,1,2);
ax=nexttile(tl,1);hold(ax,'on');
if hasC5
    positionErrorC5=logC5.reference.position(1:n,:)-logC5.state(1:n,1:3);
    positionRmseC5=sqrt(mean(positionErrorC5.^2,1));
    positionBars=[positionRmseB;positionRmseC5];
else,positionBars=positionRmseB;end
bar(ax,positionBars.');grid(ax,'on');set(ax,'XTick',1:3,'XTickLabel',axisNames);
ylabel(ax,'RMSE（m）');title(ax,'位置分轴 RMSE');
for k=1:size(positionBars,1)
    text(ax,1:3,positionBars(k,:),string(compose('%.4g',positionBars(k,:))), ...
        'HorizontalAlignment','center','VerticalAlignment','bottom');
end
if hasC5,legend(ax,names,'Location','best');end
ax=nexttile(tl,2);hold(ax,'on');
if hasC5
    attitudeRmseC5=sqrt(mean(attitudeErrorC5.^2,1))*180/pi;
    attitudeBars=[attitudeRmseB;attitudeRmseC5];
else,attitudeBars=attitudeRmseB;end
bar(ax,attitudeBars.');grid(ax,'on');set(ax,'XTick',1:3,'XTickLabel',{'横滚','俯仰','偏航'});
ylabel(ax,'RMSE（deg）');title(ax,'姿态分轴 RMSE');
for k=1:size(attitudeBars,1)
    text(ax,1:3,attitudeBars(k,:),string(compose('%.4g',attitudeBars(k,:))), ...
        'HorizontalAlignment','center','VerticalAlignment','bottom');
end
if hasC5,legend(ax,names,'Location','best');end
title(tl,'各轴跟踪误差 RMSE');drawnow;

% RBF disturbance estimates and the C5 position-head output.
tl=prepare_tab(figs,4,2,3);
for i=1:3
    ax=nexttile(tl,i);hold(ax,'on');
    plot(ax,t,logB.position_rbf_estimate_acceleration_mps2(1:n,i), ...
        'Color',colors{1},'DisplayName','B Position RBF');
    if hasC5&&isfield(logC5,'stage1_position_event_raw_acceleration_mps2')
        plot(ax,t,logC5.stage1_position_event_raw_acceleration_mps2(1:n,i),'.', ...
            'Color',colors{2},'DisplayName','C5 Position Head');
    end
    grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'位置加速度（m/s²）');title(ax,axisNames{i});
    if i==1,legend(ax,'Location','best');end
    ax=nexttile(tl,i+3);hold(ax,'on');
    plot(ax,t,logB.attitude_rbf_estimate_acceleration_rads2(1:n,i), ...
        'Color',colors{1},'DisplayName','B Attitude RBF');
    if hasC5,plot(ax,t,logC5.attitude_rbf_estimate_acceleration_rads2(1:n,i), ...
            'Color',colors{2},'DisplayName','C5 Attitude RBF');end
    grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'姿态加速度（rad/s²）');title(ax,axisNames{i});
    if i==1,legend(ax,'Location','best');end
end
title(tl,'RBF 扰动估计与 C5 位置 Head 输出');drawnow;

% Compensation and control-allocation chain.
tl=prepare_tab(figs,5,2,2);
ax=nexttile(tl,1);hold(ax,'on');
plot(ax,t,vecnorm(logB.position_rbf_compensation_force_N(1:n,:),2,2), ...
    'Color',colors{1},'DisplayName','B');
if hasC5,plot(ax,t,vecnorm(logC5.position_rbf_compensation_force_N(1:n,:),2,2), ...
        'Color',colors{2},'DisplayName','C5 RBF');end
grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'|F_{RBF}|（N）');title(ax,'位置 RBF 补偿力');legend(ax,'Location','best');
ax=nexttile(tl,2);hold(ax,'on');
plot(ax,t,vecnorm(logB.attitude_rbf_compensation_torque_Nm(1:n,:),2,2), ...
    'Color',colors{1},'DisplayName','B');
if hasC5,plot(ax,t,vecnorm(logC5.attitude_rbf_compensation_torque_Nm(1:n,:),2,2), ...
        'Color',colors{2},'DisplayName','C5');end
grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'|τ_{RBF}|（N·m）');title(ax,'姿态 RBF 补偿力矩');legend(ax,'Location','best');
for panel=3:4
    ax=nexttile(tl,panel);hold(ax,'on');
    if panel==3,index=1;ylabelText='总推力（N）';panelTitle='推力请求、分配与实现';
    else,index=2:4;ylabelText='力矩合量（N·m）';panelTitle='力矩请求、分配与实现';end
    plot_wrench(ax,t,logB,index,colors{1},'B');
    if hasC5,plot_wrench(ax,t,logC5,index,colors{2},'C5');end
    grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,ylabelText);title(ax,panelTitle);
    legend(ax,'Location','best');
end
title(tl,'RBF 补偿与控制执行链');drawnow;

% Shared mission context, including wind, deformation, motors, and limits.
tl=prepare_tab(figs,6,2,3);
ax=nexttile(tl,1);hold(ax,'on');
plot3(ax,logB.reference.position(1:n,1),logB.reference.position(1:n,2), ...
    logB.reference.position(1:n,3),'k--','DisplayName','参考');
plot3(ax,logB.state(1:n,1),logB.state(1:n,2),logB.state(1:n,3), ...
    'Color',colors{1},'DisplayName','B');
if hasC5,plot3(ax,logC5.state(1:n,1),logC5.state(1:n,2),logC5.state(1:n,3), ...
        'Color',colors{2},'DisplayName','C5');end
grid(ax,'on');axis(ax,'equal');xlabel(ax,'X（m）');ylabel(ax,'Y（m）');zlabel(ax,'Z（m）');
title(ax,'三维轨迹');legend(ax,'Location','best');view(ax,3);
ax=nexttile(tl,2);hold(ax,'on');
plot(ax,t,vecnorm(logB.wind_force_I(1:n,:),2,2),'Color',colors{1},'DisplayName','B');
if hasC5,plot(ax,t,vecnorm(logC5.wind_force_I(1:n,:),2,2),'Color',colors{2},'DisplayName','C5');end
grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'风力（N）');title(ax,'形态感知风力');legend(ax,'Location','best');
ax=nexttile(tl,3);plot(ax,scene.time,vecnorm(scene.environment_wind_I,2,2),'k');grid(ax,'on');
xlabel(ax,'时间（s）');ylabel(ax,'风速（m/s）');title(ax,'共享环境风');
ax=nexttile(tl,4);plot(ax,scene.time,scene.arms.rho_true,'LineWidth',1.0);grid(ax,'on');
xlabel(ax,'时间（s）');ylabel(ax,'臂长（m）');title(ax,'共享 Plant 变臂');
legend(ax,{'臂 1','臂 2','臂 3','臂 4'},'Location','best');
ax=nexttile(tl,5);hold(ax,'on');
motorB=logB.motor_command(1:n,:)*60/(2*pi);motorBLines=plot(ax,t,motorB,'LineWidth',.8);
motorMaxRpm=1900*60/(2*pi);limitLine=plot(ax,[t(1),t(end)],[motorMaxRpm,motorMaxRpm],'k--');
if hasC5
    motorC5=logC5.motor_command(1:n,:)*60/(2*pi);
    motorC5Lines=plot(ax,t,motorC5,'--','LineWidth',.8);
    legend(ax,[motorBLines(:);motorC5Lines(:);limitLine], ...
        {'B M1','B M2','B M3','B M4','C5 M1','C5 M2','C5 M3','C5 M4','1900 rad/s 上限'}, ...
        'Location','best');
else,legend(ax,[motorBLines(:);limitLine],{'B M1','B M2','B M3','B M4','1900 rad/s 上限'}, ...
        'Location','best');end
grid(ax,'on');xlabel(ax,'时间（s）');ylabel(ax,'转速（rpm）');title(ax,'电机转速');
ax=nexttile(tl,6);hold(ax,'on');
stairs(ax,t,double(any(logB.motor_saturated(1:n,:),2)),'Color',colors{1},'DisplayName','B 电机饱和');
stairs(ax,t,double(any(logB.generalized_clipped(1:n,:),2)),'Color',colors{1}, ...
    'LineStyle','--','DisplayName','B 控制限幅');
if hasC5
    stairs(ax,t,double(any(logC5.motor_saturated(1:n,:),2)),'Color',colors{2},'DisplayName','C5 电机饱和');
    stairs(ax,t,double(any(logC5.generalized_clipped(1:n,:),2)),'Color',colors{2}, ...
        'LineStyle','--','DisplayName','C5 控制限幅');
end
grid(ax,'on');ylim(ax,[-.05 1.05]);xlabel(ax,'时间（s）');ylabel(ax,'是否触发');
title(ax,'饱和与限幅');legend(ax,'Location','best');
title(tl,'任务环境与执行状态');drawnow;
end

function fig=prepare_figure(fig,name)
if isempty(fig)||~isgraphics(fig)
    fig=figure('Color','w','Visible','on','Name',name,'Tag','C5_COMPARISON_FIGURE');
else
    figure(fig);set(fig,'Visible','on','Name',name);
end
end

function tl=prepare_tab(fig,index,nRows,nCols)
tabs=getappdata(fig,'C5_COMPARISON_TABS');tab=tabs(index);delete(allchild(tab));
panel=uipanel(tab,'Units','normalized','Position',[0 0 1 1],'BorderType','none');
tl=tiledlayout(panel,nRows,nCols,'TileSpacing','compact','Padding','compact');
end

function plot_wrench(ax,t,logRun,index,color,name)
req=double(logRun.requested_generalized(1:numel(t),index));
alloc=double(logRun.allocated_generalized(1:numel(t),index));
realized=double(logRun.realized_generalized(1:numel(t),index));
if numel(index)==1
    plot(ax,t,req,'Color',color,'DisplayName',[name ' 请求']);
    plot(ax,t,alloc,'Color',color,'LineStyle','--','DisplayName',[name ' 分配']);
    plot(ax,t,realized,'Color',color,'LineStyle',':','LineWidth',1.2,'DisplayName',[name ' 实现']);
else
    plot(ax,t,vecnorm(req,2,2),'Color',color,'DisplayName',[name ' 请求']);
    plot(ax,t,vecnorm(alloc,2,2),'Color',color,'LineStyle','--','DisplayName',[name ' 分配']);
    plot(ax,t,vecnorm(realized,2,2),'Color',color,'LineStyle',':','LineWidth',1.2, ...
        'DisplayName',[name ' 实现']);
end
end

function err=wrap_error(err)
err=atan2(sin(err),cos(err));
end

function tf=same_path(a,b)
tf=strcmpi(char(java.io.File(char(a)).getCanonicalPath()), ...
    char(java.io.File(char(b)).getCanonicalPath()));
end

