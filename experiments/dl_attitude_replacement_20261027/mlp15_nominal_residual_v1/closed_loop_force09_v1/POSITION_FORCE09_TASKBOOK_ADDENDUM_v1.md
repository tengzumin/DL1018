# Position compensation force-scale candidate

## Scope

This isolated candidate tests one fixed factor, `position_nn_compensation_scale = 0.9`, on the actual applied DSSM position compensation acceleration. It is sourced from `closed_loop_candidate_v1`, preserving the parent's MLP output-before-RLS and tracking update order. It does not train, change the score metric, alter BS nominal feedback, modify the command filter, or alter any attitude gains.

The scale is applied after the original DSSM output, beta and clipping are computed. It does not scale the DSSM raw output or change the model update. The unscaled output and actual applied acceleration are logged separately. The scaled acceleration is converted to force using configured mass; that force is the held/injected compensation consumed by `position_bs_step`. Its `commanded_acceleration` then feeds the existing M110, PCF coordination, delayed-coordinate integrals, attitude mapping and command filter.

The C5 DSSM14 model, normalizer, initial weights, BS parameters and PCF/delayed-coordinate options are reused. Since the compensation force actually applied to the position loop is scaled, this candidate changes the physical position path and must not be described as physically equivalent to the original C5 position path.

## Verification boundary

No-Plant checks cover exact scale-1 restoration, scale-0.9 force/acceleration units, unchanged BS nominal force, original MLP source hashes and the candidate source-hash manifest. The preparation makes no Plant call and reads no TEST inputs. The release remains `PREPARED_NO_PLANT_PENDING_ROOT_LAUNCH` with zero authorized Plant calls until the root task explicitly advances it.

