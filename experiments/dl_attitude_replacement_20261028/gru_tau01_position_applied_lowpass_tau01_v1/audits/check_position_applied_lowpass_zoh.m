function report=check_position_applied_lowpass_zoh(runtimeRoot)
% No-Plant arithmetic and event-clock checks for the 100-Hz output filter.
addpath(fullfile(runtimeRoot,'matlab','core'),'-begin');
addpath(fullfile(runtimeRoot,'matlab','models'),'-begin');
addpath(fullfile(runtimeRoot,'matlab','runtime'),'-begin');
tau=.1;dtEvent=.01;expectedAlpha=1-exp(-dtEvent/tau);
[first,alpha]=position_applied_accel_lowpass_zoh(zeros(3,1),[3;-2;1],dtEvent,tau);
assert(abs(alpha-expectedAlpha)<1e-14&&abs(alpha-.09516258196404043)<1e-14, ...
    'PositionLPF:TauUnits','At dt=10 ms and tau=0.1 s the exact coefficient must be 1-exp(-0.1).');
assert(norm(first-alpha*[3;-2;1],inf)<1e-14,'PositionLPF:InitialState','Filter initial state must be zero.');
[zero,~]=position_applied_accel_lowpass_zoh(zeros(3,1),zeros(3,1),dtEvent,tau);
assert(norm(zero,inf)==0,'PositionLPF:ZeroInput','Zero input from zero state must remain zero.');
[second,~]=position_applied_accel_lowpass_zoh(first,[3;-2;1],dtEvent,tau);
assert(norm(second-(1-(1-alpha)^2)*[3;-2;1],inf)<1e-13, ...
    'PositionLPF:ZOH','Repeated held input does not match the exact event-time recursion.');
alpha1ms=1-exp(-.001/tau);
assert(abs(alpha1ms-.00995016625083195)<1e-14&&abs(alpha-alpha1ms)>.08, ...
    'PositionLPF:EventRate','Filter coefficient must use the 100-Hz interval, not a 1-ms step.');

% Exercise the exact scheduler phase used by the candidate (starts at -f*dt).
phase=-100*.001;lastEventTime=0;eventTimes=[];eventIntervals=[];
for k=1:41
    t=(k-1)*.001;
    [event,phase,dtUsed,lastEventTime]=rbf_event_scheduler_step(phase,100,.001,t,lastEventTime);
    if event,eventTimes(end+1)=t;eventIntervals(end+1)=dtUsed;end %#ok<AGROW>
end
assert(isequal(eventTimes,[.01 .02 .03 .04])&&all(abs(eventIntervals-.01)<1e-12), ...
    'PositionLPF:Scheduler','Candidate scheduler must update at 10-ms events with actual elapsed dt.');

% Saturate the pre-filter Head output, apply its beta ramp, and prove the
% convex filter cannot exceed the current beta-scaled dmax bound.
state=zeros(3,1);maxBoundViolation=0;
for k=1:240
    beta=min(k*dtEvent/1.8,1);
    raw=[12*(-1)^k;7;-9];clipped=max(min(raw,[3;3;3]),-[3;3;3]);
    input=beta*clipped;
    [state,a]=position_applied_accel_lowpass_zoh(state,input,dtEvent,tau);
    assert(a==alpha,'PositionLPF:AlphaDrift','Event coefficient changed with saturated input.');
    maxBoundViolation=max(maxBoundViolation,max(abs(state)-beta*[3;3;3]));
end
assert(maxBoundViolation<=1e-12,'PositionLPF:SaturationBypass','Filtered output bypassed beta-scaled Head bounds.');
report=struct('status','PASS_NO_PLANT_FILTER_CHECK','tau_s',tau,'event_dt_s',dtEvent, ...
    'alpha_100hz',alpha,'alpha_1khz_comparison',alpha1ms,'initial_state_norm',0, ...
    'event_count',numel(eventTimes),'event_times_s',eventTimes, ...
    'event_intervals_s',eventIntervals,'max_beta_dmax_bound_violation',maxBoundViolation, ...
    'Plant_calls',0,'plant_called',false,'TEST_data_read',false);
end
