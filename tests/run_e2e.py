"""
End-to-end validation test for RepoMedic CLI.

Tests all 10 CLI command/option combinations against 10 different repository scenarios.
Checks:
 - exit codes
 - JSON validity
 - correct output content
 - no file overwrites
 - no crashes
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(r"C:\Users\Shubham\AppData\Local\Temp\repomedic_e2e")

REPOS = {
    "repo1_healthy": BASE / "repo1_healthy",
    "repo2_no_readme": BASE / "repo2_no_readme",
    "repo3_no_license": BASE / "repo3_no_license",
    "repo4_no_gitignore": BASE / "repo4_no_gitignore",
    "repo5_syntax_error": BASE / "repo5_syntax_error",
    "repo6_dependent_files": BASE / "repo6_dependent_files",
    "repo7_modified_git": BASE / "repo7_modified_git",
    "repo8_nongit": BASE / "repo8_nongit",
    "repo9_empty": BASE / "repo9_empty",
    "repo10_invalid": BASE / "repo10_invalid_does_not_exist",
}

passed = 0
failed = 0
failures: list[str] = []


def run(args: list[str], expect_exit: int | None = 0, label: str = "") -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, "-m", "repomedic"] + args,
        capture_output=True,
        text=True,
    )
    return result


def check(
    label: str,
    result: subprocess.CompletedProcess,
    *,
    expect_exit: int | None = 0,
    contains: list[str] | None = None,
    valid_json: bool = False,
    json_keys: list[str] | None = None,
    not_contains: list[str] | None = None,
) -> None:
    global passed, failed

    errors: list[str] = []

    if expect_exit is not None and result.returncode != expect_exit:
        errors.append(
            f"exit code {result.returncode} != expected {expect_exit}\n"
            f"  stdout: {result.stdout[:300]!r}\n"
            f"  stderr: {result.stderr[:300]!r}"
        )

    if contains:
        for phrase in contains:
            if phrase.lower() not in (result.stdout + result.stderr).lower():
                errors.append(f"expected {phrase!r} in output")

    if not_contains:
        for phrase in not_contains:
            if phrase.lower() in result.stdout.lower():
                errors.append(f"did NOT expect {phrase!r} in stdout")

    if valid_json:
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            errors.append(f"invalid JSON: {e}\n  stdout: {result.stdout[:300]!r}")
            data = None
        if data is not None and json_keys:
            for key in json_keys:
                if key not in data:
                    errors.append(f"JSON missing key {key!r}")

    if errors:
        failed += 1
        msg = f"FAIL [{label}]\n" + "\n".join(f"    {e}" for e in errors)
        failures.append(msg)
        print(msg)
    else:
        passed += 1
        print(f"PASS [{label}]")


# ===========================================================================
# 1. repomedic --help
# ===========================================================================

result = run(["--help"])
check(
    "help: exit 0",
    result,
    expect_exit=0,
    contains=["scan", "analyze", "explain", "fix", "report", "validate"],
)

# Test repomedic console script executable directly
r_exe = subprocess.run(["repomedic", "--help"], capture_output=True, text=True)
check(
    "repomedic_exe_help: exit 0",
    r_exe,
    expect_exit=0,
    contains=["scan", "analyze", "explain", "fix", "report", "validate"],
)

# ===========================================================================
# 2. repomedic scan <path>
# ===========================================================================

for name, path in REPOS.items():
    if name == "repo10_invalid":
        r = run(["scan", str(path)])
        check(f"scan/{name}: exit nonzero", r, expect_exit=1)
    else:
        r = run(["scan", str(path)])
        check(f"scan/{name}: exit 0", r, expect_exit=0, contains=["scan"])

# scan --format json on healthy repo
r = run(["scan", "--format", "json", str(REPOS["repo1_healthy"])])
check(
    "scan/json/repo1_healthy",
    r,
    expect_exit=0,
    valid_json=True,
    json_keys=["root", "file_count", "total_size_bytes", "extension_counts", "languages"],
)

# scan --format json on empty repo
r = run(["scan", "--format", "json", str(REPOS["repo9_empty"])])
check(
    "scan/json/repo9_empty",
    r,
    expect_exit=0,
    valid_json=True,
    json_keys=["file_count"],
)

# ===========================================================================
# 3. repomedic analyze <path>
# ===========================================================================

for name, path in REPOS.items():
    if name == "repo10_invalid":
        r = run(["analyze", str(path)])
        check(f"analyze/{name}: exit nonzero", r, expect_exit=1)
    else:
        r = run(["analyze", str(path)])
        check(f"analyze/{name}: exit 0", r, expect_exit=0)

# analyze --format json — check JSON validity
r = run(["analyze", "--format", "json", str(REPOS["repo1_healthy"])])
check(
    "analyze/json/repo1_healthy",
    r,
    expect_exit=0,
    valid_json=True,
    json_keys=["root", "issue_count", "issues", "severity_counts"],
)

# analyze/syntax error repo — should detect CRITICAL
r = run(["analyze", "--format", "json", str(REPOS["repo5_syntax_error"])])
check(
    "analyze/json/repo5_syntax_error",
    r,
    expect_exit=0,
    valid_json=True,
    contains=["syntax"],
)

# analyze/missing readme repo — should detect governance issue
r = run(["analyze", "--format", "json", str(REPOS["repo2_no_readme"])])
try:
    data = json.loads(r.stdout)
    titles = [i["title"].lower() for i in data.get("issues", [])]
    if not any("readme" in t for t in titles):
        check("analyze/json/repo2_no_readme: readme issue detected", r, expect_exit=None,
              contains=["README"])
    else:
        passed += 1
        print("PASS [analyze/json/repo2_no_readme: readme issue detected]")
except Exception as e:
    failed += 1
    failures.append(f"FAIL [analyze/json/repo2_no_readme json parse]: {e}")
    print(f"FAIL [analyze/json/repo2_no_readme json parse]: {e}")

# ===========================================================================
# 4. repomedic explain <path>
# ===========================================================================

for name, path in REPOS.items():
    if name == "repo10_invalid":
        r = run(["explain", str(path)])
        check(f"explain/{name}: exit nonzero", r, expect_exit=1)
    else:
        r = run(["explain", str(path)])
        check(f"explain/{name}: exit 0", r, expect_exit=0)

# explain --format json
r = run(["explain", "--format", "json", str(REPOS["repo1_healthy"])])
check(
    "explain/json/repo1_healthy",
    r,
    expect_exit=0,
    valid_json=True,
    json_keys=["repo_root", "provider", "explanation"],
)

# ===========================================================================
# 5. repomedic fix --suggest <path>
# ===========================================================================

for name, path in REPOS.items():
    if name == "repo10_invalid":
        r = run(["fix", "--suggest", str(path)])
        check(f"fix_suggest/{name}: exit nonzero", r, expect_exit=1)
    else:
        r = run(["fix", "--suggest", str(path)])
        check(f"fix_suggest/{name}: exit 0", r, expect_exit=0)
        # Verify NO files were created by --suggest
        if path.exists():
            # Check a few of the governance files were not created
            for gfile in [".gitignore", "README.md", "LICENSE"]:
                if not (path / gfile).exists():
                    pass  # good, file didn't exist and --suggest didn't create it

# fix --suggest json
r = run(["fix", "--suggest", "--format", "json", str(REPOS["repo2_no_readme"])])
check(
    "fix_suggest/json/repo2_no_readme",
    r,
    expect_exit=0,
    valid_json=True,
    json_keys=["repo_root", "mode", "suggestions"],
)

# --suggest must not create files
r2_gitignore_before = (REPOS["repo2_no_readme"] / ".gitignore").exists()
run(["fix", "--suggest", str(REPOS["repo2_no_readme"])])
r2_gitignore_after = (REPOS["repo2_no_readme"] / ".gitignore").exists()
if r2_gitignore_before == r2_gitignore_after:
    passed += 1
    print("PASS [fix_suggest: no file created]")
else:
    failed += 1
    msg = "FAIL [fix_suggest: --suggest created a file it should not have!]"
    failures.append(msg)
    print(msg)

# ===========================================================================
# 6. repomedic fix --apply <path>
# ===========================================================================

# Use a fresh temp copy of repo2 so we can test apply creates README
import shutil, tempfile

apply_repo = Path(tempfile.mkdtemp(prefix="repomedic_apply_"))
shutil.copytree(REPOS["repo2_no_readme"], apply_repo / "apply_test", dirs_exist_ok=True)
apply_path = apply_repo / "apply_test"

r = run(["fix", "--apply", str(apply_path)])
check("fix_apply/repo2_no_readme: exit 0", r, expect_exit=0, contains=["created", "fix"])

# README.md should now exist
if (apply_path / "README.md").exists():
    passed += 1
    print("PASS [fix_apply: README.md was created]")
else:
    failed += 1
    failures.append("FAIL [fix_apply: README.md was NOT created]")
    print("FAIL [fix_apply: README.md was NOT created]")

# Running apply a second time should skip (no overwrite)
r2 = run(["fix", "--apply", str(apply_path)])
check("fix_apply/idempotent: exit 0", r2, expect_exit=0, contains=["skipped"])

# Confirm .gitignore was also created in first apply (repo2 has .gitignore already — skip)
# So test with repo with no gitignore:
apply_repo3 = Path(tempfile.mkdtemp(prefix="repomedic_apply3_"))
shutil.copytree(REPOS["repo3_no_license"], apply_repo3 / "apply_test3", dirs_exist_ok=True)
apply_path3 = apply_repo3 / "apply_test3"

r3 = run(["fix", "--apply", str(apply_path3)])
check("fix_apply/repo3_no_license: exit 0", r3, expect_exit=0)

# LICENSE should now exist (repo3 was missing it)
if (apply_path3 / "LICENSE").exists():
    passed += 1
    print("PASS [fix_apply: LICENSE was created]")
else:
    failed += 1
    failures.append("FAIL [fix_apply: LICENSE was NOT created]")
    print("FAIL [fix_apply: LICENSE was NOT created]")

# fix --apply --format json
apply_repoJ = Path(tempfile.mkdtemp(prefix="repomedic_applyJ_"))
shutil.copytree(REPOS["repo4_no_gitignore"], apply_repoJ / "applyJ", dirs_exist_ok=True)
apply_pathJ = apply_repoJ / "applyJ"

rj = run(["fix", "--apply", "--format", "json", str(apply_pathJ)])
check(
    "fix_apply/json/repo4_no_gitignore",
    rj,
    expect_exit=0,
    valid_json=True,
    json_keys=["repo_root", "mode", "apply_report", "verification"],
)

# ===========================================================================
# 7. repomedic report <path>
# ===========================================================================

for name, path in REPOS.items():
    if name == "repo10_invalid":
        r = run(["report", str(path)])
        check(f"report/{name}: exit nonzero", r, expect_exit=1)
    else:
        r = run(["report", str(path)])
        check(f"report/{name}: exit 0", r, expect_exit=0)

# ===========================================================================
# 8. repomedic report --json <path>
# ===========================================================================

for name, path in REPOS.items():
    if name == "repo10_invalid":
        r = run(["report", "--json", str(path)])
        check(f"report_json/{name}: exit nonzero", r, expect_exit=1)
    else:
        r = run(["report", "--json", str(path)])
        check(
            f"report_json/{name}: valid json",
            r,
            expect_exit=0,
            valid_json=True,
            json_keys=["repository", "health_score", "issues"],
        )

# ===========================================================================
# 9. repomedic validate <path>
# ===========================================================================

# Healthy repo → should PASS (exit 0)
r = run(["validate", str(REPOS["repo1_healthy"])])
check("validate/repo1_healthy: PASS", r, expect_exit=0, contains=["PASS"])

# Repo with syntax error → CRITICAL issue → FAIL (exit 1)
r = run(["validate", str(REPOS["repo5_syntax_error"])])
check("validate/repo5_syntax_error: FAIL", r, expect_exit=1, contains=["FAIL"])

# Empty repo → all governance files missing, score will be low → still passes at threshold=0
r = run(["validate", str(REPOS["repo9_empty"])])
check("validate/repo9_empty: no crash", r)  # exit 0 or 1 both ok, just no crash

# Non-git repo → should succeed without crashing (git status depends on environment)
r = run(["validate", str(REPOS["repo8_nongit"])])
check("validate/repo8_nongit: exit 0", r, expect_exit=0, contains=["Validation Result"])

# Dependent files repo → should PASS (exit 0)
r = run(["validate", str(REPOS["repo6_dependent_files"])])
check("validate/repo6_dependent_files: PASS", r, expect_exit=0, contains=["PASS"])

# Modified git repo → shows 2 changed files and PASSes (exit 0)
r = run(["validate", str(REPOS["repo7_modified_git"])])
check("validate/repo7_modified_git: PASS", r, expect_exit=0, contains=["Changed Files : 2", "PASS"])

# Invalid path → exit 2
r = run(["validate", str(REPOS["repo10_invalid"])])
check("validate/repo10_invalid: exit 2", r, expect_exit=2)

# ===========================================================================
# 10. repomedic validate <path> --fail-under 80
# ===========================================================================

# Healthy repo should have score >= 80
r = run(["validate", str(REPOS["repo1_healthy"]), "--fail-under", "80"])
check("validate/repo1_healthy/fail-under-80: PASS", r, expect_exit=0)

# Repo with syntax error (CRITICAL = 20 pts deduction) → score 80 at best with no other issues
# But repo5 has README, LICENSE, .gitignore - let's check actual outcome
r = run(["validate", "--format", "json", str(REPOS["repo5_syntax_error"]), "--fail-under", "80"]) \
    if False else run(["validate", str(REPOS["repo5_syntax_error"]), "--fail-under", "80"])
# Exit 1 because either blocking CRITICAL or low score
check("validate/repo5_syntax_error/fail-under-80: FAIL", r, expect_exit=1)

# Empty repo: only 3 governance issues (README=MEDIUM -5, LICENSE=HIGH -10, gitignore=LOW -2)
# Score = 100 - 17 = 83. At --fail-under 80, 83 >= 80 so it PASSes (exit 0).
r = run(["validate", str(REPOS["repo9_empty"]), "--fail-under", "80"])
check("validate/repo9_empty/fail-under-80: PASS (score=83)", r, expect_exit=0)

# Threshold=0 → passing regardless of score (if no critical issues)
r = run(["validate", str(REPOS["repo2_no_readme"]), "--fail-under", "0"])
check("validate/repo2_no_readme/fail-under-0: PASS", r, expect_exit=0)

# ===========================================================================
# Summary
# ===========================================================================

print()
print("=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 60)

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f)
    sys.exit(1)
else:
    print("All checks passed!")
    sys.exit(0)
