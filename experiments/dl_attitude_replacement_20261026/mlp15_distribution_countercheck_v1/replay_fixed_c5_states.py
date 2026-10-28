"""Compare both frozen models on exactly the same six original C5 teacher traces."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
BASE = RESEARCH / 'mlp15_c5_teacher_full72_v1'
BALANCED = RESEARCH / 'mlp15_c5_teacher_ghp7_balance_v1'

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    out = HERE / 'SAME_STATE_REPLAY.json'
    if out.exists():
        raise FileExistsError(out)
    torch.set_num_threads(1)
    sys.path.insert(0, str(BASE))
    import train_mlp15_c5_full72_v1 as source
    sys.path.insert(0, str(BALANCED))
    import audit_ghp7_balanced_fit_v1 as replay
    lock = source.load_and_verify_lock(require_release=False)
    ids = lock['scene_ids_in_training_order']
    x, y = source._load_c5_training_arrays(lock, ids)
    manifest = json.loads((RESEARCH / 'mlp15_balanced_devscreen_v1/MANIFEST.json').read_text())
    chosen = [r['scene_id'] for r in manifest['records'] if int(r['scene_id'].rsplit('_W', 1)[1]) >= 12]
    assert len(chosen) == 6 and all('TEST' not in s for s in chosen)
    indices = [ids.index(s) for s in chosen]
    x, y = x[indices], y[indices].astype(np.float64)
    MLP15, make_windows = replay.load_model_helpers()
    runs = {'C5_FULL72': BASE / 'runs/C5_MLP15_FULL72_SEED2026102001',
            'GHP7_BALANCED': BALANCED / 'runs/C5_MLP15_GHP7_BALANCE_SEED2026102001'}
    expected = {'C5_FULL72': '67a6564148ba8c1988d7457c04a5d3271516ff4010da18e61e29fd7da13be46b',
                'GHP7_BALANCED': '8e048e212ae17f4e588ba35d7af18ed5183799074fbc2c66dfe7c6e5a77d8138'}
    rows = []
    models = []
    for name, run in runs.items():
        assert sha(run / 'mlp15_attitude_weights_v1.mat') == expected[name]
        model, mean, std, scale = replay.load_checkpoint(run / 'final_step_60000.pt', MLP15)
        prediction, clip_count = replay.predict(model, x, mean, std, scale, make_windows)
        models.append({'model': name, 'MAT_sha256': expected[name],
                       'checkpoint_sha256': sha(run / 'final_step_60000.pt'),
                       'runtime_clip_count_by_axis': clip_count.tolist()})
        for i, scene_id in enumerate(chosen):
            difference = prediction[i] - y[i]
            rows.append({'model': name, 'scene_id': scene_id,
                         'axis_RMSE_rad_s2': np.sqrt(np.mean(difference**2, axis=0)).tolist(),
                         'vector_RMSE_rad_s2': float(np.sqrt(np.mean(np.sum(difference**2, axis=1)))),
                         'teacher_RMS_rad_s2': np.sqrt(np.mean(y[i]**2, axis=0)).tolist(),
                         'prediction_RMS_rad_s2': np.sqrt(np.mean(prediction[i]**2, axis=0)).tolist(),
                         'mean_prediction_bias_rad_s2': np.mean(difference, axis=0).tolist()})
    report = {'schema': 'C5_DISTRIBUTION_SAME_STATE_REPLAY_V1', 'Plant_calls': 0,
              'TEST_read': False, 'C5_only_data': True, 'B24_arrays_read': False,
              'data_used_for_training': True,
              'interpretation': 'Same recorded C5 state/window/target; training-data fit diagnostic, not closed-loop causality or independent validation.',
              'dataset_sha256': sha(source.DATASET_PATH),
              'source_script_sha256': sha(__file__), 'models': models, 'rows': rows}
    with out.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    for row in rows:
        print(row['model'], row['scene_id'], row['vector_RMSE_rad_s2'])

if __name__ == '__main__':
    main()
