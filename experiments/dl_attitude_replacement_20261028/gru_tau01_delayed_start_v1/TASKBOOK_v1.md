# GRU tau01 delayed-start candidate

## Falsifiable hypothesis
The parent tau01 position degradation is concentrated in the first five seconds while later position behavior is better. Holding the delayed-prediction gradient coefficient at rho=0.01 for the first five seconds, then ramping linearly to rho=0.1 from 5 to 6 seconds, may reduce startup degradation while retaining later gains. This is a testable hypothesis, not a guarantee or evidence of successful tuning.

## Frozen scope
Only rho(t) in the delayed-position prediction gradient changes. The cosine GRU, C5 position method, PCF, gamma, lambda, network, output clip, fixed J0, model weights, and the same 12-scene DEV/VAL input list are inherited unchanged. rho is computed from zero-based simulation sample index n and dt: t=n*dt, with dt checked as 1 ms. No TEST data, inertia reconstruction, training, or Plant call is authorized in this preparation.

## Status
Source and no-Plant preparation are pending root source review. The single-scene runner is gated by RELEASED status and a positive Plant-call budget.
