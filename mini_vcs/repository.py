"""Repository initialisation for the Mini Version Control System.

This first iteration intentionally implements only repository creation and
metadata validation. Commit, branch, checkout and merge features will be
added in later TDD iterations.
"""

from __future__ import annotations

import json
from pathlib import Path

CONTROL_DIR_NAME = ".mini-vcs"
DEFAULT_BRANCH = "main"
FORMAT_VERSION = 1


class RepositoryError(Exception):
    """Base class for repository errors."""


class RepositoryExistsError(RepositoryError):
    """Raised when initialisation would overwrite an existing repository."""


class InvalidRepositoryError(RepositoryError):
    """Raised when repository metadata is missing or malformed."""


class Repository:
    """A local Mini VCS repository rooted at a working directory."""

    def __init__(self, worktree: Path):
        self.worktree = Path(worktree).resolve()
        self.control_dir = self.worktree / CONTROL_DIR_NAME

    @classmethod
    def init(cls, path: str | Path, *, exist_ok: bool = False) -> "Repository":
        """Create and validate repository metadata at *path*.

        A missing target directory is created. Existing user files are left
        untouched. Reinitialisation is rejected unless ``exist_ok=True`` is
        explicitly supplied.
        """

        target = Path(path).expanduser()
        if target.exists() and not target.is_dir():
            raise NotADirectoryError(f"Repository target is not a directory: {target}")
        target.mkdir(parents=True, exist_ok=True)

        repo = cls(target)
        if repo.control_dir.exists():
            if not repo.control_dir.is_dir():
                raise InvalidRepositoryError(
                    f"Repository control path is not a directory: {repo.control_dir}"
                )
            if not exist_ok:
                raise RepositoryExistsError(f"Repository already exists: {repo.worktree}")
            repo.validate()
            return repo

        repo._create_metadata()
        return repo

    def _create_metadata(self) -> None:
        refs_heads = self.control_dir / "refs" / "heads"
        objects = self.control_dir / "objects"
        refs_heads.mkdir(parents=True)
        objects.mkdir()

        (self.control_dir / "HEAD").write_text(
            f"ref: refs/heads/{DEFAULT_BRANCH}\n", encoding="utf-8"
        )
        (refs_heads / DEFAULT_BRANCH).write_text("", encoding="utf-8")
        (self.control_dir / "config.json").write_text(
            json.dumps(
                {"format_version": FORMAT_VERSION, "default_branch": DEFAULT_BRANCH},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def validate(self) -> None:
        """Validate the metadata required by the initial repository format."""

        required_paths = [
            self.control_dir / "HEAD",
            self.control_dir / "config.json",
            self.control_dir / "objects",
            self.control_dir / "refs" / "heads",
            self.control_dir / "refs" / "heads" / DEFAULT_BRANCH,
        ]
        missing = [str(path) for path in required_paths if not path.exists()]
        if missing:
            raise InvalidRepositoryError(
                "Repository metadata is incomplete; missing: " + ", ".join(missing)
            )

        head = (self.control_dir / "HEAD").read_text(encoding="utf-8")
        expected_head = f"ref: refs/heads/{DEFAULT_BRANCH}\n"
        if head != expected_head:
            raise InvalidRepositoryError("HEAD does not point to the default branch")

        try:
            config = json.loads((self.control_dir / "config.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise InvalidRepositoryError("Repository config is not valid JSON") from exc
        if config.get("format_version") != FORMAT_VERSION:
            raise InvalidRepositoryError("Unsupported repository format version")
        if config.get("default_branch") != DEFAULT_BRANCH:
            raise InvalidRepositoryError("Repository default branch is invalid")

