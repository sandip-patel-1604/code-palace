"""Structural planning engine — pure graph analysis, no LLM required."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

from palace.graph.traversal import topological_sort
from palace.storage.duckdb_store import DuckDBStore

# ---------------------------------------------------------------------------
# Stop words — common English words that carry no semantic signal in a task
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between", "out", "off",
        "over", "under", "again", "further", "then", "once", "here", "there",
        "when", "where", "why", "how", "all", "each", "every", "both", "few",
        "more", "most", "other", "some", "such", "no", "nor", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "because", "but",
        "and", "or", "if", "while", "about", "that", "this", "these", "those",
        "it", "its", "i", "me", "my", "we", "our", "you", "your", "he", "him",
        "his", "she", "her", "they", "them", "their", "what", "which", "who",
        "whom",
    }
)

# Relevance score weights
_SYMBOL_NAME_WEIGHT = 3
_FILE_PATH_WEIGHT = 2
_DOCSTRING_WEIGHT = 1


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MatchedFile:
    """A file identified as relevant to the task, with its relevance score."""

    file_id: int
    path: str
    language: str
    relevance_score: float
    matched_symbols: list[dict] = field(default_factory=list)
    reason: str = ""


@dataclass
class DetectedPattern:
    """A naming pattern discovered among sibling files in the same directory."""

    name: str
    directory: str
    examples: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class PlanResult:
    """Output of the structural planner for a given task description."""

    task: str
    matched_files: list[MatchedFile] = field(default_factory=list)
    patterns: list[DetectedPattern] = field(default_factory=list)
    suggested_tests: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class StructuralPlanner:
    """Analyses the codebase graph and produces a structural change plan."""

    def __init__(self, store: DuckDBStore) -> None:
        self.store = store

    def plan(self, task: str, scope: str | None = None) -> PlanResult:
        """Generate a structural change plan for the given task description.

        Five-step pipeline:
        1. Keyword extraction
        2. Symbol and path matching with relevance scoring
        3. Naming-pattern detection
        4. Dependency-ordered file list
        5. Test-file suggestion
        """
        # Step 1 — keywords
        keywords = _extract_keywords(task)

        # Early-exit guard: no keywords means nothing to search for
        if not keywords:
            return PlanResult(task=task, keywords=keywords)

        # Pre-load all files once so we can iterate them cheaply
        all_files = self.store.get_all_files()

        # Apply scope filter before matching
        if scope:
            all_files = [f for f in all_files if fnmatch.fnmatch(f["path"], scope)]

        # Step 2 — score each file
        matched_files = self._score_files(all_files, keywords)

        if not matched_files:
            return PlanResult(task=task, keywords=keywords)

        # Step 3 — pattern detection across directories of matched files
        patterns = self._detect_patterns(all_files, matched_files)

        # Step 4 — topological ordering (dependency leaves first)
        matched_ids = {mf.file_id for mf in matched_files}
        ordered_ids = topological_sort(self.store, matched_ids)
        # Rebuild matched_files in dependency order, preserving scores
        score_map = {mf.file_id: mf for mf in matched_files}
        ordered_files = [score_map[fid] for fid in ordered_ids if fid in score_map]

        # Step 5 — test suggestions
        all_paths = {f["path"] for f in all_files}
        suggested_tests = _suggest_tests(ordered_files, all_paths)

        return PlanResult(
            task=task,
            matched_files=ordered_files,
            patterns=patterns,
            suggested_tests=suggested_tests,
            keywords=keywords,
        )

    # ------------------------------------------------------------------
    # Step 2 — symbol and path scoring
    # ------------------------------------------------------------------

    def _score_files(
        self,
        all_files: list[dict],
        keywords: list[str],
    ) -> list[MatchedFile]:
        """Score every file against keywords; return only those with score > 0."""
        # Pre-fetch all symbols for efficient keyword matching.
        # Group by file_id to avoid repeated per-file queries.
        all_symbols = self.store.get_symbols()
        symbols_by_file: dict[int, list[dict]] = {}
        for sym in all_symbols:
            symbols_by_file.setdefault(sym["file_id"], []).append(sym)

        results: list[MatchedFile] = []

        for file_row in all_files:
            fid: int = file_row["file_id"]
            path: str = file_row["path"]
            language: str = file_row["language"]
            file_symbols = symbols_by_file.get(fid, [])

            score, matched_syms, reasons = _score_file(
                path, file_symbols, keywords
            )

            if score > 0:
                results.append(
                    MatchedFile(
                        file_id=fid,
                        path=path,
                        language=language,
                        relevance_score=round(score, 2),
                        matched_symbols=matched_syms,
                        reason="; ".join(reasons) if reasons else "",
                    )
                )

        # Sort descending by score so the highest-relevance files are obvious
        results.sort(key=lambda m: m.relevance_score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Step 3 — pattern detection
    # ------------------------------------------------------------------

    def _detect_patterns(
        self,
        all_files: list[dict],
        matched_files: list[MatchedFile],
    ) -> list[DetectedPattern]:
        """Detect naming conventions in directories that contain matched files."""
        # Group all indexed files by their directory
        dir_to_paths: dict[str, list[str]] = {}
        for f in all_files:
            p = Path(f["path"])
            dir_str = str(p.parent)
            dir_to_paths.setdefault(dir_str, []).append(f["path"])

        # Directories that contain at least one matched file
        matched_dirs: set[str] = {str(Path(mf.path).parent) for mf in matched_files}

        detected: list[DetectedPattern] = []
        seen_patterns: set[str] = set()

        for directory in matched_dirs:
            siblings = dir_to_paths.get(directory, [])
            if len(siblings) < 2:
                continue

            # Collect base-names (without extension) to look for shared suffixes/prefixes
            basenames = [Path(p).stem for p in siblings]

            # Try common suffix patterns like *_handler, *_service, *_command, etc.
            for pattern_suffix in _find_common_suffixes(basenames):
                pattern_key = f"{directory}::{pattern_suffix}"
                if pattern_key in seen_patterns:
                    continue
                examples = [
                    Path(p).name
                    for p in siblings
                    if Path(p).stem.endswith(pattern_suffix)
                ]
                if len(examples) >= 2:
                    seen_patterns.add(pattern_key)
                    detected.append(
                        DetectedPattern(
                            name=f"{pattern_suffix.lstrip('_').replace('_', ' ').title()} pattern",
                            directory=directory,
                            examples=examples,
                            description=(
                                f"Files in {directory!r} follow the"
                                f" *{pattern_suffix}.py naming convention."
                            ),
                        )
                    )

        return detected


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_keywords(task: str) -> list[str]:
    """Tokenise, stop-filter, and stem a task description into keywords.

    Basic stemming: lowercase, strip trailing s / ed / ing.
    Returns a deduplicated ordered list (insertion order preserved).
    """
    # Split on whitespace and non-alphanumeric characters
    tokens = re.split(r"[\s\W]+", task.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token or len(token) < 2:
            continue
        if token in _STOP_WORDS:
            continue
        # Basic stemming: strip trailing "ing", "ed", trailing "s" (not -ss)
        stemmed = _stem(token)
        if stemmed in seen:
            continue
        seen.add(stemmed)
        keywords.append(stemmed)
    return keywords


def _stem(word: str) -> str:
    """Apply minimal suffix stripping to reduce words to a base form."""
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _score_file(
    path: str,
    symbols: list[dict],
    keywords: list[str],
) -> tuple[float, list[dict], list[str]]:
    """Return (score, matched_symbols, reason_parts) for a single file."""
    score = 0.0
    matched_symbols: list[dict] = []
    reasons: list[str] = []

    path_lower = path.lower()

    # Path hit scoring: check each keyword against the file path
    path_hits: list[str] = []
    for kw in keywords:
        if kw in path_lower:
            score += _FILE_PATH_WEIGHT
            path_hits.append(kw)
    if path_hits:
        reasons.append(f"path matches: {', '.join(path_hits)}")

    # Symbol scoring: name hits (weight 3) and docstring hits (weight 1)
    sym_name_hits: set[str] = set()
    doc_hits: set[str] = set()
    already_matched: set[int] = set()

    for sym in symbols:
        sym_name_lower = (sym.get("name") or "").lower()
        qualified_lower = (sym.get("qualified_name") or "").lower()
        docstring_lower = (sym.get("docstring") or "").lower()

        for kw in keywords:
            name_match = kw in sym_name_lower or kw in qualified_lower
            doc_match = kw in docstring_lower

            if name_match:
                score += _SYMBOL_NAME_WEIGHT
                sym_name_hits.add(kw)
                sym_id = sym.get("symbol_id", id(sym))
                if sym_id not in already_matched:
                    already_matched.add(sym_id)
                    matched_symbols.append(sym)
            elif doc_match:
                # Only add docstring score once per symbol per keyword
                score += _DOCSTRING_WEIGHT
                doc_hits.add(kw)

    if sym_name_hits:
        reasons.append(f"symbol names: {', '.join(sorted(sym_name_hits))}")
    if doc_hits:
        reasons.append(f"docstrings: {', '.join(sorted(doc_hits))}")

    return score, matched_symbols, reasons


def _find_common_suffixes(basenames: list[str]) -> list[str]:
    """Return suffixes (e.g. _handler) shared by two or more names in the list."""
    # Extract potential suffixes: anything after the first underscore that appears
    # in at least two basenames
    suffix_counts: dict[str, int] = {}
    for name in basenames:
        parts = name.split("_")
        if len(parts) > 1:
            # Build suffixes by joining the last 1..N parts
            for i in range(1, len(parts)):
                suffix = "_" + "_".join(parts[i:])
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1

    return [s for s, count in suffix_counts.items() if count >= 2]


def _suggest_tests(
    matched_files: list[MatchedFile],
    all_paths: set[str],
) -> list[str]:
    """Return paths of existing test files corresponding to matched source files."""
    suggestions: list[str] = []

    for mf in matched_files:
        stem = Path(mf.path).stem
        for candidate in all_paths:
            c_lower = candidate.lower()
            if f"test_{stem}" in c_lower or f"{stem}_test" in c_lower:
                if candidate not in suggestions:
                    suggestions.append(candidate)

    return suggestions
