function [s,y,raw,clip] = position_compensation_static_n4_step(s,x,event)
% Update the four-section cascade only at the C5 100-Hz event; hold between events.
assert(isstruct(s)&&isequal(size(x),[3,1])&&all(isfinite(x))&&isscalar(event), ...
    'StaticN4:Input','Expected state, finite 3x1 action, and scalar event flag.');
y=s.held;raw=y;clip=false(3,1);
if ~logical(event),return;end
if ~s.initialized
    if max(abs(x))>1e-12
        s.sections=repmat(x,1,4,4);s.held=x;s.initialized=true;
    else
        s.held=x;
    end
    y=s.held;raw=y;return;
end
raw=x;
for j=1:4
    [s.sections(:,:,j),raw]=section_step(s.sections(:,:,j),raw,s.b(j,:),s.a(j,:));
end
y=min(max(raw,-3),3);clip=abs(raw-y)>1e-12;
s.clip_count=s.clip_count+nnz(clip);s.held=y;
end

function [state,y]=section_step(state,x,b,a)
y=b(1)*x+b(2)*state(:,1)+b(3)*state(:,2)-a(2)*state(:,3)-a(3)*state(:,4);
state=[x,state(:,1),y,state(:,3)];
end
