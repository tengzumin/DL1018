function [memory, out] = phys_attitude_replacement_candidate_v2(action, memory, in, cfg)
% Isolated causal helper for the proposed non-RBF attitude replacement.
% Call prepare at state time t_k, allocate, then commit clipped command for
% interval [t_k,t_(k+1)]. This helper never accepts Plant truth or applied torque.

switch lower(char(action))
    case 'init'
        assert(isstruct(cfg) && isfield(cfg,'plant') && isfield(cfg,'rbf'), ...
            'PHYSATT:Config','Expected frozen cfg with plant and rbf fields.');
        assert(isfield(cfg.rbf,'attitude') && isfield(cfg.rbf.attitude,'dmax') && ...
            isfield(cfg.rbf.attitude,'beta_rise_time'), ...
            'PHYSATT:Config','Missing attitude dmax/beta_rise_time.');
        assert(isfield(cfg,'attitude_replacement') && ...
            isfield(cfg.attitude_replacement,'J0_controller_fixed_kgm2'), ...
            'PHYSATT:Config','Missing explicit fixed-controller inertia J0.');
        J0=cfg.attitude_replacement.J0_controller_fixed_kgm2;
        assert(isnumeric(J0) && isreal(J0) && isequal(size(J0),[3,3]) && ...
            all(isfinite(J0),'all') && norm(J0-J0.','fro')<1e-12 && ...
            all(eig(double(J0))>0), ...
            'PHYSATT:Config','Fixed-controller J0 must be finite, symmetric, and SPD.');
        assert(numel(cfg.plant.arm_initial)==4 && ...
            cfg.plant.dt>0 && cfg.plant.arm_length_min<cfg.plant.arm_length_max, ...
            'PHYSATT:Config','Invalid nominal inertia, timestep, or arm bounds.');
        assert(numel(cfg.rbf.attitude.dmax)==3 && all(isfinite(cfg.rbf.attitude.dmax)) && ...
            all(cfg.rbf.attitude.dmax>0) && cfg.rbf.attitude.beta_rise_time>0, ...
            'PHYSATT:Config','J0 must be SPD and attitude limits/rise time positive.');
        memory.J0_controller_fixed_kgm2 = double(J0);
        memory.rho_hat = double(cfg.plant.arm_initial(:));
        memory.dhat_a = zeros(3,1);
        memory.node_time = zeros(1,0);
        memory.node_omega = zeros(3,0);
        memory.node_Jhat = zeros(3,3,0);
        memory.interval_tau_cmd = zeros(3,0);
        memory.pending = false;
        memory.pending_step = struct();
        out = struct('initialized',true);
    case 'prepare'
        validate_prepare(memory,in,cfg);
        t = double(in.time_s);
        omega = double(in.omega_body(:));
        u = double(in.morph_command(:));
        if ~isempty(memory.node_time)
            dt=double(cfg.plant.dt);
            assert(abs(t-memory.node_time(end)-dt)<max(1e-12,dt*1e-9), ...
                'PHYSATT:Time','State samples must follow the configured 1 ms interval.');
        end
        rho_dot_hat = 0.05*u;
        [Jhat,~,Jdothat] = arm_mass_properties(memory.rho_hat,cfg.plant,rho_dot_hat);
        J0 = memory.J0_controller_fixed_kgm2;
        dmax = double(cfg.rbf.attitude.dmax(:));

        event = struct('updated',false,'time_s',t,'delta_s',0, ...
            'tau_cmd_bar_Nm',zeros(3,1),'r_tau_Nm',zeros(3,1), ...
            'r_a_rads2',zeros(3,1),'dhat_a_rads2',memory.dhat_a, ...
            'dhat_tau_Nm',J0*memory.dhat_a);
        if logical(in.is_attitude_event) && ~isempty(memory.node_time)
            n = numel(memory.node_time);
            assert(size(memory.interval_tau_cmd,2)==n, ...
                'PHYSATT:Causality','Each prior sample must have a committed interval command.');
            assert(t>memory.node_time(end), 'PHYSATT:Time','Event time must follow the last sample.');
            tNodes = [memory.node_time,t];
            h = diff(tNodes);
            assert(all(h>0) && abs(sum(h)-(t-memory.node_time(1)))<1e-10, ...
                'PHYSATT:Time','Invalid interval timestamps.');
            omegaNodes = [memory.node_omega,omega];
            JNodes = cat(3,memory.node_Jhat,Jhat);
            gNodes = zeros(3,n+1);
            for q = 1:n+1
                w = omegaNodes(:,q);
                J = JNodes(:,:,q);
                gNodes(:,q) = cross(w,J*w);
            end
            gIntegral = sum(0.5*(gNodes(:,1:n)+gNodes(:,2:n+1)).*h,2);
            delta = t-memory.node_time(1);
            tauCmdBar = sum(memory.interval_tau_cmd.*h,2)/delta;
            rTau = (Jhat*omega-memory.node_Jhat(:,:,1)*memory.node_omega(:,1))/delta ...
                + gIntegral/delta-tauCmdBar;
            rA = J0\rTau;
            gamma = 1-exp(-delta/0.10);
            memory.dhat_a = min(max((1-gamma)*memory.dhat_a+gamma*rA,-dmax),dmax);
            event = struct('updated',true,'time_s',t,'delta_s',delta, ...
                'tau_cmd_bar_Nm',tauCmdBar,'r_tau_Nm',rTau,'r_a_rads2',rA, ...
                'gamma',gamma,'dhat_a_rads2',memory.dhat_a, ...
                'dhat_tau_Nm',J0*memory.dhat_a);
            memory.node_time = zeros(1,0);
            memory.node_omega = zeros(3,0);
            memory.node_Jhat = zeros(3,3,0);
            memory.interval_tau_cmd = zeros(3,0);
        end

        % Current command sets Jdot_hat for the current interval, but rho_hat
        % is advanced only in commit; it cannot alter this completed residual.
        memory.node_time(end+1) = t;
        memory.node_omega(:,end+1) = omega;
        memory.node_Jhat(:,:,end+1) = Jhat;
        alphaBS = double(in.alpha_bs_body(:));
        dhatTau = J0*memory.dhat_a;
        tauShape = (Jhat-J0)*alphaBS+cross(omega,(Jhat-J0)*omega)+Jdothat*omega;
        aExtra = min(max(J0\(tauShape-dhatTau),-dmax),dmax);
        beta = min(double(in.sample_index)*double(cfg.plant.dt)/ ...
            double(cfg.rbf.attitude.beta_rise_time),1);
        tauComp = J0*(beta*aExtra);
        memory.pending = true;
        memory.pending_step = struct('time_s',t,'morph_command',u, ...
            'rho_dot_hat',rho_dot_hat,'rho_hat',memory.rho_hat,'Jhat',Jhat);
        out = struct('time_s',t,'rho_hat_m',memory.rho_hat, ...
            'rho_dot_hat_mps',rho_dot_hat,'Jhat_kgm2',Jhat, ...
            'Jdothat_kgm2ps',Jdothat,'tau_shape_Nm',tauShape, ...
            'observer',event,'dhat_a_rads2',memory.dhat_a, ...
            'dhat_tau_Nm',dhatTau,'a_extra_rads2',aExtra, ...
            'beta',beta,'tau_comp_Nm',tauComp,'estimateTorque_Nm',-tauComp);
    case 'commit'
        assert(isstruct(memory) && isfield(memory,'pending') && memory.pending, ...
            'PHYSATT:Order','commit must follow exactly one prepare.');
        assert(isstruct(in) && isfield(in,'time_s') && isfield(in,'tau_cmd_clipped_Nm'), ...
            'PHYSATT:Input','commit requires timestamp and clipped controller torque command.');
        t = double(in.time_s);
        tauCmd = double(in.tau_cmd_clipped_Nm(:));
        assert(numel(tauCmd)==3 && all(isfinite(tauCmd)) && ...
            abs(t-memory.pending_step.time_s)<1e-12, ...
            'PHYSATT:Commit','Commit timestamp/command is invalid.');
        memory.interval_tau_cmd(:,end+1) = tauCmd;
        dt = double(cfg.plant.dt);
        memory.rho_hat = min(max(memory.pending_step.rho_hat+ ...
            dt*memory.pending_step.rho_dot_hat, ...
            double(cfg.plant.arm_length_min)),double(cfg.plant.arm_length_max));
        memory.pending = false;
        memory.pending_step = struct();
        out = struct('time_s',t,'tau_cmd_clipped_Nm',tauCmd, ...
            'rho_hat_next_m',memory.rho_hat);
    otherwise
        error('PHYSATT:Action','Action must be init, prepare, or commit.');
end
end

function validate_prepare(memory,in,cfg)
    assert(isstruct(memory) && isfield(memory,'pending') && ~memory.pending, ...
        'PHYSATT:Order','prepare must follow init or commit.');
    required = {'time_s','omega_body','alpha_bs_body','morph_command', ...
        'sample_index','is_attitude_event'};
    assert(isstruct(in) && all(isfield(in,required)), ...
        'PHYSATT:Input','prepare is missing a required deployment input.');
    u = double(in.morph_command(:));
    w = double(in.omega_body(:));
    a = double(in.alpha_bs_body(:));
    assert(numel(u)==4 && numel(w)==3 && numel(a)==3 && ...
        all(isfinite([u;w;a;double(in.time_s);double(in.sample_index)])) && ...
        all(abs(u)<=1) && isscalar(in.is_attitude_event) && ...
        in.sample_index>=1 && in.sample_index==floor(in.sample_index), ...
        'PHYSATT:Input','Invalid command, state, time, or sample index.');
    assert(isstruct(cfg) && isfield(cfg,'plant') && isfield(cfg,'rbf'), ...
        'PHYSATT:Config','Missing deployment config.');
end
