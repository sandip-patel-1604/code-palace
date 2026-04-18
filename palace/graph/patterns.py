"""Cross-cutting concern and naming convention pattern detectors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# Cross-cutting concern patterns
# ---------------------------------------------------------------------------

CROSS_CUTTING_PATTERNS: dict[str, list[str]] = {
    "logging": [r"^log(ger)?$", r"^(debug|info|warn|warning|error|critical)$", r"log_\w+"],
    "error_handling": [r"handle_error", r"on_error", r"error_handler", r"exception_handler"],
    "auth": [r"auth(enticate|orize)?", r"require_\w*(auth|login|permission)", r"check_permission"],
    "validation": [r"validate_\w+", r"is_valid_\w+", r"_validator$"],
    "caching": [r"cache_\w+", r"memoize", r"lru_cache", r"@cached"],
}

# Compile regexes once, case-insensitive
_COMPILED_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    kind: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for kind, patterns in CROSS_CUTTING_PATTERNS.items()
}

ConcernKind = Literal["logging", "error_handling", "auth", "validation", "caching"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CrossCuttingConcern:
    """A cross-cutting concern identified in the codebase."""

    kind: ConcernKind
    confidence: float
    representative_symbols: list[dict] = field(default_factory=list)
    call_site_count: int = 0
    affected_files: list[str] = field(default_factory=list)


@dataclass
class NamingConvention:
    """A naming pattern discovered among sibling files in the same directory."""

    name: str
    directory: str
    examples: list[str] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _find_common_suffixes(basenames: list[str]) -> list[str]:
    """Return suffixes (e.g. _handler) shared by two or more names in the list."""
    suffix_counts: dict[str, int] = {}
    for name in basenames:
        parts = name.split("_")
        if len(parts) > 1:
            # Build suffixes by joining the last 1..N parts
            for i in range(1, len(parts)):
                suffix = "_" + "_".join(parts[i:])
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1

    return [s for s, count in suffix_counts.items() if count >= 2]


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class PatternDetector:
    """Detects cross-cutting concerns and naming conventions in the codebase."""

    def __init__(self, store) -> None:
        self.store = store

    def detect_cross_cutting(self) -> list[CrossCuttingConcern]:
        """Detect cross-cutting concerns by analysing symbols and CALLS edges.

        Single-pass: fetches all symbols once and all CALLS edges once.
        Returns a concern only when call sites span >= 3 distinct directories.
        """
        # FM-3: each called exactly once
        all_symbols = self.store.get_symbols()
        all_edges = self.store.get_edges(edge_type="CALLS")

        # FM-2: empty store → return []
        if not all_symbols:
            return []

        # Build lookup: symbol_id -> symbol dict
        sym_by_id: dict[int, dict] = {s["symbol_id"]: s for s in all_symbols}

        # Build lookup: file_id -> path (from symbols)
        # We need file paths to determine directory of each call-site.
        # Use symbol's file_id to determine directory.
        file_id_to_syms: dict[int, list[dict]] = {}
        for sym in all_symbols:
            file_id_to_syms.setdefault(sym["file_id"], []).append(sym)

        # For each concern kind, find matching symbols and count inbound CALLS
        # from distinct directories.
        # Build: target_symbol_id -> list of source_file_ids (from edges)
        target_to_sources: dict[int, list[int]] = {}
        for edge in all_edges:
            tsid = edge.get("target_symbol_id")
            sfid = edge.get("source_file_id")
            if tsid is not None and sfid is not None:
                target_to_sources.setdefault(int(tsid), []).append(int(sfid))

        # Build file_id -> directory mapping from symbols' paths
        # We need actual file paths — the store has get_all_files, but we should
        # avoid calling it to stay single-pass. Use symbols' file_id combined
        # with edges' source_file_id.
        # Since we only have file_id in symbols, we derive directory
        # from the symbol's qualified_name or use file_ids directly.
        # Actually, to get path we need to call get_all_files or use the edges'
        # source_file_id metadata. Let's call get_all_files to build the map.
        # This is acceptable: it is called once, not in a per-symbol loop.
        all_files = self.store.get_all_files()
        file_id_to_path: dict[int, str] = {f["file_id"]: f["path"] for f in all_files}

        concerns: list[CrossCuttingConcern] = []

        for kind, compiled in _COMPILED_PATTERNS.items():
            matching_symbols: list[dict] = []
            for sym in all_symbols:
                sym_name = sym.get("name") or ""
                try:
                    if any(pat.search(sym_name) for pat in compiled):
                        matching_symbols.append(sym)
                except (re.error, TypeError):
                    # FM-5: unicode or bad names must not crash
                    pass

            if not matching_symbols:
                continue

            # Collect call sites: source file_ids of all inbound CALLS to
            # any matching symbol.
            caller_dirs: set[str] = set()
            call_site_count = 0
            affected_file_ids: set[int] = set()

            for sym in matching_symbols:
                sym_id = sym["symbol_id"]
                sources = target_to_sources.get(sym_id, [])
                for src_file_id in sources:
                    call_site_count += 1
                    path = file_id_to_path.get(src_file_id, "")
                    caller_dirs.add(str(Path(path).parent) if path else "")
                    affected_file_ids.add(src_file_id)

            # FM-1: require >= 3 distinct caller directories
            if len(caller_dirs) < 3:
                continue

            affected_files = [
                file_id_to_path[fid]
                for fid in affected_file_ids
                if fid in file_id_to_path
            ]

            # Confidence: simple heuristic based on directory spread
            confidence = min(1.0, len(caller_dirs) / 10.0)

            concerns.append(CrossCuttingConcern(
                kind=kind,  # type: ignore[arg-type]
                confidence=confidence,
                representative_symbols=matching_symbols[:5],
                call_site_count=call_site_count,
                affected_files=sorted(affected_files),
            ))

        return concerns

    def detect_naming_conventions(
        self,
        all_files: list[dict],
        matched_files: list,
    ) -> list[NamingConvention]:
        """Detect naming conventions in directories containing matched files.

        Ported from StructuralPlanner._detect_patterns unchanged in behaviour.
        """
        # Group all indexed files by their directory
        dir_to_paths: dict[str, list[str]] = {}
        for f in all_files:
            p = Path(f["path"])
            dir_str = str(p.parent)
            dir_to_paths.setdefault(dir_str, []).append(f["path"])

        # Directories that contain at least one matched file
        # matched_files may be MatchedFile objects or dicts
        matched_dirs: set[str] = set()
        for mf in matched_files:
            if hasattr(mf, "path"):
                path = mf.path
            else:
                path = mf.get("path", "")
            matched_dirs.add(str(Path(path).parent))

        detected: list[NamingConvention] = []
        seen_patterns: set[str] = set()

        for directory in matched_dirs:
            siblings = dir_to_paths.get(directory, [])
            if len(siblings) < 2:
                continue

            # Collect base-names (without extension) to look for shared suffixes
            basenames = [Path(p).stem for p in siblings]

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
                        NamingConvention(
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
