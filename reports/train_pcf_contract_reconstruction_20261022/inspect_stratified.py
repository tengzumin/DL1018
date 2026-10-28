from __future__ import annotations
import csv, hashlib, json, re, time
from pathlib import Path

import h5py
import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
ARCHIVE = ROOT.parent / 'REFERENCE_FIX_FULL72_20261021_022342_313'
BASE = ARCHIVE / 'corrected_reference_training_v1'
TRAIN_INDEX = BASE / 'corrected_pair_training/manifests/PAIR_TRAINING_INPUT_INDEX.csv'
RAW_INDEX = BASE / 'g3_collection/reports/G3_D4_CACHE_INDEX_1632.csv'
AVAILABILITY = ROOT / 'reports/hf_w15_reinvestigation_20261022/training_raw_availability.csv'
EXPECTED = {
    TRAIN_INDEX: '257089f1dc455b7bc97bf1c772be31d1d8ae83079e7ec41f591d96e31fed39ca',
    RAW_INDEX: '3c8291c12628acfb9d950fb67cb84b56fe09cdaeaeac38706e8903291873e84e',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def stat(path: Path) -> dict:
    s = path.stat()
    return {'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns}


def read_csv(path: Path) -> list[dict]:
    with path.open('r', newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def wind_band(cell: int) -> str:
    if 0 <= cell <= 8:
        return 'W00_W08'
    if 9 <= cell <= 14:
        return 'W09_W14'
    if cell == 15:
        return 'W15'
    raise ValueError(f'wind_cell outside frozen 0..15: {cell}')


def scalar_preview(ds: h5py.Dataset):
    if ds.size == 0 or ds.size > 16 or ds.dtype.kind not in 'biufSU':
        return None
    x = np.asarray(ds[()])
    if x.dtype.kind == 'S':
        return x.astype('U').tolist()
    return x.tolist()


def inventory(path: Path) -> tuple[list[dict], float]:
    t0 = time.perf_counter()
    rows = []
    with h5py.File(path, 'r') as f:
        def visit(name, obj):
            row = {'path': '/' + name, 'kind': 'group' if isinstance(obj, h5py.Group) else 'dataset'}
            row['matlab_class'] = str(obj.attrs.get('MATLAB_class', b'').decode(errors='replace') if isinstance(obj.attrs.get('MATLAB_class', b''), bytes) else obj.attrs.get('MATLAB_class', ''))
            if isinstance(obj, h5py.Dataset):
                row.update(shape=list(obj.shape), dtype=str(obj.dtype), nbytes_est=int(obj.size * obj.dtype.itemsize))
                row['scalar_preview'] = scalar_preview(obj)
                if obj.dtype.kind == 'O' and obj.size:
                    refs = []
                if obj.dtype.kind == 'O':
                    row['reference_count'] = int(obj.size)
        f.visititems(visit)
        for key, value in f.attrs.items():
            rows.append({'path': '/@' + key, 'kind': 'attribute', 'value': str(value)[:256]})
    return rows, time.perf_counter() - t0


def main():
    for path, expected in EXPECTED.items():
        assert path.is_file(), path
        assert sha(path) == expected, (path, sha(path), expected)
    assert AVAILABILITY.is_file()
    availability_hash = sha(AVAILABILITY)
    train = [r for r in read_csv(TRAIN_INDEX) if r['split'].lower() == 'train']
    raw = [r for r in read_csv(RAW_INDEX) if r['split'].upper() == 'TRAIN']
    avail = {r['run_id']: r for r in read_csv(AVAILABILITY)}
    assert len(train) == len(raw) == 1536 and len({r['run_id'] for r in train}) == 1536
    raw_by_id = {r['run_id']: r for r in raw}
    assert len(raw_by_id) == 1536 and len(avail) == 1536
    joined = []
    for t in train:
        r = raw_by_id[t['run_id']]
        a = avail[t['run_id']]
        assert t['task'] == r['task'] == a['task']
        assert t['role'] == r['role'] == a['role']
        wind_match = re.search(r'_W(\d{2})(?:_|$)', r['runtime_scene_id'])
        assert wind_match and int(t['wind_cell']) == int(wind_match.group(1)) == int(a['wind_cell']), (t['run_id'], t['wind_cell'], r['runtime_scene_id'], wind_match.group(1) if wind_match else None, a['wind_cell'])
        for name in ('raw', 'event_h5', 'cache'):
            assert t[f'{name}_sha256'] == r[f'{name}_sha256'], (t['run_id'], name)
        assert Path(a['raw_path']).resolve() == Path(r['raw_path']).resolve()
        assert Path(a['run_start_path']).resolve() == Path(r['run_start_path']).resolve()
        assert Path(a['event_h5_path']).resolve() == Path(r['event_h5_path']).resolve()
        assert a['raw_exists'].lower() == a['run_start_exists'].lower() == a['event_h5_exists'].lower() == 'true'
        cell = int(t['wind_cell'])
        row = dict(t)
        row.update(raw_path=r['raw_path'], raw_path_sha256=r['raw_sha256'],
                   run_start_path=r['run_start_path'], run_start_path_sha256=r['run_start_sha256'],
                   event_h5_path=r['event_h5_path'], event_h5_path_sha256=r['event_h5_sha256'],
                   wind_band=wind_band(cell), raw_bytes=int(a['raw_bytes']),
                   run_start_bytes=int(a['run_start_bytes']), event_h5_bytes=int(a['event_h5_bytes']))
        joined.append(row)
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in joined:
        groups.setdefault((row['task'], row['role'], row['wind_band']), []).append(row)
    assert len(groups) == 18, (len(groups), sorted(groups))
    chosen = []
    group_manifest = []
    for key, rows in sorted(groups.items()):
        rows.sort(key=lambda r: r['run_id'])
        first = rows[0]
        chosen.append(first)
        group_manifest.append({'task': key[0], 'role': key[1], 'wind_band': key[2],
                               'candidate_count': len(rows), 'selected_run_id': first['run_id'],
                               'selection_rule': 'lexicographically_first_run_id'})
    assert len(chosen) == 18
    fields = ['run_id', 'task', 'role', 'wind_cell', 'wind_band', 'cache_path', 'cache_sha256',
              'raw_path', 'raw_path_sha256', 'run_start_path', 'run_start_path_sha256',
              'event_h5_path', 'event_h5_path_sha256', 'raw_bytes', 'run_start_bytes', 'event_h5_bytes']
    with (OUT / 'stratified_sample_manifest.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows({k:r[k] for k in fields} for r in chosen)
    with (OUT / 'stratified_group_counts.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(group_manifest[0])); w.writeheader(); w.writerows(group_manifest)

    inventories, samples = [], []
    total_bytes = 0
    for sample in chosen:
        for kind, path_key, expected_hash in (
            ('raw', 'raw_path', 'raw_path_sha256'),
            ('run_start', 'run_start_path', 'run_start_path_sha256'),
            ('event_h5', 'event_h5_path', 'event_h5_path_sha256'),
        ):
            path = Path(sample[path_key]).resolve()
            assert path.is_file(), path
            before_stat = stat(path)
            t0 = time.perf_counter()
            before_hash = sha(path)
            hash_seconds = time.perf_counter() - t0
            assert before_hash == sample[expected_hash], (sample['run_id'], kind, before_hash, sample[expected_hash])
            inv, open_seconds = inventory(path)
            after_hash = sha(path)
            after_stat = stat(path)
            assert before_hash == after_hash and before_stat == after_stat, (sample['run_id'], kind, 'changed during read')
            total_bytes += before_stat['bytes']
            for item in inv:
                item.update(run_id=sample['run_id'], task=sample['task'], role=sample['role'],
                            wind_band=sample['wind_band'], source_kind=kind)
                inventories.append(item)
            datasets = [r for r in inv if r['kind'] == 'dataset']
            samples.append({'run_id': sample['run_id'], 'task': sample['task'], 'role': sample['role'],
                            'wind_band': sample['wind_band'], 'source_kind': kind, 'path': str(path),
                            'sha256_before': before_hash, 'sha256_after': after_hash,
                            'bytes': before_stat['bytes'], 'mtime_ns_before': before_stat['mtime_ns'],
                            'mtime_ns_after': after_stat['mtime_ns'], 'dataset_count': len(datasets),
                            'dataset_paths': [d['path'] for d in datasets],
                            'hash_seconds': hash_seconds, 'hdf5_open_inventory_seconds': open_seconds})
    with (OUT / 'stratified_hdf5_inventory.jsonl').open('w', encoding='utf-8') as f:
        for row in inventories:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
    with (OUT / 'stratified_file_audit.json').open('w', encoding='utf-8') as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
        f.write('\n')
    raw_rows = [r for r in samples if r['source_kind'] == 'raw']
    all_raw_bytes = sum(r['raw_bytes'] if 'raw_bytes' in r else r['bytes'] for r in raw_rows)
    sec = sum(r['hash_seconds'] + r['hdf5_open_inventory_seconds'] for r in raw_rows)
    projected = sec * (58.60 * (1024**3) / max(1, all_raw_bytes))
    meta = {'status': 'STRATIFIED_FIELDS_INVENTORIED', 'created_local': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'sample_count': len(chosen), 'strata_count': len(group_manifest), 'sampling': 'task x role x wind_band; first run_id lexicographically',
            'wind_bands': {'W00_W08': [0, 8], 'W09_W14': [9, 14], 'W15': [15]},
            'source_indices': {str(p): {'sha256': EXPECTED[p]} for p in EXPECTED},
            'availability_table': {'path': str(AVAILABILITY), 'sha256': availability_hash},
            'sample_input_bytes_all_kinds': total_bytes, 'raw_samples_total_bytes': all_raw_bytes,
            'raw_hash_and_inventory_seconds': sec, 'estimated_1536_raw_hash_and_inventory_seconds_at_sample_rate': projected,
            'estimated_1536_raw_hours_at_sample_rate': projected / 3600,
            'estimated_1536_derived_storage_bytes_upper_bound': int(1536 * 1968 * (8 * (3 + 3 + 3 + 3) + 4 * 4)),
            'raws_copied': False, 'numeric_reconstruction_started': False,
            'full_1536_not_started_pending_main_model_review': True,
            'optimizer_steps': 0, 'plant_calls': 0, 'gpu_jobs': 0, 'test_accessed': False,
            'limitations': ['HDF5 structure inventory only; timing field semantics remain unverified.',
                            'Dataset references and field names are not a same-event causality proof.']}
    (OUT / 'PHASE_STATE.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == '__main__':
    main()

