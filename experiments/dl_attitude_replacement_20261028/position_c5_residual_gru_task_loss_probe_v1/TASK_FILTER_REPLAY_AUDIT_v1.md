# TRAIN24 task/filter replay audit

- Scenes checked: 24; target replay max error 8.327e-17 rad.
- Command-filter replay max error 5.829e-16 rad; applied filter-acceleration max error 7.905e-14 rad/s^2.
- Requested filter-acceleration replay max error 7.905e-14 rad/s^2; 100-Hz action hold max error 0.000e+00 m/s^2.
- Autograd segment smoke check: finite nonzero gradient=True, norm=3.94547e-06.
- The candidate loss is fixed in the JSON. Fitting is deferred: these available C5 raws use the older attitude-RBF backbone and do not match the cosine-GRU parent used for deployment.
- Read-only scope: no TEST, new Plant, real-wind fields, or inertia reconstruction.
