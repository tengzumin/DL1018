function [aFiltered,rFiltered,etaNext,rotation] = position_filter_realization_pcf_step_v3_5( ...
    thrustCommand,eulerFiltered,aRequested,eta,k2,mass,gravity,dt,coordinationEnabled)
% Nameplate filtered-reference acceleration and exact held-input eta step.
eulerFiltered=double(eulerFiltered(:)); aRequested=double(aRequested(:)); eta=double(eta(:));
k2=double(k2(:));
assert(numel(eulerFiltered)==3&&numel(aRequested)==3&&numel(eta)==3&&numel(k2)==3&& ...
    all(isfinite([eulerFiltered;aRequested;eta;k2;thrustCommand;mass;gravity;dt]))&& ...
    all(k2>=0)&&mass>0&&gravity>0&&dt>0,'PCF35:FilterStepInput','Invalid reference/filter inputs.');
p=eulerFiltered(1); q=eulerFiltered(2); y=eulerFiltered(3);
rotation=[cos(y)*cos(q),cos(y)*sin(q)*sin(p)-sin(y)*cos(p),cos(y)*sin(q)*cos(p)+sin(y)*sin(p); ...
    sin(y)*cos(q),sin(y)*sin(q)*sin(p)+cos(y)*cos(p),sin(y)*sin(q)*cos(p)-cos(y)*sin(p); ...
    -sin(q),cos(q)*sin(p),cos(q)*cos(p)];
aFiltered=(double(thrustCommand)/double(mass))*rotation*[0;0;1]-[0;0;double(gravity)];
rFiltered=aRequested-aFiltered;
etaNext=eta;
if coordinationEnabled
    decay=exp(-k2*double(dt));
    integral=double(dt)*ones(3,1);
    positive=k2>0;
    integral(positive)=-expm1(-k2(positive)*double(dt))./k2(positive);
    etaNext=decay.*eta+integral.*rFiltered;
end
assert(all(isfinite([aFiltered;rFiltered;etaNext])),'PCF35:FilterStepFinite','Nonfinite filter realization.');
end
