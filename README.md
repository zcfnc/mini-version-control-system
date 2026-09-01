# Mini Version Control System

This repository contains the first AI-assisted TDD iteration for the PRT582
Software Unit Testing Report. The current iteration implements repository
initialisation only. Requirements and the planned test cases are documented in
[`requirements.md`](requirements.md).

## Run the initial test suite

From the `Assignment2` directory:

```bash
python -m unittest discover -s tests -v
```

The implementation creates a local `.mini-vcs` directory containing metadata,
an empty `main` branch reference and an initial `HEAD` reference. It does not
modify files already present in the working directory.

