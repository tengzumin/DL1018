from __future__ import annotations
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK_IN = HERE / 'C4_INPUT_LOCK_v2.json'
LOCK_OUT = HERE / 'C4_INPUT_LOCK_v3.json'
CONTRACT_V2 = HERE / 'C4_RUN_CONTRACT_v2.json'
CONTRACT_V3 = HERE / 'C4_RUN_CONTRACT_v3.json'
LOCK_V2_SHA = '7f9d482313701940a272b1b4030af87bc2c0a5d926d9929e57bb84ea0d0aae96'

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(path: Path) -> dict[str, str]:
    return {'path': str(path.resolve()), 'sha256': sha(path)}

def main() -> None:
    assert not LOCK_OUT.exists(), f'refusing to overwrite {LOCK_OUT}'
    assert sha(LOCK_IN) == LOCK_V2_SHA, 'frozen v2 lock changed'
    old = json.loads(LOCK_IN.read_text(encoding='utf-8'))
    contract_v2 = json.loads(CONTRACT_V2.read_text(encoding='utf-8'))
    contract = json.loads(CONTRACT_V3.read_text(encoding='utf-8'))
    expected = copy.deepcopy(contract_v2)
    expected['schema'] = 'C4_COORDINATE_RUN_CONTRACT_V3'
    expected['state'] = 'LOCKED_C4_COORDINATE_NO_PLANT_PARENT_REVIEW_REQUIRED_V3'
    assert contract == expected, 'v3 contract must differ only by schema/state version'
    assert old['schema'] == 'C4_COORDINATE_INPUT_LOCK_V2'
    assert old['state'] == 'LOCKED_C4_COORDINATE_NO_PLANT_PARENT_REVIEW_REQUIRED_V2'

    payload = copy.deepcopy(old)
    payload['schema'] = 'C4_COORDINATE_INPUT_LOCK_V3'
    payload['state'] = 'LOCKED_C4_COORDINATE_NO_PLANT_PARENT_REVIEW_REQUIRED_V3'
    payload['created_utc'] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    payload['source_files']['lock_builder'] = ref(Path(__file__))
    payload['source_files']['prepare_entry'] = ref(HERE / 'prepare_c4_coordinate_v3.m')
    payload['source_files']['single_scene_runner'] = ref(HERE / 'run_c4_coordinate_v3.m')
    payload['source_files']['contract'] = ref(CONTRACT_V3)
    payload['scope'] = contract
    LOCK_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'LOCK_BUILT_NO_PLANT_V3', 'path': str(LOCK_OUT),
                      'sha256': sha(LOCK_OUT), 'active_sources': len(payload['active_source_inventory']),
                      'matlab_sources': payload['source_counts']['matlab'],
                      'mat_sources': payload['source_counts']['mat'],
                      'scenes': len(payload['scenes']),
                      'changes': ['schema', 'state', 'created_utc', 'source_files.lock_builder',
                                  'source_files.prepare_entry', 'source_files.single_scene_runner',
                                  'source_files.contract', 'scope.schema', 'scope.state']}, indent=2))

if __name__ == '__main__':
    main()
