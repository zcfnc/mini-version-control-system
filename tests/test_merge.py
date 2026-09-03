"""Tests for Mini VCS non-conflicting merge."""

import tempfile
import unittest
from pathlib import Path

from mini_vcs import CONTROL_DIR_NAME, Repository


class MergeTests(unittest.TestCase):
    """Specify compatible branch merging before implementation."""

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

    def _create_diverged_branches(self):
        """Create main and feature branches with independent file changes."""

        base_file = self.project / "base.txt"
        base_file.write_text("base\n", encoding="utf-8")
        base_id = self.repo.commit("Base commit")
        self.repo.create_branch("feature", start_point=base_id)

        self.repo.switch_branch("feature")
        (self.project / "feature.txt").write_text("feature change\n", encoding="utf-8")
        feature_id = self.repo.commit("Feature change")

        self.repo.switch_branch("main")
        (self.project / "main.txt").write_text("main change\n", encoding="utf-8")
        main_id = self.repo.commit("Main change")
        return feature_id, main_id

    def test_merge_combines_independent_changes(self):
        """A non-conflicting merge keeps changes from both branches."""

        self._create_diverged_branches()

        self.repo.merge("feature")

        self.assertEqual(
            (self.project / "feature.txt").read_text(encoding="utf-8"),
            "feature change\n",
        )
        self.assertEqual(
            (self.project / "main.txt").read_text(encoding="utf-8"),
            "main change\n",
        )

    def test_merge_preserves_current_branch_and_source_branch(self):
        """A compatible merge leaves both branch references valid."""

        feature_id, main_id = self._create_diverged_branches()

        self.repo.merge("feature")

        self.assertEqual(self._head(), "ref: refs/heads/main\n")
        self.assertTrue(self._main_ref().strip())
        self.assertTrue(
            (self.project / CONTROL_DIR_NAME / "refs" / "heads" / "feature")
            .read_text(encoding="utf-8")
            .strip()
        )
        self.assertIn(main_id, {entry["id"] for entry in self.repo.history()})
        self.assertTrue(feature_id)

    def test_merge_unknown_source_branch_is_rejected(self):
        """An unknown source branch fails without changing current state."""

        self.repo.commit("Base commit")
        before_head = self._head()
        before_ref = self._main_ref()

        with self.assertRaises(ValueError):
            self.repo.merge("does-not-exist")

        self.assertEqual(self._head(), before_head)
        self.assertEqual(self._main_ref(), before_ref)


if __name__ == "__main__":
    unittest.main()
