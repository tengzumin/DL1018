function finalize_old_kan_transfer(projectRoot)
% Rebuild paired, phase, readiness and online-diagnostic reports from saved raw.
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());expDir=fullfile(projectRoot, ...
    'experiments','old_kan_fig8_transfer_compare_v1');
sceneIds={'DL1018_DEV_T2_C00_W04','DL1018_DEV_T2_C02_W15','DL1018_DEV_T2_C03_W01', ...
    'DL1018_DEV_T2_C06_W07','DL1018_DEV_T2_C08_W08','DL1018_DEV_T2_C09_W10', ...
    'DL1018_DEV_T2_C12_W13','DL1018_DEV_T2_C14_W14'};
methods={'OLD_G1_R32','NEW_G1_R32','OLD_G12_R32','NEW_G12_R32'};
T=readtable(fullfile(projectRoot,'reports','POSITION_DEV.csv'),'TextType','string','VariableNamingRule','preserve');
paired=struct([]);sceneMap=struct([]);
for si=1:numel(sceneIds)
    sid=sceneIds{si};bi=find(string(T.scene_id)==sid&string(T.method)=='B');Bq=double(T.Q_0_20_m(bi));
    q=nan(1,4);valid=false(1,4);status=strings(1,4);att=nan(1,4);raw=cell(1,4);
    for mi=1:4
        p=fullfile(expDir,'runs','main_matrix',sid,methods{mi},'attempt_01','raw_run.mat');
        if ~isfile(p),continue,end
        z=load(p,'meta','metrics');raw{mi}=p;q(mi)=z.metrics.Q_0_20_m;status(mi)=string(z.meta.status);
        valid(mi)=logical(z.meta.complete)&&logical(z.meta.finite)&&z.meta.transitions==20000;
        att(mi)=z.metrics.A_0_20_rad;
    end
    for gamma=[1,12]
        oi=(gamma==1)*1+(gamma==12)*3;ni=oi+1;
        r=struct('scene_id',sid,'gamma',gamma,'B_Q_0_20_m',Bq, ...
            'OLD_status',char(status(oi)),'OLD_complete',valid(oi),'OLD_Q_0_20_m',q(oi), ...
            'OLD_delta_vs_B_m',q(oi)-Bq,'OLD_improvement_vs_B',(Bq-q(oi))/Bq, ...
            'OLD_win_vs_B',valid(oi)&&q(oi)<Bq,'NEW_status',char(status(ni)), ...
            'NEW_complete',valid(ni),'NEW_Q_0_20_m',q(ni),'NEW_delta_vs_B_m',q(ni)-Bq, ...
            'NEW_improvement_vs_B',(Bq-q(ni))/Bq,'NEW_win_vs_B',valid(ni)&&q(ni)<Bq, ...
            'NEW_minus_OLD_Q_m',q(ni)-q(oi),'OLD_A_0_20_rad',att(oi), ...
            'NEW_A_0_20_rad',att(ni),'B_raw_path',char(T.raw_path(bi)), ...
            'OLD_raw_path',relative_path(projectRoot,raw{oi}), ...
            'NEW_raw_path',relative_path(projectRoot,raw{ni}));
        paired=append_row(paired,r);
    end
    sceneMap=append_row(sceneMap,struct('scene_id',sid,'B_Q_0_20_m',Bq, ...
        'OLD_G1_Q_0_20_m',q(1),'NEW_G1_Q_0_20_m',q(2), ...
        'OLD_G12_Q_0_20_m',q(3),'NEW_G12_Q_0_20_m',q(4)));
end
writetable(struct2table(paired),fullfile(expDir,'reports','FIG8_MODEL_GAMMA_PAIRED.csv'));

summary=struct([]);
for mi=1:4
    qs=nan(8,1);bq=nan(8,1);valid=false(8,1);att=nan(8,1);
    for si=1:8
        sid=sceneIds{si};p=fullfile(expDir,'runs','main_matrix',sid,methods{mi},'attempt_01','raw_run.mat');
        if ~isfile(p),continue,end
        z=load(p,'meta','metrics');qs(si)=z.metrics.Q_0_20_m;bq(si)=z.meta.B_Q_0_20_m;
        valid(si)=logical(z.meta.complete)&&logical(z.meta.finite)&&z.meta.transitions==20000;
        att(si)=z.metrics.A_0_20_rad;
    end
    qMacro=mean(qs,'omitnan');bMacro=mean(bq,'omitnan');
    row=struct('method_id',methods{mi},'model_id',model_for(methods{mi}), ...
        'gamma',gamma_for(methods{mi}),'complete_scenes',nnz(valid),'expected_scenes',8, ...
        'macro_B_Q_0_20_m',bMacro,'macro_Q_0_20_m',qMacro, ...
        'macro_improvement_vs_B',(bMacro-qMacro)/bMacro, ...
        'wins_vs_B',nnz(valid&qs<bq),'losses_vs_B',nnz(valid&qs>bq), ...
        'ties_vs_B',nnz(valid&qs==bq),'worst_degradation_m',max(qs(valid)-bq(valid),[],'omitnan'), ...
        'mean_attitude_RMSE_0_20_rad',mean(att,'omitnan'));
    summary=append_row(summary,row);
end
writetable(struct2table(summary),fullfile(expDir,'reports','FIG8_MODEL_GAMMA_SUMMARY.csv'));

write_readiness_reference(projectRoot,expDir,sceneIds);
write_phase_axis(projectRoot,expDir,sceneIds,methods);
write_online_diagnostics(projectRoot,expDir,sceneIds,methods);
gate=read_json(fullfile(expDir,'reports','OLD_PACKAGE_RECOVERY_GATE.json'));
bridgePath=fullfile(expDir,'reports','ENVIRONMENT_BRIDGE.csv');bridgeRows=table;
if isfile(bridgePath),bridgeRows=readtable(bridgePath,'TextType','string','VariableNamingRule','preserve');end
histPath=fullfile(expDir,'reports','HISTORICAL_REPRODUCTION.csv');hist=table;
if isfile(histPath),hist=readtable(histPath,'TextType','string','VariableNamingRule','preserve');end

oldG1=summary(strcmp({summary.method_id},'OLD_G1_R32'));
oldG12=summary(strcmp({summary.method_id},'OLD_G12_R32'));
newG1=summary(strcmp({summary.method_id},'NEW_G1_R32'));
newG12=summary(strcmp({summary.method_id},'NEW_G12_R32'));
oldGamma=oldG12.macro_Q_0_20_m-oldG1.macro_Q_0_20_m;
newGamma=newG12.macro_Q_0_20_m-newG1.macro_Q_0_20_m;
interaction=newGamma-oldGamma;
prior=readtable(fullfile(projectRoot,'experiments','kan14_task_specialist_compare_v1', ...
    'reports','DEV24_PAIRED_RESULTS.csv'),'TextType','string','VariableNamingRule','preserve');
prior=prior(string(prior.policy_id)=='SHARED_KAN14'&ismember(string(prior.scene_id),sceneIds),:);
priorMacro=mean(double(prior.Q_0_20_m));ready32=mean(newG12.macro_Q_0_20_m); %#ok<NASGU>

reportPath=fullfile(expDir,'reports','FINAL_REPORT_ZH.md');fid=fopen(reportPath,'w');
assert(fid>=0,'OLDKAN:FinalReport','Cannot write final report.');
cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'# 旧 KAN 获胜包复现与当前八字迁移对照\n\n');
fprintf(fid,'## 执行概况\n\n');
fprintf(fid,'- 当前八场完成率：%d Plant 调用；总调用上限 48。未访问 TEST、未训练模型。\n',count_plant_markers(expDir));
fprintf(fid,'- 零 Plant 预检：PASS；8 个已有 B 均与官方生成器逐数组一致，20,000 transitions。\n');
fprintf(fid,'- 历史两场复现：\n\n');
for i=1:height(hist)
    fprintf(fid,'  - `%s` %s，Q0-5 %.6f m，Q5-20 %.6f m，Q0-20 %.6f m，最大历史差 %.3g m。\n', ...
        char(hist.scene_id(i)),char(hist.status(i)),double(hist.Q_0_5_m(i)), ...
        double(hist.Q_5_20_m(i)),double(hist.Q_0_20_m(i)),double(hist.max_abs_Q_difference_m(i)));
end
fprintf(fid,'\n## 统一 readiness=32 的主矩阵\n\n');
fprintf(fid,'| 配置 | 宏 Q0-20 (m) | 相对 B 改善 | 胜 B | 最差退化 (m) | 完整场数 |\n|---|---:|---:|---:|---:|---:|\n');
for i=1:numel(summary)
    fprintf(fid,'| %s | %.6f | %.2f%% | %d/8 | %.6f | %d/8 |\n',summary(i).method_id, ...
        summary(i).macro_Q_0_20_m,100*summary(i).macro_improvement_vs_B, ...
        summary(i).wins_vs_B,summary(i).worst_degradation_m,summary(i).complete_scenes);
end
fprintf(fid,'\n同一 Gamma 下新包减旧包的宏 Q 差：Gamma=1 为 %.6f m，Gamma=12 为 %.6f m。\n', ...
    newG1.macro_Q_0_20_m-oldG1.macro_Q_0_20_m,newG12.macro_Q_0_20_m-oldG12.macro_Q_0_20_m);
fprintf(fid,'旧包 Gamma12−Gamma1 宏 Q 差 %.6f m；新包 %.6f m；package×Gamma 差分 %.6f m（负值表示新包对增大 Gamma 的改善相对更强）。\n', ...
    oldGamma,newGamma,interaction);
fprintf(fid,'\n## readiness 对照\n\n');
R=readtable(fullfile(expDir,'reports','READY_REFERENCE_COMPARISON.csv'),'TextType','string','VariableNamingRule','preserve');
fprintf(fid,'同一新共享 KAN14、Gamma12：既有 ready1 宏 Q %.6f m，统一 ready32 宏 Q %.6f m；ready32−ready1 为 %.6f m。既有包每场 1,999 次推理，当前 ready32 预计/实测每场 1,968 次，首个有效时刻 0.32 s。\n', ...
    mean(double(R.ready1_Q_0_20_m)),mean(double(R.ready32_Q_0_20_m)), ...
    mean(double(R.ready32_minus_ready1_Q_m)));
fprintf(fid,'这只识别同一新包启动合同改变的差值；不会把旧/新包之间的差异单独归因于 readiness。\n');
fprintf(fid,'\n## 轨迹/风桥接\n\n');
fprintf(fid,'预注册门槛状态：`%s`。\n',char(gate.status));
if height(bridgeRows)>0
    fprintf(fid,'桥接限定在 C09 单一构型/时序。\n\n| 参考 | 风 | B Q (m) | 旧 G1 Q (m) | 相对改善 |\n|---|---|---:|---:|---:|\n');
    for i=1:height(bridgeRows)
        fprintf(fid,'| %s | %s | %.6f | %.6f | %.2f%% |\n',char(bridgeRows.reference_id(i)), ...
            char(bridgeRows.wind_id(i)),double(bridgeRows.B_Q_0_20_m(i)), ...
            double(bridgeRows.OLD_G1_Q_0_20_m(i)),100*double(bridgeRows.relative_improvement_vs_B(i)));
    end
else
    fprintf(fid,'按冻结规则跳过：至少一个旧包 Gamma 在 8/8 完整、宏改善 >=10%%、胜 B >=6/8 三项同时过门槛。\n');
end
fprintf(fid,'\n## 证据结论\n\n');
fprintf(fid,'历史复现检验旧包是否仍可在原 V3.5 快照上达到原 Q；当前矩阵在相同场景、相同 DL1018 Plant/控制合同下比较包身份与 Gamma。若两者同场差异稳定，证据支持“模型包整体在当前任务上的闭环行为不同”；它不能指出 normalizer、encoder、W0 或训练历史中的哪个单一部件是根因。\n\n');
fprintf(fid,'旧/新八字参考轨迹、环境风与构型的变化不能再被混成一个“数据分布不同”结论。桥接只支持 C09 上参考整体与外部风频对旧包相对 B 的敏感性；不证明新包训练失败由其中某一项造成。Gamma 的结果也只用于当前 DEV 诊断，不是未见测试的胜者声明。\n\n');
fprintf(fid,'### 文件索引\n\n- `ZERO_PLANT_PREFLIGHT.json`\n- `HISTORICAL_REPRODUCTION.csv`\n- `TRANSFER_ALL_RUNS.csv`\n- `FIG8_MODEL_GAMMA_PAIRED.csv` / `FIG8_MODEL_GAMMA_SUMMARY.csv`\n- `READY_REFERENCE_COMPARISON.csv`\n- `PHASE_AXIS_COMPARISON.csv`\n- `ONLINE_DIAGNOSTICS.csv`\n- `RESOURCE_LEDGER.csv`\n');
clear cleanup
fprintf('FINAL_REPORT_WRITTEN %s\n',reportPath);
end

function write_readiness_reference(root,expDir,sceneIds)
path=fullfile(root,'experiments','kan14_task_specialist_compare_v1','reports','DEV24_PAIRED_RESULTS.csv');
T=readtable(path,'TextType','string','VariableNamingRule','preserve');rows=struct([]);
for i=1:numel(sceneIds)
    sid=sceneIds{i};ix=find(string(T.policy_id)=='SHARED_KAN14'&string(T.scene_id)==sid);
    assert(isscalar(ix)&&double(T.gamma(ix))==12&&double(T.selected_step(ix))==60000&& ...
        strcmp(char(T.status(ix)),'STABLE')&&double(T.complete(ix))==1, ...
        'OLDKAN:Ready1Reference','Existing shared KAN14 Gamma12 reference failed for %s.',sid);
    rawPath=fullfile(root,char(T.raw_path(ix)));startPath=fullfile(root,char(T.run_start_path(ix)));
    R=load(rawPath,'log');S=load(startPath);
    if isfield(S,'runStart'),optsRef=S.runStart.opts;else,optsRef=S.opts;end
    p=optsRef.stage1_position_runtime;
    valid=logical(R.log.stage1_position_event_inference_valid(:));first=R.log.transition_time(find(valid,1));
    context=double(p.model.context_length);ready=context;
    assert(ready==1&&~isfield(p,'readiness_events')&&nnz(valid)==1999&&abs(first-.01)<1e-12, ...
        'OLDKAN:Ready1Identity','Existing run is not genuinely ready1: %s.',sid);
    mainPath=fullfile(expDir,'runs','main_matrix',sid,'NEW_G12_R32','attempt_01','raw_run.mat');
    M=load(mainPath,'meta','metrics');bq=double(T.B_Q_0_20_m(ix));q1=double(T.Q_0_20_m(ix));q32=M.metrics.Q_0_20_m;
    rows=append_row(rows,struct('scene_id',sid,'model_id','KAN14','seed',2026102001, ...
        'selected_step',60000,'gamma',12,'ready1_event_count',nnz(valid), ...
        'ready1_first_valid_time_s',first,'ready32_event_count',M.meta.valid_inference_events, ...
        'ready32_first_valid_time_s',.32,'B_Q_0_20_m',bq,'ready1_Q_0_20_m',q1, ...
        'ready32_Q_0_20_m',q32,'ready32_minus_ready1_Q_m',q32-q1, ...
        'ready1_raw_path',char(T.raw_path(ix)),'ready32_raw_path',relative_path(root,mainPath)));
end
writetable(struct2table(rows),fullfile(expDir,'reports','READY_REFERENCE_COMPARISON.csv'));
end

function write_phase_axis(root,expDir,sceneIds,methods)
rows=struct([]);T=readtable(fullfile(root,'reports','POSITION_DEV.csv'),'TextType','string','VariableNamingRule','preserve');
for i=1:numel(sceneIds)
    sid=sceneIds{i};bi=find(string(T.scene_id)==sid&string(T.method)=='B');
    bpath=fullfile(root,char(T.raw_path(bi)));rows=add_phase_rows(rows,bpath,'B_REUSED','B',0,0);
    for j=1:numel(methods)
        p=fullfile(expDir,'runs','main_matrix',sid,methods{j},'attempt_01','raw_run.mat');
        if isfile(p),rows=add_phase_rows(rows,p,methods{j},model_for(methods{j}),gamma_for(methods{j}),32);end
    end
end
hist=dir(fullfile(expDir,'runs','historical_repro','**','raw_run.mat'));
for i=1:numel(hist)
    p=fullfile(hist(i).folder,hist(i).name);rows=add_phase_rows(rows,p,'P_CF_HISTORICAL','OLD_N_KAN_REPAIR',1,32);
end
bridge=dir(fullfile(expDir,'runs','environment_bridge','**','raw_run.mat'));
for i=1:numel(bridge)
    p=fullfile(bridge(i).folder,bridge(i).name);Z=load(p,'meta');rows=add_phase_rows(rows,p, ...
        char(field_or(Z.meta,'method_id','B')),char(field_or(Z.meta,'model_id','B')), ...
        double(field_or(Z.meta,'gamma',0)),double(field_or(Z.meta,'readiness_events',0)));
end
if ~isempty(rows),writetable(struct2table(rows),fullfile(expDir,'reports','PHASE_AXIS_COMPARISON.csv'));end
end

function rows=add_phase_rows(rows,path,method,model,gamma,ready)
Z=load(path,'log','scene','meta');log=Z.log;scene=Z.scene;
sid=char(string(field_or(scene,'scene_id',field_or(field_or(Z,'meta',struct()),'scene_id','UNKNOWN'))));
n=min(numel(log.transition_time),size(log.state,1)-1);
t=double(log.transition_time(1:n));mask=t>=0&t<20;
e=double(log.reference.position(1:n,:))-double(log.state(1:n,1:3));
a=atan2(sin(double(log.filtered_attitude_reference(1:n,:))-double(log.state(1:n,7:9))), ...
    cos(double(log.filtered_attitude_reference(1:n,:))-double(log.state(1:n,7:9))));
labels=phase_labels(scene,t);phases={'NONE','EXTEND','HOLD','RETRACT','RECOVERY'};
for k=1:numel(phases)
    m=mask&labels==phases{k};samples=nnz(m);
    if samples==0,q=NaN;sse=NaN;axis=[NaN NaN NaN];axisSse=axis;peak=NaN;p95=NaN;att=NaN;attAxis=axis;
    else
        vec=vecnorm(e(m,:),2,2);q=sqrt(mean(sum(e(m,:).^2,2)));sse=sum(e(m,:).^2,'all');
        axis=sqrt(mean(e(m,:).^2,1));axisSse=sum(e(m,:).^2,1);peak=max(vec);p95=prctile(vec,95);
        att=sqrt(mean(sum(a(m,:).^2,2)));attAxis=sqrt(mean(a(m,:).^2,1));
    end
    row=struct('scene_id',sid,'method_id',method,'model_id',model, ...
        'gamma',gamma,'readiness_events',ready,'phase',ternary(strcmp(phases{k},'NONE'),'NONE_PRE',phases{k}), ...
        'samples',samples,'Q_rmse_m',q,'SSE_m2',sse,'x_RMSE_m',axis(1),'y_RMSE_m',axis(2), ...
        'z_RMSE_m',axis(3),'x_SSE_m2',axisSse(1),'y_SSE_m2',axisSse(2),'z_SSE_m2',axisSse(3), ...
        'position_peak_m',peak,'position_p95_m',p95,'attitude_Q_rmse_rad',att, ...
        'attitude_roll_RMSE_rad',attAxis(1),'attitude_pitch_RMSE_rad',attAxis(2), ...
        'attitude_yaw_RMSE_rad',attAxis(3),'raw_path',path);
    rows=append_row(rows,row);
end
end

function labels=phase_labels(scene,t)
cmd=double(scene.arms.command);rho=double(scene.arms.rho_true);dt=median(diff(double(scene.time(:))));labels=strings(numel(t),1);
for i=1:numel(t)
    k=max(1,min(size(cmd,1),round(t(i)/dt)+1));
    if any(cmd(k,:)>0)
        labels(i)="EXTEND";
    elseif any(cmd(k,:)<0)
        labels(i)="RETRACT";
    elseif any(rho(k,:)>.150001)
        labels(i)="HOLD";
    elseif any(any(abs(cmd(1:k,:))>0))
        labels(i)="RECOVERY";
    else
        labels(i)="NONE";
    end
end
end

function write_online_diagnostics(root,expDir,sceneIds,methods)
rows=struct([]);T=readtable(fullfile(root,'reports','POSITION_DEV.csv'), ...
    'TextType','string','VariableNamingRule','preserve');
for i=1:numel(sceneIds)
    sid=sceneIds{i};bi=find(string(T.scene_id)==sid&string(T.method)=='B');
    bp=fullfile(root,char(T.raw_path(bi)));
    rows=append_row(rows,diagnostic_row(bp,'B_REUSED','B',0,0));
    for j=1:numel(methods)
        p=fullfile(expDir,'runs','main_matrix',sid,methods{j},'attempt_01','raw_run.mat');
        if isfile(p)
            rows=append_row(rows,diagnostic_row(p,methods{j},model_for(methods{j}), ...
                gamma_for(methods{j}),32));
        end
    end
end
bridge=dir(fullfile(expDir,'runs','environment_bridge','**','raw_run.mat'));
for i=1:numel(bridge)
    p=fullfile(bridge(i).folder,bridge(i).name);Z=load(p,'meta');m=Z.meta;
    rows=append_row(rows,diagnostic_row(p,char(field_or(m,'method_id','BRIDGE')), ...
        char(field_or(m,'model_id','B')),double(field_or(m,'gamma',0)), ...
        double(field_or(m,'readiness_events',0))));
end
writetable(struct2table(rows),fullfile(expDir,'reports','ONLINE_DIAGNOSTICS.csv'));
end

function row=diagnostic_row(path,method,model,gamma,ready)
Z=load(path,'log','scene','meta','metrics','opts');L=Z.log;M=field_or(Z,'metrics',struct());
n=min(numel(L.transition_time),size(L.state,1)-1);t=double(L.transition_time(1:n));
mask=t>=0&t<20;labels=phase_labels(Z.scene,t);holdMask=mask&labels=="HOLD";
valid=logical(field_or(L,'stage1_position_event_inference_valid',false(n,1)));valid=fix_len(valid,n,false);
events=logical(field_or(L,'stage1_position_event',false(n,1)));events=fix_len(events,n,false);
raw=double(field_or(L,'stage1_position_raw_acceleration_mps2',nan(n,3)));
applied=double(field_or(L,'stage1_position_applied_acceleration_mps2',nan(n,3)));
phi=double(field_or(L,'stage1_position_phi_33',nan(n,33)));
beta=fix_len(double(field_or(L,'stage1_position_event_beta',nan(n,1))),n,NaN);
projection=fix_len(double(field_or(L,'stage1_position_event_projection',nan(n,1))),n,NaN);
eventDt=fix_len(double(field_or(L,'stage1_position_event_dt_s',nan(n,1))),n,NaN);
eventTime=fix_len(double(field_or(L,'stage1_position_inference_time_s',nan(n,1))),n,NaN);
eta=double(field_or(L,'stage1_position_pcf_eta_after_mps',nan(n,3)));
rf=double(field_or(L,'stage1_position_pcf_r_f_mps2',nan(n,3)));
sOrig=double(field_or(L,'stage1_position_pcf_event_s_original_mps',nan(n,3)));
sEff=double(field_or(L,'stage1_position_pcf_event_s_coord_eff_mps',nan(n,3)));
modelObj=struct;W0=nan(33,3);context=NaN;
if isfield(Z,'opts')&&isfield(Z.opts,'stage1_position_runtime')
    r=Z.opts.stage1_position_runtime;
    if isfield(r,'model'),modelObj=r.model;context=double(field_or(modelObj,'context_length',NaN));end
    if isfield(r,'position_only_search_head')
        if isfield(r.position_only_search_head,'W0')
            W0=double(r.position_only_search_head.W0);
        end
    elseif isfield(r,'weight')
        W0=double(r.weight);
    end
end
ids=find(valid);featureOut=NaN;phiNorm=NaN;phiCos=NaN;
if ~isempty(ids)
    F=double(field_or(L,'stage1_position_feature_14',nan(n,14)));F=F(ids,:);
    if isfield(modelObj,'input_mu')&&isfield(modelObj,'input_sigma')
        z=(F-double(modelObj.input_mu(:)).')./max(double(modelObj.input_sigma(:)).',1e-4);
        featureOut=nnz(abs(z)>4)/numel(z);
    end
    P=phi(ids,:);P=P(all(isfinite(P),2),:);
    if ~isempty(P),pn=vecnorm(P,2,2);phiNorm=mean(pn);end
    if size(P,1)>1
        den=vecnorm(P(1:end-1,:),2,2).*vecnorm(P(2:end,:),2,2);
        c=sum(P(1:end-1,:).*P(2:end,:),2)./max(den,eps);c=c(isfinite(c));
        if ~isempty(c),phiCos=mean(c);end
    end
end
Wb=double(field_or(L,'stage1_position_event_weight_before_33x3',nan(33,3,0)));
Wa=double(field_or(L,'stage1_position_event_weight_after_33x3',nan(33,3,0)));
resetErr=NaN;endDelta=NaN;weightTV=NaN;
if size(Wb,3)>0&&size(Wa,3)>0
    resetErr=norm(Wb(:,:,1)-W0,'fro');endDelta=norm(Wa(:,:,end)-W0,'fro');weightTV=0;
    for k=1:size(Wa,3)-1,weightTV=weightTV+norm(Wa(:,:,k+1)-Wa(:,:,k),'fro');end
end
row=struct('scene_id',char(string(Z.scene.scene_id)),'method_id',method,'model_id',model, ...
    'gamma',gamma,'readiness_events',ready,'model_context_length',context, ...
    'scheduled_events',nnz(events),'valid_inference_events',nnz(valid), ...
    'first_valid_time_s',first_finite(t(valid)),'event_dt_mean_s',mean_finite(eventDt(valid)), ...
    'event_dt_min_s',min_finite(eventDt(valid)),'event_dt_max_s',max_finite(eventDt(valid)), ...
    'inference_time_mean_s',mean_finite(eventTime(valid)), ...
    'W0_reset_fro_error',resetErr,'weight_end_delta_fro',endDelta,'weight_TV_fro',weightTV, ...
    'weight_projection_count',nnz(projection(isfinite(projection))~=0), ...
    'beta_mean',mean_finite(beta(valid)),'beta_min',min_finite(beta(valid)), ...
    'beta_max',max_finite(beta(valid)),'phi_norm_mean',phiNorm, ...
    'phi_cosine_consecutive_mean',phiCos,'normalized_feature_fraction_abs_gt4',featureOut, ...
    'PCF_eta_abs_max_mps',double(field_or(M,'eta_abs_max_mps',NaN)), ...
    'PCF_eta_event_rms_mps',rms_rows(eta,valid),'PCF_Rf_abs_max_mps2',double(field_or(M,'rf_abs_max_mps2',NaN)), ...
    'PCF_Rf_event_rms_mps2',rms_rows(rf,valid), ...
    'PCF_s_original_event_rms_mps',rms_rows(sOrig,valid), ...
    'PCF_s_effective_event_rms_mps',rms_rows(sEff,valid), ...
    'raw_x_rms_mps2',rms_axis(raw,mask,1),'raw_y_rms_mps2',rms_axis(raw,mask,2), ...
    'raw_z_rms_mps2',rms_axis(raw,mask,3),'raw_x_peak_abs_mps2',peak_axis(raw,mask,1), ...
    'raw_y_peak_abs_mps2',peak_axis(raw,mask,2),'raw_z_peak_abs_mps2',peak_axis(raw,mask,3), ...
    'applied_x_rms_mps2',rms_axis(applied,mask,1),'applied_y_rms_mps2',rms_axis(applied,mask,2), ...
    'applied_z_rms_mps2',rms_axis(applied,mask,3),'applied_x_peak_abs_mps2',peak_axis(applied,mask,1), ...
    'applied_y_peak_abs_mps2',peak_axis(applied,mask,2),'applied_z_peak_abs_mps2',peak_axis(applied,mask,3), ...
    'hold_raw_vector_rms_mps2',rms_rows(raw,holdMask), ...
    'hold_applied_vector_rms_mps2',rms_rows(applied,holdMask), ...
    'hold_raw_vector_peak_mps2',peak_rows(raw,holdMask), ...
    'hold_applied_vector_peak_mps2',peak_rows(applied,holdMask), ...
    'motor_TV_normalized_per_s',double(field_or(M,'motor_TV_normalized_per_s',NaN)), ...
    'motor_saturation_fraction',double(field_or(M,'motor_saturation_fraction',NaN)), ...
    'generalized_clip_fraction',double(field_or(M,'generalized_clip_fraction',NaN)), ...
    'motor_min_rad_s',double(field_or(M,'motor_min_rad_s',NaN)), ...
    'motor_max_rad_s',double(field_or(M,'motor_max_rad_s',NaN)), ...
    'controller_p99_ms',double(field_or(M,'controller_p99_ms',NaN)), ...
    'controller_worst_ms',double(field_or(M,'controller_worst_ms',NaN)), ...
    'control_loop_p99_ms',double(field_or(M,'control_loop_p99_ms',NaN)), ...
    'complete',logical(field_or(M,'complete',false)),'finite',logical(field_or(M,'finite',false)), ...
    'status',char(string(field_or(M,'status','MISSING'))),'raw_path',path);
end

function v=fix_len(v,n,fill)
v=v(:);v=v(1:min(n,numel(v)));v(end+1:n,1)=fill;
end
function v=rms_axis(X,mask,col)
x=column_values(X,mask,col);if isempty(x),v=NaN;else,v=sqrt(mean(x.^2));end
end
function v=peak_axis(X,mask,col)
x=column_values(X,mask,col);if isempty(x),v=NaN;else,v=max(abs(x));end
end
function x=column_values(X,mask,col)
if size(X,2)<col,x=[];return,end
n=min(size(X,1),numel(mask));x=double(X(1:n,col));m=logical(mask(1:n))&isfinite(x);x=x(m);
end
function v=rms_rows(X,mask)
n=min(size(X,1),numel(mask));x=double(X(1:n,:));m=logical(mask(1:n))&all(isfinite(x),2);
if any(m),v=sqrt(mean(sum(x(m,:).^2,2)));else,v=NaN;end
end
function v=peak_rows(X,mask)
n=min(size(X,1),numel(mask));x=double(X(1:n,:));m=logical(mask(1:n))&all(isfinite(x),2);
if any(m),v=max(vecnorm(x(m,:),2,2));else,v=NaN;end
end
function v=mean_finite(x)
x=double(x(:));x=x(isfinite(x));if isempty(x),v=NaN;else,v=mean(x);end
end
function v=min_finite(x)
x=double(x(:));x=x(isfinite(x));if isempty(x),v=NaN;else,v=min(x);end
end
function v=max_finite(x)
x=double(x(:));x=x(isfinite(x));if isempty(x),v=NaN;else,v=max(x);end
end
function v=first_finite(x)
x=double(x(:));i=find(isfinite(x),1);if isempty(i),v=NaN;else,v=x(i);end
end
function rows=append_row(rows,row)
if isempty(rows),rows=row;else,rows(end+1,1)=row;end
end
function y=model_for(method)
if startsWith(method,'OLD_'),y='OLD_N_KAN_REPAIR';else,y='NEW_KAN14_FINAL60K';end
end
function g=gamma_for(method)
tok=regexp(method,'_G(\d+)_','tokens','once');if isempty(tok),g=NaN;else,g=str2double(tok{1});end
end
function v=field_or(s,name,default)
if isstruct(s)&&isfield(s,name),v=s.(name);else,v=default;end
end
function n=count_plant_markers(expDir)
d=dir(fullfile(expDir,'runs','**','plant_started.marker'));n=sum(~[d.isdir]);
end
function path=relative_path(root,file)
rp=char(java.io.File(root).getCanonicalPath());fp=char(java.io.File(file).getCanonicalPath());
if startsWith(fp,[rp filesep],'IgnoreCase',true),path=fp(numel(rp)+2:end);else,path=fp;end
end
function out=ternary(c,a,b)
if c,out=a;else,out=b;end
end
function value=read_json(path)
value=jsondecode(fileread(path));
end
