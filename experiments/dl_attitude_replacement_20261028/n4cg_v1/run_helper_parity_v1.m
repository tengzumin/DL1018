function run_helper_parity_v1()
% R2025b no-Plant numerical parity for the frozen causal N4 gate helper.
here=fileparts(mfilename('fullpath'));addpath(here);
fixture=load(fullfile(here,'HELPER_PARITY_FIXTURE_v1.mat'));
n=size(fixture.u,2);s=position_compensation_n4_causal_gate_init();
uout=zeros(size(fixture.u));n4raw=zeros(size(fixture.u));diagv=zeros(5,n);
for k=1:n
    [s,uout(:,k),n4raw(:,k),d]=position_compensation_n4_causal_gate_step( ...
        s,fixture.u(:,k),true,fixture.time_s(k));
    diagv(:,k)=[d.Ebp;d.Elp;d.ratio;d.gtarget;d.g];
end
err_out=max(abs(uout(:)-fixture.expected_out(:)));
err_n4=max(abs(n4raw(:)-fixture.expected_n4_raw(:)));
err_diag=max(abs(diagv(:)-fixture.expected_diag(:)));
bpstate=zeros(3,size(fixture.bp_sos_reference,1),2);
lpstate=zeros(3,size(fixture.lp_sos_reference,1),2);
bp=zeros(size(fixture.u));lp=zeros(size(fixture.u));
for k=1:n
    [bpstate,bp(:,k)]=sos_local(fixture.bp_sos_reference,bpstate,fixture.u(:,k));
    [lpstate,lp(:,k)]=sos_local(fixture.lp_sos_reference,lpstate,fixture.u(:,k));
end
err_bp=max(abs(bp(:)-fixture.bp_filter_reference(:)));
err_lp=max(abs(lp(:)-fixture.lp_filter_reference(:)));
err=max([err_out,err_n4,err_diag,err_bp,err_lp]);
status='PASS_MATLAB_HELPER_PARITY';
if ~isfinite(err)||err>2e-10,status='FAIL_MATLAB_HELPER_PARITY';end
result=struct('status',status,'matlab_release',version('-release'), ...
    'events',n,'max_abs_error',err,'error_uout',err_out,'error_n4_raw',err_n4, ...
    'error_gate_diagnostics',err_diag,'error_bp_sos_reference',err_bp, ...
    'error_lp_sos_reference',err_lp,'plant_called',false,'full_runner_called',false);
fid=fopen(fullfile(here,'MATLAB_PARITY_RESULT_v1.json'),'w');
if fid<0,error('N4GateParity:Write','Cannot write parity result.');end
cleanup=onCleanup(@()fclose(fid));
fwrite(fid,[jsonencode(result),newline],'char');
if ~strcmp(status,'PASS_MATLAB_HELPER_PARITY'),error('N4GateParity:Fail','Numerical helper parity failed: %.3g',err);end
fprintf('N4 gate helper parity PASS (R%s), max error %.3g\n',version('-release'),err);
end

function [state,y]=sos_local(sos,state,x)
y=x;
for section=1:size(sos,1)
    row=sos(section,:);z1=state(:,section,1);z2=state(:,section,2);
    next=row(1)*y+z1;
    state(:,section,1)=row(2)*y-row(5)*next+z2;
    state(:,section,2)=row(3)*y-row(6)*next;
    y=next;
end
end
