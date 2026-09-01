import json
import tempfile
import unittest
from pathlib import Path

from mini_vcs import (
    CONTROL_DIR_NAME,
    DEFAULT_BRANCH,
    InvalidRepositoryError,
    Repository,
    RepositoryExistsError,
)


class RepositoryInitialisationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_creates_control_directory(self):
        Repository.init(self.root / "project")
        self.assertTrue((self.root / "project" / CONTROL_DIR_NAME).is_dir())

    def test_init_creates_required_subdirectories(self):
        Repository.init(self.root / "project")
        control = self.root / "project" / CONTROL_DIR_NAME
        self.assertTrue((control / "objects").is_dir())
        self.assertTrue((control / "refs" / "heads").is_dir())

    def test_init_writes_head_to_default_branch(self):
        Repository.init(self.root / "project")
        head = (self.root / "project" / CONTROL_DIR_NAME / "HEAD").read_text()
        self.assertEqual(head, "ref: refs/heads/main\n")

    def test_init_creates_empty_main_ref(self):
        Repository.init(self.root / "project")
        ref = self.root / "project" / CONTROL_DIR_NAME / "refs" / "heads" / DEFAULT_BRANCH
        self.assertEqual(ref.read_text(), "")

    def test_init_stores_format_metadata(self):
        Repository.init(self.root / "project")
        config = self.root / "project" / CONTROL_DIR_NAME / "config.json"
        self.assertEqual(json.loads(config.read_text()), {"format_version": 1, "default_branch": "main"})

    def test_init_creates_missing_target_directory(self):
        target = self.root / "nested" / "project"
        Repository.init(target)
        self.assertTrue(target.is_dir())

    def test_init_preserves_existing_working_files(self):
        target = self.root / "project"
        target.mkdir()
        user_file = target / "notes.txt"
        user_file.write_text("keep this file")
        Repository.init(target)
        self.assertEqual(user_file.read_text(), "keep this file")

    def test_init_rejects_file_as_target(self):
        target = self.root / "not-a-directory"
        target.write_text("file")
        with self.assertRaises(NotADirectoryError):
            Repository.init(target)

    def test_init_rejects_existing_repository_without_exist_ok(self):
        target = self.root / "project"
        Repository.init(target)
        with self.assertRaises(RepositoryExistsError):
            Repository.init(target)

    def test_init_returns_repository_instance_when_exist_ok(self):
        target = self.root / "project"
        Repository.init(target)
        repo = Repository.init(target, exist_ok=True)
        self.assertIsInstance(repo, Repository)

    def test_init_is_repeatable_with_exist_ok(self):
        target = self.root / "project"
        Repository.init(target)
        Repository.init(target, exist_ok=True)
        Repository.init(target, exist_ok=True)
        Repository(target).validate()

    def test_init_rejects_malformed_existing_metadata(self):
        target = self.root / "project"
        Repository.init(target)
        (target / CONTROL_DIR_NAME / "HEAD").write_text("broken\n")
        with self.assertRaises(InvalidRepositoryError):
            Repository.init(target, exist_ok=True)


if __name__ == "__main__":
    unittest.main()

