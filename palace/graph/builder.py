"""Graph builder — wires parsing output into the storage layer."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from palace.core.models import EdgeType
from palace.parsing.extractors.base import FileExtraction
from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import EdgeRecord, FileRecord, ImportRecord, SymbolRecord


@dataclass
class BuildStats:
    """Summary of a completed graph build operation."""

    # Phase 1 — parsing and graph construction
    files: int = 0
    symbols: int = 0
    edges: int = 0
    imports_total: int = 0
    imports_resolved: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    # Phase 2 — None means the phase was skipped or not yet run
    commits: int | None = None
    embeddings: int | None = None
    domains: int | None = None


class GraphBuilder:
    """Translates parsed FileExtractions into a persistent symbol graph.

    Three-phase algorithm:
        Phase 1 — files and symbols inserted into the store.
        Phase 2 — raw imports stored and resolved to file_ids where possible.
        Phase 3 — import edges created for every resolved import.
    """

    def __init__(self, store: DuckDBStore) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, extractions: list[FileExtraction], root: Path) -> BuildStats:
        """Build the graph from a list of FileExtractions rooted at root.

        Returns a BuildStats instance summarising what was stored.
        """
        started = time.monotonic()
        stats = BuildStats()

        # Collect all errors from the extraction phase
        for extraction in extractions:
            stats.errors.extend(extraction.errors)

        # file_id keyed by the file's string path (relative or absolute)
        file_id_map: dict[str, int] = {}

        # Phase 1 — files and symbols
        self._phase_insert_files_and_symbols(extractions, root, file_id_map, stats)

        # Phase 2 — import storage and resolution
        import_edges = self._phase_insert_imports(extractions, root, file_id_map, stats)

        # Phase 3 — create edges for resolved imports
        self._phase_create_edges(import_edges, stats)

        stats.duration_seconds = time.monotonic() - started
        return stats

    # ------------------------------------------------------------------
    # Phase 1: files and symbols
    # ------------------------------------------------------------------

    def _phase_insert_files_and_symbols(
        self,
        extractions: list[FileExtraction],
        root: Path,
        file_id_map: dict[str, int],
        stats: BuildStats,
    ) -> None:
        """Insert all files then their symbols, building file_id_map in place."""
        for extraction in extractions:
            path_str = str(extraction.path)
            file_hash = self._hash_file(extraction.path)
            size_bytes = self._file_size(extraction.path)
            line_count = self._line_count(extraction.path)

            record = FileRecord(
                path=path_str,
                language=extraction.language,
                size_bytes=size_bytes,
                line_count=line_count,
                hash=file_hash,
            )
            file_id = self.store.upsert_file(record)
            file_id_map[path_str] = file_id
            stats.files += 1

        # Insert symbols in a second pass so file_id_map is fully populated
        for extraction in extractions:
            file_id = file_id_map[str(extraction.path)]
            # Map parent_name -> symbol_id within this file
            local_symbol_ids: dict[str, int] = {}

            for sym in extraction.symbols:
                parent_id: int | None = None
                if sym.parent_name is not None:
                    parent_id = local_symbol_ids.get(sym.parent_name)

                sym_record = SymbolRecord(
                    file_id=file_id,
                    name=sym.name,
                    qualified_name=sym.qualified_name,
                    kind=str(sym.kind),
                    line_start=sym.line_start,
                    line_end=sym.line_end,
                    col_start=sym.col_start,
                    col_end=sym.col_end,
                    parent_id=parent_id,
                    signature=sym.signature,
                    docstring=sym.docstring,
                    is_exported=sym.is_exported,
                    metadata=sym.metadata if sym.metadata else None,
                )
                symbol_id = self.store.upsert_symbol(sym_record)
                local_symbol_ids[sym.name] = symbol_id
                stats.symbols += 1

    # ------------------------------------------------------------------
    # Phase 2: imports
    # ------------------------------------------------------------------

    def _phase_insert_imports(
        self,
        extractions: list[FileExtraction],
        root: Path,
        file_id_map: dict[str, int],
        stats: BuildStats,
    ) -> list[tuple[int, int]]:
        """Store all imports, resolve them to file_ids, return (source_id, target_id) pairs."""
        edges: list[tuple[int, int]] = []

        for extraction in extractions:
            file_id = file_id_map[str(extraction.path)]

            for imp in extraction.imports:
                imported_names_str: str | None = (
                    ",".join(imp.imported_names) if imp.imported_names else None
                )
                import_record = ImportRecord(
                    file_id=file_id,
                    module_path=imp.module_path,
                    line_number=imp.line_number,
                    imported_names=imported_names_str,
                    alias=imp.alias,
                    is_relative=imp.is_relative,
                )
                import_id = self.store.upsert_import(import_record)
                stats.imports_total += 1

                # Attempt resolution
                resolved_path = self._resolve_import(
                    imp.module_path,
                    imp.is_relative,
                    extraction.path,
                    extraction.language,
                    root,
                )

                if resolved_path is not None:
                    resolved_id = file_id_map.get(str(resolved_path))
                    if resolved_id is not None:
                        self.store.resolve_import(import_id, resolved_id)
                        edges.append((file_id, resolved_id))
                        stats.imports_resolved += 1

        return edges

    # ------------------------------------------------------------------
    # Phase 3: edges
    # ------------------------------------------------------------------

    def _phase_create_edges(
        self,
        import_edges: list[tuple[int, int]],
        stats: BuildStats,
    ) -> None:
        """Create deduplicated IMPORTS edges for each resolved import pair."""
        seen: set[tuple[int, int]] = set()
        for source_id, target_id in import_edges:
            key = (source_id, target_id)
            if key in seen:
                continue
            seen.add(key)
            self.store.upsert_edge(
                EdgeRecord(
                    source_file_id=source_id,
                    edge_type=str(EdgeType.IMPORTS),
                    target_file_id=target_id,
                )
            )
            stats.edges += 1

    # ------------------------------------------------------------------
    # Import resolution
    # ------------------------------------------------------------------

    def _resolve_import(
        self,
        module_path: str,
        is_relative: bool,
        source_file: Path,
        language: str,
        root: Path,
    ) -> Path | None:
        """Try to map an import statement to a concrete file path under root.

        Returns an absolute Path if resolved, None if unresolvable (external dep).
        """
        if language == "python":
            return self._resolve_python(module_path, is_relative, source_file, root)
        if language in ("typescript", "javascript"):
            return self._resolve_typescript(module_path, source_file, root)
        if language == "go":
            return self._resolve_go(module_path, root)
        if language == "java":
            return self._resolve_java(module_path, root)
        if language == "cpp":
            return self._resolve_cpp(module_path, is_relative, source_file, root)
        return None

    def _resolve_python(
        self,
        module_path: str,
        is_relative: bool,
        source_file: Path,
        root: Path,
    ) -> Path | None:
        """Resolve Python imports using dotted-module-to-path conventions."""
        if is_relative:
            # Relative import: resolve from the directory of the importing file
            base = source_file.parent
            # Strip leading dots — importlib semantics: one dot = current package
            stripped = module_path.lstrip(".")
            if not stripped:
                # "from . import X" — the package directory itself
                candidates = [base / "__init__.py"]
            else:
                parts = stripped.split(".")
                candidates = [
                    base.joinpath(*parts).with_suffix(".py"),
                    base.joinpath(*parts, "__init__.py"),
                ]
        else:
            parts = module_path.split(".")
            candidates = [
                root.joinpath(*parts).with_suffix(".py"),
                root.joinpath(*parts, "__init__.py"),
            ]

        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def _resolve_typescript(
        self,
        module_path: str,
        source_file: Path,
        root: Path,
    ) -> Path | None:
        """Resolve TypeScript/JavaScript relative and index imports."""
        # Only resolve relative imports (starting with . or ..)
        if not module_path.startswith("."):
            return None

        base = source_file.parent
        target = (base / module_path).resolve()

        candidates = [
            target.with_suffix(".ts"),
            target.with_suffix(".tsx"),
            target / "index.ts",
            target.with_suffix(".js"),
            target.with_suffix(".jsx"),
            target / "index.js",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _resolve_go(self, module_path: str, root: Path) -> Path | None:
        """Resolve Go imports by matching package directories under root."""
        # Go module paths: last segment is often a directory name
        parts = module_path.split("/")
        # Try progressively shorter suffixes of the import path
        for depth in range(len(parts), 0, -1):
            sub = Path(*parts[-depth:])
            candidate_dir = root / sub
            if candidate_dir.is_dir():
                # Return the first .go file found in that directory
                for go_file in sorted(candidate_dir.glob("*.go")):
                    return go_file
        return None

    def _resolve_cpp(
        self,
        module_path: str,
        is_relative: bool,
        source_file: Path,
        root: Path,
    ) -> Path | None:
        """Resolve C++ #include directives to concrete file paths.

        Local includes (#include "foo.h") are searched relative to the
        including file's directory first, then relative to the project root.
        System includes (#include <iostream>) are unresolvable externals and
        always return None.
        """
        if not is_relative:
            # System include — cannot resolve to a project file
            return None

        # Search relative to source file directory first, then project root
        candidates = [
            source_file.parent / module_path,
            root / module_path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def _resolve_java(self, module_path: str, root: Path) -> Path | None:
        """Resolve Java fully-qualified class imports to .java file paths."""
        parts = module_path.split(".")
        candidate = root.joinpath(*parts).with_suffix(".java")
        if candidate.exists():
            return candidate.resolve()
        return None

    # ------------------------------------------------------------------
    # File stat helpers — best-effort, return 0/empty on error
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Return SHA-256 hex digest of the file contents."""
        try:
            data = path.read_bytes()
            return hashlib.sha256(data).hexdigest()
        except OSError:
            return ""

    @staticmethod
    def _file_size(path: Path) -> int:
        """Return file size in bytes, or 0 on error."""
        try:
            return path.stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _line_count(path: Path) -> int:
        """Return number of lines in the file, or 0 on error."""
        try:
            text = path.read_bytes()
            return text.count(b"\n") + (1 if text and not text.endswith(b"\n") else 0)
        except OSError:
            return 0
