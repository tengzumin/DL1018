function [appliedAcceleration,appliedForce] = position_stage1_scale_compensation_v1(unscaledAcceleration,mass,scale)
% Scale only the applied DSSM position compensation; retain its raw output/update.
unscaledAcceleration=double(unscaledAcceleration(:));
assert(numel(unscaledAcceleration)==3&&all(isfinite(unscaledAcceleration))&& ...
    isscalar(mass)&&isfinite(mass)&&mass>0&&isscalar(scale)&&isfinite(scale)&& ...
    scale>=0&&scale<=1,'DSSM:CompensationScaleInput','Invalid compensation scaling input.');
appliedAcceleration=double(scale)*unscaledAcceleration;
appliedForce=double(mass)*appliedAcceleration;
end
