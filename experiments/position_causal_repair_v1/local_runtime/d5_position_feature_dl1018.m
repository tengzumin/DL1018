function feature=d5_position_feature_dl1018(inputDim,feature14,velocityI,nominalAccel)
% Candidate-only causal X14/X20 feature constructor; no B or attitude path uses it.
feature14=double(feature14(:));velocityI=double(velocityI(:));nominalAccel=double(nominalAccel(:));
assert(numel(feature14)==14&&numel(velocityI)==3&&numel(nominalAccel)==3&& ...
    all(isfinite([feature14;velocityI;nominalAccel])),'D5:FeatureInputs','Invalid candidate feature inputs.');
switch double(inputDim)
    case 14,feature=feature14;
    case 20,feature=[feature14;velocityI;nominalAccel];
    otherwise,error('D5:InputDim','Candidate input dimension must be 14 or 20.');
end
end
