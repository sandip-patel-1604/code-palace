"""T_8 gate tests — Git History Parser validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from palace.storage.duckdb_store import DuckDBStore
from palace.temporal.history import GitHistory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    """Fresh in-memory DuckDB store with schema initialised."""
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Minimal git repo initialised with identity config."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in cwd, raise on failure."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo: Path, filename: str, content: str, message: str) -> None:
    """Write a file and create a commit in repo."""
    (repo / filename).write_text(content, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)


# ---------------------------------------------------------------------------
# T_8.1 — Parse
# ---------------------------------------------------------------------------


class TestGitHistoryParse:
    def test_parse_real_git(self, git_repo: Path) -> None:
        """T_8.1: Three commits in a real git repo are all returned by parse()."""
        _commit(git_repo, "a.py", "x = 1\n", "first")
        _commit(git_repo, "b.py", "y = 2\n", "second")
        _commit(git_repo, "c.py", "z = 3\n", "third")

        history = GitHistory(git_repo)
        commits = history.parse()

        assert len(commits) == 3
        # parse() returns newest-first (git log default).
        messages = {c["message"] for c in commits}
        assert messages == {"first", "second", "third"}
        # Every commit must have required keys.
        for c in commits:
            assert "sha" in c
            assert "author_name" in c
            assert "author_email" in c
            assert "committed_at" in c
            assert "files" in c
            assert isinstance(c["files"], list)

    def test_file_changes(self, git_repo: Path) -> None:
        """T_8.1: Per-file insertions/deletions match actual content size."""
        # Write a 5-line file.
        content = "line1\nline2\nline3\nline4\nline5\n"
        _commit(git_repo, "thing.py", content, "add thing")

        history = GitHistory(git_repo)
        commits = history.parse()

        assert len(commits) == 1
        files = commits[0]["files"]
        assert len(files) == 1
        fc = files[0]
        assert fc["file_path"] == "thing.py"
        assert fc["insertions"] == 5
        assert fc["deletions"] == 0

    def test_max_commits(self, git_repo: Path) -> None:
        """T_8.1: max_commits=3 limits results when 5 commits exist."""
        for i in range(5):
            _commit(git_repo, f"f{i}.py", f"v = {i}\n", f"commit {i}")

        history = GitHistory(git_repo)
        commits = history.parse(max_commits=3)

        assert len(commits) == 3


# ---------------------------------------------------------------------------
# T_8.2 — Edge cases
# ---------------------------------------------------------------------------


class TestGitHistoryEdgeCases:
    def test_not_git_repo(self, tmp_path: Path) -> None:
        """T_8.2: Passing a non-git directory raises ValueError."""
        with pytest.raises(ValueError, match="not a git repository"):
            GitHistory(tmp_path)

    def test_binary_files(self, git_repo: Path) -> None:
        """T_8.2: Binary file commits produce insertions=None and deletions=None."""
        # Write a minimal PNG header (binary bytes).
        binary_path = git_repo / "image.png"
        binary_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        )
        _git(git_repo, "add", "image.png")
        _git(git_repo, "commit", "-m", "add binary")

        history = GitHistory(git_repo)
        commits = history.parse()

        assert len(commits) == 1
        files = commits[0]["files"]
        assert len(files) == 1
        fc = files[0]
        assert fc["insertions"] is None
        assert fc["deletions"] is None

    def test_empty_repo(self, git_repo: Path) -> None:
        """T_8.2: A repo with no commits returns an empty list from parse()."""
        history = GitHistory(git_repo)
        result = history.parse()
        assert result == []


# ---------------------------------------------------------------------------
# T_8.3 — Ingest / store integration
# ---------------------------------------------------------------------------


class TestGitHistoryIngest:
    def test_store_integration(self, git_repo: Path, store: DuckDBStore) -> None:
        """T_8.3: ingest() persists commits to DuckDB; commit_count matches."""
        _commit(git_repo, "alpha.py", "a = 1\n", "alpha commit")
        _commit(git_repo, "beta.py", "b = 2\n", "beta commit")

        history = GitHistory(git_repo)
        count = history.ingest(store)

        assert count == 2
        assert store.get_commit_count() == 2
