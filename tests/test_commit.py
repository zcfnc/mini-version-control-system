"""Failing TDD tests for the Mini VCS commit feature.

Public contract introduced by these tests:
``Repository.commit(message)`` returns a unique commit ID and stores a JSON
commit object in ``.mini-vcs/objects/<commit_id>.json``. Each object contains
``id``, ``message``, ``parent`` and ``snapshot`` fields. ``snapshot`` maps a
working-tree-relative file path to its UTF-8 text content.
"""

import json
import tempfile
import unittest
from pathlib import Path

from mini_vcs import CONTROL_DIR_NAME, Repository


class CommitTests(unittest.TestCase):
    """Specify the expected commit behaviour before it is implemented."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "project"
        self.repo = Repository.init(self.project)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _read_commit(self, commit_id: str) -> dict:
        """Read the persisted JSON object for a commit."""

        object_path = self.project / CONTROL_DIR_NAME / "objects" / f"{commit_id}.json"
        return json.loads(object_path.read_text(encoding="utf-8"))

    def test_commit_creates_commit_object(self):
        commit_id = self.repo.commit("Initial commit")

        object_path = self.project / CONTROL_DIR_NAME / "objects" / f"{commit_id}.json"
        self.assertTrue(object_path.is_file())

    def test_commit_stores_file_snapshot(self):
        (self.project / "notes.txt").write_text("Version one\n", encoding="utf-8")

        commit_id = self.repo.commit("Save notes")

        commit = self._read_commit(commit_id)
        self.assertEqual(commit["snapshot"], {"notes.txt": "Version one\n"})

    def test_commit_generates_unique_id(self):
        first_id = self.repo.commit("First commit")
        second_id = self.repo.commit("Second commit")

        self.assertNotEqual(first_id, second_id)

    def test_commit_stores_message(self):
        message = "Add the project notes"

        commit_id = self.repo.commit(message)

        commit = self._read_commit(commit_id)
        self.assertEqual(commit["id"], commit_id)
        self.assertEqual(commit["message"], message)

    def test_first_commit_has_no_parent(self):
        commit_id = self.repo.commit("Initial commit")

        commit = self._read_commit(commit_id)
        self.assertIsNone(commit["parent"])

    def test_second_commit_stores_previous_parent(self):
        first_id = self.repo.commit("Initial commit")
        (self.project / "notes.txt").write_text("Updated\n", encoding="utf-8")

        second_id = self.repo.commit("Update notes")

        second_commit = self._read_commit(second_id)
        self.assertEqual(second_commit["parent"], first_id)

    def test_empty_commit_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.commit("")

    def test_commit_ignores_mini_vcs_metadata(self):
        (self.project / "notes.txt").write_text("Keep this\n", encoding="utf-8")

        commit_id = self.repo.commit("Save user files only")

        commit = self._read_commit(commit_id)
        self.assertEqual(commit["snapshot"], {"notes.txt": "Keep this\n"})
        self.assertFalse(any(path.startswith(f"{CONTROL_DIR_NAME}/") for path in commit["snapshot"]))


if __name__ == "__main__":
    unittest.main()
