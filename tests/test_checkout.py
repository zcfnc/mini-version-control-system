"""Tests for Mini VCS checkout."""

import tempfile
import unittest
from pathlib import Path

from mini_vcs import CONTROL_DIR_NAME, Repository


class CheckoutTests(unittest.TestCase):
    """Specify commit restoration and checkout failure safety."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "project"
        self.repo = Repository.init(self.project)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _head(self) -> str:
        return (self.project / CONTROL_DIR_NAME / "HEAD").read_text(encoding="utf-8")

    def _main_ref(self) -> str:
        return (
            self.project
            / CONTROL_DIR_NAME
            / "refs"
            / "heads"
            / "main"
        ).read_text(encoding="utf-8")

    def test_checkout_restores_commit_snapshot(self):
        """Checkout restores the files stored by an earlier commit."""

        notes = self.project / "notes.txt"
        notes.write_text("version one\n", encoding="utf-8")
        first_id = self.repo.commit("First version")
        notes.write_text("version two\n", encoding="utf-8")
        self.repo.commit("Second version")

        self.repo.checkout(first_id)

        self.assertEqual(notes.read_text(encoding="utf-8"), "version one\n")

    def test_checkout_restores_files_deleted_in_target_snapshot(self):
        """Checkout restores a file that is absent from the current snapshot."""

        notes = self.project / "notes.txt"
        extra = self.project / "extra.txt"
        notes.write_text("version one\n", encoding="utf-8")
        extra.write_text("restore me\n", encoding="utf-8")
        first_id = self.repo.commit("Save two files")
        extra.unlink()
        self.repo.commit("Remove extra file")

        self.repo.checkout(first_id)

        self.assertTrue(extra.is_file())
        self.assertEqual(extra.read_text(encoding="utf-8"), "restore me\n")

    def test_checkout_does_not_corrupt_branch_references(self):
        """Restoring an old commit does not rewrite HEAD or the main ref."""

        notes = self.project / "notes.txt"
        notes.write_text("version one\n", encoding="utf-8")
        first_id = self.repo.commit("First version")
        notes.write_text("version two\n", encoding="utf-8")
        second_id = self.repo.commit("Second version")
        before_head = self._head()
        before_ref = self._main_ref()

        self.repo.checkout(first_id)

        self.assertEqual(self._head(), before_head)
        self.assertEqual(self._main_ref(), before_ref)
        self.assertEqual(self._main_ref().strip(), second_id)

    def test_checkout_unknown_commit_is_rejected(self):
        """An unknown commit is rejected without changing repository state."""

        notes = self.project / "notes.txt"
        notes.write_text("keep this\n", encoding="utf-8")
        self.repo.commit("Existing commit")
        before_head = self._head()
        before_ref = self._main_ref()
        before_content = notes.read_text(encoding="utf-8")

        with self.assertRaises(ValueError):
            self.repo.checkout("0" * 64)

        self.assertEqual(self._head(), before_head)
        self.assertEqual(self._main_ref(), before_ref)
        self.assertEqual(notes.read_text(encoding="utf-8"), before_content)


if __name__ == "__main__":
    unittest.main()
