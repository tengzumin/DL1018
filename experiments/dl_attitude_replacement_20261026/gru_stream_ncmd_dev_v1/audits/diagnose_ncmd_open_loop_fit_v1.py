from __future__ import annotations
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from trained_model_parity_reference import model_from_mat, stream

ROOT = Path(__file__).resolve().parents[4]
STUDY = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_ncmd_dev_v1'
FEATURE_PATH = ROOT / 'experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/matched_teacher_data_v1.npz'
FEATURE_MANIFEST = ROOT / 'experiments/dl_attitude_replacement_20261026/mlp15_c5_teacher_redistill_v1/DATASET_MANIFEST_v1.json'
TARGET_PATH = ROOT / 'experiments/dl_attitude_replacement_20261026/nominal_command_target_data_v1/nominal_command_target_v1.npz'
TARGET_MANIFEST = ROOT / 'experiments/dl_attitude_replacement_20261026/nominal_command_target_data_v1/MANIFEST_v1.json'
COSINE_RELEASE = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_cosine_dev_v1/RELEASE.json'
NCMD_RELEASE = STUDY / 'RELEASE.json'
LOCKED_CFG = STUDY / 'LOCKED_CFG.json'
OUT_CSV = STUDY / 'audits/NCMD_OPEN_LOOP_FIT_METRICS_v1.csv'
OUT_JSON = STUDY / 'audits/NCMD_OPEN_LOOP_FIT_METRICS_v1.json'
EXPECTED_FEATURE_SHA = 'b3a8ca6446d6bdde0573e6c233aa222a6cfb28d35f13b084e8dd9683c16c111f'
EXPECTED_TARGET_SHA = '88df5c2f2088910a9c5650a5c67efdb7f42d30cabc021d0da83b68b72578ffb7'
EXPECTED_TARGET_MANIFEST_SHA = 'fc5ed29cfd0a5260a2992f28b8ada21ccd72f7d25c7bbe00831dca7a10e9e0ab'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def summarize(error: np.ndarray, target: np.ndarray) -> tuple[float, float, float]:
    return (float(np.sqrt(np.mean(error * error))), float(np.mean(error)),
            float(np.sqrt(np.mean(target * target))))


def main() -> None:
    feature_sha, target_sha, target_manifest_sha = sha(FEATURE_PATH), sha(TARGET_PATH), sha(TARGET_MANIFEST)
    assert feature_sha == EXPECTED_FEATURE_SHA
    assert target_sha == EXPECTED_TARGET_SHA
    assert target_manifest_sha == EXPECTED_TARGET_MANIFEST_SHA
    old_release, new_release = read_json(COSINE_RELEASE), read_json(NCMD_RELEASE)
    old_model_path, new_model_path = Path(old_release['model_path']), Path(new_release['model_path'])
    old_model_sha, new_model_sha = sha(old_model_path), sha(new_model_path)
    assert old_model_sha == old_release['model_sha256']
    assert new_model_sha == new_release['model_sha256']
    assert new_release['candidate'] == 'GRU32_STREAM72_NCMD_S2026102001'

    old_model = model_from_mat(loadmat(old_model_path))
    new_model = model_from_mat(loadmat(new_model_path))
    for key in ('input_mean', 'input_std', 'target_rms'):
        assert np.array_equal(old_model[key], new_model[key]), f'normalizer mismatch: {key}'
    cfg = read_json(LOCKED_CFG)
    dmax = np.asarray(cfg['dmax'], dtype=np.float64).reshape(3)
    feature = np.load(FEATURE_PATH, allow_pickle=False)
    target = np.load(TARGET_PATH, allow_pickle=False)
    rows: list[dict] = []
    aggregate_inputs: dict[tuple, list[np.ndarray]] = {}
    splits = (
        ('DEV24', 'c5_train_x', 'c5_train_scene_ids', 'c5_train_y', 'c5_train_y_clipped_float32', 'c5_train_y_clipped_float32'),
        ('VAL48_AS_DEV_TRAIN', 'c5_val_x', 'c5_val_scene_ids', 'c5_val_y', 'c5_val_y_clipped_float32', 'c5_val_y_clipped_float32'),
    )
    for split, x_key, ids_key, teacher_key, ncmd_key, target_ids_key in splits:
        X = np.asarray(feature[x_key], dtype=np.float64)
        ids = np.asarray(feature[ids_key]).astype(str)
        ids_y = np.asarray(target[target_ids_key]).astype(str)
        Y_teacher = np.asarray(feature[teacher_key], dtype=np.float64)
        Y_ncmd = np.asarray(target[ncmd_key], dtype=np.float64)
        assert X.shape == (len(ids), 1999, 13)
        assert np.array_equal(ids, ids_y)
        assert Y_teacher.shape == Y_ncmd.shape == (len(ids), 1999, 3)
        assert np.isfinite(X).all() and np.isfinite(Y_teacher).all() and np.isfinite(Y_ncmd).all()
        for model_name, model, model_sha in (
            ('COSINE', old_model, old_model_sha), ('NCMD', new_model, new_model_sha),
        ):
            for scene_index, scene_id in enumerate(ids):
                predicted_raw, _ = stream(X[scene_index], model, np.float64)
                predicted_clipped = np.clip(predicted_raw, -dmax, dmax)
                phases = (
                    ('ALL', np.ones(1999, dtype=bool)),
                    ('BETA_MATURE', np.arange(1, 2000) * 0.01 >= 2.2),
                )
                for target_name, Y in (('NCMD_CLIPPED_TARGET', Y_ncmd), ('C5_TEACHER_TARGET', Y_teacher)):
                    for stage, pred in (('PRE_DMAX', predicted_raw), ('POST_DMAX', predicted_clipped)):
                        for phase, mask in phases:
                            for axis, axis_name in enumerate(('roll', 'pitch', 'yaw')):
                                err = pred[mask, axis] - Y[scene_index, mask, axis]
                                target_axis = Y[scene_index, mask, axis]
                                rmse, bias, target_rms = summarize(err, target_axis)
                                row = {
                                    'candidate_model': model_name,
                                    'candidate_model_sha256': model_sha,
                                    'target': target_name,
                                    'prediction_stage': stage,
                                    'split': split,
                                    'scene_id': scene_id,
                                    'phase': phase,
                                    'axis': axis_name,
                                    'event_count': int(mask.sum()),
                                    'rmse_rad_s2': rmse,
                                    'mean_bias_rad_s2': bias,
                                    'target_rms_rad_s2': target_rms,
                                }
                                rows.append(row)
                                key = (model_name, target_name, stage, split, phase, axis_name)
                                aggregate_inputs.setdefault(key, []).append(err)

    with OUT_CSV.open('w', newline='', encoding='utf-8') as stream_file:
        writer = csv.DictWriter(stream_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for key, error_parts in sorted(aggregate_inputs.items()):
        model_name, target_name, stage, split, phase, axis = key
        errors = np.concatenate(error_parts)
        summary.append({
            'candidate_model': model_name, 'target': target_name, 'prediction_stage': stage,
            'split': split, 'phase': phase, 'axis': axis,
            'scene_count': len(error_parts), 'event_count': int(errors.size),
            'rmse_rad_s2': float(np.sqrt(np.mean(errors * errors))),
            'mean_bias_rad_s2': float(np.mean(errors)),
        })
    report = {
        'schema': 'DL1018_GRU_STREAM_NCMD_OPEN_LOOP_FIT_V1',
        'status': 'PASS_NCMD_OPEN_LOOP_DIAGNOSTIC',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': {'Plant_calls': 0, 'training_jobs': 0, 'optimizer_updates': 0, 'TEST_read': False,
                  'data_role': 'DEV24 + VAL48_AS_DEV_TRAIN; not independent validation'},
        'comparison_contract': 'Compare both frozen models on the exact same clipped NCMD target, and separately against the old C5 teacher target. RMSE/bias definitions are identical across candidate models; no cross-target loss-size claim.',
        'models': {
            'COSINE': {'path': str(old_model_path), 'sha256': old_model_sha},
            'NCMD': {'path': str(new_model_path), 'sha256': new_model_sha},
        },
        'inputs': {
            'feature_dataset_path': str(FEATURE_PATH), 'feature_dataset_sha256': feature_sha,
            'feature_manifest_path': str(FEATURE_MANIFEST), 'feature_manifest_sha256': sha(FEATURE_MANIFEST),
            'target_dataset_path': str(TARGET_PATH), 'target_dataset_sha256': target_sha,
            'target_manifest_path': str(TARGET_MANIFEST), 'target_manifest_sha256': target_manifest_sha,
            'feature_members_read': ['c5_train_x', 'c5_train_scene_ids', 'c5_val_x', 'c5_val_scene_ids',
                                     'c5_train_y', 'c5_val_y'],
            'target_members_read': ['c5_train_scene_ids', 'c5_val_scene_ids',
                                    'c5_train_y_clipped_float32', 'c5_val_y_clipped_float32'],
            'unclipped_target_members_read': False,
            'B24_arrays_read': False,
            'dmax_rad_s2': dmax.tolist(),
        },
        'event_contract': {'events_per_scene': 1999, 'hidden_reset_per_scene': True,
                           'hidden_carry_within_scene': True, 'mature_phase': 'event time >= 2.2 s',
                           'prediction_is_current_event_only': True},
        'per_split_axis_summary': summary,
        'per_scene_axis_csv_path': str(OUT_CSV),
        'per_scene_axis_csv_sha256': sha(OUT_CSV),
    }
    OUT_JSON.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'csv': str(OUT_CSV), 'json': str(OUT_JSON),
                      'csv_sha256': sha(OUT_CSV), 'json_sha256': sha(OUT_JSON),
                      'row_count': len(rows), 'summary_count': len(summary)}, indent=2))


if __name__ == '__main__':
    main()
