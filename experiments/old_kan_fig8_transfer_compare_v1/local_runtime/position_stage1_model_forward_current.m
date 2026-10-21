function [phi,phiSequence] = position_stage1_model_forward_current(model,window)
% Deterministic MATLAB inference for the teacher-reuse model candidates.
inputDim=double(model.input_dim);
assert(ismember(inputDim,[14,20]),'D5:ModelInputDim','Expected a 14- or 20-input position model.');
mu=double(model.input_mu(:));sigma=max(double(model.input_sigma(:)),1e-4);
x=(double(window)-mu)./sigma;
windowLength=double(model.window);
architecture=char(model.architecture);
validLength=isequal(size(x,1),inputDim)&& ...
    (isequal(size(x,2),windowLength)||(ismember(architecture,{'MLP','KAN','TCN'})&& ...
    size(x,2)>=1&&size(x,2)<=windowLength));
assert(validLength&&all(isfinite(x),'all'), ...
    'D5:ModelInput','Expected a finite normalized candidate window of model.window length.');
hSequence=[];
switch architecture
    case 'MLP'
        z=silu(double(model.fc1_W)*x(:,end)+double(model.fc1_b(:)));
        z=silu(double(model.fc2_W)*z+double(model.fc2_b(:)));
        h=tanh(double(model.fc3_W)*z+double(model.fc3_b(:)));
    case 'KAN'
        cur=x(:,end);clipped=max(min(cur,4),-4);
        basis=bspline_basis(clipped,double(model.knots(:)));
        hpre=double(model.feature_b(:));W=double(model.spline_W);
        for i=1:inputDim
            for b=1:8,hpre=hpre+W(:,i,b)*basis(i,b);end
        end
        siluInput=clipped;
        if logical(model.silu_unclipped),siluInput=cur;end
        h=tanh(hpre+double(model.linear_W)*silu(siluInput));
    case 'TCN'
        x=causal_conv(x,double(model.stem_W),double(model.stem_b(:)),1);
        dilations=double(model.dilations(:));
        for b=1:numel(dilations)
            prefix=sprintf('block%d_',b);
            convW=double(model.([prefix 'conv_W']));convB=double(model.([prefix 'conv_b']));
            mixW=double(model.([prefix 'mix_W']));mixB=double(model.([prefix 'mix_b']));
            y=causal_conv(x,convW,convB(:),dilations(b));
            y=causal_conv(silu(y),mixW,mixB(:),1);
            x=silu(x+y);
        end
        hSequence=tanh(double(model.project_W)*x+double(model.project_b(:)));
        h=hSequence(:,end);
    case 'GRU'
        state=zeros(32,1);Wih=double(model.gru_W_ih);Whh=double(model.gru_W_hh);
        bih=double(model.gru_b_ih(:));bhh=double(model.gru_b_hh(:));
        for k=1:windowLength
            gi=Wih*x(:,k)+bih;gh=Whh*state+bhh;
            ir=gi(1:32);iz=gi(33:64);inn=gi(65:96);
            hr=gh(1:32);hz=gh(33:64);hn=gh(65:96);
            reset=1./(1+exp(-(ir+hr)));update=1./(1+exp(-(iz+hz)));
            new=tanh(inn+reset.*hn);state=(1-update).*new+update.*state;
        end
        h=tanh(double(model.project_W)*state+double(model.project_b(:)));
    case 'DSSM'
        state=zeros(32,1);alpha=exp(-0.01./double(model.ssm_tau(:)));
        W=double(model.input_W);b=double(model.input_b(:));
        for k=1:windowLength
            drive=tanh(W*x(:,k)+b);
            state=alpha.*state+(1-alpha).*drive;
        end
        h=tanh(double(model.project_W)*state+double(model.project_b(:)));
    case 'N_TCN'
        dilations=[1 2 4];
        for b=1:3
            prefix=sprintf('block%d_',b);
            if b==1,skip=double(model.skip_W)*x+double(model.skip_b(:));else,skip=x;end
            w1=double(model.([prefix 'conv1_W']));b1=double(model.([prefix 'conv1_b']));
            x=max(causal_conv(x,w1,b1(:),dilations(b)),0);
            w2=double(model.([prefix 'conv2_W']));b2=double(model.([prefix 'conv2_b']));
            x=max(causal_conv(x,w2,b2(:),dilations(b))+skip,0);
        end
        h=tanh(double(model.feature_W)*x(:,end)+double(model.feature_b(:)));
    case 'N_MLP'
        z=max(double(model.fc1_W)*x(:,end)+double(model.fc1_b(:)),0);
        z=max(double(model.fc2_W)*z+double(model.fc2_b(:)),0);
        h=tanh(double(model.fc3_W)*z+double(model.fc3_b(:)));
    case 'N_KAN'
        cur=x(:,end);clipped=max(min(cur,4),-4);
        basis=bspline_basis(clipped,double(model.knots(:)));
        hpre=double(model.feature_b(:));W=double(model.spline_W);
        for i=1:inputDim
            for b=1:8,hpre=hpre+W(:,i,b)*basis(i,b);end
        end
        siluInput=clipped;
        if isfield(model,'kan_silu_unclipped')&&logical(model.kan_silu_unclipped)
            siluInput=cur;
        end
        y=siluInput./(1+exp(-siluInput));
        h=tanh(hpre+double(model.linear_W)*y);
    case 'N_DEEP_KAN'
        cur=x(:,end);clipped=max(min(cur,4),-4);
        h0=kan_hidden(model,clipped,cur);
        basis=bspline_basis(max(min(h0,1),-1)*4,double(model.knots(:)));
        W=double(model.deep_spline_W);g=zeros(32,1);
        for i=1:32
            for b=1:8,g=g+W(:,i,b)*basis(i,b);end
        end
        h=h0+tanh(g+double(model.deep_linear_W)*silu(h0)+double(model.deep_b(:)));
    case 'N_HISTORY_KAN'
        cur=x(:,end);clipped=max(min(cur,4),-4);
        h0=kan_hidden(model,clipped,cur);
        z=x(1:10,:);dilations=[1 2 4 8];
        for b=1:4
            prefix=sprintf('history_conv%d_',b);
            convW=double(model.([prefix 'W']));convB=double(model.([prefix 'b']));
            z=silu(causal_conv(z,convW,convB(:),dilations(b)));
        end
        delta=tanh(double(model.history_proj_W)*z(:,end)+double(model.history_proj_b(:)));
        h=h0+delta;
    case 'N_WIDE_SILU_MLP'
        z=silu(double(model.fc1_W)*x(:,end)+double(model.fc1_b(:)));
        z=silu(double(model.fc2_W)*z+double(model.fc2_b(:)));
        h=tanh(double(model.fc3_W)*z+double(model.fc3_b(:)));
    case 'N_GRU'
        state=zeros(32,1);Wih=double(model.gru_W_ih);Whh=double(model.gru_W_hh);
        bih=double(model.gru_b_ih(:));bhh=double(model.gru_b_hh(:));
        for k=1:32
            gi=Wih*x(:,k)+bih;gh=Whh*state+bhh;
            ir=gi(1:32);iz=gi(33:64);inn=gi(65:96);
            hr=gh(1:32);hz=gh(33:64);hn=gh(65:96);
            reset=1./(1+exp(-(ir+hr)));update=1./(1+exp(-(iz+hz)));
            new=tanh(inn+reset.*hn);state=(1-update).*new+update.*state;
        end
        h=tanh(double(model.feature_W)*state+double(model.feature_b(:)));
    case 'N_DSSM'
        state=zeros(32,1);a=double(model.ssm_a(:));
        E=double(model.ssm_E_W);eb=double(model.ssm_E_b(:));
        B=double(model.ssm_B_W);C=double(model.ssm_C_W);D=double(model.ssm_D_W);
        for k=1:32
            z=max(E*x(:,k)+eb,0);state=a.*state+B*z;
        end
        h=tanh(C*state+D*z);
    otherwise
        error('POSADV:ModelArchitecture','Unsupported exported architecture: %s.',architecture);
end
phi=[h;1]/sqrt(1+sum(h.^2));
phiSequence=[];
if ~isempty(hSequence)
    phiSequence=[hSequence;ones(1,size(hSequence,2))]./sqrt(1+sum(hSequence.^2,1));
    phi=phiSequence(:,end);
end
assert(isequal(size(phi),[33,1])&&all(isfinite(phi)), ...
    'POSADV:ModelFeature','Encoder returned an invalid 33D feature.');
end

function h=kan_hidden(model,clipped,current)
basis=bspline_basis(clipped,double(model.knots(:)));
hpre=double(model.feature_b(:));W=double(model.spline_W);
for i=1:14
    for b=1:8,hpre=hpre+W(:,i,b)*basis(i,b);end
end
y=current./(1+exp(-current));
h=tanh(hpre+double(model.linear_W)*y);
end

function y=silu(x)
y=x./(1+exp(-x));
end

function y=causal_conv(x,w,b,dilation)
[cout,cin,kernel]=size(w);
assert(size(x,1)==cin&&numel(b)==cout&&ismember(kernel,[1,3]), ...
    'POSADV:ConvShape','Invalid causal convolution weight shape.');
T=size(x,2);y=zeros(cout,T);
for j=1:kernel
    lag=(kernel-j)*dilation;
    if lag<T,y(:,lag+1:end)=y(:,lag+1:end)+w(:,:,j)*x(:,1:end-lag);end
end
y=y+b(:);
end

function B=bspline_basis(x,knots)
x=max(min(x,4),-4);n0=numel(knots)-1;B=zeros(numel(x),n0);
for i=1:n0,B(:,i)=double(x>=knots(i)&x<knots(i+1));end
for d=1:3
    n=numel(knots)-d-1;next=zeros(numel(x),n);
    for i=1:n
        ld=knots(i+d)-knots(i);rd=knots(i+d+1)-knots(i+1);
        if ld>0,next(:,i)=next(:,i)+(x-knots(i))/ld.*B(:,i);end
        if rd>0,next(:,i)=next(:,i)+(knots(i+d+1)-x)/rd.*B(:,i+1);end
    end
    B=next;
end
B(x>=4,:)=0;B(x>=4,end)=1;
end

