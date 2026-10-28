function [s,uout,uN4,d] = position_compensation_n4_causal_gate_step(s,u,event,t)
% Eventwise causal blend; all internal filters continue through startup/warmup.
assert(isstruct(s)&&isequal(size(u),[3,1])&&all(isfinite(u))&&isscalar(event)&&isscalar(t), ...
    'N4Gate:Input','Expected state, finite 3x1 action, event flag, and event time.');
uout=s.held;uN4=s.held_n4_raw;d=diagnostics(s);
if ~logical(event),return;end
s.event_count=s.event_count+1;
[s.bp_state,bp]=sos_step(s.bp_sos,s.bp_state,u);
[s.lp_state,lp]=sos_step(s.lp_sos,s.lp_state,u);
rhoE=exp(-0.01/1.0);rhoG=exp(-0.01/0.3);
s.Ebp=rhoE*s.Ebp+(1-rhoE)*sum(bp.^2);
s.Elp=rhoE*s.Elp+(1-rhoE)*sum(lp.^2);
s.ratio=s.Ebp/(s.Ebp+s.Elp+1e-8);
rawTarget=min(max((s.ratio-0.35)/0.30,0),1);
[s.n4,~,uN4,~]=position_compensation_static_n4_step(s.n4,u,true);
s.held_n4_raw=uN4;
if t<2.0
    s.gtarget=0;s.g=0;unclipped=u;
else
    s.gtarget=rawTarget;
    s.g=rhoG*s.g+(1-rhoG)*s.gtarget;
    unclipped=u+s.g*(uN4-u);
end
uout=min(max(unclipped,-3),3);
s.clip_count=s.clip_count+nnz(abs(unclipped-uout)>1e-12);
s.held=uout;d=diagnostics(s);
end

function [state,y]=sos_step(sos,state,x)
y=x;
for section=1:size(sos,1)
    b=sos(section,1:3);a=sos(section,4:6);
    z1=state(:,section,1);z2=state(:,section,2);
    next=b(1)*y+z1;
    state(:,section,1)=b(2)*y-a(2)*next+z2;
    state(:,section,2)=b(3)*y-a(3)*next;
    y=next;
end
end

function d=diagnostics(s)
d=struct('Ebp',s.Ebp,'Elp',s.Elp,'ratio',s.ratio, ...
    'gtarget',s.gtarget,'g',s.g,'clip_count',s.clip_count);
end
