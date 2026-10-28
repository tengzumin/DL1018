function [memory,out] = phys_attitude_replacement_gate_v1(action,memory,in,cfg)
% Gated derivative of the frozen v2 helper; F=O=1 delegates unchanged.
action=lower(char(action));
switch action
    case 'init'
        assert(isstruct(in)&&all(isfield(in,{'feedforward_enabled','observer_enabled'})), ...
            'GATEPHYS:Flags','init requires feedforward_enabled and observer_enabled.');
        F=binary_flag(in.feedforward_enabled,'feedforward_enabled');
        O=binary_flag(in.observer_enabled,'observer_enabled');
        [memory,~]=phys_attitude_replacement_candidate_v2('init',struct,struct,cfg);
        memory.gate_F=F; memory.gate_O=O;
        out=struct('initialized',true,'feedforward_enabled',F,'observer_enabled',O);
    case 'prepare'
        assert(isstruct(memory)&&isfield(memory,'gate_F')&&isfield(memory,'gate_O'), ...
            'GATEPHYS:Order','init must precede prepare.');
        assert(isstruct(in)&&all(isfield(in,{'feedforward_enabled','observer_enabled'})), ...
            'GATEPHYS:Flags','prepare requires feedforward_enabled and observer_enabled.');
        F=binary_flag(in.feedforward_enabled,'feedforward_enabled');
        O=binary_flag(in.observer_enabled,'observer_enabled');
        assert(F==memory.gate_F&&O==memory.gate_O, ...
            'GATEPHYS:Flags','F/O cannot change during a run.');
        helperInput=rmfield(in,{'feedforward_enabled','observer_enabled'});
        if F&&O
            [memory,out]=phys_attitude_replacement_candidate_v2('prepare',memory,helperInput,cfg);
            return
        end
        if ~O, helperInput.is_attitude_event=false; end
        [memory,out]=phys_attitude_replacement_candidate_v2('prepare',memory,helperInput,cfg);
        if ~O
            memory.dhat_a=zeros(3,1);
            memory.node_time=zeros(1,0);
            memory.node_omega=zeros(3,0);
            memory.node_Jhat=zeros(3,3,0);
            memory.interval_tau_cmd=zeros(3,0);
        end
        J0=memory.J0_controller_fixed_kgm2;
        dmax=double(cfg.rbf.attitude.dmax(:));
        aExtra=min(max(J0\(double(F)*out.tau_shape_Nm-double(O)*out.dhat_tau_Nm),-dmax),dmax);
        tauComp=J0*(double(out.beta)*aExtra);
        out.a_extra_rads2=aExtra;
        out.tau_comp_Nm=tauComp;
        out.estimateTorque_Nm=-tauComp;
    case 'commit'
        assert(isstruct(memory)&&isfield(memory,'gate_O'), ...
            'GATEPHYS:Order','init must precede commit.');
        [memory,out]=phys_attitude_replacement_candidate_v2('commit',memory,in,cfg);
        if ~memory.gate_O
            memory.dhat_a=zeros(3,1);
            memory.node_time=zeros(1,0);
            memory.node_omega=zeros(3,0);
            memory.node_Jhat=zeros(3,3,0);
            memory.interval_tau_cmd=zeros(3,0);
        end
    otherwise
        error('GATEPHYS:Action','Action must be init, prepare, or commit.');
end
end

function value=binary_flag(value,name)
assert((islogical(value)&&isscalar(value))|| ...
    (isnumeric(value)&&isreal(value)&&isscalar(value)&&isfinite(double(value))&&ismember(double(value),[0,1])), ...
    'GATEPHYS:Flags','%s must be a scalar binary flag.',name);
value=logical(value);
end