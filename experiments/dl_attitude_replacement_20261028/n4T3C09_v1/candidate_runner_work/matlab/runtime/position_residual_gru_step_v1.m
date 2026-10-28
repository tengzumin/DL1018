function [hidden,raw] = position_residual_gru_step_v1(hidden,x14,model)
% One causal PyTorch GRU(14,32) event, gate order reset/update/new.
assert(isequal(size(hidden),[32,1])&&numel(x14)==14&& ...
    all(isfinite(double(hidden(:))))&&all(isfinite(double(x14(:)))), ...
    'PositionResidualGRU:Input','Expected finite 32-state and 14-feature columns.');
x=(double(x14(:))-double(model.input_mean(:)))./double(model.input_std(:));
gi=double(model.gru_weight_ih_l0)*x+double(model.gru_bias_ih_l0(:));
gh=double(model.gru_weight_hh_l0)*double(hidden(:))+double(model.gru_bias_hh_l0(:));
reset=1./(1+exp(-(gi(1:32)+gh(1:32))));
update=1./(1+exp(-(gi(33:64)+gh(33:64))));
new=tanh(gi(65:96)+reset.*gh(65:96));
hidden=(1-update).*new+update.*double(hidden(:));
raw=double(model.head_weight)*hidden+double(model.head_bias(:));
assert(isequal(size(raw),[3,1])&&all(isfinite([hidden;raw])), ...
    'PositionResidualGRU:Output','GRU produced a non-finite state or three-axis output.');
end
