function [arms,meta] = tcn0916_morphology_scenario(topology,time,seed,opts)
%TCN0916_MORPHOLOGY_SCENARIO Seeded command/true morphology trajectory.
    if nargin < 4, opts = struct; end
    time = double(time(:)); dt = median(diff(time));
    [names,sets] = tcn0916_topologies();
    idx = find(strcmp(names,char(string(topology))),1);
    assert(~isempty(idx),'TCN0916:Topology','unknown morphology topology.');
    active = sets{idx};
    rs = RandStream('mt19937ar','Seed',double(seed));
    morphSpeedMps=double(field_or(opts,'morph_speed_mps',.02));
    minHoldS=double(field_or(opts,'min_hold_s',NaN));
    assert(isscalar(morphSpeedMps)&&isfinite(morphSpeedMps)&&morphSpeedMps>0, ...
        'TCN0916:MorphologySpeed','morph_speed_mps must be a positive finite scalar.');
    assert(isscalar(minHoldS)&&(isnan(minHoldS)||(isfinite(minHoldS)&&minHoldS>=0)), ...
        'TCN0916:MorphologyHold','min_hold_s must be a nonnegative finite scalar when provided.');
    target = .15*ones(4,1); start = inf(4,1); retractStart = inf(4,1);
    retract = logical(field_or(opts,'retract',mod(seed,4)==0));
    for a = active
        stratum = mod(a+seed-1,3)+1;
        edges = [0.155 0.18;0.18 0.215;0.215 0.25];
        target(a) = edges(stratum,1) + diff(edges(stratum,:))*rand(rs);
        if isfield(opts,'target_override')
            override=opts.target_override(:); if numel(override)==4 && isfinite(override(a)), target(a)=override(a); end
        end
        start(a) = max(5.2,5.2+.8*rand(rs));
        if isfield(opts,'start_override')
            override=opts.start_override(:); if numel(override)==4 && isfinite(override(a)), start(a)=max(5.2,override(a)); end
        end
        if isfield(opts,'retract_start_override')
            override=opts.retract_start_override(:);
            if numel(override)==4&&isfinite(override(a)),retractStart(a)=override(a);
            else,retractStart(a)=start(a)+(target(a)-.15)/morphSpeedMps+.5+.8*rand(rs);
            end
        elseif isfinite(minHoldS)
            retractStart(a)=start(a)+(target(a)-.15)/morphSpeedMps+minHoldS;
        else
            retractStart(a)=start(a)+(target(a)-.15)/morphSpeedMps+.5+.8*rand(rs);
        end
        requiredHoldS=0;
        if isfinite(minHoldS),requiredHoldS=minHoldS;end
        assert(target(a)>=.15&&target(a)<=.25&& ...
            retractStart(a)>=start(a)+(target(a)-.15)/morphSpeedMps+requiredHoldS-1e-12, ...
            'TCN0916:MorphologyTiming','Target length or retract timing violates the speed/hold contract.');
    end
    n = numel(time); command = zeros(n,4); rhoTrue = .15*ones(n,4); rhoDotTrue=zeros(n,4);
    rho = .15*ones(4,1);
    for k = 1:n
        for a = active
            if time(k) < start(a)
                rate = 0;
            elseif retract && time(k) >= retractStart(a)
                rate = -morphSpeedMps*(rho(a) > .15+1e-12);
            else
                rate = morphSpeedMps*(rho(a) < target(a)-1e-12);
            end
            rhoDotTrue(k,a) = rate; command(k,a) = rate/morphSpeedMps;
        end
        rhoTrue(k,:) = rho.';
        rho = min(max(rho + dt*rhoDotTrue(k,:).',.15),.25);
    end
    arms = struct('command',command,'rho_true',rhoTrue,'rhoDot_true',rhoDotTrue);
    if isempty(active)
        timingMode='synchronous';
    elseif max(start(active))-min(start(active))<.05
        timingMode='synchronous';
    elseif max(start(active))-min(start(active))<.4
        timingMode='mildly_staggered';
    else
        timingMode='asynchronous';
    end
    meta = struct('topology',names{idx},'active_arms',active,'target_arm_lengths',target, ...
        'start_time_s',start,'retract_start_time_s',retractStart,'retract',retract, ...
        'timing_mode',timingMode,'command_speed_mps',morphSpeedMps, ...
        'minimum_hold_s',minHoldS,'actual_hold_s',retractStart-(start+(target-.15)/morphSpeedMps), ...
        'arm_length_min_m',.15, ...
        'arm_length_max_m',.25,'seed',seed);
end

function v = field_or(s,name,defaultValue)
    if isfield(s,name), v = s.(name); else, v = defaultValue; end
end
