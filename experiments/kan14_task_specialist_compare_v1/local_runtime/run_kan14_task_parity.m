function summary=run_kan14_task_parity(projectRoot)
% Zero-Plant PyTorch/MATLAB parity and frozen controller-contract checks.
if nargin<1||isempty(projectRoot),projectRoot=pwd;end
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
out=fullfile(projectRoot,'experiments','kan14_task_specialist_compare_v1');
local=fullfile(out,'local_runtime');
addpath(genpath(fullfile(projectRoot,'matlab')));
addpath(genpath(local),'-begin');rehash;clear position_stage1_model_forward_v2
[cfg,~,resolved]=init_dl1018();
assert(strcmp(projectRoot,resolved),'KAN14TASK:Root','Unexpected project root.');
addpath(genpath(local),'-begin');rehash;clear position_stage1_model_forward_v2
assert(abs(cfg.plant.dt-.001)<1e-12&&cfg.rbf.runtime.position_update_hz==100, ...
    'KAN14TASK:Clock','Expected 1 ms Plant and 100 Hz position update.');
registryPath=fullfile(out,'manifests','package_registry.csv');
C=readcell(registryPath,'Delimiter',',','Encoding','UTF-8');
headers=string(C(1,:));headers(1)=erase(headers(1),char(65279));
assert(size(C,1)==5&&all(cellfun(@(r)str2double(celltext(C,r,headers,'fixture_count'))==64,num2cell(2:5))), ...
    'KAN14TASK:Packages','Expected four packages with 64 fixtures each.');
parityColumn=column_index(headers,'parity_status');
resolvedForward=which('position_stage1_model_forward_v2','-all');
if iscell(resolvedForward),resolvedText=strjoin(resolvedForward,newline);else,resolvedText=char(resolvedForward);end
assert(contains(lower(resolvedText),lower(local)),'KAN14TASK:Path','The local KAN inference adapter is not first on the path.');
rows=struct([]);
for i=1:size(C,1)-1
    rowIndex=i+1;
    packageId=celltext(C,rowIndex,headers,'package_id');policyId=celltext(C,rowIndex,headers,'policy_id');
    taskName=celltext(C,rowIndex,headers,'task');
    matPath=fullfile(projectRoot,strrep(celltext(C,rowIndex,headers,'mat_path'),'/',filesep));
    F=load(matPath);model=F.model;windows=double(F.windows);
    assert(double(F.fixture_count)==64&&isequal(size(windows),[14,32,64]), ...
        'KAN14TASK:FixtureShape','Package %s has an invalid parity fixture shape.',packageId);
    assert(strcmp(char(model.model_id),'KAN14')&&strcmp(char(model.architecture),'KAN')&& ...
        double(model.input_dim)==14&&double(model.window)==32&&double(model.context_length)==1, ...
        'KAN14TASK:ModelContract','Package %s is not the frozen current-frame KAN14.',packageId);
    phiError=0;outputError=0;readoutError=0;
    for q=1:64
        phi=position_stage1_model_forward_v2(model,windows(:,:,q));
        y=double(model.output_W).'*phi;
        phiError=max(phiError,max(abs(phi-double(F.expected_phi(:,q)))));
        outputError=max(outputError,max(abs(y-double(F.expected_output(:,q)))));
        readoutError=max(readoutError,max(abs(y-double(model.output_W).'*phi)));
    end
    opts=position_only_search_options(cfg,model,'FEATURE',12,1);
    p=opts.stage1_position_runtime;W0=double(model.output_W);
    assert(~opts.rbf_position_output_enabled&&~opts.rbf_position_update_enabled&& ...
        opts.rbf_attitude_enabled&&opts.rbf_attitude_output_enabled&&opts.rbf_attitude_update_enabled&& ...
        p.command_filter_coordination_v3_5.enabled&&p.update_enabled&& ...
        opts.position_rbf_frequency_hz==100&&norm(double(p.weight)-W0,'fro')<1e-12, ...
        'KAN14TASK:ControllerIsolation','Position replacement changed B attitude RBF/PCF/W0 contract.');
    h=p.position_only_search_head;
    assert(h.enabled&&strcmp(h.head_type,'FEATURE')&&h.gamma==12&&h.kappa==1&& ...
        h.encoder_frozen&&h.state_reset_each_episode, ...
        'KAN14TASK:HeadContract','Unexpected FEATURE head configuration.');
    % Verify output-before-update and the frozen state bounds/leakage law.
    phi=double(F.expected_phi(:,1));sEff=[.13;-.27;.41];dtUpdate=.01;beta=.63;state0=W0;
    [raw,applied,state1,~,~]=position_only_search_head_step( ...
        phi,W0,state0,'FEATURE',12,1,sEff,dtUpdate,beta,cfg.rbf.position.dmax);
    rawExpected=state0.'*phi;
    appliedExpected=beta*max(min(rawExpected,double(cfg.rbf.position.dmax(:))),-double(cfg.rbf.position.dmax(:)));
    stateExpected=state0+dtUpdate*(-12*beta*phi*(sEff.')-.002*state0);
    stateExpected=max(min(stateExpected,60),-60);
    headError=max([max(abs(raw-rawExpected)),max(abs(applied-appliedExpected)),max(abs(state1-stateExpected),[],'all')]);
    passed=phiError<=1e-5&&outputError<=1e-5&&readoutError<=1e-12&&headError<=1e-10;
    item=struct('package_id',packageId,'policy_id',policyId,'task',taskName, ...
        'seed',str2double(celltext(C,rowIndex,headers,'seed')),'selected_step',str2double(celltext(C,rowIndex,headers,'selected_step')),'fixture_count',64, ...
        'status',ternary(passed,'PASS','FAIL'),'max_phi_error',phiError,'max_output_error',outputError, ...
        'max_readout_identity_error',readoutError,'max_output_then_update_error',headError, ...
        'controller_contract_pass',true,'plant_starts',0,'resolved_inference_function',resolvedText, ...
        'tolerance_model_outputs',1e-5,'tolerance_head_identity',1e-10);
    if isempty(rows),rows=item;else,rows(end+1,1)=item;end %#ok<AGROW>
    package=fullfile(fileparts(matPath));
    write_json(fullfile(package,'matlab_parity.json'),item);
    E=jsondecode(fileread(fullfile(package,'export_report.json')));E.status=item.status;E.matlab_parity=item;
    write_json(fullfile(package,'export_report.json'),E);
    C{rowIndex,parityColumn}=item.status;
    fprintf('KAN14_TASK_PARITY %s %s fixtures=64 phi=%.3g output=%.3g head=%.3g status=%s\n', ...
        policyId,taskName,phiError,outputError,headError,item.status);
end
writecell(C,registryPath,'Delimiter',',','Encoding','UTF-8');
allPass=numel(rows)==4&&all(strcmp({rows.status},'PASS'));
summary=struct('status',ternary(allPass,'PASS','FAIL'),'package_count',numel(rows), ...
    'fixtures_per_package',64,'fixture_total',sum([rows.fixture_count]),'plant_starts',0, ...
    'controller_contract','FEATURE gamma=12 kappa=1 PCF=true; own W0; position RBF disabled; B attitude RBF retained; 100 Hz update; 1 ms Plant step', ...
    'packages',rows,'completed_at_utc',char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss.SSSXXX')));
write_json(fullfile(out,'reports','EXPORT_PARITY.json'),summary);
if ~allPass,error('KAN14TASK:ParityGate','One or more package parity checks failed.');end
statePath=fullfile(out,'state','state.json');state=jsondecode(fileread(statePath));
state.status='IN_PROGRESS';state.phase='ZERO_PLANT_PARITY_COMPLETE';state.parity='PASS';
state.packages_exported=4;state.updated_at_utc=summary.completed_at_utc;write_json(statePath,state);
fprintf('KAN14_TASK_PARITY_COMPLETE status=%s packages=%d fixtures=%d Plant=%d\n', ...
    summary.status,summary.package_count,summary.fixture_total,summary.plant_starts);
end

function write_json(path,value)
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
fid=fopen(path,'w','n','UTF-8');assert(fid>=0,'KAN14TASK:Write','Could not write %s.',path);
c=onCleanup(@()fclose(fid));fwrite(fid,jsonencode(value,'PrettyPrint',true),'char');fwrite(fid,newline,'char');
end

function y=ternary(c,a,b),if c,y=a;else,y=b;end,end
function i=column_index(headers,name)
i=find(headers==string(name),1);assert(~isempty(i),'KAN14TASK:Registry','Missing registry column %s.',name);
end
function value=celltext(C,row,headers,name)
i=column_index(headers,name);value=char(string(C{row,i}));
end
