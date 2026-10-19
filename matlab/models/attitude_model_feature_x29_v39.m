function [phi,W0,y0] = attitude_model_feature_x29_v39(model,X)
% Frozen V3.6 A_KAN29 feature/readout split, double precision.
X=double(X);D=double(model.input_dim);
assert(D==29&&isequal(size(X),[29 32])&&all(isfinite(X),'all'), ...
    'X29V39:FeatureInput','Expected a finite 29-by-32 X29 event window.');
x=(X-double(model.input_mu(:)))./max(double(model.input_sigma(:)),1e-6);
cur=min(max(x(:,end),-4),4);knots=double(model.knots(:).');
p=model.params;W=double(p.spline_W);L=double(p.linear_W);b=double(p.feature_b(:));
assert(numel(knots)==12&&isequal(size(W),[32 29 8])&&isequal(size(L),[32 29])&&numel(b)==32, ...
    'X29V39:ParameterShape','Frozen A_KAN29 parameter dimensions do not match V3.6.');
basis=zeros(29,8);
for j=1:29,basis(j,:)=cubic_basis_scalar(cur(j),knots);end
z=reshape(sum(sum(W.*reshape(basis,[1 29 8]),3),2),[],1)+L*silu(cur)+b;
h=tanh(z);phi=[h;1]/sqrt(1+sum(h.^2));
W0=double(p.readout__weight).';
assert(isequal(size(phi),[33 1])&&isequal(size(W0),[33 3])&& ...
    abs(norm(phi)-1)<=1e-12&&all(isfinite(phi),'all')&&all(isfinite(W0),'all'), ...
    'X29V39:FeatureOutput','Invalid normalized feature or frozen readout shape.');
y0=W0.'*phi;
assert(isequal(size(y0),[3 1])&&all(isfinite(y0)), ...
    'X29V39:ReadoutOutput','Frozen A_KAN29 readout produced an invalid output.');
end

function b=cubic_basis_scalar(x,k)
b=double((x>=k(1:end-1))&(x<k(2:end)));
for degree=1:3
    count=numel(k)-degree-1;next=zeros(1,count);
    for i=1:count
        ld=k(i+degree)-k(i);rd=k(i+degree+1)-k(i+1);
        if ld>0,next(i)=next(i)+(x-k(i))/ld*b(i);end
        if rd>0,next(i)=next(i)+(k(i+degree+1)-x)/rd*b(i+1);end
    end
    b=next;
end
if x==k(end),b(:)=0;b(end)=1;end
end
function y=silu(x),y=x./(1+exp(-x));end
