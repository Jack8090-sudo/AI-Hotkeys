"""obsidian_todo.main end to end (I4): backup, atomic write, newline style, abort paths.

The model call (ask_qwen) is replaced; the To-Do file lives in the temporary tree.
"""

import contextlib
import io
import sys
import unittest
from unittest import mock

from tests.support import FIXTURES, AppTree

GOLDEN = (FIXTURES / "todo" / "golden_ok.md").read_text(encoding="utf-8")


class ObsidianMainTest(unittest.TestCase):
    def setUp(self):
        self.tree = AppTree()
        self.ot = self.tree.load_action("obsidian_todo")
        self.todo = self.tree.root / "vault" / "To-Do List.md"
        self.todo.parent.mkdir()

    def tearDown(self):
        self.tree.close()

    def run_main(self, answer=None, error=None):
        def fake_ask(text):
            if error:
                raise error
            return answer
        with mock.patch.object(self.ot, "ask_qwen", fake_ask), \
                mock.patch.object(sys, "argv", ["obsidian_todo.py", str(self.todo)]), \
                contextlib.redirect_stdout(io.StringIO()):
            return self.ot.main()

    def status(self):
        return self.ot.STATUS_FILE.read_text(encoding="utf-8").split("\n")[0]

    def backups(self):
        return sorted(p.name for p in self.todo.parent.glob("*.backup_*.md"))

    def test_status_files_live_in_the_temporary_work_folder(self):
        self.assertEqual(self.ot.STATUS_FILE.parent, self.tree.work)

    def test_success_replaces_file_keeps_crlf_and_makes_backup(self):
        original = GOLDEN.replace("\n", "\r\n").encode("utf-8")
        self.todo.write_bytes(original)
        improved = GOLDEN.replace("Sistema di clan", "Sistema dei clan")
        self.assertEqual(self.run_main(answer=improved), 0)
        self.assertEqual(self.status(), "OK")
        raw = self.todo.read_bytes()
        self.assertIn(b"Sistema dei clan", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))     # still CRLF
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual((self.todo.parent / backups[0]).read_bytes(), original)
        self.assertFalse((self.todo.parent / ".To-Do List.md.tmp").exists())

    def test_safety_failure_leaves_file_untouched(self):
        self.todo.write_text(GOLDEN, encoding="utf-8")
        before = self.todo.read_bytes()
        self.assertEqual(self.run_main(answer=GOLDEN.replace("- [ ] Sistema di clan\n", "")), 2)
        self.assertEqual(self.status(), "ERRORE")
        self.assertEqual(self.todo.read_bytes(), before)
        self.assertEqual(self.backups(), [])

    def test_empty_answer_and_ollama_error_fail_without_writing(self):
        self.todo.write_text(GOLDEN, encoding="utf-8")
        before = self.todo.read_bytes()
        self.assertEqual(self.run_main(answer="   "), 1)
        self.assertEqual(self.run_main(error=ConnectionRefusedError("down")), 1)
        self.assertEqual(self.status(), "ERRORE")
        self.assertEqual(self.todo.read_bytes(), before)

    def test_missing_file(self):
        self.assertEqual(self.run_main(answer=GOLDEN), 1)
        self.assertEqual(self.status(), "ERRORE")

    def test_file_modified_during_the_run_is_not_overwritten(self):
        self.todo.write_text(GOLDEN, encoding="utf-8")

        def ask_and_edit(text):
            self.todo.write_text(GOLDEN + "\n- [ ] aggiunto mentre Qwen lavorava\n", encoding="utf-8")
            return GOLDEN

        with mock.patch.object(self.ot, "ask_qwen", ask_and_edit), \
                mock.patch.object(sys, "argv", ["obsidian_todo.py", str(self.todo)]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.ot.main(), 2)
        self.assertIn("aggiunto mentre Qwen lavorava", self.todo.read_text(encoding="utf-8"))

    # ---- known defect C13: flipped by step S5 ----

    @unittest.expectedFailure
    def test_C13_replace_failure_reports_error_and_keeps_original(self):
        """C13: an os.replace failure escapes main(): no status is written, tmp is left behind."""
        self.todo.write_text(GOLDEN, encoding="utf-8")
        before = self.todo.read_bytes()
        with mock.patch.object(self.ot.os, "replace", side_effect=PermissionError("locked")):
            rc = self.run_main(answer=GOLDEN.replace("Sistema di clan", "Sistema dei clan"))
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.status(), "ERRORE")
        self.assertEqual(self.todo.read_bytes(), before)
        self.assertFalse((self.todo.parent / ".To-Do List.md.tmp").exists())


if __name__ == "__main__":
    unittest.main()
