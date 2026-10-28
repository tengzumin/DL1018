function [Phi, audit] = rbf_mimo_basis(z, cfg)
    % FUNCTION:
    %   按配置生成共享 MIMO RBF 网络的高斯基函数向量。
    % PURPOSE:
    %   对指定特征分量归一化后计算其到各中心的径向基响应，并可追加线性基函数。
    % INPUT: z 为联合特征列向量；cfg 定义 RBF 输入维数、尺度、中心、宽度及可选线性维数。
    % OUTPUT: Phi 为高斯基函数及可选线性特征拼接成的列向量。
    % RBF_MIMO_BASIS  Generate the shared MIMO RBF basis vector.
    % The first cfg.rbf_input_dim entries are normalized and evaluated by
    % Gaussian RBF centers. Optional trailing entries are appended as linear
    % basis functions for backward compatibility.

    z = z(:);

    if isfield(cfg, 'rbf_input_dim')
        rbf_dim = cfg.rbf_input_dim;
    else
        rbf_dim = size(cfg.centers, 1);
    end

    if numel(z) < rbf_dim
        error('rbf_mimo_basis:InputTooShort', ...
            'Input z has %d elements, but cfg.rbf_input_dim is %d.', numel(z), rbf_dim);
    end

    z_rbf = z(1:rbf_dim);
    scale = cfg.input_scale(:);
    if numel(scale) < rbf_dim
        error('rbf_mimo_basis:ScaleTooShort', ...
            'cfg.input_scale has %d elements, but cfg.rbf_input_dim is %d.', numel(scale), rbf_dim);
    end

    z_scaled = z_rbf ./ max(scale(1:rbf_dim), eps);
    centers = cfg.centers;
    if size(centers, 1) ~= rbf_dim
        error('rbf_mimo_basis:CenterDimensionMismatch', ...
            'cfg.centers has %d rows, but cfg.rbf_input_dim is %d.', size(centers, 1), rbf_dim);
    end

    diff = centers - z_scaled;
    dist_sq = sum(diff .^ 2, 1);
    Phi_rbf = exp(-dist_sq(:) ./ (2 * cfg.sigma ^ 2));
    widthScale = 1;
    if isfield(cfg, 'width_scale') && ~isempty(cfg.width_scale)
        widthScale = double(cfg.width_scale);
        assert(isscalar(widthScale) && isfinite(widthScale) && widthScale >= .85 && widthScale <= 1.15, ...
            'TCN0916:RbfWidthScale', 'width_scale must be a finite scalar in [0.85, 1.15].');
    end
    phi0Norm = norm(Phi_rbf, 2);
    usedFallback = false;
    if widthScale ~= 1
        raw = Phi_rbf .^ (1 / widthScale ^ 2);
        rawNorm = norm(raw, 2);
        if ~isfinite(rawNorm) || rawNorm <= 1e-12 || phi0Norm <= 1e-12
            usedFallback = true;
        else
            Phi_rbf = raw * (phi0Norm / rawNorm);
        end
    end
    audit = struct('width_scale',widthScale,'phi0_norm',phi0Norm, ...
        'phi_norm',norm(Phi_rbf,2),'relative_norm_error', ...
        abs(norm(Phi_rbf,2)-phi0Norm)/max(phi0Norm,eps), ...
        'relative_feature_change',norm(Phi_rbf-exp(-dist_sq(:)./(2*cfg.sigma^2)),2)/max(phi0Norm,eps), ...
        'used_numerical_fallback',usedFallback);

    linear_dim = 0;
    if isfield(cfg, 'linear_dim')
        linear_dim = cfg.linear_dim;
    end

    if linear_dim > 0
        if numel(z) < rbf_dim + linear_dim
            error('rbf_mimo_basis:LinearInputTooShort', ...
                'Input z has %d elements, but %d are required.', numel(z), rbf_dim + linear_dim);
        end

        z_linear = z(rbf_dim + (1:linear_dim));
        if isfield(cfg, 'linear_scale') && ~isempty(cfg.linear_scale)
            linear_scale = cfg.linear_scale(:);
        else
            linear_scale = ones(linear_dim, 1);
        end
        if numel(linear_scale) < linear_dim
            error('rbf_mimo_basis:LinearScaleTooShort', ...
                'cfg.linear_scale has %d elements, but cfg.linear_dim is %d.', numel(linear_scale), linear_dim);
        end
        Phi = [Phi_rbf; z_linear ./ max(linear_scale(1:linear_dim), eps)];
    else
        Phi = Phi_rbf;
    end

end
