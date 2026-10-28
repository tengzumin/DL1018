function out = delayed_prediction_step_candidate(W_k, phi_k, s_eff_k, n, t_n, phi_prev, y_prev, j, t_j)
% Pure one-step proposal; Python reference: delayed_prediction_kernel.py.
% n,j are zero-based raw plant indices; beta follows C2 MATLAB k=n+1 clock.
h=0.01; dt=0.001; gamma=12; lambda=0.002; tau=0.1; rho=h/tau; firstValid=320;
betaRise=1.8; sLimit=[7;8;10]; predLimit=3; weightLimit=60;
if ~isnumeric(W_k) || ~isreal(W_k) || ~isequal(size(W_k),[33,3]) || any(~isfinite(W_k(:)))
    error('DelayedPrediction:BadW','W_k must be finite real 33-by-3.');
end
if ~isnumeric(phi_k) || ~isreal(phi_k) || ~isequal(size(phi_k),[33,1]) || any(~isfinite(phi_k(:))) || abs(norm(phi_k)-1)>1e-10
    error('DelayedPrediction:BadPhi','phi_k must be finite unit-norm 33-by-1.');
end
if ~isnumeric(s_eff_k) || ~isreal(s_eff_k) || ~isequal(size(s_eff_k),[3,1]) || any(~isfinite(s_eff_k(:))) || any(abs(s_eff_k)>sLimit+1e-12)
    error('DelayedPrediction:BadSEff','s_eff_k must be finite 3-by-1 within original limits.');
end
if ~isscalar(n) || ~isfinite(n) || n<firstValid || n~=fix(n) || mod(n,10)~=0 || ~isscalar(t_n) || ~isfinite(t_n) || t_n<0 || abs(t_n-n*dt)>1e-12
    error('DelayedPrediction:BadCurrentTime','n and t_n must describe a zero-based 1-ms index.');
end
previous={phi_prev,y_prev,j,t_j};
hasPrevious=~all(cellfun(@isempty,previous));
if hasPrevious && any(cellfun(@isempty,previous))
    error('DelayedPrediction:IncompletePrevious','Previous phi/target/index/time must be supplied together.');
end
if ~hasPrevious && n~=firstValid
    error('DelayedPrediction:MissingPrevious','Only first ready event n=320 may omit a previous target.');
end
predGrad=zeros(33,3); previousRaw=[]; previousResidual=[];
if hasPrevious
    if ~isnumeric(phi_prev) || ~isreal(phi_prev) || ~isequal(size(phi_prev),[33,1]) || any(~isfinite(phi_prev(:))) || abs(norm(phi_prev)-1)>1e-10
        error('DelayedPrediction:BadPreviousPhi','phi_prev must be finite unit-norm 33-by-1.');
    end
    if ~isnumeric(y_prev) || ~isreal(y_prev) || ~isequal(size(y_prev),[3,1]) || any(~isfinite(y_prev(:)))
        error('DelayedPrediction:BadTarget','y_prev must be finite real 3-by-1.');
    end
    if ~isscalar(j) || ~isfinite(j) || j<firstValid || j~=fix(j) || mod(j,10)~=0 || n-j~=10 || ~isscalar(t_j) || ~isfinite(t_j) || abs(t_j-j*dt)>1e-12 || abs((t_n-t_j)-h)>1e-12
        error('DelayedPrediction:BadPreviousTime','Previous event must be j=n-10 and exactly 10 ms earlier.');
    end
    previousRaw=W_k.'*phi_prev;
    previousResidual=previousRaw-y_prev;
    predGrad=phi_prev*previousResidual.';
end
beta=min((n+1)*dt/betaRise,1); raw=W_k.'*phi_k; applied=beta*min(max(raw,-predLimit),predLimit);
candidate=W_k-h*gamma*beta*(phi_k*s_eff_k.')-h*lambda*W_k-rho*predGrad;
W_next=min(max(candidate,-weightLimit),weightLimit); % one joint projection
out=struct('raw',raw,'applied',applied,'beta',beta,'has_previous',hasPrevious, ...
    'previous_raw',previousRaw,'previous_residual',previousResidual, ...
    'prediction_gradient',predGrad,'preprojection_candidate',candidate,'W_next',W_next);
end
