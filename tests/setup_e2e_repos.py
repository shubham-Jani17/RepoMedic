"""Script to create 10 test repositories for end-to-end validation of RepoMedic.

Calling this script multiple times is safe: each repo directory is fully
removed and recreated from scratch so that artefacts from previous runs
(e.g. files written by ``repomedic fix --apply``) cannot contaminate the
test fixture.
"""

import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(r"C:\Users\Shubham\AppData\Local\Temp\repomedic_e2e")


def git_init(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True)


def git_configure(path: Path) -> None:
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, capture_output=True)


def git_commit(path: Path) -> None:
    git_configure(path)
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, capture_output=True)


def create_repos() -> None:
    BASE.mkdir(parents=True, exist_ok=True)

    def _fresh_dir(path: Path) -> Path:
        """Remove and recreate *path* so previous-run artefacts are gone."""
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ---- Repo 1: Healthy Python project ----
    r1 = _fresh_dir(BASE / "repo1_healthy")
    (r1 / "README.md").write_text("# My Project\nA healthy project.\n", encoding="utf-8")
    (r1 / "LICENSE").write_text("MIT License\nCopyright 2025\n", encoding="utf-8")
    (r1 / ".gitignore").write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
    (r1 / "main.py").write_text(
        "def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n",
        encoding="utf-8",
    )
    (r1 / "utils.py").write_text("def helper():\n    return 42\n", encoding="utf-8")
    git_init(r1)
    git_commit(r1)
    print(f"  [ok] repo1_healthy: {r1}")

    # ---- Repo 2: Missing README ----
    r2 = _fresh_dir(BASE / "repo2_no_readme")
    (r2 / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (r2 / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (r2 / "app.py").write_text("x = 1\n", encoding="utf-8")
    print(f"  [ok] repo2_no_readme: {r2}")

    # ---- Repo 3: Missing LICENSE ----
    r3 = _fresh_dir(BASE / "repo3_no_license")
    (r3 / "README.md").write_text("# No License Project\n", encoding="utf-8")
    (r3 / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (r3 / "app.py").write_text("x = 1\n", encoding="utf-8")
    print(f"  [ok] repo3_no_license: {r3}")

    # ---- Repo 4: Missing .gitignore ----
    r4 = _fresh_dir(BASE / "repo4_no_gitignore")
    (r4 / "README.md").write_text("# No gitignore\n", encoding="utf-8")
    (r4 / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (r4 / "app.py").write_text("x = 1\n", encoding="utf-8")
    print(f"  [ok] repo4_no_gitignore: {r4}")

    # ---- Repo 5: Python syntax error ----
    r5 = _fresh_dir(BASE / "repo5_syntax_error")
    (r5 / "README.md").write_text("# Syntax Error Project\n", encoding="utf-8")
    (r5 / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (r5 / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    # Deliberately broken Python
    (r5 / "broken.py").write_text("def foo(\n    x = 1\n", encoding="utf-8")
    print(f"  [ok] repo5_syntax_error: {r5}")

    # ---- Repo 6: Multiple dependent Python files ----
    r6 = _fresh_dir(BASE / "repo6_dependent_files")
    (r6 / "README.md").write_text("# Dependent files\n", encoding="utf-8")
    (r6 / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (r6 / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (r6 / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
    (r6 / "services.py").write_text(
        "from models import User\n\ndef get_user():\n    return User()\n", encoding="utf-8"
    )
    (r6 / "api.py").write_text(
        "from services import get_user\n\ndef handle():\n    return get_user()\n",
        encoding="utf-8",
    )
    git_init(r6)
    git_commit(r6)
    print(f"  [ok] repo6_dependent_files: {r6}")

    # ---- Repo 7: Modified Git files ----
    r7 = _fresh_dir(BASE / "repo7_modified_git")
    (r7 / "README.md").write_text("# Git Modified Repo\n", encoding="utf-8")
    (r7 / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (r7 / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (r7 / "main.py").write_text("x = 1\n", encoding="utf-8")
    git_init(r7)
    git_commit(r7)
    # Modify existing tracked file + add untracked file
    (r7 / "main.py").write_text("x = 2\n", encoding="utf-8")
    (r7 / "new_file.py").write_text("y = 3\n", encoding="utf-8")
    print(f"  [ok] repo7_modified_git: {r7}")

    # ---- Repo 8: Non-Git project ----
    r8 = _fresh_dir(BASE / "repo8_nongit")
    (r8 / "README.md").write_text("# Non-Git Project\n", encoding="utf-8")
    (r8 / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (r8 / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (r8 / "app.py").write_text("print('hello')\n", encoding="utf-8")
    print(f"  [ok] repo8_nongit: {r8}")

    # ---- Repo 9: Empty project ----
    r9 = _fresh_dir(BASE / "repo9_empty")
    print(f"  [ok] repo9_empty: {r9}")

    # ---- Repo 10: Invalid path (does NOT exist) ----
    r10 = BASE / "repo10_invalid_does_not_exist"
    print(f"  [ok] repo10_invalid_path (not created): {r10}")

    print("\nAll test repos ready.")
    print(f"BASE = {BASE}")


if __name__ == "__main__":
    create_repos()
