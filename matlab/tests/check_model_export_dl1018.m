function report=check_model_export_dl1018(projectRoot,modality,package)
% Re-load the disk export and compare 64 windows with the frozen PyTorch outputs.
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
modality=lower(char(modality));package=lower(char(package));
 [cfg,~,~]=init_dl1018();
assert(ismember(modality,{'position','attitude'})&& ...
    ismember(package,{'initial','final_candidate','selected'}), ...
    'DL1018:ModelParityArgs','Unsupported model parity target.');
folder=fullfile(projectRoot,'models',modality,package);
fixture=load(fullfile(folder,'matlab_model_and_parity.mat'));
assert(fixture.fixture_count==64&&size(fixture.windows,3)==64, ...
    'DL1018:ParityCount','Expected exactly 64 windows.');
model=fixture.model;windows=double(fixture.windows);
phiError=0;outputError=0;physicalError=0;doubleReadoutError=0;headAppliedError=0;
Pplant=simulation_parameters(cfg,cfg.plant.arm_initial,zeros(4,1));P0=controller_parameters(cfg,Pplant,'fixed');
x0=zeros(12,1);ir=struct('euler',zeros(3,1),'euler_rate',zeros(3,1),'euler_acceleration',zeros(3,1));
[~,ai0]=attitude_bs_step(x0,ir,zeros(3,1),P0);ai0.J0=P0.inertia;
for q=1:64
    window=windows(:,:,q);
    if strcmp(modality,'position')
        phi=position_stage1_model_forward_v2(model,window);
        y=double(model.output_W).'*phi;
        readout=double(model.output_W).';
        expectedPhysical=double(fixture.expected_output(:,q));
        physicalError=max(physicalError,max(abs(y-expectedPhysical)));
        doubleReadoutError=max(doubleReadoutError,max(abs(y-readout*phi)));
        beta=double(fixture.beta(q));surface=double(fixture.surface(:,q));
        [rawP,appliedP,~,~,~]=position_stage1_update_head_pcf_v3_5( ...
            phi,double(model.output_W),surface,.01,beta,[3;3;3],zeros(3,1),true);
        expectedAppliedP=beta*min(max(rawP,-[3;3;3]),[3;3;3]);
        headAppliedError=max(headAppliedError,max(abs(appliedP-expectedAppliedP)));
        assert(max(abs(rawP-double(model.output_W).'*phi))<=1e-12, ...
            'DL1018:PositionHeadOutput','Position Head output changed before update.');
    else
        [phi,W0,y]=attitude_model_feature_x29_v39(model,window);
        expectedPhysical=double(fixture.expected_output(:,q)).*double(model.D_A(:));
        physicalError=max(physicalError,max(abs(y.*double(model.D_A(:))-expectedPhysical)));
        doubleReadoutError=max(doubleReadoutError,max(abs(y-W0.'*phi)));
        beta=double(fixture.beta(q));surface=double(fixture.surface(:,q));ai=ai0;ai.surface=surface;
        [rawA,appliedA,tauA,deltaFrozen]=attitude_kan_head_step_v39( ...
            phi,W0,zeros(33,3),ai,beta,.01,double(model.dmax(:)),true,false);
        expectedAppliedA=min(max(rawA,-1),1);
        expectedTau=P0.inertia*(beta*(double(model.dmax(:)).*expectedAppliedA));
        headAppliedError=max(headAppliedError,max([abs(appliedA-expectedAppliedA);abs(tauA-expectedTau)]));
        assert(isequal(deltaFrozen,zeros(33,3)),'DL1018:FrozenAttitudeHead','Frozen DeltaW changed.');
        [~,~,~,deltaOnline]=attitude_kan_head_step_v39( ...
            phi,W0,zeros(33,3),ai,beta,.01,double(model.dmax(:)),true,true);
        assert(all(isfinite(deltaOnline),'all')&&norm(deltaOnline,'fro')<=.20+1e-12, ...
            'DL1018:OnlineAttitudeHead','Online DeltaW violates the source projection.');
        [rawPre,appliedPre,tauPre,deltaPre]=attitude_kan_head_step_v39( ...
            phi,W0,zeros(33,3),ai,beta,.01,double(model.dmax(:)),false,true);
        assert(max(abs(rawPre-W0.'*phi))<=1e-12&&all(appliedPre==0)&&all(tauPre==0)&& ...
            isequal(deltaPre,zeros(33,3)),'DL1018:AttitudeReadyBoundary','Pre-ready output or update is invalid.');
    end
    phiError=max(phiError,max(abs(phi-double(fixture.expected_phi(:,q)))));
    outputError=max(outputError,max(abs(y-double(fixture.expected_output(:,q)))));
end
if strcmp(modality,'position')
    entry=which('position_stage1_model_forward_v2','-all');
else
    entry=which('attitude_model_feature_x29_v39','-all');
end
if iscell(entry),entryText=strjoin(entry,newline);else,entryText=char(entry);end
isolated=contains(lower(entryText),lower(projectRoot))&&~contains(lower(entryText),'dl1009');
passed=phiError<=1e-5&&outputError<=1e-5&&physicalError<=1e-5&& ...
    doubleReadoutError<=1e-10&&headAppliedError<=1e-10&&isolated;
report=struct('gate_id',sprintf('MODEL_PARITY_%s_%s',upper(modality),upper(package)), ...
    'status',ternary(passed,'PASS','FAIL'),'modality',modality, ...
    'package',package,'fixture_count',64,'max_phi_error',phiError, ...
    'max_output_error',outputError,'max_physical_output_error',physicalError, ...
    'max_double_readout_error',doubleReadoutError,'max_head_applied_error',headAppliedError, ...
    'beta_values',unique(double(fixture.beta(:))).','boundary_feature_fixtures',8, ...
    'resolved_function',entryText, ...
    'path_isolation',isolated,'tolerance_float32',1e-5,'tolerance_double_readout',1e-10);
write_gate_report_dl1018(fullfile(folder,'matlab_parity.json'),report);
end

function y=ternary(c,a,b),if c,y=a;else,y=b;end,end
