# Position compensation force-scale candidate

## Scope

This isolated candidate tests one fixed factor, `position_nn_compensation_scale = 0.9`, on the actual applied DSSM position compensation acceleration. It does not train, change the metric, alter the BS nominal feedback, modify the command filter, or change the MLP15 update-first/RLS timing.

The scale is applied after the original DSSM output, beta and clipping are computed, and after the corresponding weight update has been computed. The unscaled model raw output and applied acceleration remain traceable. The scaled acceleration is converted to force using the configured mass; that force is the held and injected value consumed by `position_bs_step`. The resulting `commanded_acceleration` then feeds the existing M110, PCF coordination, delayed-coordinate integrals, attitude mapping and command filter.

The C5 DSSM14 model, normalizer, initial weights, BS parameters and PCF/delayed-coordinate options are reused. Since the compensation force actually applied to the position loop is scaled, this candidate changes the physical position path and must not be described as physically equivalent to the original C5 position path.

## Verification boundary

The no-Plant checks verify exact scale-1 restoration, scale-0.9 force/acceleration units, unchanged BS nominal force, source identities and the existing MLP15 update-first checks. No Plant calls or TEST inputs are used in this preparation. The release remains `PREPARED_NO_PLANT_PENDING_ROOT_LAUNCH` with zero authorized Plant calls until the root task explicitly advances it.

