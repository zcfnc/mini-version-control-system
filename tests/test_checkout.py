"""Tests for Mini VCS checkout."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_repeated_checkout_removes_files_absent_from_target(self):
        """Repeated restores remove files absent from the selected snapshot."""

        notes = self.project / "notes.txt"
        extra = self.project / "extra.txt"
        notes.write_text("version one\n", encoding="utf-8")
        extra.write_text("old version only\n", encoding="utf-8")
        first_id = self.repo.commit("Save the original two files")

        notes.write_text("version two\n", encoding="utf-8")
        extra.unlink()
        second_id = self.repo.commit("Update notes and remove extra")

        self.repo.checkout(first_id)
        self.assertEqual(extra.read_text(encoding="utf-8"), "old version only\n")
        self.assertEqual(notes.read_text(encoding="utf-8"), "version one\n")

        # Reopening verifies persistent repository state, not an in-memory cache.
        self.repo = Repository(self.project)
        self.repo.checkout(second_id)

        self.assertFalse(extra.exists(), "A file absent from the target must be removed")
        self.assertEqual(notes.read_text(encoding="utf-8"), "version two\n")

    def test_checkout_write_failure_preserves_working_tree_and_references(self):
        """A failed restore rolls back file changes and preserves all branch refs."""

        first = self.project / "a.txt"
        second = self.project / "b.txt"
        extra = self.project / "extra.txt"
        first.write_text("old a\n", encoding="utf-8")
        second.write_text("old b\n", encoding="utf-8")
        target_id = self.repo.commit("Original snapshot")

        first.write_text("current a\n", encoding="utf-8")
        second.write_text("current b\n", encoding="utf-8")
        extra.write_text("keep this tracked file\n", encoding="utf-8")
        self.repo.commit("Current snapshot with extra file")
        self.repo.create_branch("feature")
        (self.project / "personal.txt").write_text("untracked notes\n", encoding="utf-8")

        def capture_state():
            working_files = {
                path.relative_to(self.project).as_posix(): path.read_bytes()
                for path in self.project.rglob("*")
                if path.is_file()
                and path.relative_to(self.project).parts[0] != CONTROL_DIR_NAME
            }
            refs_directory = self.project / CONTROL_DIR_NAME / "refs" / "heads"
            branch_refs = {
                path.relative_to(refs_directory).as_posix(): path.read_bytes()
                for path in refs_directory.rglob("*")
                if path.is_file()
            }
            return working_files, self._head(), branch_refs

        before = capture_state()
        original_replace = os.replace
        failure_injected = False

        def replace_with_failure(source, destination, *args, **kwargs):
            nonlocal failure_injected
            if not failure_injected and Path(destination) == second:
                failure_injected = True
                raise OSError("simulated checkout write failure")
            return original_replace(source, destination, *args, **kwargs)

        # Fail once at the I/O boundary; later writes are allowed for rollback.
        with patch("mini_vcs.repository.os.replace", side_effect=replace_with_failure):
            with self.assertRaisesRegex(OSError, "simulated checkout write failure"):
                self.repo.checkout(target_id)

        self.assertTrue(failure_injected, "The test must reach the simulated write failure")
        self.assertEqual(
            capture_state(), before,
            "A failed checkout must preserve working files, HEAD and all branch refs",
        )

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
