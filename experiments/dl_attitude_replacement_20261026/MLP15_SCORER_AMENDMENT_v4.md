# MLP15 scorer amendment v4

The previous scorer artifacts are retained. The v2t calculation used sqrt(mean(sum(axis position errors))) for its 8–12 s field, omitting the per-axis square. Signed errors could cancel to a negative mean and produce an imaginary value, which MATLAB JSON correctly rejected.

The v2v scorer computes the three-dimensional position RMSE as sqrt(mean(sum(axis_error.^2))). This matches the frozen 0–20 s metric and the stated RMSE definition. The change corrects only this score formula and preserves the candidate release, raw files, references, scene pairing, thresholds, and advancement gate. No Plant call or raw change occurs.