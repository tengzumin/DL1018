function [raw,applied,weightNext,projection,info] = position_stage1_update_head_pcf_v3_5( ...
    phi,weight,surface,eventDt,beta,dmax,etaBefore,coordinationEnabled)
% Apply the V3.5 command-filter coordination surface to the original K1 Head.
phi=double(phi(:)); weight=double(weight); surface=double(surface(:));
etaBefore=double(etaBefore(:));
assert(numel(surface)==3&&numel(etaBefore)==3&&all(isfinite([surface;etaBefore])), ...
    'PCF35:HeadState','Surface and auxiliary state must be finite 3-vectors.');
if coordinationEnabled && any(etaBefore~=0)
    updateSurface=surface-etaBefore;
else
    % Preserve exact legacy arithmetic for disabled coordination and eta=0.
    updateSurface=surface;
end
[raw,applied,weightNext,projection]=position_stage1_update_head( ...
    phi,weight,updateSurface,eventDt,beta,dmax);
info=struct('surface',updateSurface,'surface_effective', ...
    max(min(updateSurface,[7;8;10]),-[7;8;10]));
end
