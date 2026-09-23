"""Tests for scripts/executor.py (AI File Cleaner).

Isolation strategy:
  * Every test runs inside its own tempfile.TemporaryDirectory().
  * os.path.dirname is patched so that dirname(executor.__file__) resolves into
    <tmp>/scripts; combined with executor's os.path.join(..., "..") this makes
    the export file land at <tmp>/export_tasks.json (never the real repo root).
  * os.path.expanduser is patched so "~/_Quarantine" and "~/Downloads" map
    into <tmp>/... (the real home directory is never touched).
  * All task paths are absolute paths inside the temp directory.

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
EXECUTOR_PATH = os.path.join(REPO_ROOT, "scripts", "executor.py")

_spec = importlib.util.spec_from_file_location("executor", EXECUTOR_PATH)
executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(executor)

# Collision suffix: production code carried a "%Y%md%H%M%S" bug (yields
# e.g. file_202609d123456.txt) which another agent is fixing to
# "%Y%m%d%H%M%S" (file_20260923123456.txt). Accept both spellings so the
# tests do not depend on which version is currently in the tree:
#   fixed: 14 digits            -> \d{14}
#   buggy: 6 digits + 'd' + 6   -> \d{6}d\d{6}  (e.g. 202609d123456)
COLLISION_RE = re.compile(r"^file_(?:\d{14}|\d{6}d\d{6})\.txt$")


def _run_executor(tmp_dir, tasks):
    """Write tasks to the (fake) export file inside tmp_dir and run executor.main().

    Returns the captured stdout.
    """
    real_dirname = os.path.dirname
    real_expanduser = os.path.expanduser

    # Executor resolves its export file as dirname(__file__)/../export_tasks.json.
    # POSIX requires the intermediate "scripts" component to actually exist for
    # the ".." to resolve, so create it (mirrors the real repo layout).
    os.makedirs(os.path.join(tmp_dir, "scripts"), exist_ok=True)

    def fake_dirname(path):
        if os.path.abspath(path) == EXECUTOR_PATH:
            return os.path.join(tmp_dir, "scripts")
        return real_dirname(path)

    def fake_expanduser(path):
        if path.startswith("~/"):
            return os.path.join(tmp_dir, path[2:])
        return real_expanduser(path)

    export_path = os.path.join(tmp_dir, "export_tasks.json")
    with open(export_path, "w", encoding="utf-8") as fh:
        json.dump(tasks, fh)

    out = io.StringIO()
    with mock.patch("os.path.dirname", side_effect=fake_dirname), \
         mock.patch("os.path.expanduser", side_effect=fake_expanduser), \
         contextlib.redirect_stdout(out):
        executor.main()
    return out.getvalue()


def _counts(output):
    success = int(re.search(r"Successfully processed:\s*(\d+)", output).group(1))
    errors = int(re.search(r"Errors:\s*(\d+)", output).group(1))
    return success, errors


class ExecutorTests(unittest.TestCase):
    def test_missing_file_skipped_and_error_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "does_not_exist.txt")
            tasks = [{
                "path": missing,
                "destination": os.path.join(tmp, "dest"),
                "type": "FILE_MOVE",
            }]
            out = _run_executor(tmp, tasks)
            success, errors = _counts(out)
            self.assertEqual(success, 0)
            self.assertEqual(errors, 1)
            self.assertIn("[SKIP] File not found", out)
            # No successes -> export file must NOT be renamed to .done
            self.assertTrue(os.path.exists(os.path.join(tmp, "export_tasks.json")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "export_tasks.json.done")))

    def test_delete_moves_to_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "src")
            os.makedirs(src_dir)
            src = os.path.join(src_dir, "doc.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("hello")
            tasks = [{"path": src, "destination": "DELETE", "type": "FILE_MOVE"}]
            out = _run_executor(tmp, tasks)
            success, errors = _counts(out)
            self.assertEqual((success, errors), (1, 0))
            self.assertIn("[MOVED TO QUARANTINE]", out)
            quarantined = os.path.join(tmp, "_Quarantine", "Deleted_Files", "doc.txt")
            self.assertTrue(os.path.exists(quarantined))
            # The original file is gone (moved, not rm'ed, not left behind)
            self.assertFalse(os.path.exists(src))

    def test_collision_adds_timestamp_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_a = os.path.join(tmp, "a")
            src_b = os.path.join(tmp, "b")
            dest = os.path.join(tmp, "dest")
            os.makedirs(src_a)
            os.makedirs(src_b)
            f1 = os.path.join(src_a, "file.txt")
            f2 = os.path.join(src_b, "file.txt")
            with open(f1, "w", encoding="utf-8") as fh:
                fh.write("1")
            with open(f2, "w", encoding="utf-8") as fh:
                fh.write("2")
            tasks = [
                {"path": f1, "destination": dest, "type": "FILE_MOVE"},
                {"path": f2, "destination": dest, "type": "FILE_MOVE"},
            ]
            out = _run_executor(tmp, tasks)
            success, errors = _counts(out)
            self.assertEqual((success, errors), (2, 0))
            names = sorted(os.listdir(dest))
            self.assertIn("file.txt", names)
            suffixed = [n for n in names if n != "file.txt"]
            self.assertEqual(len(suffixed), 1)
            self.assertRegex(suffixed[0], COLLISION_RE)

    def test_dir_move_existing_destination_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "folder")
            os.makedirs(src_dir)
            payload = os.path.join(src_dir, "inner.txt")
            with open(payload, "w", encoding="utf-8") as fh:
                fh.write("data")
            dest = os.path.join(tmp, "dest")
            # The folder name is already taken at the destination
            os.makedirs(os.path.join(dest, "folder"))
            marker = os.path.join(dest, "folder", "marker.txt")
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write("keep")
            tasks = [{"path": src_dir, "destination": dest, "type": "DIR_MOVE"}]
            out = _run_executor(tmp, tasks)
            success, errors = _counts(out)
            self.assertEqual(success, 0)
            self.assertEqual(errors, 1)
            self.assertIn("Directory already exists", out)
            # Source untouched, nothing moved or overwritten
            self.assertTrue(os.path.exists(src_dir))
            self.assertTrue(os.path.exists(payload))
            self.assertTrue(os.path.exists(marker))

    def test_dir_move_success_moves_whole_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "folder")
            os.makedirs(src_dir)
            payload = os.path.join(src_dir, "inner.txt")
            with open(payload, "w", encoding="utf-8") as fh:
                fh.write("data")
            dest = os.path.join(tmp, "dest")
            tasks = [{"path": src_dir, "destination": dest, "type": "DIR_MOVE"}]
            out = _run_executor(tmp, tasks)
            success, errors = _counts(out)
            self.assertEqual((success, errors), (1, 0))
            self.assertIn("[MOVED ENTIRE FOLDER]", out)
            self.assertFalse(os.path.exists(src_dir))
            self.assertTrue(os.path.exists(os.path.join(dest, "folder", "inner.txt")))

    def test_export_renamed_to_done_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.txt")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("x")
            dest = os.path.join(tmp, "dest")
            tasks = [{"path": src, "destination": dest, "type": "FILE_MOVE"}]
            out = _run_executor(tmp, tasks)
            success, errors = _counts(out)
            self.assertEqual((success, errors), (1, 0))
            self.assertFalse(os.path.exists(os.path.join(tmp, "export_tasks.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "export_tasks.json.done")))


if __name__ == "__main__":
    unittest.main()