function [s,uout,uN4,d]=position_compensation_n4_causal_gate_step(s,u,event,t)
% Update each event, including warmup; hold output and state between events.
assert(isstruct(s)&&isequal(size(u),[3,1])&&all(isfinite(u))&& ...
    isscalar(event)&&isscalar(t)&&isfinite(t), ...
    'N4Gate:Input','Expected finite 3x1 action, scalar event and time.');
uout=s.held;uN4=s.held_n4_raw;d=diagnostics(s,false(3,1));
if ~logical(event),return;end
s.event_count=s.event_count+1;
[s.bp_state,bp]=sos_step(s.bp_sos,s.bp_state,u);
[s.lo_state,lo]=sos_step(s.lo_sos,s.lo_state,u);
rhoE=exp(-.01);rhoG=exp(-.01/.3);
s.Ebp=rhoE*s.Ebp+(1-rhoE)*sum(bp.^2);
s.Elo=rhoE*s.Elo+(1-rhoE)*sum(lo.^2);
s.ratio=s.Ebp/(s.Ebp+s.Elo+1e-8);
[s.n4,~,uN4,~]=position_compensation_static_n4_step(s.n4,u,true);
s.held_n4_raw=uN4;
if ~s.lead_initialized
    if max(abs(uN4))>1e-12
        % Initialize the unity-DC lead at its constant-input steady state.
        s.lead_x1=uN4;s.lead_y1=uN4;s.lead_initialized=true;
    end
    uLead=uN4;
else
    uLead=s.lead_b(1)*uN4+s.lead_b(2)*s.lead_x1-s.lead_a1*s.lead_y1;
    s.lead_x1=uN4;s.lead_y1=uLead;
end
s.held_n4_lead=uLead;
if t<2
    s.gtarget=0;s.g=0;
else
    s.gtarget=min(max((s.ratio-.35)/.30,0),1);
    s.g=rhoG*s.g+(1-rhoG)*s.gtarget;
end
unclipped=u+s.g*(uLead-u);
uout=min(max(unclipped,-3),3);
clip=abs(unclipped-uout)>1e-12;
s.clip_count=s.clip_count+nnz(clip);s.held=uout;
d=diagnostics(s,clip);
end

function [state,y]=sos_step(sos,state,x)
y=x;
for j=1:size(sos,1)
    z1=state(:,j,1);z2=state(:,j,2);row=sos(j,:);
    next=row(1)*y+z1;
    state(:,j,1)=row(2)*y-row(5)*next+z2;
    state(:,j,2)=row(3)*y-row(6)*next;
    y=next;
end
end

function d=diagnostics(s,clip)
d=struct('Ebp',s.Ebp,'Elo',s.Elo,'ratio',s.ratio,'gtarget',s.gtarget, ...
    'g',s.g,'clip',clip,'clip_count',s.clip_count, ...
    'n4_raw',s.held_n4_raw,'n4_lead',s.held_n4_lead, ...
    'lead_initialized',s.lead_initialized);
end
