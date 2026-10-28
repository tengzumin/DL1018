function residual=tcn_attitude_forward_v1(windowNormalized,model)
% Causal 13x15 TCN forward pass; weight order matches PyTorch Conv1d.
windowNormalized=double(windowNormalized);
required={'input_weight','input_bias','conv1_weight','conv1_bias', ...
    'conv2_weight','conv2_bias','conv3_weight','conv3_bias', ...
    'head_weight','head_bias','target_rms'};
assert(isstruct(model)&&all(isfield(model,required))&& ...
    isequal(size(windowNormalized),[13,15])&&all(isfinite(windowNormalized),'all'), ...
    'DLTCN:ForwardInput','Expected a finite normalized 13-by-15 input window and model weights.');

z=double(model.input_weight)*windowNormalized+double(model.input_bias(:));
z=max(z,0);
dilations=[1,2,4];
for layer=1:3
    W=double(model.(sprintf('conv%d_weight',layer)));
    b=double(model.(sprintf('conv%d_bias',layer))(:));
    assert(isequal(size(W),[32,32,3])&&numel(b)==32, ...
        'DLTCN:WeightShape','Conv layer %d has an unexpected shape.',layer);
    next=zeros(32,15);
    d=dilations(layer);
    for t=1:15
        a=b;
        for tap=1:3
            source=t-d*(3-tap);
            if source>=1
                a=a+W(:,:,tap)*z(:,source);
            end
        end
        next(:,t)=max(a,0);
    end
    z=next;
end
residual=double(model.head_weight)*z(:,end)+double(model.head_bias(:));
residual=residual.*double(model.target_rms(:));
assert(numel(residual)==3&&all(isfinite(residual)), ...
    'DLTCN:ForwardFinite','TCN output is invalid.');
residual=residual(:);
end
