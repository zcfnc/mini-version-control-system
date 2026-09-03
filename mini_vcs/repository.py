"""Repository storage for the Mini Version Control System.

The repository currently supports initialisation and commits.  Later
iterations can build history, branching, checkout and merge on top of the
stable object and reference format implemented here.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
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

    def commit(self, message: str) -> str:
        """Create a commit for the current working tree and return its ID.

        Commit objects are JSON files in ``.mini-vcs/objects``.  A snapshot
        contains every UTF-8 text file below the working tree except the
        control directory itself.  The branch reference is updated only
        after the object has been written successfully.
        """

        if not isinstance(message, str) or not message.strip():
            raise ValueError("Commit message must not be empty")

        self.validate()
        branch_ref = self._current_branch_ref_path()
        parent = self._read_ref(branch_ref)
        snapshot = self._working_tree_snapshot()

        payload = {
            "message": message,
            "parent": parent,
            "snapshot": snapshot,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        commit_id = hashlib.sha256(canonical).hexdigest()

        # A content hash is stable, while the collision guard also ensures
        # that a second object is never silently overwritten.
        suffix = 1
        while (self.control_dir / "objects" / f"{commit_id}.json").exists():
            commit_id = hashlib.sha256(canonical + f"\0{suffix}".encode("ascii")).hexdigest()
            suffix += 1

        commit = {
            "id": commit_id,
            "message": message,
            "parent": parent,
            "snapshot": snapshot,
        }
        object_path = self.control_dir / "objects" / f"{commit_id}.json"
        self._atomic_write_json(object_path, commit)

        # This happens last so an object-write failure cannot advance the
        # branch.  The helper also replaces the ref atomically.
        self._atomic_write_text(branch_ref, f"{commit_id}\n")
        return commit_id

    def _current_branch_ref_path(self) -> Path:
        """Return the ref file selected by HEAD, rejecting detached HEAD."""

        head_path = self.control_dir / "HEAD"
        head = head_path.read_text(encoding="utf-8").strip()
        prefix = "ref: "
        if not head.startswith(prefix):
            raise InvalidRepositoryError("HEAD does not contain a symbolic branch reference")
        ref_name = head[len(prefix):]
        if not ref_name.startswith("refs/heads/") or ref_name.endswith("/"):
            raise InvalidRepositoryError("HEAD contains an invalid branch reference")
        ref_path = self.control_dir / ref_name
        try:
            ref_path.relative_to(self.control_dir / "refs" / "heads")
        except ValueError as exc:
            raise InvalidRepositoryError("HEAD branch reference escapes the repository") from exc
        if not ref_path.is_file():
            raise InvalidRepositoryError(f"Branch reference is missing: {ref_name}")
        return ref_path

    @staticmethod
    def _read_ref(ref_path: Path) -> str | None:
        """Read a branch reference, mapping the initial empty ref to None."""

        value = ref_path.read_text(encoding="utf-8").strip()
        return value or None

    def _working_tree_snapshot(self) -> dict[str, str]:
        """Return a deterministic UTF-8 snapshot excluding repository metadata."""

        snapshot: dict[str, str] = {}
        for path in sorted(self.worktree.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.worktree)
            if relative.parts and relative.parts[0] == CONTROL_DIR_NAME:
                continue
            try:
                snapshot[relative.as_posix()] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Working-tree file is not UTF-8 text: {relative}") from exc
        return snapshot

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        """Write text through a same-directory temporary file and replace."""

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(text)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
            temporary_name = None
        finally:
            if temporary_name is not None:
                try:
                    Path(temporary_name).unlink()
                except FileNotFoundError:
                    pass

    @classmethod
    def _atomic_write_json(cls, path: Path, value: dict) -> None:
        """Serialise JSON consistently and write it atomically."""

        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        cls._atomic_write_text(path, text)

    def history(self) -> list[dict]:
        """Return the current branch history from newest commit to oldest.

        The branch reference is read once, then each commit object's parent is
        followed until the initial commit.  A repository with an empty branch
        returns an empty list.  Missing, malformed or cyclic metadata raises
        :class:`InvalidRepositoryError` instead of returning a misleading
        partial history.
        """

        self.validate()
        current_id = self._read_ref(self._current_branch_ref_path())
        commits: list[dict] = []
        visited: set[str] = set()

        while current_id is not None:
            if current_id in visited:
                raise InvalidRepositoryError("Commit history contains a parent cycle")
            visited.add(current_id)

            commit = self._read_commit_object(current_id)
            commits.append(commit)

            parent = commit["parent"]
            if parent is not None and not isinstance(parent, str):
                raise InvalidRepositoryError("Commit parent must be a commit ID or null")
            current_id = parent

        return commits

    def _read_commit_object(self, commit_id: str) -> dict:
        """Load and validate one persisted commit object."""

        if not re.fullmatch(r"[0-9a-f]{64}", commit_id):
            raise InvalidRepositoryError(f"Invalid commit ID in history: {commit_id!r}")

        object_path = self.control_dir / "objects" / f"{commit_id}.json"
        if not object_path.is_file():
            raise InvalidRepositoryError(f"Commit object is missing: {commit_id}")
        try:
            commit = json.loads(object_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidRepositoryError(f"Commit object is not valid JSON: {commit_id}") from exc

        if not isinstance(commit, dict):
            raise InvalidRepositoryError(f"Commit object is not an object: {commit_id}")
        required = {"id", "message", "parent", "snapshot"}
        if not required.issubset(commit):
            raise InvalidRepositoryError(f"Commit object is incomplete: {commit_id}")
        if commit["id"] != commit_id:
            raise InvalidRepositoryError(f"Commit object ID does not match its filename: {commit_id}")
        if not isinstance(commit["message"], str) or not isinstance(commit["snapshot"], dict):
            raise InvalidRepositoryError(f"Commit object has invalid fields: {commit_id}")
        return commit
