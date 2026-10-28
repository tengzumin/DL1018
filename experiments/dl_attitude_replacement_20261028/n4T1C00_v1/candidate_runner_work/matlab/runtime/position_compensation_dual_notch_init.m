function s = position_compensation_dual_notch_init()
% Fixed W09 diagnostic only: two causal 100-Hz, Q=4 notches at 2.2/3.2 Hz.
fs=100;Q=4;f=[2.2,3.2];
s=struct('b',zeros(2,3),'a',zeros(2,3),'section1',zeros(3,4), ...
    'section2',zeros(3,4),'held',zeros(3,1),'initialized',false,'clip_count',0);
for j=1:2
    w0=2*pi*f(j)/fs;alpha=sin(w0)/(2*Q);scale=1+alpha;
    s.b(j,:)=[1,-2*cos(w0),1]/scale;
    s.a(j,:)=[1,-2*cos(w0)/scale,(1-alpha)/scale];
end
end
