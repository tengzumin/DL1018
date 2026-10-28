function [windInertial,details] = wind_velocity_profile(t,windCfg)
    % FUNCTION:
    %   按确定性配置生成随时间变化的惯性系风速序列。
    % PURPOSE:
    %   将单频/多频正弦或平滑阵风标量速度投影到配置指定的三维风向。
    % INPUT: t 为秒（标量或列向量）；windCfg 包含类型、方向及对应波形参数。
    % OUTPUT: windInertial 为 3xN 惯性系风速（m/s）；details 返回归一化风向、标量速度及单位信息。
    % 按确定性风场配置生成惯性系风速，单位为 m/s。
    assert(isnumeric(t) && (isscalar(t) || iscolumn(t)) && all(isfinite(t)),'TCN0901:WindTime','t must be a finite scalar or column vector.');
    assert(isstruct(windCfg) && isfield(windCfg,'type') && isfield(windCfg,'direction'),'TCN0901:WindConfig','windCfg requires type and direction.');
    d = double(windCfg.direction(:));
    assert(numel(d) == 3 && all(isfinite(d)) && norm(d) > 0,'TCN0901:WindDirection','direction must be a finite nonzero 3-vector.');
    d = d / norm(d);
    tv = double(t(:));
    kind = char(string(windCfg.type));
    switch kind
    case 'single_sine'
        require_scalar(windCfg,'amplitude');
        require_scalar(windCfg,'frequency_hz');
        require_scalar(windCfg,'phase_rad');
        assert(windCfg.frequency_hz > 0,'TCN0901:WindFrequency','frequency_hz must be positive.');
        speed = windCfg.amplitude * sin(2 * pi * windCfg.frequency_hz * tv + windCfg.phase_rad);
    case 'multi_sine'
        a = double(windCfg.amplitudes(:));
        f = double(windCfg.frequencies_hz(:));
        p = double(windCfg.phases_rad(:));
        assert(numel(a) >= 2 && numel(a) <= 4 && numel(f) == numel(a) && numel(p) == numel(a) && all(isfinite([a;f;p])) && all(f > 0),'TCN0901:WindMultiSine','multi_sine requires 2-4 finite terms with positive Hz.');
        speed = zeros(size(tv));
        for i = 1:numel(a),speed = speed + a(i) * sin(2 * pi * f(i) * tv + p(i));
        end
    case 'biased_dual_sine'
        fields = {'V0','A1','f1','phi1','A2','f2','phi2','rise_time_s'};
        for i = 1:numel(fields),require_scalar(windCfg,fields{i});end
        assert(windCfg.f1 > 0 && windCfg.f2 > 0 && windCfg.f1 ~= windCfg.f2, ...
            'TCN0901:WindDualSineFrequency','biased_dual_sine frequencies must be positive and distinct.');
        assert(windCfg.rise_time_s >= 0,'TCN0901:WindRiseTime', ...
            'biased_dual_sine rise_time_s must be nonnegative.');
        assert(windCfg.V0 > abs(windCfg.A1) + abs(windCfg.A2), ...
            'TCN0901:WindPersistence', ...
            'Persistent one-direction wind requires V0 > abs(A1) + abs(A2); got V0=%.6g, amplitudes %.6g and %.6g m/s.', ...
            windCfg.V0,windCfg.A1,windCfg.A2);
        lowFrequency = windCfg.A1 * sin(2*pi*windCfg.f1*tv + windCfg.phi1);
        highFrequency = windCfg.A2 * sin(2*pi*windCfg.f2*tv + windCfg.phi2);
        rawSpeed = windCfg.V0 + lowFrequency + highFrequency;
        beta = zeros(size(tv));
        if windCfg.rise_time_s == 0
            beta(tv >= 0) = 1;
        else
            rising = tv >= 0 & tv < windCfg.rise_time_s;
            beta(rising) = .5 * (1 - cos(pi * tv(rising) / windCfg.rise_time_s));
            beta(tv >= windCfg.rise_time_s) = 1;
        end
        lowFrequency = beta .* lowFrequency;
        highFrequency = beta .* highFrequency;
        bias = beta .* windCfg.V0;
        speed = beta .* rawSpeed;
    case 'smooth_gust'
        fields = {'peak_speed','start_s','rise_s','hold_s','fall_s'};
        for i = 1:numel(fields),require_scalar(windCfg,fields{i});
        end;
        assert(windCfg.peak_speed >= 0 && windCfg.rise_s > 0 && windCfg.hold_s >= 0 && windCfg.fall_s > 0,'TCN0901:WindGust','smooth_gust durations/peak are invalid.');
        s = windCfg.start_s;
        r = windCfg.rise_s;
        h = windCfg.hold_s;
        f = windCfg.fall_s;
        speed = zeros(size(tv));
        q = tv >= s & tv < s + r;
        speed(q) = windCfg.peak_speed * .5 .* (1 - cos(pi * (tv(q) - s) / r));
        q = tv >= s + r & tv < s + r + h;
        speed(q) = windCfg.peak_speed;
        q = tv >= s + r + h & tv < s + r + h + f;
        speed(q) = windCfg.peak_speed * .5 .* (1 + cos(pi * (tv(q) - (s + r + h)) / f));
    otherwise
        error('TCN0901:WindType','Unsupported wind type: %s.',kind);
    end
    windInertial = d * speed.';
    assert(isequal(size(windInertial),[3,numel(tv)]) && all(isfinite(windInertial),'all'),'TCN0901:WindOutput','Wind output must be finite 3xN.');
    details = struct('type',kind,'direction_unit',d,'speed',speed,'frequency_unit','Hz','velocity_unit','m/s','scalar_input',isscalar(t));
    if strcmp(kind,'biased_dual_sine')
        details.raw_speed = rawSpeed;
        details.startup_envelope = beta;
        details.bias_component = bias;
        details.low_frequency_component = lowFrequency;
        details.high_frequency_component = highFrequency;
    end
end

function require_scalar(s,name)
    % FUNCTION:
    %   校验风场配置中的指定参数为有限数值标量。
    % INPUT: s 为风场配置结构体，name 为待校验字段；无输出，非法时触发配置错误。
    assert(isfield(s,name) && isnumeric(s.(name)) && isscalar(s.(name)) && isfinite(s.(name)),'TCN0901:WindConfig','windCfg.%s must be a finite scalar.',name);
end
