# Fixed lead helper protocol v1

Scope: deterministic helper parity only. No runner, plant simulation, wind, W, or future-sample access.

- Base: copied N4 causal gate and static N4 helpers from n4cg_v2; all existing N4, SOS gate, EMA, threshold, startup, event-hold, and clipping settings remain frozen.
- Fixed lead after raw N4 output: C(s)=(1+0.08s)/(1+0.03s), Fs=100 Hz, bilinear b=[17/7,-15/7], a=[1,-5/7].
- Difference equation per event: y[n]=(17/7)x[n]-(15/7)x[n-1]+(5/7)y[n-1]. On the first nonzero input, set both histories to that input (DC-one steady state). Update on every event, including while the gate is closed; hold between events.
- Gate features continue to use the unfiltered C5 action. Output is clip(u + g*(lead(N4(u))-u), -3, 3).
- Validation is deterministic Python/MATLAB R2025b helper parity only; no parameter search.
- The earlier exploratory frequency analysis reports 2.55x broadband white-noise RMS gain versus N4 (peak gain 2.667); parity does not establish closed-loop suitability.
