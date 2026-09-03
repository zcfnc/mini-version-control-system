"""RED-phase tests for the Mini VCS commit-history feature.

These tests define the expected ``Repository.history()`` contract before the
feature is implemented.  They should fail with an informative missing-method
error until the History iteration is completed.
"""

import tempfile
import unittest
from pathlib import Path

from mini_vcs import Repository


class HistoryTests(unittest.TestCase):
    """Specify newest-first history and the empty-history boundary case."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "project"
        self.repo = Repository.init(self.project)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_history_empty_repository(self):
        """An initialised repository has no commits and no history entries."""

        self.assertEqual(self.repo.history(), [])

    def test_history_returns_single_commit(self):
        """One commit is returned as one history record."""

        (self.project / "notes.txt").write_text("Version one\n", encoding="utf-8")
        commit_id = self.repo.commit("Initial notes")

        history = self.repo.history()

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], commit_id)

    def test_history_returns_newest_first(self):
        """Multiple commits are listed from the current head backwards."""

        notes = self.project / "notes.txt"
        notes.write_text("Version one\n", encoding="utf-8")
        first_id = self.repo.commit("Initial notes")
        notes.write_text("Version two\n", encoding="utf-8")
        second_id = self.repo.commit("Update notes")

        history = self.repo.history()

        self.assertEqual([entry["id"] for entry in history], [second_id, first_id])

    def test_history_preserves_message_and_parent(self):
        """History records retain each commit message and parent relationship."""

        first_id = self.repo.commit("Initial commit")
        second_id = self.repo.commit("Second commit")

        history = self.repo.history()

        self.assertEqual(history[0]["id"], second_id)
        self.assertEqual(history[0]["message"], "Second commit")
        self.assertEqual(history[0]["parent"], first_id)
        self.assertEqual(history[1]["message"], "Initial commit")
        self.assertIsNone(history[1]["parent"])


if __name__ == "__main__":
    unittest.main()
