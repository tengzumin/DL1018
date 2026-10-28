"""Real Windows file-share tests for retry1 JSON replacement; never trains."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import platform
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from ctypes import wintypes

sys.dont_write_bytecode = True

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
CreateFileW = kernel32.CreateFileW
CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                        wintypes.HANDLE]
CreateFileW.restype = wintypes.HANDLE
CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _open_lock(path: Path, allow_delete: bool):
    share = FILE_SHARE_READ | FILE_SHARE_WRITE
    if allow_delete:
        share |= FILE_SHARE_DELETE
    handle = CreateFileW(str(path), GENERIC_READ, share, None, OPEN_EXISTING,
                         FILE_ATTRIBUTE_NORMAL, None)
    if handle is None or handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _counted_write(trainer, target: Path, value: dict, attempts_out=None):
    attempts = attempts_out if attempts_out is not None else {"count": 0, "winerrors": []}
    attempts["count"] = 0
    attempts["winerrors"] = []
    temp = target.with_name(target.name + ".tmp")
    path_class = type(target)
    original = path_class.replace

    def counted_replace(self, destination, *args, **kwargs):
        if self == temp:
            attempts["count"] += 1
        try:
            return original(self, destination, *args, **kwargs)
        except PermissionError as exc:
            if self == temp:
                attempts["winerrors"].append(getattr(exc, "winerror", None))
            raise

    with mock.patch.object(path_class, "replace", counted_replace):
        trainer._write_json(target, value)
    return attempts["count"]


def run(repo_root: Path, report_root: Path) -> dict:
    if os.name != "nt":
        raise RuntimeError("this check requires real Windows CreateFileW semantics")
    trainer_path = repo_root / "experiments/attitude_cm18_a2_20261024/train_cm18_a2_retry1_v1.py"
    exporter_path = repo_root / "experiments/attitude_cm18_a2_20261024/export_best_cm18_a2_retry1_v1.py"
    spec = importlib.util.spec_from_file_location("retry1_trainer_fixture", trainer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load retry trainer")
    trainer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = trainer
    spec.loader.exec_module(trainer)
    for source in (trainer_path, exporter_path):
        compile(source.read_text(encoding="utf-8"), str(source), "exec")

    case_dir = report_root / ("case_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8])
    case_dir.mkdir(exist_ok=False)
    results = {}

    # Denying FILE_SHARE_DELETE must make real replace attempts fail until the handle closes.
    short_path = case_dir / "short_lock.json"
    short_path.write_bytes(b'{"old":true}\n')
    short_handle = _open_lock(short_path, allow_delete=False)
    releaser_error = []

    def release_short():
        time.sleep(0.15)
        if not CloseHandle(short_handle):
            releaser_error.append(ctypes.get_last_error())

    releaser = threading.Thread(target=release_short, name="release-short-lock", daemon=True)
    releaser.start()
    t0 = time.perf_counter()
    short_attempts = _counted_write(trainer, short_path, {"case": "short", "written": True})
    short_seconds = time.perf_counter() - t0
    releaser.join(timeout=2)
    if releaser.is_alive() or releaser_error:
        raise RuntimeError(f"short lock release failed: {releaser_error}")
    short_value = json.loads(short_path.read_text(encoding="utf-8"))
    if short_attempts < 2 or short_attempts > 20 or short_value != {"case": "short", "written": True}:
        raise AssertionError("short non-delete-sharing lock did not prove retry-then-success")
    results["short_non_delete_lock"] = {
        "status": "PASS", "attempts": short_attempts,
        "elapsed_seconds": short_seconds, "new_value": short_value,
    }

    # A long-lived lock must exhaust the bounded retries and preserve old bytes.
    long_path = case_dir / "long_lock.json"
    old_bytes = b'{"sentinel":"keep-this-old-file"}\n'
    long_path.write_bytes(old_bytes)
    long_handle = _open_lock(long_path, allow_delete=False)
    long_attempts = {"count": 0}
    t0 = time.perf_counter()
    try:
        try:
            _counted_write(trainer, long_path, {"case": "long", "must_not_land": True}, long_attempts)
        except PermissionError as exc:
            elapsed = time.perf_counter() - t0
            if getattr(exc, "winerror", None) not in (5, 32, 33):
                raise AssertionError(f"unexpected final Windows error: {exc!r}") from exc
        else:
            raise AssertionError("long lock unexpectedly reported success")
        long_attempts = long_attempts["count"]
    finally:
        if not CloseHandle(long_handle):
            raise ctypes.WinError(ctypes.get_last_error())
    if long_attempts != 20 or long_path.read_bytes() != old_bytes:
        raise AssertionError("long-lock exhaustion count or old-file preservation failed")
    temp_path = long_path.with_name(long_path.name + ".tmp")
    if not temp_path.is_file() or json.loads(temp_path.read_text(encoding="utf-8")) != {"case": "long", "must_not_land": True}:
        raise AssertionError("failed replacement temp file was not preserved for inspection")
    if elapsed > 1.5:
        raise AssertionError(f"retry window exceeded expected bound: {elapsed:.3f}s")
    results["long_non_delete_lock"] = {
        "status": "PASS", "attempts": long_attempts,
        "elapsed_seconds": elapsed, "old_sha256_preserved": _sha256(long_path),
        "old_file_unchanged": True,
        "failed_temp_preserved": temp_path.is_file(),
        "failed_temp_sha256": _sha256(temp_path),
    }

    # FILE_SHARE_DELETE still gets an observed MoveFileExW denial while held; release after 150 ms.
    share_delete_path = case_dir / "share_delete_transient.json"
    share_delete_path.write_bytes(b'{"old":true}\n')
    share_delete_handle = _open_lock(share_delete_path, allow_delete=True)
    share_delete_error = []

    def release_share_delete():
        time.sleep(0.15)
        if not CloseHandle(share_delete_handle):
            share_delete_error.append(ctypes.get_last_error())

    share_delete_releaser = threading.Thread(target=release_share_delete,
                                             name="release-share-delete-lock", daemon=True)
    share_delete_releaser.start()
    share_delete_attempts = {"count": 0, "winerrors": []}
    t0 = time.perf_counter()
    _counted_write(trainer, share_delete_path,
                   {"case": "share_delete_transient", "written": True}, share_delete_attempts)
    share_delete_seconds = time.perf_counter() - t0
    share_delete_releaser.join(timeout=2)
    if share_delete_releaser.is_alive() or share_delete_error:
        raise RuntimeError(f"share-delete lock release failed: {share_delete_error}")
    share_delete_value = json.loads(share_delete_path.read_text(encoding="utf-8"))
    if (share_delete_attempts["count"] < 2 or 5 not in share_delete_attempts["winerrors"]
            or share_delete_value != {"case": "share_delete_transient", "written": True}):
        raise AssertionError("share-delete transient lock did not prove WinError5 then bounded retry success")
    results["share_delete_transient_lock"] = {
        "status": "PASS", "share_delete_flag": True,
        "attempts": share_delete_attempts["count"],
        "observed_winerrors": share_delete_attempts["winerrors"],
        "elapsed_seconds": share_delete_seconds, "new_value": share_delete_value,
    }
    return {
        "schema": "CM18_A2_RETRY1_WINDOWS_REPLACE_TEST_V1",
        "status": "PASS",
        "test_directory": str(case_dir.relative_to(repo_root)),
        "platform": platform.platform(),
        "python": sys.version,
        "trainer_sha256": _sha256(trainer_path),
        "exporter_sha256": _sha256(exporter_path),
        "retry_contract": {"attempts": 20, "sleep_seconds": 0.05,
                            "maximum_sleep_seconds": 0.95,
                            "retry_winerrors": [5, 32, 33]},
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    repo_root = args.repo_root.resolve(strict=True)
    report_root = Path(__file__).resolve().parent
    result = run(repo_root, report_root)
    out = report_root / ("ROOT_WINDOWS_REPLACE_TEST_RESULT_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + ".json")
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    print("result_path=" + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())