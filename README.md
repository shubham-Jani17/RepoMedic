# RepoMedic

**Repository health analysis and repair tool.**

RepoMedic analyzes a software repository, identifies problems, explains likely root causes, suggests or safely applies fixes, verifies changes, calculates a health score, analyzes dependency impact, and validates whether the repository is safe to proceed with.  

We created this project as part of the IBM BOB 2.0 Hackathon🧑🏻‍💻💻

---

## Installation

```bash
pip install -e ".[dev]"
```

Requires Python 3.10 or later.

---

## Usage

```
repomedic --help
```

```
Usage: repomedic [OPTIONS] COMMAND [ARGS]...

  RepoMedic — repository health analysis and repair tool.

  Quick start:
    repomedic scan        Scan a repository for problems
    repomedic analyze     Analyze and rank identified problems
    repomedic explain     Explain root causes of a problem
    repomedic fix         Suggest or apply fixes
    repomedic report      Generate a health report
    repomedic validate    Validate the repository is safe to proceed

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  analyze   Analyze and rank identified problems.
  explain   Explain the root cause of a problem.
  fix       Suggest or apply fixes for identified problems.
  report    Generate a repository health report.
  scan      Scan a repository for problems.
  validate  Validate that the repository is safe to proceed with.
```

You can also invoke RepoMedic as a Python module:

```bash
python -m repomedic --help
```

---

## Commands

| Command    | Status          | Description                                              |
|------------|-----------------|----------------------------------------------------------|
| `scan`     | 🚧 stub          | Walk the repository and collect raw findings             |
| `analyze`  | 🚧 stub          | Rank and group findings by severity and impact           |
| `explain`  | 🚧 stub          | AI-powered root-cause explanation for a finding          |
| `fix`      | 🚧 stub          | Suggest or automatically apply a safe fix                |
| `report`   | 🚧 stub          | Render a health-score report (text / JSON / HTML)        |
| `validate` | 🚧 stub          | Confirm the repository passes all safety gates           |

---

## Project layout

```
repomedic/
├── __init__.py       # package version
├── __main__.py       # python -m repomedic entry point
├── cli/
│   ├── __init__.py
│   └── main.py       # Click command group + sub-commands
├── scanner/          # repository walking and raw finding collection
├── analyzer/         # problem ranking and root-cause analysis
├── graph/            # dependency graph construction and impact analysis
├── ai/               # AI explanation and suggestion generation
├── fixer/            # automated and supervised fix application
├── reporter/         # health-score reporting and output formatting
├── validator/        # post-fix validation and safety checks
└── utils/            # shared utilities (file helpers, logging, config)

tests/
pyproject.toml
README.md
```

---

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=repomedic
```

---

## License

MIT
