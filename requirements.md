# Mini Version Control System – Requirements and Initial Test Design

## 1. Project objective

The project will implement a small, local, Git-like version control system for learning and testing purposes. It will store file snapshots and lightweight metadata in a hidden `.mini-vcs` directory. The implementation will be developed using an AI-assisted Test-Driven Development (AI-TDD) workflow.

## 2. Scope

### In scope

- Repository initialisation.
- Creation of commits containing working-directory snapshots.
- Commit history retrieval.
- Branch creation and branch switching.
- Checkout of an existing commit.
- Merge of two local branches.
- Detection and reporting of merge conflicts.
- Automated unit tests for normal, boundary, invalid-input and exceptional cases.

### Out of scope

- Remote repositories, push, pull or network synchronisation.
- User authentication and multi-user access control.
- Full compatibility with Git.
- Binary-file optimisation, compression and a graphical user interface.

## 3. Functional requirements

- **FR-01 – Initialise repository:** The system shall create a valid repository control directory for a selected working directory.
- **FR-02 – Initialise default branch:** A new repository shall contain a `main` branch reference and a `HEAD` reference to that branch.
- **FR-03 – Preserve working files:** Initialisation shall not modify or delete files already present in the working directory.
- **FR-04 – Create commit:** The system shall save a snapshot of tracked working files and return a unique commit identifier.
- **FR-05 – View history:** The system shall return commits in reverse chronological order, including their identifiers and messages.
- **FR-06 – Create branch:** The system shall create a branch pointing to a selected or current commit.
- **FR-07 – Switch branch:** The system shall switch `HEAD` to an existing branch and restore its latest snapshot.
- **FR-08 – Checkout commit:** The system shall restore the working directory to a selected commit.
- **FR-09 – Merge branches:** The system shall merge a source branch into the current branch when changes do not conflict.
- **FR-10 – Detect conflicts:** The system shall identify conflicting changes and prevent a silent overwrite.
- **FR-11 – Validate operations:** The system shall reject missing commits, missing branches, invalid paths and malformed repository metadata with clear errors.
- **FR-12 – Protect failed operations:** A failed operation shall not leave contradictory or partially written repository metadata.

## 4. Non-functional requirements

- **NFR-01 – Correctness:** Repository state shall be deterministic for the same sequence of inputs.
- **NFR-02 – Data integrity:** Commit objects and references shall not be silently overwritten or corrupted by failed operations.
- **NFR-03 – Usability:** Public operations shall return clear results and actionable error messages.
- **NFR-04 – Maintainability:** The implementation shall use small, modular Python components with documented public behaviour.
- **NFR-05 – Testability:** Core repository operations shall be testable with temporary directories and without network access.
- **NFR-06 – Performance:** Initialisation and metadata operations should complete within two seconds for a normal local repository.
- **NFR-07 – Portability:** The system should work on supported Python versions on Windows, macOS and Linux.

## 5. Assumptions

- The user has permission to read and write the selected working directory.
- File paths are local paths and are represented using Python's `pathlib`.
- The initial implementation targets text files and small repositories.
- `main` is the default branch name.
- A repository is identified by the presence of valid `.mini-vcs` metadata.

## 6. Constraints

- The project must be developed with AI assistance and reviewed by the student.
- Automated tests must be designed before implementing each major feature.
- The first implementation iteration is limited to repository initialisation.
- No external network service may be required to run the core tests.

## 7. Initial test cases

The following tests are designed before implementation. The first iteration implements the repository-initialisation tests; later iterations will implement commit, branch, checkout and merge tests.

| Test ID | Test case name | Test purpose |
|---|---|---|
| TC-01 | `test_init_creates_control_directory` | Verify that initialisation creates the hidden `.mini-vcs` directory. |
| TC-02 | `test_init_creates_required_subdirectories` | Verify that object storage and branch-reference directories are created. |
| TC-03 | `test_init_writes_head_to_default_branch` | Verify that `HEAD` points to `refs/heads/main`. |
| TC-04 | `test_init_creates_empty_main_ref` | Verify that the new `main` reference starts without a commit. |
| TC-05 | `test_init_stores_format_metadata` | Verify that repository format metadata is written and readable. |
| TC-06 | `test_init_creates_missing_target_directory` | Verify boundary behaviour when the requested working directory does not yet exist. |
| TC-07 | `test_init_preserves_existing_working_files` | Prevent initialisation from deleting or changing user files. |
| TC-08 | `test_init_rejects_file_as_target` | Verify that a regular file cannot be used as a repository directory. |
| TC-09 | `test_init_rejects_existing_repository_without_exist_ok` | Prevent accidental reinitialisation of an existing repository. |
| TC-10 | `test_init_returns_repository_instance_when_exist_ok` | Verify that an explicitly idempotent initialisation returns a usable repository object. |
| TC-11 | `test_init_is_repeatable_with_exist_ok` | Verify that repeated idempotent initialisation does not corrupt metadata. |
| TC-12 | `test_init_rejects_malformed_existing_metadata` | Verify that an existing invalid control directory is reported instead of being silently accepted. |
| TC-13 | `test_commit_stores_snapshot` | Verify that a future commit operation saves the expected file snapshot. |
| TC-14 | `test_checkout_unknown_commit_fails` | Verify that checkout rejects a commit identifier that does not exist. |
| TC-15 | `test_merge_conflict_is_reported` | Verify that a future merge operation reports conflicting edits rather than overwriting them. |

For each test group, the report will explain the expected behaviour, the reason the test is necessary, and the defect it is intended to prevent.

