function result=run_helper_parity_v2()
% Compare MATLAB event recurrence with independent SciPy plus 1-ms holds.
here=fileparts(mfilename('fullpath'));
addpath(fullfile(here,'candidate_runner_work','matlab','runtime'));
f=load(fullfile(here,'HELPER_PARITY_FIXTURE_v2.mat'));
assert(isequal(size(f.u),[3,1999,25])&&isequal(size(f.time_s),[1999,25]));
errOut=0;errN4=0;errDiag=0;errCoeff=0;
for scene=1:25
    s=position_compensation_n4_causal_gate_init();
    errCoeff=max([errCoeff;abs(s.bp_sos(:)-f.bp_sos(:));abs(s.lo_sos(:)-f.lo_sos(:))]);
    for k=1:1999
        [s,out,n4,d]=position_compensation_n4_causal_gate_step(s,f.u(:,k,scene),true,f.time_s(k,scene));
        diagv=[d.Ebp;d.Elo;d.ratio;d.gtarget;d.g];
        errOut=max(errOut,max(abs(out-f.expected_out(:,k,scene))));
        errN4=max(errN4,max(abs(n4-f.expected_n4_raw(:,k,scene))));
        errDiag=max(errDiag,max(abs(diagv-f.expected_diag(:,k,scene))));
    end
    assert(s.event_count==1999);
end
% The exact 1-kHz runner schedule: 0.01...19.99 s, no update at t=0.
s=position_compensation_n4_causal_gate_init();eventIndex=0;held=zeros(3,1);rawHeld=zeros(3,1);
for k=0:19999
    event=k>0&&mod(k,10)==0;
    if event
        eventIndex=eventIndex+1;u=f.u(:,eventIndex,1);
    else
        u=[99;-99;99];before=s;
    end
    [s,out,n4,~]=position_compensation_n4_causal_gate_step(s,u,event,k*.001);
    if event
        held=f.expected_out(:,eventIndex,1);rawHeld=f.expected_n4_raw(:,eventIndex,1);
    else
        assert(isequaln(s,before),'N4GateParity:NonEventState','A non-event changed internal state.');
    end
    errOut=max(errOut,max(abs(out-held)));errN4=max(errN4,max(abs(n4-rawHeld)));
end
assert(eventIndex==1999&&s.event_count==1999);
err=max([errOut,errN4,errDiag,errCoeff]);
assert(isfinite(err)&&err<=2e-10,'N4GateParity:Fail','Parity failed: %.17g',err);
result=struct('status','PASS_MATLAB_HELPER_PARITY_V2','matlab_release',version('-release'), ...
    'train_scene_count',24,'stress_scene_count',1,'events_per_scene',1999, ...
    'one_khz_transition_count',20000,'one_khz_event_count',eventIndex, ...
    'max_abs_error',err,'output_error',errOut,'n4_raw_error',errN4, ...
    'diagnostic_error',errDiag,'coefficient_error',errCoeff,'plant_calls',0);
path=fullfile(here,'MATLAB_PARITY_RESULT_v2.json');
assert(~isfile(path),'N4GateParity:NoOverwrite','Result already exists.');
fid=fopen(path,'w');assert(fid>=0);c=onCleanup(@()fclose(fid));
fwrite(fid,[jsonencode(result,'PrettyPrint',true),newline],'char');clear c;
fprintf('N4Gate V2 parity PASS R%s max %.3g\n',version('-release'),err);
end
