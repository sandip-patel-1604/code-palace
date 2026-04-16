"""T_12 gate tests — palace diff command impact analysis validation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from palace.cli.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture()
def git_project(tmp_path: Path) -> Path:
    """Create a minimal git repo with two commits so HEAD~1..HEAD has a diff.

    Layout:
      <tmp>/repo/
        module_a.py   — initial commit
        module_b.py   — initial commit
        .palace/      — created by palace init on initial commit state
        module_c.py   — second commit (the file in the diff)
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # --- git plumbing: init and configure identity ---
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo), check=True, capture_output=True,
    )

    # --- first commit: two source files ---
    (repo / "module_a.py").write_text(
        '"""Module A."""\n\nfrom __future__ import annotations\n\n\ndef func_a() -> None:\n    """Do A."""\n',
        encoding="utf-8",
    )
    (repo / "module_b.py").write_text(
        '"""Module B."""\n\nfrom __future__ import annotations\n\nfrom module_a import func_a\n\n\ndef func_b() -> None:\n    """Do B."""\n    func_a()\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "module_a.py", "module_b.py"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(repo), check=True, capture_output=True,
    )

    # --- palace init on the initial state ---
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(repo), "--no-progress"])
    assert result.exit_code == 0, f"palace init failed:\n{result.output}"

    # --- second commit: add a new file (creates HEAD~1..HEAD diff) ---
    (repo / "module_c.py").write_text(
        '"""Module C."""\n\nfrom __future__ import annotations\n\nfrom module_b import func_b\n\n\ndef func_c() -> None:\n    """Do C."""\n    func_b()\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "module_c.py"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add module_c"],
        cwd=str(repo), check=True, capture_output=True,
    )

    return repo


# ---------------------------------------------------------------------------
# T_12.1 — Diff command integration tests
# ---------------------------------------------------------------------------


class TestDiffCommand:
    """T_12.1 — palace diff command: git diff impact analysis."""

    def test_diff_default(self, cli_runner: CliRunner, git_project: Path) -> None:
        """T_12.1: palace diff on a project with 1 changed file exits 0 and shows file names."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(git_project))
            result = cli_runner.invoke(
                app,
                ["diff", "HEAD~1..HEAD"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        # The changed file from the second commit should appear in the output
        assert "module_c" in result.output.lower(), (
            f"Expected changed file 'module_c' in output:\n{result.output}"
        )

    def test_diff_json(self, cli_runner: CliRunner, git_project: Path) -> None:
        """T_12.1: palace diff HEAD~1..HEAD --format json emits valid JSON with required keys."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(git_project))
            result = cli_runner.invoke(
                app,
                ["diff", "HEAD~1..HEAD", "--format", "json"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        data = json.loads(result.output)
        assert "range" in data, f"Missing 'range' key:\n{data}"
        assert "changed_files" in data, f"Missing 'changed_files' key:\n{data}"
        assert "domains_affected" in data, f"Missing 'domains_affected' key:\n{data}"
        assert "total_transitive" in data, f"Missing 'total_transitive' key:\n{data}"
        assert "overall_risk" in data, f"Missing 'overall_risk' key:\n{data}"
        assert "suggested_tests" in data, f"Missing 'suggested_tests' key:\n{data}"
        assert isinstance(data["changed_files"], list)
        # Range should be echoed back
        assert data["range"] == "HEAD~1..HEAD"

    def test_empty_diff(self, cli_runner: CliRunner, git_project: Path) -> None:
        """T_12.1: palace diff HEAD..HEAD (same commit) exits 0 and prints 'No changes in range'."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(git_project))
            result = cli_runner.invoke(
                app,
                ["diff", "HEAD..HEAD"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert "no changes" in result.output.lower(), (
            f"Expected 'no changes' message:\n{result.output}"
        )

    def test_no_palace(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_12.1: palace diff without .palace/ present exits 1 with an error message."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            result = cli_runner.invoke(app, ["diff", "HEAD~1..HEAD"])
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 1
        assert "No palace found" in result.output or "palace init" in result.output

    def test_not_git_repo(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_12.1: palace diff inside a palace-indexed dir that is not a git repo exits 1."""
        # Create a non-git directory, run palace init, then try diff
        project = tmp_path / "nongit"
        project.mkdir()
        (project / "a_file.py").write_text(
            '"""A file."""\n\nfrom __future__ import annotations\n',
            encoding="utf-8",
        )
        runner = CliRunner()
        init_result = runner.invoke(app, ["init", str(project), "--no-progress"])
        assert init_result.exit_code == 0, f"init failed:\n{init_result.output}"

        original_cwd = os.getcwd()
        try:
            os.chdir(str(project))
            result = cli_runner.invoke(app, ["diff", "HEAD~1..HEAD"])
        finally:
            os.chdir(original_cwd)

        # git diff will fail outside a repo → exit 1.
        # The error may surface as returncode only when the console singleton
        # was bound before CliRunner replaced sys.stdout; checking exit code
        # is the reliable assertion here.
        assert result.exit_code == 1, (
            f"Expected exit_code=1 for non-git repo, got {result.exit_code}:\n{result.output}"
        )
