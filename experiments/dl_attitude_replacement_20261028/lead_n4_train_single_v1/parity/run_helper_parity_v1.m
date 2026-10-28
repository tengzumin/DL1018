function run_helper_parity_v1(inputPath, outputPath)
% Deterministic helper parity endpoint; no plant or runner is invoked.
assert(strcmp(version('-release'),'2025b'), 'Parity:Version', ...
    'Expected MATLAB R2025b, got %s.', version('-release'));
addpath(fullfile(fileparts(mfilename('fullpath')),'matlab'));
in=readmatrix(inputPath);
s=position_compensation_n4_causal_gate_init();
out=zeros(size(in,1),25);
for k=1:size(in,1)
    t=in(k,1);event=logical(in(k,2));u=in(k,3:5).';
    [s,uout,~,d]=position_compensation_n4_causal_gate_step(s,u,event,t);
    out(k,:)=[t,double(event),u.',uout.',d.n4_raw.',d.n4_lead.', ...
        d.Ebp,d.Elo,d.ratio,d.gtarget,d.g,double(d.clip.'), ...
        s.event_count,s.clip_count,double(d.lead_initialized)];
end
writematrix(out,outputPath);
disp(['MATLAB_RELEASE=' version('-release') ' ROWS=' num2str(size(in,1)) ...
    ' EVENTS=' num2str(s.event_count) ' CLIPS=' num2str(s.clip_count)]);
end
