function report=run_teacher_reuse_canaries(root,dryRun,mode)
% Resumable teacher-reuse six-scene canary modes; no TEST access.
if nargin<1||isempty(root),root=pwd;end
if nargin<2,dryRun=false;end
if nargin<3||isempty(mode),mode='ORIGINAL';end
extension=strcmpi(mode,'X20_EXTENSION');
officialFull=strcmpi(mode,'OFFICIAL_FULL');
belowRbf=strcmpi(mode,'BELOW_RBF');
frozenSix=strcmpi(mode,'FROZEN_SIX');
dev24Locked=strcmpi(mode,'DEV24_LOCKED');
assert(extension||officialFull||belowRbf||frozenSix||dev24Locked||strcmpi(mode,'ORIGINAL'),'MODEL:Mode','Unknown canary mode %s.',mode);
root=char(java.io.File(root).getCanonicalPath());out=fullfile(root,'experiments','teacher_reuse_model_screen_v1');
local=fullfile(out,'local_runtime');addpath(genpath(fullfile(root,'matlab')));addpath(genpath(local),'-begin');rehash;
[cfg,~,resolved]=init_dl1018();assert(strcmp(root,resolved),'MODEL:Root','Unexpected project root.');
addpath(genpath(local),'-begin');rehash;
if extension,parityPaths={fullfile(out,'reports','x20_extension_zero_plant_parity.json')};
elseif officialFull,parityPath=fullfile(out,'reports','official_selected_zero_plant_parity.json');
    parityPaths={parityPath};
elseif belowRbf,parityPaths={fullfile(out,'reports','rbf_qualified_zero_plant_parity.json')};
elseif frozenSix,parityPaths={fullfile(out,'reports','official_selected_zero_plant_parity.json'), ...
        fullfile(out,'reports','rbf_qualified_zero_plant_parity.json')};
elseif dev24Locked,parityPaths={fullfile(out,'reports','official_selected_zero_plant_parity.json'), ...
        fullfile(out,'reports','rbf_qualified_zero_plant_parity.json')};
else,parityPaths={fullfile(out,'reports','zero_plant_model_parity.json')};end
for pi=1:numel(parityPaths)
    pre=jsondecode(fileread(parityPaths{pi}));
    assert(strcmp(pre.status,'PASS')&&pre.plant_starts==0,'MODEL:ParityGate','Zero-Plant parity gate must pass.');
end
protocol=jsondecode(fileread(fullfile(out,'protocol.json')));head=protocol.upstream_position_head;
assert(strcmp(head.head_type,'FEATURE')&&head.gamma==12&&head.kappa==1&&head.PCF, ...
    'MODEL:Head','The frozen upstream FEATURE_G12_K1 + PCF head must be used.');
specs=readtable(fullfile(root,'configs','scene_specs.csv'),'TextType','string');
bridge=readtable(fullfile(root,'experiments','position_causal_repair_v1','manifests','BRIDGE6.csv'),'TextType','string');
bridgePair=readtable(fullfile(root,'experiments','position_causal_repair_v1','reports','D1_G04_PAIRED_ALL.csv'),'TextType','string');
finalBridge=readtable(fullfile(root,'experiments','position_causal_repair_v1','reports','D3_INITIAL_FINAL_BRIDGE.csv'),'TextType','string');
dev=readtable(fullfile(root,'reports','POSITION_DEV.csv'),'TextType','string');devB=dev(dev.method=="B",:);
ids=unique(bridge.scene_id,'stable');assert(numel(ids)==6&&height(devB)==24,'MODEL:CanaryInputs','Missing BRIDGE6 or DEV B references.');
statePath=fullfile(out,'state','state.json');state=load_state(statePath);if ~isfield(state,'started_at_utc')||isempty(state.started_at_utc),state.started_at_utc=utc_now();end
taskStart=datetime(state.started_at_utc,'InputFormat','yyyy-MM-dd''T''HH:mm:ss.SSSXXX','TimeZone','UTC','Locale','en_US');
ledger=fullfile(out,'RESOURCE_LEDGER.csv');if ~isfile(ledger),write_text(ledger,['timestamp_utc,phase,resource_type,identity,count,status,notes' newline]);end
if extension,models={'KAN20','GRU20','DSSM20'};seedList=[2026102001 2026102002];variants={'fast_screen'};
elseif officialFull,models={'MLP14','GRU14'};seedList=[2026102001 2026102002];variants={'best_teacher_val','final_step'};
elseif belowRbf,models={'KAN14','DSSM14','GRU20','DSSM20'};seedList=[2026102001 2026102002];variants={'best_teacher_val','final_step'};
elseif frozenSix,models={};seedList=[];variants={};
elseif dev24Locked,models={};seedList=[];variants={};
else,models={'MLP14','KAN14','TCN14','GRU14','DSSM14','MLP20','TCN20','TCN14_L128'};seedList=2026102001;variants={'fast_screen'};end
if belowRbf
    auth=jsondecode(fileread(fullfile(out,'reports','rbf_qualified_extension_authorization.json')));
    assert(strcmp(auth.status,'USER_AUTHORIZED_SCOPE_EXTENSION')&& ...
        isequal(string(models(:)),string(auth.additional_official_configurations(:))), ...
        'MODEL:ExtensionAuthorization','Missing authorization for the below-RBF official extension.');
end
rows=struct([]);scores=struct([]);
loopText=fileread(fullfile(local,'run_dl1018_closed_loop.m'));
assert(contains(loopText,'stage1PositionHistory=zeros(stage1ModelInputDim,stage1ModelContextLength);')&& ...
    contains(loopText,'feature=[feature14;x(k,4:6).'';stage1Preview.nominal_acceleration(:)];')&& ...
    contains(loopText,'stage1PositionHeldForceLog')&&contains(loopText,'stage1PositionEventDt'), ...
    'MODEL:RuntimeContract','Runtime must use causal X20 preview, variable context, event updates and held 1-kHz force.');
if frozenSix
    lock=jsondecode(fileread(fullfile(out,'reports','frozen_six_candidates_locked.json')));
    assert(strcmp(lock.status,'CANDIDATES_LOCKED_FOR_FROZEN_SIX')&&numel(lock.candidates)==2, ...
        'MODEL:FrozenLock','Frozen six-scene candidates are not locked.');
    assert(isequal(sort(string({lock.candidates.group})),sort(["CURRENT_FRAME" "TEMPORAL"]))&& ...
        numel(unique(string({lock.candidates.model_id})))==2, ...
        'MODEL:FrozenGroups','Lock must contain one distinct current-frame and one temporal candidate.');
    for ci=1:numel(lock.candidates)
        c=lock.candidates(ci);package=canary_package(out,'FROZEN_SIX',char(c.model_id),double(c.seed),char(c.checkpoint_kind));
        if any(strcmp(char(c.model_id),{'MLP14','GRU14'}))
            selection=jsondecode(fileread(fullfile(out,'reports','official_full_canary_selection.json')));
        else
            selection=jsondecode(fileread(fullfile(out,'reports','rbf_qualified_canary_selection.json')));
        end
        selected=selection.selected_best_package_per_config;
        si=find(strcmp({selected.model_id},char(c.model_id)),1);
        assert(~isempty(si)&&strcmp(selected(si).group_id,char(c.source_group))&& ...
            double(selected(si).seed)==double(c.seed)&&strcmp(selected(si).checkpoint_kind,char(c.checkpoint_kind)), ...
            'MODEL:FrozenPackageLock','Locked frozen package must be the official best package for %s.',char(c.model_id));
        q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=char(c.model_id);
        opts=position_only_search_options(cfg,model,head.head_type,head.gamma,head.kappa);
        opts.stage1_position_runtime.update_enabled=false;
        assert(~opts.stage1_position_runtime.update_enabled&&opts.rbf_attitude_update_enabled&& ...
            norm(opts.stage1_position_runtime.weight-double(model.output_W),'fro')<1e-12, ...
            'MODEL:FrozenIsolation','Frozen mode must disable only the neural position update.');
    end
elseif dev24Locked
    lock=jsondecode(fileread(fullfile(out,'reports','dev24_candidates_locked.json')));
    assert(strcmp(lock.status,'CANDIDATES_LOCKED_BEFORE_DEV24')&&numel(lock.candidates)==2&& ...
        isequal([lock.candidates.order],[1 2])&&numel(unique(string({lock.candidates.model_id})))==2, ...
        'MODEL:DevLock','DEV24 candidates/order must be locked for two distinct configurations.');
    for ci=1:numel(lock.candidates)
        c=lock.candidates(ci);assert(~logical(c.freeze_position_updates), ...
            'MODEL:DevMode','Locked candidates are expected to use the selected online package.');
        if any(strcmp(char(c.model_id),{'MLP14','GRU14'}))
            selection=jsondecode(fileread(fullfile(out,'reports','official_full_canary_selection.json')));
        else
            selection=jsondecode(fileread(fullfile(out,'reports','rbf_qualified_canary_selection.json')));
        end
        selected=selection.selected_best_package_per_config;si=find(strcmp({selected.model_id},char(c.model_id)),1);
        assert(~isempty(si)&&strcmp(selected(si).group_id,char(c.source_group))&& ...
            double(selected(si).seed)==double(c.seed)&&strcmp(selected(si).checkpoint_kind,char(c.checkpoint_kind)), ...
            'MODEL:DevPackageLock','Locked DEV package must match the selected online package for %s.',char(c.model_id));
        q=load(fullfile(canary_package(out,'FROZEN_SIX',char(c.model_id),double(c.seed),char(c.checkpoint_kind)), ...
            'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=char(c.model_id);
        opts=position_only_search_options(cfg,model,head.head_type,head.gamma,head.kappa);
        assert(opts.stage1_position_runtime.update_enabled&&opts.rbf_attitude_update_enabled&& ...
            norm(opts.stage1_position_runtime.weight-double(model.output_W),'fro')<1e-12, ...
            'MODEL:DevMode','Online position updates and original B attitude RBF must be enabled.');
    end
else
for mi=1:numel(models)
    modelId=models{mi};
    for si=1:numel(seedList)
        for vi=1:numel(variants)
            package=canary_package(out,mode,modelId,seedList(si),variants{vi});
            q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=modelId;
            opts=position_only_search_options(cfg,model,head.head_type,head.gamma,head.kappa);
            p=opts.stage1_position_runtime;
            assert(~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
                opts.rbf_attitude_enabled&&opts.rbf_attitude_output_enabled&&opts.rbf_attitude_update_enabled&& ...
                p.command_filter_coordination_v3_5.enabled&&norm(p.weight-double(model.output_W),'fro')<1e-12, ...
                'MODEL:ControllerIsolation','%s changed position-RBF, B attitude-RBF, PCF or own W0.',modelId);
        end
    end
end
end
if dryRun
    if dev24Locked
        write_json(fullfile(out,'reports','dev24_canary_preflight.json'),struct( ...
            'status','DEV24_PREFLIGHT_PASS','candidate_count',numel(lock.candidates), ...
            'scene_count',height(devB),'plant_starts',count_plants(out), ...
            'candidate_order',{{lock.candidates.dev_group_id}},'test_accessed',false));
        fprintf('DEV24_PREFLIGHT PASS candidates=%d scenes=%d Plant=%d\n',numel(lock.candidates),height(devB),count_plants(out));
        return
    end
    if frozenSix
        write_json(fullfile(out,'reports','frozen_six_canary_preflight.json'),struct( ...
            'status','FROZEN_SIX_PREFLIGHT_PASS','models',{{lock.candidates.model_id}}, ...
            'scene_count',numel(ids),'plant_starts',count_plants(out),'position_update_enabled',false, ...
            'attitude_rbf_update_enabled',true));
        fprintf('FROZEN_SIX_PREFLIGHT PASS models=%d scenes=%d Plant=%d\n',numel(lock.candidates),numel(ids),count_plants(out));
        return
    end
    contextLengths=zeros(1,numel(models)*numel(seedList)*numel(variants));j=0;
    for mi=1:numel(models)
        for si=1:numel(seedList)
            for vi=1:numel(variants)
                j=j+1;package=canary_package(out,mode,models{mi},seedList(si),variants{vi});
                q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');contextLengths(j)=double(q.model.context_length);
            end
        end
    end
    report=struct('status','CANARY_RUNTIME_PREFLIGHT_PASS','models',numel(models), ...
        'seeds',numel(seedList),'checkpoint_variants',numel(variants),'package_count',numel(contextLengths), ...
        'scene_count',numel(ids),'plant_starts',count_plants(out),'context_lengths',contextLengths);
    if extension,preflightPath=fullfile(out,'reports','x20_extension_canary_preflight.json');
    elseif officialFull,preflightPath=fullfile(out,'reports','official_full_canary_preflight.json');
    elseif belowRbf,preflightPath=fullfile(out,'reports','rbf_qualified_canary_preflight.json');
    else,preflightPath=fullfile(out,'reports','canary_runtime_preflight.json');end
    write_json(preflightPath,report);
    fprintf('CANARY_RUNTIME_PREFLIGHT PASS models=%d scenes=%d Plant=%d\n',numel(models),numel(ids),report.plant_starts);
    return
end
if extension
    report=run_x20_extension_groups(root,out,cfg,head,models,seedList,specs,ids,bridge,bridgePair,finalBridge,devB);
    return
end
if officialFull
    report=run_official_full_groups(root,out,cfg,head,models,seedList,variants,specs,ids,bridge,bridgePair,finalBridge,devB, ...
        'official_full',84+numel(models)*numel(seedList)*numel(variants)*numel(ids));
    return
end
if belowRbf
    report=run_official_full_groups(root,out,cfg,head,models,seedList,variants,specs,ids,bridge,bridgePair,finalBridge,devB, ...
        'rbf_qualified',count_plants(out)+numel(models)*numel(seedList)*numel(variants)*numel(ids));
    return
end
if frozenSix
    report=run_frozen_six_groups(root,out,cfg,head,specs,ids,bridge,bridgePair,finalBridge,devB,taskStart,lock);
    return
end
if dev24Locked
    report=run_locked_dev24(root,out,cfg,head,specs,devB,taskStart,lock);
    return
end
state.phase='SMALL_SCREEN_CANARY';state.status='IN_PROGRESS';state.head=head;state.plant_budget_max=198;
state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
for mi=1:numel(models)
    modelId=models{mi};package=fullfile(out,'models','fast_screen',modelId,'seed2026102001');
    q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=modelId;
    group=['SMALL_' modelId];[r,s]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,taskStart,48,group,'FEATURE',head.gamma,head.kappa,false,false);
    rows=append_rows(rows,r);scores=append_score(scores,s);
    persist_rows(rows,fullfile(out,'reports','small_canary_results.csv'));
    write_json(fullfile(out,'reports','small_canary_group_scores.json'),struct('groups',scores));
    append_ledger(out,'SMALL_SCREEN_CANARY','model',modelId,0,'SCREENED', ...
        sprintf('head=%s gamma=%g kappa=%g group_complete=%d',head.head_type,head.gamma,head.kappa,s.complete_stable));
    update_state(out,group,'SMALL_SCREEN_CANARY',count_plants(out),numel(rows),s);
end
current=scores(strcmp({scores.group_id},'SMALL_MLP14')|strcmp({scores.group_id},'SMALL_KAN14')|strcmp({scores.group_id},'SMALL_MLP20'));
temporal=scores(strcmp({scores.group_id},'SMALL_TCN14')|strcmp({scores.group_id},'SMALL_GRU14')| ...
    strcmp({scores.group_id},'SMALL_DSSM14')|strcmp({scores.group_id},'SMALL_TCN20')|strcmp({scores.group_id},'SMALL_TCN14_L128'));
bestCurrent=choose_best(current);bestTemporal=choose_best(temporal);
report=struct('status','SMALL_SCREEN_CANARY_COMPLETE','plant_starts',count_plants(out), ...
    'plant_budget_max',198,'head',head,'current_frame_winner',bestCurrent,'temporal_winner',bestTemporal, ...
    'group_scores',scores,'completed_runs',numel(rows),'expected_runs_if_all_valid',48, ...
    'selection_metric','complete finite stable equal-weight six-scene mean Q_0_20_m; same-scene B reported, not a pass gate', ...
    'next_stage','Train two seeds from scratch for each available group winner on all 1536 teacher TRAIN runs.');
write_json(fullfile(out,'reports','small_canary_selection.json'),report);
write_final_canary_report(out,report);
state.phase='SMALL_SCREEN_CANARY_COMPLETE';state.status='IN_PROGRESS';state.active_group='';state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
fprintf('SMALL_CANARY_FINAL current=%s temporal=%s starts=%d/198\n', ...
    field_or(bestCurrent,'group_id','NONE'),field_or(bestTemporal,'group_id','NONE'),count_plants(out));
end
function package=canary_package(out,mode,modelId,seed,variant)
if strcmpi(mode,'OFFICIAL_FULL')||strcmpi(mode,'BELOW_RBF')||strcmpi(mode,'FROZEN_SIX')
    package=fullfile(out,'models','official_export',modelId,sprintf('seed%d',seed),variant);
else
    package=fullfile(out,'models','fast_screen',modelId,sprintf('seed%d',seed));
end
end

function report=run_official_full_groups(root,out,cfg,head,models,seeds,variants,specs,ids,bridge,bridgePair,finalBridge,devB,prefix,planned)
% Compare all best/final packages for both full-fit seeds on the same six scenes.
started=datetime('now','TimeZone','UTC');rowsAll=struct([]);scores=struct([]);packages=struct([]);
stage=upper(prefix);if strcmp(prefix,'official_full'),groupPrefix='OFFICIAL';else,groupPrefix=stage;end
statePath=fullfile(out,'state','state.json');state=load_state(statePath);
state.phase=[stage '_CANARY'];state.status='IN_PROGRESS';state.head=head;
if isfield(state,'plant_budget_max'),state=rmfield(state,'plant_budget_max');end
state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();
write_json(statePath,state);resultsPath=fullfile(out,'reports',[prefix '_canary_results.csv']);
scorePath=fullfile(out,'reports',[prefix '_canary_seed_scores.json']);
for mi=1:numel(models)
    modelId=models{mi};
    for si=1:numel(seeds)
        seed=seeds(si);
        for vi=1:numel(variants)
            variant=variants{vi};package=canary_package(out,'OFFICIAL_FULL',modelId,seed,variant);
            q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=modelId;
            group=sprintf('%s_%s_SEED%d_%s',groupPrefix,modelId,seed,upper(variant));
            [r,s]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,started, ...
                planned,group,'FEATURE',head.gamma,head.kappa,false,false);
            rowsAll=append_rows(rowsAll,r);scores=append_score(scores,s);
            p=struct('model_id',modelId,'seed',seed,'checkpoint_kind',variant,'group_id',group);
            if isempty(packages),packages=p;else,packages(end+1,1)=p;end %#ok<AGROW>
            persist_rows(rowsAll,resultsPath);write_json(scorePath,struct('group_scores',scores));
            append_ledger(out,[stage '_CANARY'],'package',group,0,'SCREENED', ...
                sprintf('complete_stable=%d macro_Q=%.10g',s.complete_stable,s.macro_Q_0_20_m));
            update_state(out,group,[stage '_CANARY'],count_plants(out),numel(rowsAll),s);
        end
    end
end

selected=struct([]);
for mi=1:numel(models)
    modelId=models{mi};groupStart=string(groupPrefix)+"_"+string(modelId)+"_";
    ix=find(startsWith(string({scores.group_id}),groupStart));
    subset=scores(ix);ok=arrayfun(@(s)s.complete_stable&&isfinite(s.macro_Q_0_20_m),subset);
    if ~any(ok),continue;end
    valid=subset(ok);[~,bestIx]=min([valid.macro_Q_0_20_m]);best=valid(bestIx);
    meta=find(strcmp({packages.group_id},best.group_id),1);assert(~isempty(meta),'MODEL:PackageMeta','Missing selected package metadata.');
    item=packages(meta);item.macro_Q_0_20_m=best.macro_Q_0_20_m;
    item.same_scene_B_macro_Q_0_20_m=best.same_scene_B_macro_Q_0_20_m;
    item.delta_Q_vs_B_m=best.delta_Q_vs_B_m;item.complete_stable=best.complete_stable;
    if isempty(selected),selected=item;else,selected(end+1,1)=item;end %#ok<AGROW>
end
advance=cell(1,numel(selected));
for i=1:numel(selected),advance{i}=selected(i).model_id;end
report=struct('status',[upper(prefix) '_CANARY_COMPLETE'],'head',head,'package_scores',scores, ...
    'selected_best_package_per_config',selected,'results_csv',relpath(root,resultsPath), ...
    'selection_metric','Lowest complete stable equal-weight six-scene Q_0_20_m among both seeds x best/final checkpoints; same-scene B is reported.', ...
    'advance_to_frozen_six_scene',{advance},'package_count',numel(packages), ...
    'new_plant_starts_this_stage',sum([scores.new_plant_starts]), ...
    'cumulative_new_plant_starts',count_plants(out),'finished_at_utc',utc_now());
write_json(fullfile(out,'reports',[prefix '_canary_selection.json']),report);
state=load_state(statePath);state.phase=[upper(prefix) '_CANARY_COMPLETE'];state.status='IN_PROGRESS';
state.active_group='';state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
fprintf('%s_CANARY_COMPLETE packages=%d selected=%s cumulative_new_Plant=%d\n',upper(prefix), ...
    numel(packages),strjoin(advance,','),count_plants(out));
end

function report=run_frozen_six_groups(root,out,cfg,head,specs,ids,bridge,bridgePair,finalBridge,devB,started,lock)
statePath=fullfile(out,'state','state.json');state=load_state(statePath);
state.phase='FROZEN_SIX_CANARY';state.status='IN_PROGRESS';state.head=head;
if isfield(state,'plant_budget_max'),state=rmfield(state,'plant_budget_max');end
state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
allRows=struct([]);scores=struct([]);planned=count_plants(out)+numel(lock.candidates)*numel(ids);
resultsPath=fullfile(out,'reports','frozen_six_canary_results.csv');scorePath=fullfile(out,'reports','frozen_six_canary_scores.json');
for ci=1:numel(lock.candidates)
    c=lock.candidates(ci);modelId=char(c.model_id);seed=double(c.seed);variant=char(c.checkpoint_kind);
    package=canary_package(out,'FROZEN_SIX',modelId,seed,variant);
    q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=modelId;
    group=sprintf('FROZEN_%s_SEED%d_%s',modelId,seed,upper(variant));
    [r,s]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,started, ...
        planned,group,'FEATURE',head.gamma,head.kappa,false,true);
    allRows=append_rows(allRows,r);scores=append_score(scores,s);
    persist_rows(allRows,resultsPath);write_json(scorePath,struct('group_scores',scores));
    append_ledger(out,'FROZEN_SIX_CANARY','package',group,0,'SCREENED', ...
        sprintf('complete_stable=%d macro_Q=%.10g position_update_enabled=false',s.complete_stable,s.macro_Q_0_20_m));
    update_state(out,group,'FROZEN_SIX_CANARY',count_plants(out),numel(allRows),s);
end
ordered=scores;ok=arrayfun(@(s)s.complete_stable&&isfinite(s.macro_Q_0_20_m),ordered);ordered=ordered(ok);
if numel(ordered)==2,[~,ix]=sort([ordered.macro_Q_0_20_m]);ordered=ordered(ix);end
devOrder=cell(1,numel(ordered));for i=1:numel(ordered),devOrder{i}=ordered(i).group_id;end
report=struct('status','FROZEN_SIX_CANARY_COMPLETE','candidate_lock',lock.candidates, ...
    'group_scores',scores,'results_csv',relpath(root,resultsPath), ...
    'selection_metric','Lowest complete stable equal-weight six-scene Q_0_20_m; frozen runs disable only neural position updates.', ...
    'dev24_order_locked_before_dev',{devOrder},'additional_plant_starts',sum([scores.new_plant_starts]), ...
    'cumulative_new_plant_starts',count_plants(out),'finished_at_utc',utc_now());
write_json(fullfile(out,'reports','frozen_six_canary_selection.json'),report);
state=load_state(statePath);state.phase='FROZEN_SIX_CANARY_COMPLETE';state.status='IN_PROGRESS';
state.active_group='';state.active_scene='';state.active_run_id='';state.cumulative_new_plant_starts=count_plants(out);
state.updated_at_utc=utc_now();write_json(statePath,state);
fprintf('FROZEN_SIX_CANARY_COMPLETE candidates=%d cumulative_new_Plant=%d\n',numel(scores),count_plants(out));
end

function report=run_locked_dev24(root,out,cfg,head,specs,devB,taskStart,lock)
statePath=fullfile(out,'state','state.json');state=load_state(statePath);
state.phase='LOCKED_DEV24';state.status='IN_PROGRESS';state.head=head;
if isfield(state,'plant_budget_max'),state=rmfield(state,'plant_budget_max');end
state.active_group='';state.active_scene='';state.active_run_id='';state.cumulative_new_plant_starts=count_plants(out);
state.updated_at_utc=utc_now();write_json(statePath,state);
started=datetime('now','TimeZone','UTC');allRows=struct([]);candidateResults=struct([]);
resultsPath=fullfile(out,'reports','teacher_reuse_locked_dev24_results.csv');reportPath=fullfile(out,'reports','teacher_reuse_locked_dev24_result.json');
for ci=1:numel(lock.candidates)
    c=lock.candidates(ci);modelId=char(c.model_id);group=char(c.dev_group_id);
    package=canary_package(out,'FROZEN_SIX',modelId,double(c.seed),char(c.checkpoint_kind));
    q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=modelId;
    rows=struct([]);planned=count_plants(out)+height(devB)*(numel(lock.candidates)-ci+1);
    for si=1:height(devB)
        sceneId=char(devB.scene_id(si));spec=specs(specs.scene_id==sceneId,:);
        assert(height(spec)==1,'MODEL:DevScene','Expected one DEV spec for %s.',sceneId);
        b=baseline_row(group,sceneId,table(),table(),table(),devB);
        row=run_one(root,out,cfg,model,spec,'LOCKED_DEV',group,'FEATURE',head.gamma,head.kappa, ...
            b,started,planned,logical(c.freeze_position_updates));
        rows=append_rows(rows,row);allRows=append_rows(allRows,row);persist_rows(allRows,resultsPath);
        state=load_state(statePath);state.phase='LOCKED_DEV24';state.active_group=group;state.active_scene=sceneId;
        state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
    end
    full=numel(rows)==height(devB)&&all([rows.complete])&&all([rows.finite])&& ...
        all([rows.transitions]==20000)&&all(strcmp({rows.status},'STABLE'))&&all(isfinite([rows.Q_0_20_m]));
    qMacro=NaN;bMacro=mean([rows.B_Q_0_20_m]);if full,qMacro=mean([rows.Q_0_20_m]);end
    pass=full&&isfinite(qMacro)&&qMacro<bMacro;
    item=struct('order',double(c.order),'group_id',group,'model_id',modelId,'seed',double(c.seed), ...
        'checkpoint_kind',char(c.checkpoint_kind),'freeze_position_updates',logical(c.freeze_position_updates), ...
        'scene_count',numel(rows),'expected_scene_count',height(devB),'complete_finite_stable',full, ...
        'macro_Q_0_20_m',qMacro,'same_scene_B_macro_Q_0_20_m',bMacro, ...
        'delta_Q_vs_B_m',qMacro-bMacro,'wins_vs_same_scene_B',nnz([rows.Q_0_20_m]<[rows.B_Q_0_20_m]), ...
        'strictly_below_B',pass,'plant_starts',sum(double([rows.plant_started])));
    if isempty(candidateResults),candidateResults=item;else,candidateResults(end+1,1)=item;end %#ok<AGROW>
    if pass,status='PASS';elseif ci<numel(lock.candidates),status='FIRST_CANDIDATE_DID_NOT_BEAT_B_SECOND_PENDING';else,status='NO_POSITION_WINNER';end
    report=struct('status',status,'candidate_lock',lock.candidates(1:ci), ...
        'candidate_results',candidateResults,'results_csv',relpath(root,resultsPath), ...
        'selection_rule',lock.dev_gate,'test_accessed',false, ...
        'cumulative_new_plant_starts',count_plants(out),'finished_at_utc',utc_now());
    write_json(reportPath,report);
    if pass,candidateStatus='PASS';else,candidateStatus='COMPLETE_NOT_BELOW_B';end
    append_ledger(out,'LOCKED_DEV24','candidate',group,sum(double([rows.plant_started])), ...
        candidateStatus,sprintf('Q=%.10g same_scene_B=%.10g',qMacro,bMacro));
    if pass,break;end
end
state=load_state(statePath);state.phase='LOCKED_DEV24_COMPLETE';state.status='COMPLETE';
state.active_group='';state.active_scene='';state.active_run_id='';state.cumulative_new_plant_starts=count_plants(out);
state.plant_starts=count_plants(out);state.final_result_status=report.status;state.completed_at_utc=utc_now();
for staleField={'active_fit','active_fit_step','active_fit_status'}
    if isfield(state,staleField{1}),state=rmfield(state,staleField{1});end
end
state.updated_at_utc=utc_now();write_json(statePath,state);
fprintf('LOCKED_DEV24_COMPLETE status=%s candidates_run=%d cumulative_new_Plant=%d\n', ...
    report.status,numel(candidateResults),count_plants(out));
end

function report=run_x20_extension_groups(root,out,cfg,head,models,seeds,specs,ids,bridge,bridgePair,finalBridge,devB)
% Each user-added X20 candidate is screened in both seeds on the same six scenes.
started=datetime('now','TimeZone','UTC');planned=84;rowsAll=struct([]);scores=struct([]);
statePath=fullfile(out,'state','state.json');state=load_state(statePath);
state.phase='X20_EXTENSION_CANARY';state.status='IN_PROGRESS';state.head=head;
state.plant_budget_max=198;state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();
write_json(statePath,state);
resultsPath=fullfile(out,'reports','x20_extension_canary_results.csv');
scorePath=fullfile(out,'reports','x20_extension_canary_seed_scores.json');
for mi=1:numel(models)
    modelId=models{mi};
    for si=1:numel(seeds)
        seed=seeds(si);package=fullfile(out,'models','fast_screen',modelId,sprintf('seed%d',seed));
        q=load(fullfile(package,'matlab_model_and_parity.mat'),'model');model=q.model;model.model_id=modelId;
        group=sprintf('X20_%s_SEED%d',modelId,seed);
        [r,s]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,started, ...
            planned,group,'FEATURE',head.gamma,head.kappa,false,false);
        rowsAll=append_rows(rowsAll,r);scores=append_score(scores,s);
        persist_rows(rowsAll,resultsPath);write_json(scorePath,struct('group_scores',scores));
        append_ledger(out,'X20_EXTENSION_CANARY','model_seed',[modelId '_SEED' num2str(seed)],0, ...
            'SCREENED',sprintf('complete_stable=%d macro_Q=%.10g same_scene_B=%.10g', ...
            s.complete_stable,s.macro_Q_0_20_m,s.same_scene_B_macro_Q_0_20_m));
        update_state(out,group,'X20_EXTENSION_CANARY',count_plants(out),numel(rowsAll),s);
    end
end
base=jsondecode(fileread(fullfile(out,'reports','small_canary_selection.json')));
groups=struct([]);
for mi=1:numel(models)
    modelId=models{mi};seedMacro=NaN(1,numel(seeds));seedStable=false(1,numel(seeds));
    for si=1:numel(seeds)
        group=sprintf('X20_%s_SEED%d',modelId,seeds(si));ix=find(strcmp({scores.group_id},group),1);
        if ~isempty(ix),seedMacro(si)=scores(ix).macro_Q_0_20_m;seedStable(si)=scores(ix).complete_stable;end
    end
    if strcmp(modelId,'KAN20'),incumbent=base.current_frame_winner;
    else,incumbent=base.temporal_winner;end
    stable=numel(seedStable)==2&&all(seedStable)&&numel(rowsAll)>0;
    if stable,macro=mean(seedMacro);else,macro=NaN;end
    competitive=stable&&isfinite(macro)&&macro<=double(incumbent.macro_Q_0_20_m);
    if strcmp(modelId,'KAN20'),modelGroup='CURRENT';else,modelGroup='TEMPORAL';end
    item=struct('model_id',modelId,'group',modelGroup, ...
        'seed_ids',seeds,'seed_macro_Q_0_20_m',seedMacro,'seed_complete_stable',seedStable, ...
        'two_seed_mean_macro_Q_0_20_m',macro,'incumbent_model',char(incumbent.group_id), ...
        'incumbent_macro_Q_0_20_m',double(incumbent.macro_Q_0_20_m), ...
        'both_seeds_complete_stable',stable,'competitive_for_full_training',competitive);
    if isempty(groups),groups=item;else,groups(end+1,1)=item;end %#ok<AGROW>
end
advance={groups([groups.competitive_for_full_training]).model_id};
report=struct('status','X20_EXTENSION_CANARY_COMPLETE','head',head,'models',groups, ...
    'seed_group_scores',scores,'results_csv',relpath(root,resultsPath), ...
    'selection_rule','Both seeds must complete all six scenes finite and STABLE; their mean six-scene Q must be no worse than the frozen same-group winner.', ...
    'additional_plant_starts',sum([scores.new_plant_starts]), ...
    'cumulative_new_plant_starts',count_plants(out),'advance_to_full_training',{advance}, ...
    'plant_starts',count_plants(out),'finished_at_utc',utc_now());
write_json(fullfile(out,'reports','x20_extension_canary_selection.json'),report);
state=load_state(statePath);state.phase='X20_EXTENSION_CANARY_COMPLETE';state.status='IN_PROGRESS';
state.active_group='';state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(statePath,state);
fprintf('X20_EXTENSION_CANARY_COMPLETE competitive=%s Plant=%d/198\n',strjoin(advance,','),count_plants(out));
end

function write_final_canary_report(out,r)
lines={'# 教师复用模型快筛六场结果','', ...
    sprintf('状态：%s；新 Plant：%d/198。',r.status,r.plant_starts), ...
    sprintf('当前帧组优胜：%s；时序组优胜：%s。',field_or(r.current_frame_winner,'group_id','NONE'),field_or(r.temporal_winner,'group_id','NONE')), ...
    '按 BRIDGE6 六场完整、有限、稳定结果的等权宏 Q 选组；B 仅作同场参照，不要求小筛胜 B。', ...
    '六场是开发筛选，不是盲测；无效或物理硬停组不会进入全量教师训练。',''};
lines=[lines,{'| 模型组 | 完整稳定 | 宏 Q (m) | 同场 B 宏 Q (m) | 差值 (m) | 胜 B 场数 | 新 Plant |','|---|---:|---:|---:|---:|---:|---:|'}];
for i=1:numel(r.group_scores)
    s=r.group_scores(i);lines{end+1}=sprintf('| %s | %d/6 | %.9g | %.9g | %.9g | %d/6 | %d |', ...
        s.group_id,6*logical(s.complete_stable),s.macro_Q_0_20_m,s.same_scene_B_macro_Q_0_20_m, ...
        s.delta_Q_vs_B_m,s.wins,s.new_plant_starts); %#ok<AGROW>
end
write_text(fullfile(out,'reports','SMALL_CANARY_REPORT_ZH.md'),strjoin(lines,newline));
end

function [rows,score]=run_group(root,out,cfg,model,specs,ids,bridge,bridgePair,finalBridge,devB,taskStart,planned,group,headType,gamma,kappa,reuseFinal,freezePosition)
rows=struct([]);stop=false;dirGroup=fullfile(out,'runs',group);if ~isfolder(dirGroup),mkdir(dirGroup);end
if reuseFinal,assert(strcmp(headType,'FEATURE')&&gamma==1&&kappa==1,'POSSEARCH:Reuse','Invalid Final reuse.');end
for i=1:6
    if stop,break;end
    sceneId=char(ids(i));sceneDir=fullfile(dirGroup,sceneId);if ~isfolder(sceneDir),mkdir(sceneDir);end
    mp=fullfile(sceneDir,'metrics.json');
    if isfile(mp)
        saved=jsondecode(fileread(mp));row=saved.metrics_row;
        if ~logical(saved.source_reused),assert(isfile(fullfile(sceneDir,'raw_run.mat')),'POSSEARCH:MissingRaw','Missing raw log %s.',sceneId);end
    elseif reuseFinal
        f=finalBridge(finalBridge.scene_id==sceneId,:);spec=specs(specs.scene_id==sceneId,:);
        assert(height(f)==1&&height(spec)==1,'POSSEARCH:FinalRow','Missing original Final row.');
        b=baseline_row(group,sceneId,bridge,bridgePair,finalBridge,devB);
        row=make_reused_final_row(f,spec,model,b);write_json(mp,struct('metrics_row',row,'source_reused',true));
    else
        spec=specs(specs.scene_id==sceneId,:);b=baseline_row(group,sceneId,bridge,bridgePair,finalBridge,devB);
        row=run_one(root,out,cfg,model,spec,group,group,headType,gamma,kappa,b,taskStart,planned,freezePosition);
    end
    rows=append_rows(rows,row);if ~row.complete||~row.finite||~strcmp(row.status,'STABLE'),stop=true;end
end
score=score_six(rows,group,headType,gamma,kappa);emit_group(out,rows,score,planned,taskStart);
end

function row=run_one(root,out,cfg,model,spec,phase,group,headType,gamma,kappa,b,taskStart,planned,freezePosition)
sceneId=char(spec.scene_id);sceneDir=fullfile(out,'runs',group,sceneId);if ~isfolder(sceneDir),mkdir(sceneDir);end
raw=fullfile(sceneDir,'raw_run.mat');start=fullfile(sceneDir,'run_start.mat');marker=fullfile(sceneDir,'plant_started.marker');mp=fullfile(sceneDir,'metrics.json');
if isfile(mp)
    saved=jsondecode(fileread(mp));row=saved.metrics_row;assert(isfile(raw),'POSSEARCH:MissingRaw','Metrics without raw evidence.');return
end
if isfile(marker)&&~isfile(raw),error('POSSEARCH:InterruptedPlant','Plant marker exists without raw log at %s; do not rerun.',sceneId);end
if isfile(fullfile(sceneDir,'error.json'))&&~isfile(raw),error('POSSEARCH:PriorError','Inspect prior error at %s.',sceneDir);end
if isfile(raw)
    q=load(raw,'log','scene');log=q.log;scene=q.scene;assert(isfile(start),'POSSEARCH:MissingStart','Raw without run_start.');
    z=load(start,'runStart');rs=z.runStart;plantStarted=isfile(marker);
else
    generated=make_scenes_dl1018('GET',root,sceneId);scene=generated.scene;
    addpath(genpath(fullfile(out,'local_runtime')),'-begin');rehash;
    opts=feval('position_only_search_options',cfg,model,headType,gamma,kappa);
    if freezePosition
        opts.stage1_position_runtime.update_enabled=false;
        opts.stage1_position_runtime.position_only_search_head.online_updates_enabled=false;
        assert(~opts.stage1_position_runtime.update_enabled&&opts.rbf_attitude_update_enabled, ...
            'MODEL:FrozenIsolation','Frozen mode must disable only neural position updates.');
    end
    if contains(upper(group),'OFFICIAL_')||contains(upper(group),'RBF_QUALIFIED_')|| ...
            contains(upper(group),'FROZEN_')||contains(upper(group),'LOCKED_DEV')
        candidateFitStatus='OFFICIAL_TEACHER_FIT';
    else
        candidateFitStatus='SMALL_TEACHER_FIT';
    end
    rs=struct('contract_version','DL1018_V311_R2E_PAPER_FINAL','run_id',sprintf('POSONLY_%s_%s_G%g_K%g',phase,sceneId,gamma,kappa), ...
        'gate_id',group,'phase',phase,'split',char(spec.split),'collector_id','POSITION_ONLY_SEARCH', ...
        'model_id',char(model.model_id),'head_type',headType,'gamma',gamma,'kappa',kappa,'encoder_frozen',true, ...
        'candidate_fit_status',candidateFitStatus,'scene_spec',spec,'cfg',cfg,'opts',opts,'initial_state',scene.initial_state, ...
        'reused_B_run_id',char(b.run_id),'started_at_utc',utc_now());
    runStart=rs;save(start,'runStart','-v7');state=load_state(fullfile(out,'state','state.json'));
    state.active_group=group;state.active_scene=sceneId;state.active_run_id=rs.run_id;state.head_type=headType;
    state.gamma=gamma;state.kappa=kappa;state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();
    write_json(fullfile(out,'state','state.json'),state);opts.r2e_first_plant_step_marker=marker;
    try
        episode=@run_episode_dl1018;log=episode(scene,'P_A',cfg,opts,raw);plantStarted=isfile(marker);
    catch err
        plantStarted=isfile(marker);if plantStarted,append_ledger(out,phase,'Plant',rs.run_id,1,'ENGINEERING_ERROR',err.identifier);end
        write_json(fullfile(sceneDir,'error.json'),struct('identifier',err.identifier,'message',err.message,'plant_started',plantStarted,'scene_id',sceneId));rethrow(err)
    end
end
core=measure_pcf_dl1018(log,scene,double(rs.opts.stage1_position_runtime.weight));
met=metrics_dl1018(log,scene,spec,core,double(b.Q_0_20_m),double(field_or(b,'A_0_20_rad',NaN)),double(b.position_peak_m),true);
row=make_row(rs.run_id,phase,sceneId,char(spec.task),headType,gamma,kappa,char(model.model_id),log,core,met,b,plantStarted, ...
    relpath(root,raw),relpath(root,start),cfg.rbf.position.dmax);
if plantStarted,append_ledger(out,phase,'Plant',rs.run_id,1,char(log.status),sprintf('%s %s gamma=%g kappa=%g',headType,sceneId,gamma,kappa));end
write_json(mp,struct('metrics_row',row,'source_reused',false,'finished_at_utc',utc_now()));
if ~strcmp(phase,'LOCKED_DEV'),persist_rows(row,fullfile(out,'reports','SEARCH_ALL_RUNS.csv'));end
state=load_state(fullfile(out,'state','state.json'));state.active_group='';state.active_scene='';state.active_run_id='';
state.cumulative_new_plant_starts=count_plants(out);state.updated_at_utc=utc_now();write_json(fullfile(out,'state','state.json'),state);
fprintf('POSITION_SEARCH_RUN %s %s status=%s Q=%.9g B=%.9g starts=%d ETA=%s\n',group,sceneId,row.status,row.Q_0_20_m,row.B_Q_0_20_m,count_plants(out),eta_text(count_plants(out),planned,taskStart));
end

function row=make_row(id,phase,sceneId,task,headType,gamma,kappa,modelId,log,core,met,b,started,raw,start,dmax)
event=logical(log.stage1_position_event_inference_valid(:));rawHead=double(log.stage1_position_event_raw_acceleration_mps2);
biasBefore=double(field_or(log,'stage1_position_event_bias_before_mps2',zeros(3,nnz(event))));
biasAfter=double(field_or(log,'stage1_position_event_bias_after_mps2',zeros(3,nnz(event))));
biasDelta=0;if ~isempty(biasBefore)&&~isempty(biasAfter),biasDelta=nnz(vecnorm(biasAfter-biasBefore,2,1)>0);end
clipCount=0;if any(event),clipCount=nnz(any(abs(rawHead(event,:))>double(dmax(:)).'+1e-12,2));end
row=struct('run_id',id,'phase',phase,'scene_id',sceneId,'task',task,'head_type',headType,'gamma',gamma,'kappa',kappa, ...
    'model_id',modelId,'status',char(log.status),'complete',logical(core.complete),'finite',logical(core.finite), ...
    'transitions',double(core.transitions),'plant_started',logical(started),'Q_0_20_m',double(met.Q_0_20_m), ...
    'B_run_id',char(b.run_id),'B_raw_path',char(b.raw_path),'B_Q_0_20_m',double(b.Q_0_20_m), ...
    'delta_Q_vs_B_m',double(met.Q_0_20_m)-double(b.Q_0_20_m), ...
    'Q_5_20_m',double(met.Q_5_20_m),'position_axis_rmse_m',jsonencode(met.position_axis_rmse_m), ...
    'attitude_axis_rmse_rad',jsonencode(met.attitude_axis_rmse_rad),'A_0_20_rad',double(met.A_0_20_rad), ...
    'position_peak_m',double(met.position_peak_m),'position_p95_m',double(met.position_p95_m), ...
    'B_position_peak_m',double(b.position_peak_m),'motor_TV_normalized_per_s',double(met.motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(met.motor_saturation_fraction),'generalized_clip_fraction',double(met.generalized_clip_fraction), ...
    'motor_min_rad_s',double(met.motor_min_rad_s),'motor_max_rad_s',double(met.motor_max_rad_s), ...
    'controller_p99_ms',double(met.controller_p99_ms),'controller_worst_ms',double(met.controller_worst_ms), ...
    'position_head_update_count',double(met.position_head_update_count),'position_head_projection_count',double(met.position_head_projection_count), ...
    'bias_update_count',biasDelta,'head_output_clip_count',clipCount, ...
    'bias_projection_count',nnz(double(field_or(log,'stage1_position_event_bias_projection',zeros(numel(log.transition_time),1)))~=0), ...
    'bias_final_mps2',jsonencode(double(field_or(log,'stage1_position_search_final_bias_mps2',zeros(3,1)))), ...
    'safety_stop_reason',char(met.safety_stop_reason),'source','NEW_PLANT','raw_path',raw,'run_start_path',start, ...
    'phase_metrics_json',char(met.phase_metrics_json));
end
function row=make_reused_final_row(f,spec,model,b)
row=struct('run_id',char(f.run_id),'phase','FEATURE_G1_K1','scene_id',char(spec.scene_id),'task',char(spec.task), ...
    'head_type','FEATURE','gamma',1,'kappa',1,'model_id',char(model.model_id),'status',char(f.status_final), ...
    'complete',parse_bool(f.complete_final),'finite',parse_bool(f.finite_final),'transitions',double(f.transitions), ...
    'plant_started',false,'Q_0_20_m',double(f.Final_Q_0_20_m),'B_run_id',char(b.run_id),'B_raw_path',char(b.raw_path), ...
    'B_Q_0_20_m',double(f.B_Q_0_20_m), ...
    'delta_Q_vs_B_m',double(f.Final_Q_0_20_m)-double(f.B_Q_0_20_m),'Q_5_20_m',NaN, ...
    'position_axis_rmse_m',jsonencode([f.Final_axis_rmse_x_m f.Final_axis_rmse_y_m f.Final_axis_rmse_z_m]), ...
    'attitude_axis_rmse_rad','[]','A_0_20_rad',double(f.Final_A_0_20_rad), ...
    'position_peak_m',double(f.Final_position_peak_m),'position_p95_m',double(f.Final_position_p95_m), ...
    'B_position_peak_m',double(b.position_peak_m),'motor_TV_normalized_per_s',double(f.Final_motor_TV_normalized_per_s), ...
    'motor_saturation_fraction',double(f.Final_motor_saturation_fraction),'generalized_clip_fraction',double(f.Final_generalized_clip_fraction), ...
    'motor_min_rad_s',NaN,'motor_max_rad_s',NaN,'controller_p99_ms',NaN,'controller_worst_ms',NaN, ...
    'position_head_update_count',NaN,'position_head_projection_count',NaN,'bias_update_count',0,'head_output_clip_count',NaN, ...
    'bias_projection_count',0,'bias_final_mps2','[0,0,0]', ...
    'safety_stop_reason','','source','REUSED_VERIFIED_ORIGINAL_FINAL','raw_path',char(f.raw_path), ...
    'run_start_path','experiments/position_causal_repair_v1/runs/D3_FINAL_INITIAL_BRIDGE','phase_metrics_json','[]');
end

function b=baseline_row(group,sceneId,bridge,bridgePair,finalBridge,devB)
if contains(group,'LOCKED_DEV')
    z=devB(devB.scene_id==sceneId,:);assert(height(z)==1,'POSSEARCH:BRow','Missing DEV B for %s.',sceneId);
    b=struct('run_id',char(z.run_id),'Q_0_20_m',double(z.Q_0_20_m),'A_0_20_rad',double(z.A_0_20_rad), ...
        'position_peak_m',double(z.position_peak_m),'complete',parse_bool(z.complete),'finite',parse_bool(z.finite), ...
        'raw_path',char(z.raw_path));
else
    z=finalBridge(finalBridge.scene_id==sceneId,:);assert(height(z)==1,'POSSEARCH:BRow','Missing bridge B for %s.',sceneId);
    bp=bridgePair(bridgePair.scene_id==sceneId,:);bm=bridge(bridge.scene_id==sceneId&bridge.role=="B",:);
    assert(height(bp)==1&&height(bm)==1&&abs(double(bp.B_Q_0_20_m)-double(z.B_Q_0_20_m))<1e-9, ...
        'POSSEARCH:BPairIdentity','D3/D1 B baseline mismatch for %s.',sceneId);
    b=struct('run_id',char(bm.run_id),'Q_0_20_m',double(bp.B_Q_0_20_m),'A_0_20_rad',double(bp.B_A_0_20_rad), ...
        'position_peak_m',double(bp.B_position_peak_m),'complete',parse_bool(bp.B_complete), ...
        'finite',parse_bool(bp.B_finite),'raw_path',char(bm.raw_path));
end
assert(b.complete&&b.finite&&isfinite(b.Q_0_20_m),'POSSEARCH:BStatus','Invalid same-scene B for %s.',sceneId);
end
function score=score_six(rows,group,headType,gamma,kappa)
full=numel(rows)==6&&all([rows.complete])&&all([rows.finite])&&all([rows.transitions]==20000)&& ...
    all(strcmp({rows.status},'STABLE'))&&all(isfinite([rows.Q_0_20_m]));
q=NaN;b=mean([rows.B_Q_0_20_m]);if full,q=mean([rows.Q_0_20_m]);end
score=struct('group_id',group,'head_type',headType,'gamma',gamma,'kappa',kappa,'n',numel(rows), ...
    'expected_n',6,'complete_stable',full,'macro_Q_0_20_m',q,'same_scene_B_macro_Q_0_20_m',b, ...
    'delta_Q_vs_B_m',q-b,'wins',nnz([rows.Q_0_20_m]<[rows.B_Q_0_20_m]), ...
    'new_plant_starts',sum(double([rows.plant_started])));
end
function best=choose_best(scores)
best=[];if isempty(scores),return;end
ok=arrayfun(@(s)s.complete_stable&&isfinite(s.macro_Q_0_20_m),scores);scores=scores(ok);
if isempty(scores),return;end
[~,i]=min([scores.macro_Q_0_20_m]);best=scores(i);
end
function a=append_rows(a,b)
if isempty(b),return;elseif isempty(a),a=b(:);else,a=[a(:);b(:)];end
end
function a=append_score(a,b)
if isempty(a),a=b(:);elseif ~isempty(b),a=[a(:);b(:)];end
end
function persist_rows(rows,path)
if isempty(rows),return;end
writetable(struct2table(rows,'AsArray',true),path);
end
function emit_group(out,rows,s,planned,taskStart)
valid=~isempty(rows)&&all([rows.complete])&&all([rows.finite])&&all(strcmp({rows.status},'STABLE'));
q=NaN;b=NaN;if ~isempty(rows),b=mean([rows.B_Q_0_20_m]);if valid&&numel(rows)==6,q=mean([rows.Q_0_20_m]);end,end
txt=sprintf('POSITION_SEARCH_SIX %s head=%s gamma=%g kappa=%g stable=%d/6 macro_Q=%.10g same_scene_B=%.10g starts=%d/%d ETA=%s\n', ...
    s.group_id,s.head_type,s.gamma,s.kappa,nnz([rows.complete]&[rows.finite]&strcmp({rows.status},'STABLE')),q,b,count_plants(out),planned,eta_text(count_plants(out),planned,taskStart));
for i=1:numel(rows),txt=[txt sprintf('  %s Q=%.10g B=%.10g delta=%.10g status=%s source=%s\n', ...
        rows(i).scene_id,rows(i).Q_0_20_m,rows(i).B_Q_0_20_m,rows(i).delta_Q_vs_B_m,rows(i).status,rows(i).source)];end %#ok<AGROW>
txt=[txt sprintf('  cumulative_new_Plant=%d/%d remaining_estimate=%s\n',count_plants(out),planned,eta_text(count_plants(out),planned,taskStart))];
log_progress(out,txt);fprintf('%s',txt);
end
function emit_dev_chunk(out,chunk,allRows,headType,gamma,kappa,plants,planned,taskStart)
chunkStable=numel(chunk)==6&&all([chunk.complete])&&all([chunk.finite])&&all(strcmp({chunk.status},'STABLE'));
chunkQ=NaN;chunkB=mean([chunk.B_Q_0_20_m]);if chunkStable,chunkQ=mean([chunk.Q_0_20_m]);end
cumStable=~isempty(allRows)&&all([allRows.complete])&&all([allRows.finite])&&all(strcmp({allRows.status},'STABLE'));
cumQ=NaN;cumB=mean([allRows.B_Q_0_20_m]);if cumStable,cumQ=mean([allRows.Q_0_20_m]);end
txt=sprintf('POSITION_SEARCH_DEV_SIX head=%s gamma=%g kappa=%g completed=%d/24 chunk_stable=%d/6 chunk_Q=%.10g chunk_B=%.10g cumulative_Q=%.10g cumulative_B=%.10g starts=%d/%d ETA=%s\n', ...
    headType,gamma,kappa,numel(allRows),nnz([chunk.complete]&[chunk.finite]&strcmp({chunk.status},'STABLE')),chunkQ,chunkB,cumQ,cumB,plants,planned,eta_text(plants,planned,taskStart));
for i=1:numel(chunk),txt=[txt sprintf('  %s Q=%.10g B=%.10g delta=%.10g status=%s\n', ...
    chunk(i).scene_id,chunk(i).Q_0_20_m,chunk(i).B_Q_0_20_m,chunk(i).delta_Q_vs_B_m,chunk(i).status)];end %#ok<AGROW>
log_progress(out,txt);fprintf('%s',txt);
end
function candidate=make_candidate(best,model,cfg)
candidate=struct('candidate_id',sprintf('POSITION_%s_G%g_K%g',best.head_type,best.gamma,best.kappa), ...
    'head_type',best.head_type,'gamma',best.gamma,'kappa',best.kappa,'selected_six_scene_group',best.group_id, ...
    'model_id',char(model.model_id),'model_origin','FINAL','encoder_frozen',true, ...
    'normalizer_id','POSITION_INITIAL_TRAIN_ONLY','position_rbf_output_enabled',false,'position_rbf_update_enabled',false, ...
    'attitude_controller','original_B_RBF_unchanged','pcf_enabled',true,'position_event_hz',100, ...
    'plant_dt_s',cfg.plant.dt,'beta_rise_s',cfg.rbf.position.beta_rise_time,'feature_dimension',33, ...
    'W0',double(model.output_W),'weight_initial',best.kappa*double(model.output_W),'weight_bound',60, ...
    'bias_initial',zeros(3,1),'bias_bound_mps2',3,'output_dmax_mps2',double(cfg.rbf.position.dmax(:)), ...
    'leakage',.002,'state_reset_each_episode',true,'selection_metric','24-scene equal-weight mean Q_0_20_m only', ...
    'development_set_evaluated',true);
if strcmp(candidate.head_type,'BIAS'),candidate.weight_initial=double(model.output_W);end
end
function write_final_report(out,r,rows,scores,model)
% Normalize persisted rows before grouping. Cached JSON rows are structs,
% while MATLAB callers may pass a table after a resume/import.
if istable(rows),rows=table2struct(rows);end
if istable(scores),scores=table2struct(scores);end
L={'# 只优化位置补偿器：闭环搜索结果','', ...
    ['状态：**' char(r.status) '**'], ...
    sprintf('候选：%s，gamma=%g，kappa=%g；冻结编码器：%s。',r.selected_candidate.head_type,r.selected_candidate.gamma,r.selected_candidate.kappa,char(model.model_id)), ...
    sprintf('DEV：%d/24 完整稳定；候选宏 Q=%.10g m，同场 B 宏 Q=%.10g m，差（候选−B）=%.10g m，相对变化=%.4f%%。', ...
       r.completed_dev_rows,r.macro_Q_0_20_m,r.same_scene_B_macro_Q_0_20_m,r.candidate_minus_B_m,100*r.relative_change_vs_B), ...
    sprintf('只按位置 Q 判定是否超过 B：%d。姿态只记录；编码器 fit=0；新 Plant=%d/78。', ...
       r.candidate_beats_B_by_position_only,r.cumulative_new_plant_starts), ...
    '这24场已作为开发集观察，不是盲测；不据此宣称未见场景泛化。','','## 按任务汇总','','| 任务 | 场数 | 宏Q (m) | 同场B宏Q (m) | 差值 (m) | X/Y/Z位置轴RMSE (m) | 胜场 |', ...
    '|---|---:|---:|---:|---:|---|---:|'};
tasks=unique(string({rows.task}),'stable');
for ti=1:numel(tasks)
    use=string({rows.task})==tasks(ti);sub=rows(use);
    % Keep the aggregation on a normalized table so both imported and cached
    % rows use the same, explicit variable names.
    subTable=struct2table(sub,'AsArray',true);
    axisCell=cell(height(subTable),1);
    for ai=1:height(subTable),axisCell{ai}=reshape(jsondecode(char(subTable.position_axis_rmse_m(ai))),1,[]);end
    axisMat=vertcat(axisCell{:});axisR=sqrt(mean(axisMat.^2,1));q=mean(subTable.Q_0_20_m);b=mean(subTable.B_Q_0_20_m);
    L{end+1}=sprintf('| %s | %d | %.8g | %.8g | %.8g | %.7g / %.7g / %.7g | %d |', ...
        char(tasks(ti)),height(subTable),q,b,q-b,axisR(1),axisR(2),axisR(3),nnz(subTable.Q_0_20_m<subTable.B_Q_0_20_m)); %#ok<AGROW>
end
L=[L,{'','## 24场逐场配对','','| 场景 | 任务 | Q (m) | 同场 B (m) | 差值 (m) | 位置轴RMSE (m) | 姿态轴RMSE (rad) | 峰值 (m) | 电机TV | 状态 |', ...
    '|---|---|---:|---:|---:|---|---|---:|---:|---|'}];
for i=1:numel(rows)
    L{end+1}=sprintf('| %s | %s | %.8g | %.8g | %.8g | %s | %s | %.8g | %.8g | %s |', ...
        char(rows(i).scene_id),char(rows(i).task),double(rows(i).Q_0_20_m),double(rows(i).B_Q_0_20_m),double(rows(i).delta_Q_vs_B_m), ...
        char(rows(i).position_axis_rmse_m),char(rows(i).attitude_axis_rmse_rad),double(rows(i).position_peak_m),double(rows(i).motor_TV_normalized_per_s),char(rows(i).status)); %#ok<AGROW>
end
L=[L,{'','## BRIDGE6搜索组','','| 组 | Head | gamma | kappa | 稳定完整 | 宏Q (m) | B宏Q (m) | 差值 (m) | 新Plant |','|---|---|---:|---:|---:|---:|---:|---:|---:|'}];
for i=1:numel(scores)
    L{end+1}=sprintf('| %s | %s | %g | %g | %d/6 | %.8g | %.8g | %.8g | %d |', ...
        scores(i).group_id,scores(i).head_type,scores(i).gamma,scores(i).kappa,6*logical(scores(i).complete_stable), ...
        scores(i).macro_Q_0_20_m,scores(i).same_scene_B_macro_Q_0_20_m,scores(i).delta_Q_vs_B_m,scores(i).new_plant_starts); %#ok<AGROW>
end
L=[L,{'','候选包见 models/position_only_candidate_package.mat。复现命令见 models/candidate_manifest.json。原B、Final、合同和G06均未修改。'}];
write_text(fullfile(out,'reports','FINAL_REPORT_ZH.md'),strjoin(L,newline));
end
function update_state(out,group,phase,plants,rows,score)
p=fullfile(out,'state','state.json');s=load_state(p);s.phase=phase;s.status='IN_PROGRESS';s.active_group=group;
s.active_scene='';s.active_run_id='';s.cumulative_new_plant_starts=plants;s.completed_search_rows=rows;s.updated_at_utc=utc_now();
if ~isempty(score),s.last_group_complete_stable=score.complete_stable;s.last_group_macro_Q_0_20_m=score.macro_Q_0_20_m;s.last_group_B_macro_Q_0_20_m=score.same_scene_B_macro_Q_0_20_m;end
write_json(p,s);
end
function s=load_state(p)
if isfile(p),s=jsondecode(fileread(p));else,s=struct;end
if ~isfield(s,'started_at_utc'),s.started_at_utc='';end
end
function update_state_done(out,status,plants,candidate)
p=fullfile(out,'state','state.json');s=load_state(p);s.phase='POSITION_SEARCH_COMPLETE';s.status=status;s.active_group='';s.active_scene='';s.active_run_id='';
s.cumulative_new_plant_starts=plants;s.candidate=candidate;s.updated_at_utc=utc_now();write_json(p,s);
end
function n=count_plants(out),d=dir(fullfile(out,'runs','**','plant_started.marker'));n=numel(d);end
function s=eta_text(plants,planned,t0)
if plants<1,s='待首组实测';return;end
elapsed=max(1,seconds(datetime('now','TimeZone','UTC')-t0));remaining=max(0,planned-plants)*elapsed/plants;
if remaining<3600,s=sprintf('约 %.0f 分钟',remaining/60);else,s=sprintf('约 %.1f 小时',remaining/3600);end
end
function append_ledger(out,phase,kind,id,count,status,notes)
p=fullfile(out,'RESOURCE_LEDGER.csv');if contains(fileread(p),char(id)),return;end
f=fopen(p,'a');fprintf(f,'%s,%s,%s,%s,%d,%s,%s\n',utc_now(),phase,kind,id,count,status,strrep(char(notes),',',';'));fclose(f);
end
function log_progress(out,s)
f=fopen(fullfile(out,'reports','progress.log'),'a');fwrite(f,s,'char');fclose(f);
end
function write_json(p,s)
f=fopen(p,'w');assert(f>0,'POSSEARCH:Write','Cannot write %s.',p);fwrite(f,jsonencode(s,'PrettyPrint',true),'char');fclose(f);
end
function write_text(p,s)
f=fopen(p,'w');assert(f>0,'POSSEARCH:Write','Cannot write %s.',p);fwrite(f,char(s),'char');fclose(f);
end
function x=utc_now(),x=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));end
function p=relpath(root,path),p=strrep(char(java.io.File(path).getCanonicalPath()),[root filesep],'');p=strrep(p,filesep,'/');end
function v=field_or(s,n,d),if isfield(s,n),v=s.(n);else,v=d;end,end
function y=parse_bool(x),if islogical(x),y=x;elseif isnumeric(x),y=x~=0;else,y=any(strcmpi(char(string(x)),{'true','1'}));end,end
function y=iff(c,a,b),if c,y=a;else,y=b;end,end
