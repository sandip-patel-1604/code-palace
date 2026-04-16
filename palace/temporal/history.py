"""Git history parser — reads git log and stores commits in DuckDB for Code Palace."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palace.storage.duckdb_store import DuckDBStore

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

# Unique sentinel for splitting commits — unlikely to appear in real output.
_COMMIT_START = "<<PALACE_COMMIT>>"

# Field separator within the header line.
_FIELD_SEP = "<<F>>"

# Binary files show `-\t-` for insertions/deletions in numstat.
_BINARY_RE = re.compile(r"^-\t-\t")

# Rename path format: `{old => new}` brace notation in numstat paths.
_RENAME_BRACE_RE = re.compile(r"\{[^}]*=>\s*([^}]*)\}")


# ------------------------------------------------------------------
# Public class
# ------------------------------------------------------------------


class GitHistory:
    """Parse a git repository's commit history and persist it to DuckDB."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._validate_git_repo()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, max_commits: int = 10_000) -> list[dict]:
        """Run git log and return structured commit data.

        Each returned dict has keys:
            sha, author_name, author_email, committed_at, message,
            insertions (int), deletions (int),
            files (list[dict] with file_path, insertions, deletions, change_type).
        """
        raw = self._run_git_log(max_commits)
        if not raw.strip():
            return []
        return _parse_log_output(raw)

    def ingest(self, store: DuckDBStore, max_commits: int = 10_000) -> int:
        """Parse git history and store every commit + file-change in DuckDB.

        Resolves file_path to file_id via store.get_file_by_path().
        Returns total number of commits now stored.
        """
        commits = self.parse(max_commits)
        for commit in commits:
            commit_id = store.upsert_commit(
                sha=commit["sha"],
                author_name=commit["author_name"],
                author_email=commit["author_email"],
                committed_at=commit["committed_at"],
                message=commit["message"],
                insertions=commit["insertions"],
                deletions=commit["deletions"],
            )
            for fc in commit["files"]:
                file_row = store.get_file_by_path(fc["file_path"])
                file_id: int | None = file_row["file_id"] if file_row else None
                store.upsert_file_change(
                    commit_id=commit_id,
                    file_path=fc["file_path"],
                    file_id=file_id,
                    insertions=fc["insertions"],
                    deletions=fc["deletions"],
                    change_type=fc["change_type"],
                )
        return store.get_commit_count()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_git_repo(self) -> None:
        """Raise ValueError if self._root is not inside a git repository."""
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=self._root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(
                f"{self._root!r} is not a git repository (git rev-parse failed)"
            )

    def _run_git_log(self, max_commits: int) -> str:
        """Execute git log and return raw stdout as a string."""
        fmt = f"--format={_COMMIT_START}{_FIELD_SEP}%H{_FIELD_SEP}%aN{_FIELD_SEP}%aE{_FIELD_SEP}%cI{_FIELD_SEP}%s"
        result = subprocess.run(
            [
                "git",
                "log",
                fmt,
                "--numstat",
                f"--max-count={max_commits}",
            ],
            cwd=self._root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout


# ------------------------------------------------------------------
# Module-level parsing helpers
# ------------------------------------------------------------------


def _parse_log_output(raw: str) -> list[dict]:
    """Split raw git log output into per-commit dicts."""
    blocks = raw.split(_COMMIT_START)
    commits: list[dict] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        commit = _parse_commit_block(block)
        if commit is not None:
            commits.append(commit)
    return commits


def _parse_commit_block(block: str) -> dict | None:
    """Parse one commit block (header line + numstat lines) into a dict."""
    lines = block.splitlines()
    if not lines:
        return None

    # First line is the header with _FIELD_SEP-separated fields.
    # The format starts with _FIELD_SEP so first element after split is empty.
    header_line = lines[0]
    parts = header_line.split(_FIELD_SEP)
    # Expected: ["", sha, author_name, author_email, committed_at, message]
    # Filter out empty parts from leading separator
    parts = [p for p in parts if p or parts.index(p) > 0]
    parts = [p.strip() for p in header_line.split(_FIELD_SEP) if p.strip()]

    if len(parts) < 5:
        return None

    sha, author_name, author_email, committed_at, message = (
        parts[0], parts[1], parts[2], parts[3], parts[4],
    )

    file_changes, total_ins, total_del = _parse_numstat_lines(lines[1:])

    return {
        "sha": sha,
        "author_name": author_name,
        "author_email": author_email,
        "committed_at": committed_at,
        "message": message,
        "insertions": total_ins,
        "deletions": total_del,
        "files": file_changes,
    }


def _parse_numstat_lines(lines: list[str]) -> tuple[list[dict], int, int]:
    """Parse numstat lines into file-change records."""
    file_changes: list[dict] = []
    total_ins = 0
    total_del = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # numstat: insertions<TAB>deletions<TAB>path
        tab_parts = line.split("\t", 2)
        if len(tab_parts) < 3:
            continue

        ins_str, del_str, raw_path = tab_parts

        # Resolve rename brace notation
        file_path = _resolve_rename_path(raw_path)

        # Detect binary files
        if ins_str == "-" and del_str == "-":
            insertions: int | None = None
            deletions: int | None = None
        else:
            try:
                insertions = int(ins_str)
                deletions = int(del_str)
            except ValueError:
                insertions = None
                deletions = None

        if insertions is not None:
            total_ins += insertions
        if deletions is not None:
            total_del += deletions

        change_type = _infer_change_type(raw_path, insertions, deletions)

        file_changes.append({
            "file_path": file_path,
            "insertions": insertions,
            "deletions": deletions,
            "change_type": change_type,
        })

    return file_changes, total_ins, total_del


def _resolve_rename_path(raw_path: str) -> str:
    """Convert git rename brace notation to the final (destination) path."""
    match = _RENAME_BRACE_RE.search(raw_path)
    if not match:
        return raw_path.strip()
    new_part = match.group(1).strip()
    resolved = _RENAME_BRACE_RE.sub(new_part, raw_path)
    resolved = re.sub(r"/+", "/", resolved).strip("/")
    return resolved


def _infer_change_type(
    raw_path: str,
    insertions: int | None,
    deletions: int | None,
) -> str:
    """Return a change_type string: A, M, D, or R."""
    if _RENAME_BRACE_RE.search(raw_path):
        return "R"
    if insertions == 0 and deletions and deletions > 0:
        return "D"
    if deletions == 0 and insertions and insertions > 0:
        return "A"
    return "M"
