"""Tests for Mini VCS merge conflict detection."""

import tempfile
import unittest
from pathlib import Path

from mini_vcs import CONTROL_DIR_NAME, MergeConflictError, Repository


class ConflictDetectionTests(unittest.TestCase):
    """Specify conflict reporting and state preservation before implementation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "project"
        self.repo = Repository.init(self.project)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _state(self):
        control = self.project / CONTROL_DIR_NAME
        return {
            "head": (control / "HEAD").read_text(encoding="utf-8"),
            "main": (control / "refs" / "heads" / "main").read_text(encoding="utf-8"),
            "feature": (control / "refs" / "heads" / "feature").read_text(encoding="utf-8"),
            "notes": (self.project / "notes.txt").read_text(encoding="utf-8"),
        }

    def _create_conflicting_branches(self):
        """Create two branches with different edits to the same file."""

        notes = self.project / "notes.txt"
        notes.write_text("base\n", encoding="utf-8")
        base_id = self.repo.commit("Base commit")
        self.repo.create_branch("feature", start_point=base_id)

        self.repo.switch_branch("feature")
        notes.write_text("feature version\n", encoding="utf-8")
        self.repo.commit("Feature edit")

        self.repo.switch_branch("main")
        notes.write_text("main version\n", encoding="utf-8")
        self.repo.commit("Main edit")

    def test_merge_detects_conflicting_edits(self):
        """Different edits to one file raise a clear merge conflict."""

        self._create_conflicting_branches()

        with self.assertRaises(MergeConflictError) as context:
            self.repo.merge("feature")

        self.assertIn("notes.txt", str(context.exception))

    def test_conflict_preserves_working_tree_and_references(self):
        """A conflict does not overwrite files or update either branch ref."""

        self._create_conflicting_branches()
        before = self._state()

        with self.assertRaises(MergeConflictError):
            self.repo.merge("feature")

        self.assertEqual(self._state(), before)


if __name__ == "__main__":
    unittest.main()
