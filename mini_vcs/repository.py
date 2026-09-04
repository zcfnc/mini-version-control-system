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


class MergeConflictError(RepositoryError):
    """Raised when both branches change the same file differently."""


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
        prefix = "ref: refs/heads/"
        if not head.startswith(prefix) or not head.endswith("\n"):
            raise InvalidRepositoryError("HEAD does not contain a valid branch reference")
        branch_name = head[len(prefix):-1]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", branch_name):
            raise InvalidRepositoryError("HEAD contains an invalid branch name")
        active_ref = self.control_dir / "refs" / "heads" / branch_name
        if not active_ref.is_file():
            raise InvalidRepositoryError("HEAD points to a missing branch reference")

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

    def create_branch(self, name: str, *, start_point: str | None = None) -> None:
        """Create ``name`` at ``start_point`` or at the current branch head."""

        self.validate()
        branch_path = self._branch_ref_path(name)
        if branch_path.exists():
            raise ValueError(f"Branch already exists: {name}")

        if start_point is None:
            start_point = self._read_ref(self._current_branch_ref_path())
        elif not isinstance(start_point, str) or not re.fullmatch(r"[0-9a-f]{64}", start_point):
            raise ValueError(f"Invalid branch start commit: {start_point!r}")
        if start_point is not None:
            self._read_commit_object(start_point)

        self._atomic_write_text(branch_path, f"{start_point or ''}\n")

    def switch_branch(self, name: str) -> None:
        """Switch HEAD to ``name`` and restore its latest committed snapshot."""

        self.validate()
        target_ref = self._branch_ref_path(name)
        if not target_ref.is_file():
            raise ValueError(f"Unknown branch: {name}")

        target_id = self._read_ref(target_ref)
        target_commit = self._read_commit_object(target_id) if target_id else None
        target_snapshot = target_commit["snapshot"] if target_commit else {}

        current_id = self._read_ref(self._current_branch_ref_path())
        current_commit = self._read_commit_object(current_id) if current_id else None
        current_snapshot = current_commit["snapshot"] if current_commit else {}
        self._restore_snapshot(current_snapshot, target_snapshot)

        # Update HEAD only after the snapshot has been restored successfully.
        self._atomic_write_text(self.control_dir / "HEAD", f"ref: refs/heads/{name}\n")

    def checkout(self, commit_id: str) -> None:
        """Restore the working tree from an existing commit.

        Checkout is intentionally non-destructive to repository references:
        HEAD and the current branch ref remain unchanged.  This keeps the
        operation safe while later iterations can add an explicit detached
        HEAD policy if required by the project specification.
        """

        self.validate()
        if not isinstance(commit_id, str) or not re.fullmatch(r"[0-9a-f]{64}", commit_id):
            raise ValueError(f"Unknown commit: {commit_id!r}")

        object_path = self.control_dir / "objects" / f"{commit_id}.json"
        if not object_path.is_file():
            raise ValueError(f"Unknown commit: {commit_id}")
        target_commit = self._read_commit_object(commit_id)

        current_id = self._read_ref(self._current_branch_ref_path())
        current_commit = self._read_commit_object(current_id) if current_id else None
        current_snapshot = current_commit["snapshot"] if current_commit else {}
        self._restore_snapshot(current_snapshot, target_commit["snapshot"])

    def merge(self, source_branch: str) -> str:
        """Merge compatible changes from ``source_branch`` into HEAD.

        A three-way snapshot comparison preserves current-only and
        source-only edits.  If both branches changed the same path differently
        from their common ancestor, :class:`MergeConflictError` is raised
        before any working-tree or reference update.  A successful merge is
        recorded as a normal commit whose parent is the current branch head;
        the source branch reference is never changed.
        """

        self.validate()
        current_ref = self._current_branch_ref_path()
        source_ref = self._branch_ref_path(source_branch)
        if source_ref == current_ref:
            raise ValueError("Cannot merge a branch into itself")
        if not source_ref.is_file():
            raise ValueError(f"Unknown source branch: {source_branch}")

        current_id = self._read_ref(current_ref)
        source_id = self._read_ref(source_ref)
        if source_id is None:
            raise ValueError(f"Source branch has no commits: {source_branch}")

        current_commit = self._read_commit_object(current_id) if current_id else None
        source_commit = self._read_commit_object(source_id)
        base_commit = self._common_ancestor(current_id, source_id)
        current_snapshot = current_commit["snapshot"] if current_commit else {}
        source_snapshot = source_commit["snapshot"]
        base_snapshot = base_commit["snapshot"] if base_commit else {}

        merged_snapshot, conflicts = self._three_way_snapshot(
            base_snapshot, current_snapshot, source_snapshot
        )
        if conflicts:
            names = ", ".join(sorted(conflicts))
            raise MergeConflictError(f"Merge conflict in file(s): {names}")

        self._restore_snapshot(current_snapshot, merged_snapshot)
        return self.commit(f"Merge branch '{source_branch}'")

    def _common_ancestor(self, current_id: str | None, source_id: str) -> dict | None:
        """Return the nearest commit shared by both parent chains."""

        current_ancestors: dict[str, dict] = {}
        cursor = current_id
        while cursor is not None:
            if cursor in current_ancestors:
                raise InvalidRepositoryError("Commit history contains a parent cycle")
            commit = self._read_commit_object(cursor)
            current_ancestors[cursor] = commit
            cursor = commit["parent"]

        cursor = source_id
        visited: set[str] = set()
        while cursor is not None:
            if cursor in visited:
                raise InvalidRepositoryError("Commit history contains a parent cycle")
            visited.add(cursor)
            if cursor in current_ancestors:
                return current_ancestors[cursor]
            cursor = self._read_commit_object(cursor)["parent"]
        return None

    @staticmethod
    def _three_way_snapshot(
        base: dict[str, str], current: dict[str, str], source: dict[str, str]
    ) -> tuple[dict[str, str], set[str]]:
        """Combine snapshots and return paths with incompatible edits."""

        missing = object()
        merged: dict[str, str] = {}
        conflicts: set[str] = set()
        for path in set(base) | set(current) | set(source):
            base_value = base.get(path, missing)
            current_value = current.get(path, missing)
            source_value = source.get(path, missing)

            if current_value == source_value:
                chosen = current_value
            elif current_value == base_value:
                chosen = source_value
            elif source_value == base_value:
                chosen = current_value
            else:
                conflicts.add(path)
                continue

            if chosen is not missing:
                merged[path] = chosen
        return merged, conflicts

    def _branch_ref_path(self, name: str) -> Path:
        """Return a safe branch ref path and reject traversal/invalid names."""

        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise ValueError(f"Invalid branch name: {name!r}")
        heads_dir = self.control_dir / "refs" / "heads"
        branch_path = heads_dir / name
        try:
            branch_path.relative_to(heads_dir)
        except ValueError as exc:
            raise ValueError(f"Invalid branch name: {name!r}") from exc
        return branch_path

    def _restore_snapshot(self, current: dict, target: dict) -> None:
        """Restore target files, removing files tracked only by current."""

        for relative in current.keys() - target.keys():
            path = self._snapshot_path(relative)
            if path.is_file():
                path.unlink()

        for relative, content in target.items():
            if not isinstance(relative, str) or not isinstance(content, str):
                raise InvalidRepositoryError("Commit snapshot contains invalid file data")
            self._atomic_write_text(self._snapshot_path(relative), content)

    def _snapshot_path(self, relative: str) -> Path:
        """Resolve a snapshot path while keeping it inside the worktree."""

        candidate = self.worktree / Path(relative)
        try:
            candidate.relative_to(self.worktree)
        except ValueError as exc:
            raise InvalidRepositoryError(f"Snapshot path escapes repository: {relative!r}") from exc
        if Path(relative).is_absolute() or relative == CONTROL_DIR_NAME or relative.startswith(f"{CONTROL_DIR_NAME}/"):
            raise InvalidRepositoryError(f"Snapshot path targets repository metadata: {relative!r}")
        return candidate

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
