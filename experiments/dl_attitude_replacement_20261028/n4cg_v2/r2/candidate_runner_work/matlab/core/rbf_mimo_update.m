function [d_hat, net, info] = rbf_mimo_update(z, s, net, cfg, dt)
    % FUNCTION:
    %   使用当前 RBF 权重输出扰动估计，并按离散自适应律更新网络权重。
    % PURPOSE:
    %   将误差信号限幅后用于下一时刻的因果权重更新，避免本采样权重更新反向改变当前输出。
    % INPUT: z 为联合特征，s 为三轴学习误差信号，net.W 为权重，cfg 含基函数/增益/泄漏/投影界限，dt 为更新时间（s）。
    % OUTPUT: d_hat 为限幅后的三轴估计；net 返回新权重；info 可选记录更新前后量。
    % RBF_MIMO_UPDATE  共享 MIMO RBF 更新函数。
    % z 为联合特征输入，s 为 3 维学习信号，输出当前步的 3 轴扰动估计。
    % 当前实现采用“当前权重输出 + 下一步权重更新”的因果形式：
    % W_dot = -Phi * sat(s)' * Gamma - W * Sigma。
    % 第一项按基函数和限幅误差信号调整权重，cfg.gamma 按输出通道缩放适应速度；第二项泄漏权重以抑制长期漂移。
    % 更新以 dt 前向 Euler 离散，并将更新后权重逐元素投影到 cfg.wmax 范围。

    z = z(:);
    s = s(:);
    s_eff = max(min(s, cfg.s_limit), -cfg.s_limit);
    if isfield(cfg,'basis_override')
        Phi=double(cfg.basis_override(:));
        basisAudit=struct('width_scale',1,'phi0_norm',norm(Phi),'phi_norm',norm(Phi), ...
            'relative_norm_error',0,'relative_feature_change',0,'used_numerical_fallback',false);
    else
        [Phi, basisAudit] = rbf_mimo_basis(z, cfg);
    end
    W_before = net.W;
    assert(size(W_before,1)==numel(Phi),'rbf_mimo_update:BasisWeightMismatch', ...
        'Weight rows (%d) do not match basis dimension (%d).',size(W_before,1),numel(Phi));

    output_unclipped = W_before.' * Phi;
    output_limit_active = any(abs(output_unclipped(:)) > double(cfg.dmax(:)));
    d_hat = output_unclipped;
    d_hat = max(min(d_hat, cfg.dmax), -cfg.dmax);

    gamma_vec = cfg.gamma(:).';
    sigma_vec = cfg.sigma_w(:).';
    basisGamma=ones(size(Phi));
    if isfield(cfg,'basis_gamma_scale'),basisGamma=double(cfg.basis_gamma_scale(:));end
    assert(numel(basisGamma)==numel(Phi)&&all(isfinite(basisGamma))&&all(basisGamma>0), ...
        'rbf_mimo_update:BasisGamma','Basis gamma scale must be positive and match the basis.');
    W_dot = -(Phi .* basisGamma) * (gamma_vec .* s_eff.') - W_before .* sigma_vec;

    W_unprojected = W_before + W_dot * dt;
    W_after = max(min(W_unprojected, cfg.wmax), -cfg.wmax);
    net.W = W_after;
    if nargout >= 3
        info = struct('input',z,'surface',s,'surface_effective',s_eff, ...
            'Phi',Phi,'W_before',W_before,'output_unclipped',output_unclipped, ...
            'output_limit_active',output_limit_active,'W_dot',W_dot, ...
            'W_unprojected',W_unprojected,'W_after',W_after,'basis_audit',basisAudit);
    end

end
