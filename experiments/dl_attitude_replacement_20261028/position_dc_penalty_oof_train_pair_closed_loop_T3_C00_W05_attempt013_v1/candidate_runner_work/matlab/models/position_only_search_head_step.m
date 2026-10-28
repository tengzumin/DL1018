function [raw,applied,stateNext,projection,audit]=position_only_search_head_step( ...
    phi,W0,state,headType,gamma,kappa,sEff,eventDt,beta,dmax)
% Output-then-update position-only search Head; encoder and attitude remain frozen.
phi=double(phi(:));W0=double(W0);state=double(state);sEff=double(sEff(:));
headType=upper(char(headType));
assert(numel(phi)==33&&isequal(size(W0),[33,3])&&numel(sEff)==3&& ...
    isscalar(gamma)&&isfinite(gamma)&&gamma>0&&isscalar(kappa)&& ...
    isfinite(kappa)&&kappa>=0&&isscalar(eventDt)&&isfinite(eventDt)&&eventDt>0&& ...
    isscalar(beta)&&isfinite(beta)&&beta>=0&&beta<=1&&numel(dmax)==3, ...
    'POSSEARCH:Input','Invalid position-only search Head input.');
switch headType
    case 'FEATURE'
        assert(isequal(size(state),[33,3]),'POSSEARCH:FeatureState','FEATURE state must be 33x3.');
        raw=state.'*phi;
        clipped=max(min(raw,double(dmax(:))),-double(dmax(:)));
        applied=beta*clipped;
        unprojected=state+eventDt*(-gamma*beta*phi*(sEff.')-0.002*state);
        projection=any(abs(unprojected(:))>60);
        stateNext=max(min(unprojected,60),-60);
        audit=struct('bias_before',zeros(3,1),'bias_after',zeros(3,1), ...
            'bias_projection',false,'state_bound',60);
    case 'BIAS'
        assert(numel(state)==3,'POSSEARCH:BiasState','BIAS state must be a 3-vector.');
        state=state(:);
        raw=kappa*(W0.'*phi)+state;
        clipped=max(min(raw,double(dmax(:))),-double(dmax(:)));
        applied=beta*clipped;
        unprojected=state+eventDt*(-gamma*beta*sEff-0.002*state);
        projection=any(abs(unprojected)>3);
        stateNext=max(min(unprojected,3),-3);
        audit=struct('bias_before',state,'bias_after',stateNext, ...
            'bias_projection',projection,'state_bound',3);
    otherwise
        error('POSSEARCH:HeadType','Unknown search Head type %s.',headType);
end
end
