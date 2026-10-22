import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import run_dl1018


class SceneReferenceGateTest(unittest.TestCase):
    def setUp(self):
        fixture_root = Path(__file__).resolve().parents[1] / "reports" / "integration_next14_v1" / "engineering" / "fixtures"
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="python_scene_reference_", dir=fixture_root))
        (self.root / "reports").mkdir()
        configs = self.root / "configs"
        configs.mkdir()
        (configs / "contract_dl1018.json").write_text(
            json.dumps({"contract_id": run_dl1018.CONTRACT}), encoding="utf-8"
        )

    def write_g01(self, reference_id=None):
        report = {"status": "PASS", "next_gate_allowed": True}
        if reference_id is not None:
            report["reference_contract_id"] = reference_id
        (self.root / "reports" / "G01_SCENES.json").write_text(
            json.dumps(report), encoding="utf-8"
        )

    def test_old_pass_report_is_rejected_before_pass_skip(self):
        self.write_g01()

        with self.assertRaises(run_dl1018.GateError):
            run_dl1018.run_gate(self.root, None, "G01_SCENES")

        self.assertFalse((self.root / "logs").exists())
        self.assertFalse((self.root / "data").exists())

    def test_missing_g01_with_attempt_rows_is_not_stamped_as_new(self):
        logs = self.root / "logs"
        logs.mkdir()
        (logs / "attempt_index.csv").write_text(
            "run_id,status\nG02_P_TEACHER_OLD_B,STABLE\n", encoding="utf-8"
        )

        with self.assertRaises(run_dl1018.GateError):
            run_dl1018.run_gate(self.root, None, "G01_SCENES")

        self.assertFalse((self.root / "data").exists())
        self.assertFalse((self.root / "reports" / "G01_SCENES.json").exists())

    def test_through_rejects_orphaned_scene_configs_before_g00_writes(self):
        for config_name in ("scene_specs.csv", "dataset_plan.json"):
            with self.subTest(config_name=config_name):
                root = self.root / config_name.replace(".", "_")
                (root / "reports").mkdir(parents=True)
                configs = root / "configs"
                configs.mkdir()
                (configs / "contract_dl1018.json").write_text(
                    json.dumps({"contract_id": run_dl1018.CONTRACT}), encoding="utf-8"
                )
                (configs / config_name).write_text("fixture\n", encoding="utf-8")

                with mock.patch.object(run_dl1018, "_safe_print"):
                    status = run_dl1018.main([
                        "--through", "G02_P_TEACHER", "--root", str(root)
                    ])

                self.assertEqual(status, run_dl1018.EXIT_CONTRACT)
                self.assertFalse((root / "logs").exists())
                self.assertFalse((root / "data").exists())

    def test_downstream_gate_requires_current_g01_before_layout(self):
        self.write_g01("DL1018_OLD_SCENE_REFERENCE")

        with self.assertRaises(run_dl1018.GateError):
            run_dl1018.run_gate(self.root, None, "G02_P_TEACHER")

        self.assertFalse((self.root / "logs").exists())
        self.assertFalse((self.root / "data").exists())

    def test_current_g01_reference_identity_is_allowed(self):
        self.write_g01(run_dl1018.REFERENCE_CONTRACT_ID)

        run_dl1018._assert_scene_reference(self.root)

    def test_through_rejects_legacy_g01_before_g00_writes_state(self):
        self.write_g01()

        with mock.patch.object(run_dl1018, "_safe_print"):
            status = run_dl1018.main([
                "--through", "G02_P_TEACHER", "--root", str(self.root)
            ])

        self.assertEqual(status, run_dl1018.EXIT_CONTRACT)
        self.assertFalse((self.root / "logs").exists())
        self.assertFalse((self.root / "data").exists())


if __name__ == "__main__":
    unittest.main()
