function s = position_compensation_static_n4_init()
% Fixed 100-Hz four-notch bank; state updates are eventwise and causal.
fs=100;Q=4;f=[2.2,3.2,3.7,4.8];
s=struct('b',zeros(4,3),'a',zeros(4,3),'sections',zeros(3,4,4), ...
    'held',zeros(3,1),'initialized',false,'clip_count',0);
for j=1:4
    w0=2*pi*f(j)/fs;alpha=sin(w0)/(2*Q);scale=1+alpha;
    s.b(j,:)=[1,-2*cos(w0),1]/scale;
    s.a(j,:)=[1,-2*cos(w0)/scale,(1-alpha)/scale];
end
end
