function [raw,applied,weightNext,projection]=position_stage1_update_head( ...
    phi,weight,surface,eventDt,beta,dmax)
% Causal output-then-update event for the bounded position head.
phi=double(phi(:)); weight=double(weight); surface=double(surface(:));
assert(isequal(size(weight),[33,3])&&numel(phi)==33&&numel(surface)==3&& ...
    isscalar(eventDt)&&eventDt>0&&isscalar(beta)&&beta>=0&&beta<=1, ...
    'POSADV:HeadInput','Invalid position-head event inputs.');
raw=weight.'*phi;
clipped=max(min(raw,double(dmax(:))),-double(dmax(:)));
applied=beta*clipped;
sEff=max(min(surface,[7;8;10]),-[7;8;10]);
weightDot=-beta*phi*(sEff.')-0.002*weight;
unprojected=weight+eventDt*weightDot;
projection=any(abs(unprojected(:))>60);
weightNext=max(min(unprojected,60),-60);
end
