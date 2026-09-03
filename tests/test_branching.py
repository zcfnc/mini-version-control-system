"""Tests for Mini VCS branch creation and switching."""

import tempfile
import unittest
from pathlib import Path

from mini_vcs import CONTROL_DIR_NAME, Repository


class BranchingTests(unittest.TestCase):
    """Specify branch references and branch-switch behaviour."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "project"
        self.repo = Repository.init(self.project)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _branch_ref(self, name: str) -> Path:
        return self.project / CONTROL_DIR_NAME / "refs" / "heads" / name

    def test_create_branch_points_to_current_commit(self):
        """A new branch points to the current branch head."""

        (self.project / "notes.txt").write_text("main version\n", encoding="utf-8")
        commit_id = self.repo.commit("Main commit")

        self.repo.create_branch("feature")

        self.assertEqual(self._branch_ref("feature").read_text(encoding="utf-8").strip(), commit_id)

    def test_create_branch_from_selected_commit(self):
        """A branch can start from an explicitly selected commit."""

        notes = self.project / "notes.txt"
        notes.write_text("version one\n", encoding="utf-8")
        first_id = self.repo.commit("First commit")
        notes.write_text("version two\n", encoding="utf-8")
        self.repo.commit("Second commit")

        self.repo.create_branch("old-version", start_point=first_id)

        self.assertEqual(
            self._branch_ref("old-version").read_text(encoding="utf-8").strip(),
            first_id,
        )

    def test_duplicate_branch_is_rejected(self):
        """Creating an existing branch must not replace its reference."""

        self.repo.create_branch("feature")
        original = self._branch_ref("feature").read_text(encoding="utf-8")

        with self.assertRaises(ValueError):
            self.repo.create_branch("feature")

        self.assertEqual(self._branch_ref("feature").read_text(encoding="utf-8"), original)

    def test_switch_branch_restores_snapshot(self):
        """Switching branches changes HEAD and restores that branch's files."""

        notes = self.project / "notes.txt"
        notes.write_text("main version\n", encoding="utf-8")
        main_id = self.repo.commit("Main commit")
        self.repo.create_branch("feature", start_point=main_id)
        notes.write_text("main update\n", encoding="utf-8")
        self.repo.commit("Main update")

        self.repo.switch_branch("feature")

        head = (self.project / CONTROL_DIR_NAME / "HEAD").read_text(encoding="utf-8")
        self.assertEqual(head, "ref: refs/heads/feature\n")
        self.assertEqual(notes.read_text(encoding="utf-8"), "main version\n")

    def test_switch_unknown_branch_is_rejected(self):
        """Switching to an unknown branch must fail without changing HEAD."""

        before = (self.project / CONTROL_DIR_NAME / "HEAD").read_text(encoding="utf-8")

        with self.assertRaises(ValueError):
            self.repo.switch_branch("does-not-exist")

        after = (self.project / CONTROL_DIR_NAME / "HEAD").read_text(encoding="utf-8")
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
