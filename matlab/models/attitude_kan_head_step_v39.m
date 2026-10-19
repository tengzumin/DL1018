function [yRaw,yApplied,dTau,DeltaWAfter,d] = attitude_kan_head_step_v39( ...
    phi,W0,DeltaWBefore,ai0,beta,dtEvent,dmax,ready,headEnabled)
% Predict with W0+DeltaW_before, then update for the next event only.
if nargin<8,ready=true;end
if nargin<9,headEnabled=true;end
phi=double(phi(:));W0=double(W0);DeltaWBefore=double(DeltaWBefore);
dmax=double(dmax(:));beta=double(beta);dtEvent=double(dtEvent);
assert(isequal(size(phi),[33 1])&&isequal(size(W0),[33 3])&& ...
    isequal(size(DeltaWBefore),[33 3])&&isequal(size(dmax),[3 1])&& ...
    isequal(size(ai0.surface(:)),[3 1])&&isequal(size(ai0.euler_rate_map),[3 3])&& ...
    abs(norm(phi)-1)<=1e-10&&all(isfinite([phi;W0(:);DeltaWBefore(:);dmax; ...
    ai0.surface(:);ai0.euler_rate_map(:);beta;dtEvent]))&&all(dmax>0)&&beta>=0, ...
    'X23V38:HeadInput','Invalid head dimensions, values, or normalized feature.');
if ready
    assert(isfinite(dtEvent)&&dtEvent>0,'X23V38:EventDt','Ready update requires the actual positive event interval.');
end
J0=double(ai0.J0);
assert(isequal(size(J0),[3 3])&&all(isfinite(J0),'all')&&rcond(J0)>eps, ...
    'X23V38:Inertia','J0 must be a finite nonsingular 3-by-3 nominal inertia.');
DeltaWAfter=DeltaWBefore;
yRaw=(W0+DeltaWBefore).'*phi;
yApplied=zeros(3,1);dTau=zeros(3,1);
d=struct('ready',logical(ready),'head_enabled',logical(headEnabled), ...
    'saturated',false,'projection_active',false,'update_norm',0, ...
    'weight_norm_before',norm(DeltaWBefore,'fro'),'weight_norm_after',norm(DeltaWBefore,'fro'), ...
    'z2_eff',zeros(3,1),'drive_norm',0,'dt_event_s',dtEvent, ...
    'weight_before',DeltaWBefore,'weight_after',DeltaWBefore);
if ~ready
    return
end
yApplied=min(max(yRaw,-1),1);
d.saturated=any(abs(yRaw)>=1);
dTau=J0*(beta*(dmax.*yApplied));
if ~headEnabled
    return
end
z2eff=min(max(double(ai0.surface(:)),-[2.3;2.3;1.4]),[2.3;2.3;1.4]);
drive=-0.002*beta*phi*((dmax.*(double(ai0.euler_rate_map).'*z2eff)).');
if d.saturated,drive(:)=0;end
candidate=DeltaWBefore+dtEvent*(drive-0.02*DeltaWBefore);
candidateNorm=norm(candidate,'fro');
if candidateNorm>0.20
    DeltaWAfter=candidate*(0.20/candidateNorm);d.projection_active=true;
else
    DeltaWAfter=candidate;
end
d.z2_eff=z2eff;d.drive_norm=norm(drive,'fro');
d.update_norm=norm(DeltaWAfter-DeltaWBefore,'fro');
d.weight_norm_after=norm(DeltaWAfter,'fro');
d.weight_after=DeltaWAfter;
assert(all(isfinite([yRaw;yApplied;dTau;DeltaWAfter(:)]))&&d.weight_norm_after<=0.20+1e-12, ...
    'X23V38:HeadNumerics','Head update became nonfinite or escaped its projection ball.');
end
