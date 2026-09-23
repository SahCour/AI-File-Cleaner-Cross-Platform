"""Tests for rollback.py (AI File Cleaner).

Isolation strategy:
  * Every test runs inside its own tempfile.TemporaryDirectory() and
    os.chdir()s into it (LOG_FILE is relative to CWD), restoring the
    previous CWD in tearDown.
  * subprocess.run is patched with a fake that performs os.replace inside
    the temp directory; the real /bin/mv is never invoked.
  * All file paths are absolute paths inside the temp directory.

Only the standard library is used (unittest, tempfile, unittest.mock,
contextlib, io, json, os, re, importlib.util).
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROLLBACK_PATH = os.path.join(REPO_ROOT, "rollback.py")

_spec = importlib.util.spec_from_file_location("rollback", ROLLBACK_PATH)
rollback = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rollback)


def _fake_run(real_os):
    """Return a subprocess.run fake that does os.replace(current_target, original_source)."""

    def run(cmd, capture_output=False, text=False):
        assert cmd[0] == "/bin/mv"
        assert cmd[1] == "-n"
        current_target = cmd[2]
        original_source = cmd[3]
        try:
            real_os.replace(current_target, original_source)
            return mock.Mock(returncode=0, stderr="")
        except Exception as exc:  # noqa: BLE001
            return mock.Mock(returncode=1, stderr=str(exc))

    return run


class RollbackBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.addCleanup(self._restore_cwd)

    def _restore_cwd(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def _run_rollback(self, logs):
        log_path = os.path.join(self._tmp.name, rollback.LOG_FILE)
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(logs, fh)

        out = io.StringIO()
        with mock.patch("subprocess.run", side_effect=_fake_run(os)), \
             contextlib.redirect_stdout(out):
            rollback.main()
        return out.getvalue()

    def _counts(self, output):
        success = int(re.search(r"Успешно восстановлено:\s*(\d+)", output).group(1))
        errors = int(re.search(r"Ошибок:\s*(\d+)", output).group(1)) if "Ошибок:" in output else 0
        return success, errors


class RollbackTests(RollbackBase):
    def test_reverse_order_last_success_restored_first(self):
        # Two consecutive successful moves: A -> B, then B -> C.
        # Rollback must process from the end: B -> A happens BEFORE C -> B.
        a = os.path.join(self._tmp.name, "a.txt")
        b = os.path.join(self._tmp.name, "b.txt")
        c = os.path.join(self._tmp.name, "c.txt")
        with open(c, "w", encoding="utf-8") as fh:
            fh.write("data")
        logs = [
            {"source": a, "target": b, "status": "success", "type": "file"},
            {"source": b, "target": c, "status": "success", "type": "file"},
        ]
        log_path = os.path.join(self._tmp.name, rollback.LOG_FILE)
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(logs, fh)

        moves = []

        def recording_run(cmd, capture_output=False, text=False):
            moves.append((cmd[2], cmd[3]))
            return _fake_run(os)(cmd, capture_output=capture_output, text=text)

        with mock.patch("subprocess.run", side_effect=recording_run), \
             contextlib.redirect_stdout(io.StringIO()):
            rollback.main()

        # Reverse order: the last successful move is restored first.
        self.assertEqual(moves, [(c, b), (b, a)])
        # Full rollback of the chain A->B->C leaves the file back at A; B and C
        # are emptied out again.
        self.assertTrue(os.path.exists(a))
        self.assertFalse(os.path.exists(b))
        self.assertFalse(os.path.exists(c))
        with open(a, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "data")

    def test_non_success_entries_skipped(self):
        src = os.path.join(self._tmp.name, "target.txt")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("x")
        logs = [
            {"source": os.path.join(self._tmp.name, "orig.txt"), "target": src,
             "status": "failed", "type": "file"},
            {"source": os.path.join(self._tmp.name, "orig2.txt"), "target": src,
             "status": "success", "type": "file"},
        ]
        out = self._run_rollback(logs)
        success, errors = self._counts(out)
        self.assertEqual((success, errors), (1, 0))
        # The file was restored by the success entry only.
        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, "orig2.txt")))

    def test_missing_target_warns_and_counts_error(self):
        missing = os.path.join(self._tmp.name, "gone.txt")
        logs = [{"source": os.path.join(self._tmp.name, "orig.txt"),
                 "target": missing, "status": "success", "type": "file"}]
        out = self._run_rollback(logs)
        success, errors = self._counts(out)
        self.assertEqual(success, 0)
        self.assertEqual(errors, 1)
        self.assertIn("больше не существует", out)
        self.assertIn("⚠️", out)
        # No crash, no files created
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, "orig.txt")))

    def test_log_renamed_to_bak_after_success(self):
        src = os.path.join(self._tmp.name, "f.txt")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("y")
        orig = os.path.join(self._tmp.name, "orig.txt")
        logs = [{"source": orig, "target": src, "status": "success", "type": "file"}]
        out = self._run_rollback(logs)
        success, errors = self._counts(out)
        self.assertEqual((success, errors), (1, 0))
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, rollback.LOG_FILE)))
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, rollback.LOG_FILE + ".bak")))

    def test_log_not_renamed_when_nothing_succeeded(self):
        # Only a failed entry: nothing restored -> log must stay in place.
        src = os.path.join(self._tmp.name, "f.txt")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("y")
        logs = [{"source": os.path.join(self._tmp.name, "orig.txt"), "target": src,
                 "status": "failed", "type": "file"}]
        out = self._run_rollback(logs)
        success, errors = self._counts(out)
        self.assertEqual((success, errors), (0, 0))
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, rollback.LOG_FILE)))
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, rollback.LOG_FILE + ".bak")))

    def test_no_log_file_exits_cleanly(self):
        # rollback.main() calls sys.exit(1) when move_log.json is missing.
        with mock.patch("sys.exit", side_effect=SystemExit(1)), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                rollback.main()


if __name__ == "__main__":
    unittest.main()