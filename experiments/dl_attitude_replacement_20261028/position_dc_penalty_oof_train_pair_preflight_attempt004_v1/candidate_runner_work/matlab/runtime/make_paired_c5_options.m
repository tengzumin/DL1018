function [baseline,candidate]=make_paired_c5_options(cfg,positionModel)
% Construct both arms from one C5 position stack and one initial RBF state.
common=position_only_search_options(cfg,positionModel,'FEATURE',12,1);
common.position_delayed_prediction_enabled=true;
common.position_coordinate_mask=[1;1;0];
common.paired_position_method_id='C5_AXIS_MIXED_COORDINATE_M110';
common.rbf_attitude_initial_weight=zeros(size(cfg.rbf.attitude.centers,2),3);
baseline=common;
baseline.paired_arm='baseline';
candidate=common;
candidate.paired_arm='candidate';
flags={'rbf_attitude_enabled','rbf_attitude_output_enabled', ...
    'rbf_attitude_update_enabled'};
for i=1:numel(flags)
    assert(isequal(common.(flags{i}),true),'PAIRED:CommonRBF', ...
        'C5 source options must enable the baseline attitude RBF.');
    candidate.(flags{i})=false;
end
normalizedBaseline=rmfield(baseline,[flags,{'paired_arm'}]);
normalizedCandidate=rmfield(candidate,[flags,{'paired_arm'}]);
assert(isequaln(normalizedBaseline,normalizedCandidate), ...
    'PAIRED:Options','Normalized arm options differ.');
end
