function [s,y,raw,clip] = position_compensation_dual_notch_step(s,x,event)
% One online tick. Call on every 1-ms step; update the IIR only on stage-1 events.
assert(isstruct(s)&&isequal(size(x),[3,1])&&all(isfinite(x))&&isscalar(event), ...
    'DualNotch:Input','Expected state, finite 3x1 action, and scalar event flag.');
y=s.held;raw=y;clip=false(3,1);
if ~logical(event),return;end
if ~s.initialized
    if max(abs(x))>1e-12
        s.section1=repmat(x,1,4);s.section2=repmat(x,1,4);
        s.held=x;s.initialized=true;
    else
        s.held=x;
    end
    y=s.held;raw=y;return;
end
[s.section1,u]=section_step(s.section1,x,s.b(1,:),s.a(1,:));
[s.section2,raw]=section_step(s.section2,u,s.b(2,:),s.a(2,:));
y=min(max(raw,-3),3);clip=abs(raw-y)>1e-12;
s.clip_count=s.clip_count+nnz(clip);s.held=y;
end

function [state,y]=section_step(state,x,b,a)
y=b(1)*x+b(2)*state(:,1)+b(3)*state(:,2)-a(2)*state(:,3)-a(3)*state(:,4);
state=[x,state(:,1),y,state(:,3)];
end
