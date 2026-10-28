from __future__ import annotations
import csv, hashlib, json
from pathlib import Path
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/MANIFEST.json'
OUT = Path(__file__).resolve().parent
G = 9.8
MAX_TILT = np.deg2rad(30.0)
WINDOWS = [('0-5s', 0.0, 5.0), ('15-20s', 15.0, 20.0), ('0-20s', 0.0, 20.0)]
TOL_RAD = 1e-8


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def decode_u16(x) -> str:
    return ''.join(chr(int(c)) for c in np.asarray(x).reshape(-1) if int(c)).rstrip('\x00')


def euler_zyx_to_R(euler):
    e = np.asarray(euler, dtype=np.float64)
    r, p, y = e[:, 0], e[:, 1], e[:, 2]
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    R = np.empty((len(e), 3, 3), dtype=np.float64)
    R[:, 0, 0] = cy * cp
    R[:, 0, 1] = cy * sp * sr - sy * cr
    R[:, 0, 2] = cy * sp * cr + sy * sr
    R[:, 1, 0] = sy * cp
    R[:, 1, 1] = sy * sp * sr + cy * cr
    R[:, 1, 2] = sy * sp * cr - cy * sr
    R[:, 2, 0] = -sp
    R[:, 2, 1] = cp * sr
    R[:, 2, 2] = cp * cr
    return R


def so3_angle(e1, e2):
    R1, R2 = euler_zyx_to_R(e1), euler_zyx_to_R(e2)
    rel = np.einsum('nki,nkj->nij', R1, R2)
    cos_theta = np.clip((np.trace(rel, axis1=1, axis2=2) - 1.0) / 2.0, -1.0, 1.0)
    sin_theta = 0.5 * np.sqrt((rel[:, 2, 1] - rel[:, 1, 2])**2 +
                              (rel[:, 0, 2] - rel[:, 2, 0])**2 +
                              (rel[:, 1, 0] - rel[:, 0, 1])**2)
    return np.arctan2(sin_theta, cos_theta)


def fixed_task(acc, yaw):
    ax, ay, az = acc[:, 0], acc[:, 1], acc[:, 2]
    c, s = np.cos(yaw), np.sin(yaw)
    A = c * ax + s * ay
    B = s * ax - c * ay
    roll = np.arctan2(B, np.hypot(az + G, A))
    pitch = np.arctan2(A, az + G)
    tilt = np.hypot(roll, pitch)
    scale = np.minimum(1.0, MAX_TILT / np.maximum(tilt, 1e-300))
    roll, pitch = roll * scale, pitch * scale
    return np.column_stack((roll, pitch, yaw)), tilt > MAX_TILT


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert manifest.get('TEST_read') is False, 'manifest says TEST_read is not false'
    assert len(manifest['records']) == 6
    metric_rows, triangle_rows, hashes, group_samples = [], [], [], {}
    hashes.append({'kind': 'manifest', 'scene_id': '', 'arm': '', 'path': str(MANIFEST),
                   'expected_sha256': '', 'observed_sha256': sha256(MANIFEST), 'expected_matches_observed': ''})
    source_files = [
        ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/candidate_runner_work/matlab/core/position_bs_step.m',
        ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/candidate_runner_work/matlab/core/baseline_force_to_attitude.m',
        ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/candidate_runner_work/matlab/core/vehicle_derivative.m',
        ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/candidate_runner_work/matlab/core/morphology_aware_wind_load.m',
        ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_dev_v1/candidate_runner_work/matlab/runtime/run_mlp15_dev72_closed_loop.m',
    ]
    for p in source_files:
        if p.exists():
            hashes.append({'kind': 'source', 'scene_id': '', 'arm': '', 'path': str(p),
                           'expected_sha256': '', 'observed_sha256': sha256(p), 'expected_matches_observed': ''})

    for rec in manifest['records']:
        scene_id = rec['scene_id']
        tag = scene_id.rsplit('_', 1)[-1]
        for arm, path_key, sha_key in [('B', 'b_raw_path', 'b_raw_sha256'), ('C5', 'c5_raw_path', 'c5_raw_sha256')]:
            raw_path = Path(rec[path_key])
            got_sha = sha256(raw_path)
            assert got_sha == rec[sha_key], f'{scene_id}/{arm}: raw SHA mismatch'
            hashes.append({'kind': 'raw', 'scene_id': scene_id, 'arm': arm, 'path': str(raw_path),
                           'expected_sha256': rec[sha_key], 'observed_sha256': got_sha, 'expected_matches_observed': 'true'})
            with h5py.File(raw_path, 'r') as f:
                test_accessed = int(np.asarray(f['runIdentity/TEST_accessed']).reshape(-1)[0])
                assert test_accessed == 0, f'{scene_id}/{arm}: raw identity TEST_accessed={test_accessed}'
                log, scene = f['log'], f['scene']
                t = np.asarray(log['transition_time'], dtype=np.float64).reshape(-1)
                state = np.asarray(log['state'], dtype=np.float64)
                filt = np.asarray(log['filtered_attitude_reference'], dtype=np.float64).T
                wind_force = np.asarray(log['wind_force_I'], dtype=np.float64)
                ref = scene['reference']
                acc = np.asarray(ref['acceleration'], dtype=np.float64)[:, :len(t)].T
                yaw = np.asarray(ref['yaw'], dtype=np.float64).reshape(-1)[:len(t)]
                wind = np.asarray(scene['environment_wind_I'], dtype=np.float64)
                assert state.shape == (12, len(t) + 1)
                assert filt.shape == (len(t), 3)
                assert wind_force.shape == (3, len(t))
                assert acc.shape == (len(t), 3) and yaw.shape == (len(t),)
                actual = state[6:9, :len(t)].T
                fixed, clipped = fixed_task(acc, yaw)
                d_af = so3_angle(actual, fixed)
                d_ai = so3_angle(actual, filt)
                d_if = so3_angle(filt, fixed)
                violation = np.maximum.reduce((np.zeros_like(d_af), d_af - d_ai - d_if, np.abs(d_ai - d_if) - d_af))
                max_wind_norm = float(np.max(np.linalg.norm(wind, axis=0)))
                mean_wind = np.mean(wind, axis=1)
                wind_force_norm = np.linalg.norm(wind_force, axis=0)
                wind_force_horizontal = np.linalg.norm(wind_force[:2], axis=0)
                wind_class = 'zero_wind' if max_wind_norm <= 1e-12 else 'nonzero_wind'
                wind_group = f'{wind_class}_{tag}'
                for win_name, lo, hi in WINDOWS:
                    mask = (t >= lo) & (t < hi)
                    expected_count = int(round((hi - lo) / (t[1] - t[0])))
                    assert int(mask.sum()) == expected_count, f'{scene_id}/{arm}/{win_name}: sample count {mask.sum()}'
                    af, ai, iff, v = d_af[mask], d_ai[mask], d_if[mask], violation[mask]
                    f_norm, f_horizontal = wind_force_norm[mask], wind_force_horizontal[mask]
                    rms = lambda x: float(np.sqrt(np.mean(x * x)))
                    metric_rows.append({
                        'scene_id': scene_id, 'wind_tag': tag, 'wind_group': wind_group, 'arm': arm,
                        'window': win_name, 'samples': int(mask.sum()), 't_first_s': float(t[mask][0]), 't_last_s': float(t[mask][-1]),
                        'wind_max_norm_raw': max_wind_norm, 'wind_mean_x_raw': float(mean_wind[0]),
                        'wind_mean_y_raw': float(mean_wind[1]), 'wind_mean_z_raw': float(mean_wind[2]),
                        'wind_force_max_norm_N': float(np.max(f_norm)),
                        'wind_force_rms_norm_N': float(np.sqrt(np.mean(f_norm * f_norm))),
                        'wind_force_max_horizontal_N': float(np.max(f_horizontal)),
                        'wind_force_rms_horizontal_N': float(np.sqrt(np.mean(f_horizontal * f_horizontal))),
                        'actual_vs_fixedtask_rms_rad': rms(af), 'actual_vs_fixedtask_rms_deg': float(np.rad2deg(rms(af))),
                        'actual_vs_filtered_inner_reference_rms_rad': rms(ai), 'actual_vs_filtered_inner_reference_rms_deg': float(np.rad2deg(rms(ai))),
                        'filtered_inner_reference_vs_fixedtask_rms_rad': rms(iff), 'filtered_inner_reference_vs_fixedtask_rms_deg': float(np.rad2deg(rms(iff))),
                        'fixedtask_projection_active_count': int(np.count_nonzero(clipped[mask])),
                        'pointwise_triangle_violation_count_gt_1e-8rad': int(np.count_nonzero(v > TOL_RAD)),
                        'pointwise_triangle_max_violation_rad': float(np.max(v)),
                        'pointwise_triangle_max_violation_deg': float(np.rad2deg(np.max(v))),
                    })
                    triangle_rows.append({
                        'scene_id': scene_id, 'wind_group': wind_group, 'arm': arm, 'window': win_name,
                        'samples': int(mask.sum()), 'pointwise_bound': 'abs(d_actual_fixed-d_actual_filtered)<=d_filtered_fixed',
                        'max_abs_difference_minus_bound_rad': float(np.max(np.abs(af - ai) - iff)),
                        'max_d_actual_fixed_minus_sum_rad': float(np.max(af - ai - iff)),
                        'max_abs_diff_lower_bound_violation_rad': float(np.max(np.abs(ai - iff) - af)),
                        'violations_gt_1e-8rad': int(np.count_nonzero(v > TOL_RAD)),
                        'max_positive_violation_rad': float(np.max(v)),
                    })
                    group_samples.setdefault((wind_group, arm, win_name), []).append((af, ai, iff))

    def summarize_group(wind_group, arm, win_name, packs):
        vals = [np.concatenate([p[i] for p in packs]) for i in range(3)]
        rms = lambda x: float(np.sqrt(np.mean(x * x)))
        macro = [float(np.mean([rms(p[i]) for p in packs])) for i in range(3)]
        return {'wind_group': wind_group, 'arm': arm, 'window': win_name,
                'aggregation': 'pooled_sample_rms_plus_scenario_macro',
                'scenes': len(packs), 'samples': len(vals[0]),
                'pooled_actual_vs_fixedtask_rms_deg': float(np.rad2deg(rms(vals[0]))),
                'pooled_actual_vs_filtered_inner_reference_rms_deg': float(np.rad2deg(rms(vals[1]))),
                'pooled_filtered_inner_reference_vs_fixedtask_rms_deg': float(np.rad2deg(rms(vals[2]))),
                'scenario_macro_actual_vs_fixedtask_rms_deg': float(np.rad2deg(macro[0])),
                'scenario_macro_actual_vs_filtered_inner_reference_rms_deg': float(np.rad2deg(macro[1])),
                'scenario_macro_filtered_inner_reference_vs_fixedtask_rms_deg': float(np.rad2deg(macro[2]))}

    group_rows = []
    combined = {}
    for (wind_group, arm, win_name), packs in sorted(group_samples.items()):
        if wind_group.startswith('nonzero_wind_'):
            combined.setdefault((arm, win_name), []).extend(packs)
        group_rows.append(summarize_group(wind_group, arm, win_name, packs))
    for (arm, win_name), packs in sorted(combined.items()):
        group_rows.append(summarize_group('combined_nonzero_wind_W12_W13', arm, win_name, packs))

    def write_csv(name, rows):
        path = OUT / name
        with path.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
    write_csv('scene_window_metrics.csv', metric_rows)
    write_csv('wind_group_summary.csv', group_rows)
    write_csv('pointwise_triangle_checks.csv', triangle_rows)
    hashes.append({'kind': 'script', 'scene_id': '', 'arm': '', 'path': str(Path(__file__).resolve(),),
                   'expected_sha256': '', 'observed_sha256': sha256(Path(__file__)), 'expected_matches_observed': ''})
    write_csv('INPUT_SHA256.csv', hashes)
    print(json.dumps({'status':'PASS','manifest_sha256':sha256(MANIFEST),'records':len(manifest['records']),
                      'metric_rows':len(metric_rows),'triangle_rows':len(triangle_rows),'hash_rows':len(hashes),
                      'max_triangle_violation_rad':max(r['pointwise_triangle_max_violation_rad'] for r in metric_rows),
                      'triangle_violations':sum(r['pointwise_triangle_violation_count_gt_1e-8rad'] for r in metric_rows)},indent=2))

if __name__ == '__main__':
    main()
