---
project: code-palace
archetype: single-package Python CLI tool with storage and parsing engine
languages: [python]
frameworks: [typer, rich, duckdb, tree-sitter]
last_scanned: 2026-04-15
files_sampled: 28
total_source_files: 30
confidence_must: 0.97
confidence_should: 0.84
must_rules: 18
should_rules: 9
may_rules: 4
scanned_by: project-style-guard (claude-sonnet-4-6) — full 28-file pass
---

# Code Palace — Style Guide

> **Law**: Every Claude Code session reads this before touching any code file.
> MUST rules are hard constraints — rewrite violations before presenting code.
> SHOULD rules should be followed unless a concrete tradeoff is documented.

---

## Project Fingerprint

| Attribute         | Value                                                     |
|-------------------|-----------------------------------------------------------|
| Language          | Python 3.10 (target), 3.12 runtime                       |
| Entry point       | `palace/cli/main.py` → `palace` console script            |
| CLI framework     | Typer 0.15 with `rich_markup_mode="rich"`                 |
| Output            | Rich Console, Panel, Table, Tree, Progress                |
| Storage           | DuckDB 1.1 via `DuckDBPyConnection`                       |
| Parsing           | tree-sitter via `tree_sitter_language_pack`               |
| Linter            | Ruff (E, F, I, N, UP, RUF); line-length=100               |
| Type checker      | mypy strict=true, python_version=3.10                     |
| Test framework    | pytest 8, `typer.testing.CliRunner`                       |
| Build             | Hatchling                                                 |

---

## 1. Module Header & Future Import

### [MUST] Every `.py` file has a module docstring then `from __future__ import annotations`
Confidence: 1.0 — observed in all 28 sampled files, zero exceptions.

Order is always: docstring → blank line → `from __future__ import annotations` → blank line → imports.

```python
# CORRECT — palace/core/models.py
"""Core domain models and enumerations for Code Palace."""

from __future__ import annotations

from enum import StrEnum
```

```python
# CORRECT — palace/parsing/engine.py
"""Parsing engine — orchestrates file discovery and multi-language extraction."""

from __future__ import annotations

import fnmatch
from pathlib import Path
```

**Counter-example** (never):
```python
from __future__ import annotations  # missing docstring before future import

"""Module docstring."""  # docstring after the future import
```

---

## 2. Import Ordering and Style

### [MUST] Imports: stdlib → third-party → local, each group separated by a single blank line
Confidence: 1.0 — every file with mixed imports follows this three-group structure.

```python
# stdlib
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# third-party
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.tree import Tree

# local (palace-internal)
from palace.core.config import PalaceConfig
from palace.core.palace import Palace
```

### [MUST] Use `from X import Y` form for multi-name imports from the same module
Confidence: 0.98 — no bare `import rich` style seen; all rich imports are `from rich.X import Y`.

### [MUST] Late imports go inside functions with a `# noqa: E402` comment at module level
Confidence: 0.95 — only seen in `cli/main.py` for command registration:

```python
# Register commands
from palace.cli.commands.init import init_command  # noqa: E402
from palace.cli.commands.symbols import symbols_command  # noqa: E402
```

Late function-body imports (no noqa needed) are used in `palace/core/palace.py` and `cli/commands/init.py` to avoid circular imports:

```python
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()
```

---

## 3. Naming Conventions

### [MUST] Classes: PascalCase
Confidence: 1.0

Real examples from the codebase:
`PalaceConfig`, `Palace`, `DuckDBStore`, `ParsingEngine`, `GraphBuilder`, `StructuralPlanner`,
`SymbolKind`, `EdgeType`, `GraphLayer`, `FileRecord`, `SymbolRecord`, `EdgeRecord`, `ImportRecord`,
`Store`, `Extractor`, `PythonExtractor`, `GoExtractor`, `TypeScriptExtractor`, `JavaExtractor`,
`CppExtractor`, `BuildStats`, `MatchedFile`, `DetectedPattern`, `PlanResult`, `FileExtraction`,
`SymbolInfo`, `ImportInfo`.

### [MUST] Functions and methods: snake_case
Confidence: 1.0

Examples: `detect_languages`, `initialize_schema`, `upsert_file`, `get_symbols`,
`parse_all`, `version_callback`, `_run_init`, `_print_summary`, `_resolve_import`.

### [MUST] Module-level constants: SCREAMING_SNAKE_CASE
Confidence: 1.0

Examples: `PALACE_DIR_NAME`, `CONFIG_FILE_NAME`, `DB_FILE_NAME`, `DEFAULT_EXCLUDE_PATTERNS`,
`EXTENSION_TO_LANGUAGE`, `SUPPORTED_LANGUAGES`, `_MAX_FILE_BYTES`, `_BINARY_CHECK_BYTES`,
`_MAX_DEPTH`, `_STOP_WORDS`, `_SYMBOL_NAME_WEIGHT`, `_FILE_PATH_WEIGHT`, `_DOCSTRING_WEIGHT`.

Private module-level constants use leading underscore: `_MAX_DEPTH`, `_STOP_WORDS`.

### [MUST] Private/internal helpers: leading single underscore `_name`
Confidence: 0.98

Pattern is consistent: all module-level functions not meant as public API get `_` prefix.
Examples: `_is_binary`, `_matches_exclude`, `_node_text`, `_get_docstring`, `_build_signature`,
`_extract_imports`, `_extract_symbols`, `_now_iso`, `_short_path`, `_render_tree`.

Private class attributes: `self._con` (DuckDBStore), `self._parser` (extractors),
`self._extractors` (ParsingEngine), `self.store` is public (no underscore) by design.

### [MUST] File names: snake_case.py
Confidence: 1.0

All source files: `config.py`, `models.py`, `palace.py`, `main.py`, `init.py`, `symbols.py`,
`deps.py`, `plan.py`, `store.py`, `duckdb_store.py`, `engine.py`, `base.py`, `python.py`,
`go.py`, `typescript.py`, `java.py`, `cpp.py`, `builder.py`, `traversal.py`, `planner.py`,
`layers.py`.

### [MUST] Test files: `test_<subject>.py` under `tests/unit/` or `tests/integration/`
Confidence: 1.0

---

## 4. Type Annotations

### [MUST] All public function signatures are fully annotated — parameters and return type
Confidence: 1.0 — mypy strict=true enforces this.

```python
def upsert_file(self, record: FileRecord) -> int: ...
def get_symbols(
    self,
    file_id: int | None = None,
    kind: str | None = None,
    name_pattern: str | None = None,
) -> list[dict]: ...
def parse_all(self, root: Path, exclude: list[str] | None = None) -> list[FileExtraction]: ...
```

### [MUST] Use lowercase `dict`, `list`, `tuple`, `set` for generics — not `Dict`, `List`, `Tuple`
Confidence: 1.0 — Python 3.9+ style, enforced by Ruff UP rules.

```python
# CORRECT
counts: dict[str, int] = {}
results: list[FileExtraction] = []
working: set[int] = set()
edges: list[tuple[int, int]] = []

# WRONG — triggers Ruff UP006/UP007
from typing import Dict, List, Tuple
counts: Dict[str, int] = {}
```

### [MUST] Use `Optional[X]` (with `# noqa: UP007`) only for Typer command parameters
Confidence: 0.95 — the Typer framework requires `Optional` for optional CLI arguments.

```python
# Typer parameters — MUST use Optional with noqa
def symbols_command(
    kind: Optional[str] = typer.Option(None, "--kind", "-k", ...),  # noqa: UP007
    file: Optional[str] = typer.Option(None, "--file", "-f", ...),  # noqa: UP007
) -> None: ...

# All other contexts — MUST use X | None
def get_file_by_path(self, path: str) -> dict | None: ...
signature: str | None = None
parent_id: int | None = None
```

### [MUST] `typing.Callable` is used for callback type hints (not `collections.abc.Callable` yet)
Confidence: 0.95

```python
from typing import Callable
progress_callback: Callable[[int, int], None] | None = None
```

### [SHOULD] `typing.Any` is used with `list[Any]` or `params: list[Any]` for dynamic SQL params
Confidence: 0.90

```python
from typing import Any
params: list[Any] = []
conditions: list[str] = []
```

---

## 5. Dataclasses

### [MUST] Use `@dataclass` for all plain data records — not `NamedTuple`, not `TypedDict`
Confidence: 1.0 — used for `FileRecord`, `SymbolRecord`, `EdgeRecord`, `ImportRecord`,
`PalaceConfig`, `BuildStats`, `MatchedFile`, `DetectedPattern`, `PlanResult`, `SymbolInfo`,
`ImportInfo`, `FileExtraction`.

```python
@dataclass
class FileRecord:
    """Input record for inserting/upserting a source file."""

    path: str
    language: str
    size_bytes: int
    line_count: int
    hash: str
```

### [MUST] Mutable defaults use `field(default_factory=...)`, never direct assignment
Confidence: 1.0

```python
@dataclass
class PalaceConfig:
    languages: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)

@dataclass
class BuildStats:
    errors: list[str] = field(default_factory=list)
```

### [SHOULD] Required fields come before optional (defaulted) fields in dataclass definitions
Confidence: 0.95 — consistent across all dataclasses.

---

## 6. Protocols

### [MUST] Interfaces are defined as `Protocol` + `@runtime_checkable` with `...` stubs
Confidence: 1.0 — `Store` in `store.py`, `Extractor` in `parsing/extractors/base.py`.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Store(Protocol):
    """Protocol defining the storage interface for Code Palace."""

    def initialize_schema(self) -> None:
        """Create all tables, sequences, and indexes.  Must be idempotent."""
        ...

    def upsert_file(self, record: FileRecord) -> int:
        """Insert or update a file row.  Returns the file_id."""
        ...
```

```python
@runtime_checkable
class Extractor(Protocol):
    """Protocol for language-specific AST symbol extractors."""

    language: str
    extensions: list[str]

    def extract(self, source: bytes, file_path: Path) -> FileExtraction:
        """Parse source bytes and return all symbols and imports found."""
        ...
```

### [MUST] Concrete extractor classes match the Extractor Protocol shape: `language: str = "x"`, `extensions: list[str] = [...]`, `__init__` calling `get_parser(lang)`, and `extract()` method
Confidence: 1.0 — verified in PythonExtractor, GoExtractor, TypeScriptExtractor.

```python
class PythonExtractor:
    """Extracts symbols and imports from Python source files."""

    language: str = "python"
    extensions: list[str] = [".py", ".pyi"]

    def __init__(self) -> None:
        self._parser = get_parser("python")

    def extract(self, source: bytes, file_path: Path) -> FileExtraction:
        """Parse source bytes and return all symbols and imports found."""
        result = FileExtraction(path=file_path, language=self.language)
        if not source.strip():
            return result
        try:
            tree = self._parser.parse(source)
            root = tree.root_node
            if root.has_error:
                result.errors.append("Syntax errors detected in source")
            result.symbols = _extract_symbols(root)
            result.imports = _extract_imports(root)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Parse error: {exc}")
        return result
```

---

## 7. Enumerations

### [MUST] String enumerations use `StrEnum`, never `str, Enum` or `Enum` alone
Confidence: 1.0 — `SymbolKind`, `EdgeType`, `GraphLayer` all use `StrEnum`.

```python
from enum import StrEnum

class SymbolKind(StrEnum):
    """Types of symbols extracted from source code ASTs."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
```

**Counter-example** (never):
```python
from enum import Enum

class SymbolKind(str, Enum):  # wrong — use StrEnum
    FUNCTION = "function"
```

---

## 8. Docstrings

### [MUST] Module docstring: short imperative phrase, ends without a period
Confidence: 0.97 — consistent across all 28 files.

Pattern: `"""<Module> — <purpose>."""` or `"""<Short noun phrase> for Code Palace."""`

Real examples:
```python
"""Palace CLI — the main entry point."""
"""Core domain models and enumerations for Code Palace."""
"""DuckDB-backed implementation of the Store protocol."""
"""Parsing engine — orchestrates file discovery and multi-language extraction."""
"""Graph builder — wires parsing output into the storage layer."""
"""High-level Palace orchestrator — parsing, graph building, and storage."""
"""Structural planning engine — pure graph analysis, no LLM required."""
"""Graph layer taxonomy for Code Palace analysis layers."""
```

### [MUST] Class docstrings: one sentence describing what the class *is*, not what it *does*
Confidence: 0.97

```python
class PalaceConfig:
    """Configuration for a Palace instance rooted at a specific directory."""

class DuckDBStore:
    """Persistent symbol-graph storage backed by DuckDB."""

class GraphBuilder:
    """Translates parsed FileExtractions into a persistent symbol graph."""
```

For classes with a multi-phase algorithm, a second sentence documents the lifecycle:
```python
class Palace:
    """High-level API orchestrating parsing, graph building, and storage.

    Lifecycle: create → init() (or open()) → use → close().
    """
```

### [MUST] Public method docstrings: short imperative verb phrase, explains contract not implementation
Confidence: 0.97

Pattern: `"""Verb phrase.  Returns/Raises/Requires <key contract>."""`
(Two spaces before inline suffix clause — see §8.4 below.)

```python
def upsert_file(self, record: FileRecord) -> int:
    """Insert or update a file row.  Returns the file_id."""

def get_dependencies(self, file_id: int, transitive: bool = False) -> list[dict]:
    """Return files that file_id depends on (its imports).

    Non-transitive: direct edges only (depth 1).
    Transitive: recursive walk downward; each result includes 'depth'.
    """
```

### [SHOULD] Two spaces between the one-liner and an inline suffix clause in method docstrings
Confidence: 0.82 — observed consistently in `store.py` and `duckdb_store.py`.

```python
"""Insert or update a file row.  Returns the file_id."""
#                              ^^  two spaces before "Returns"
```

### [SHOULD] Multi-line docstrings: opening on first line, blank line before extended content
Confidence: 0.85

```python
def plan(self, task: str, scope: str | None = None) -> PlanResult:
    """Generate a structural change plan for the given task description.

    Five-step pipeline:
    1. Keyword extraction
    2. Symbol and path matching with relevance scoring
    ...
    """
```

### [MUST] Private helper functions: include a one-line docstring explaining WHY, not WHAT
Confidence: 0.95

```python
def _is_binary(data: bytes) -> bool:
    """Return True if the byte sample looks like a binary file.

    Uses two signals: non-decodable UTF-8 sequences, or a high ratio of raw
    bytes that cannot appear in human-readable source code.
    """
```

---

## 9. Error Handling

### [MUST] CLI commands: exit with `raise typer.Exit(1)` for failures — never `sys.exit()`
Confidence: 1.0 — pattern in every command; `sys.exit` not present anywhere.

```python
if config is None:
    console.print(
        "[red]Error:[/red] No palace found in this directory or any parent.\n"
        "Run [bold]palace init[/bold] first."
    )
    raise typer.Exit(1)
```

### [MUST] Extractor `extract()` methods: catch `Exception` with `# noqa: BLE001` — never let parse errors propagate
Confidence: 1.0 — identical pattern in all 5 extractors.

```python
try:
    tree = self._parser.parse(source)
    ...
except Exception as exc:  # noqa: BLE001
    result.errors.append(f"Parse error: {exc}")
```

### [MUST] DuckDB queries that must return a row: use `assert row is not None` after `fetchone()`
Confidence: 0.95 — used in `upsert_file`, `upsert_symbol`, `upsert_import`.

```python
row = self._con.execute("... RETURNING file_id", [...]).fetchone()
assert row is not None
return int(row[0])
```

### [SHOULD] File I/O helpers: catch `OSError` silently, return empty/zero/`""` sentinel
Confidence: 0.90 — pattern in `_hash_file`, `_file_size`, `_line_count`, `parse_all`.

```python
@staticmethod
def _hash_file(path: Path) -> str:
    try:
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()
    except OSError:
        return ""
```

### [SHOULD] Protocol stubs use bare `...` (not `pass`, not `raise NotImplementedError`)
Confidence: 0.95

```python
def initialize_schema(self) -> None:
    """Create all tables.  Must be idempotent."""
    ...  # correct — Ellipsis in Protocol stub
```

---

## 10. Rich Console Output Patterns

### [MUST] CLI files instantiate `console = Console()` at module level as a bare singleton
Confidence: 1.0 — every command module (`init.py`, `symbols.py`, `deps.py`, `plan.py`).

```python
from rich.console import Console

console = Console()
```

### [MUST] Error messages use `[red]Error:[/red]` markup prefix; warnings use `[yellow]Warning:[/yellow]`
Confidence: 1.0

```python
console.print(f"[red]Error:[/red] path does not exist: {root}")
console.print(
    f"[yellow]Warning:[/yellow] {root} already has a .palace/ directory.\n"
    "Use [bold]--force[/bold] to re-index."
)
```

### [MUST] JSON output uses `typer.echo(json.dumps(..., indent=2))` — not `console.print()` — to avoid Rich line-wrapping
Confidence: 1.0 — seen in `symbols.py` and `deps.py`.

```python
typer.echo(json.dumps(clean, indent=2))
```

### [SHOULD] Summary panels use `Panel(content, title="[bold green]...[/bold green]", expand=False)`
Confidence: 0.85

```python
console.print(
    Panel(
        panel_content,
        title="[bold green]Palace Init[/bold green]",
        expand=False,
    )
)
```

### [SHOULD] Progress bars use `Progress(TextColumn, BarColumn, MofNCompleteColumn, transient=True)`
Confidence: 0.90 — exact pattern from `init.py`.

```python
with Progress(
    TextColumn("[bold blue]{task.description}"),
    BarColumn(),
    MofNCompleteColumn(),
    console=console,
    transient=True,
) as progress:
    task = progress.add_task("Parsing…", total=None)
```

---

## 11. DuckDB Query Patterns

### [MUST] Always use positional `?` parameters — never f-string interpolation for user values
Confidence: 1.0 — all data parameters use `?` lists; the only f-strings embed constants like `_MAX_DEPTH`.

```python
# CORRECT — parameterised
self._con.execute("SELECT * FROM files WHERE path = ?", [path]).fetchone()

# ACCEPTABLE — constant embedded via f-string (not user data)
f"AND d.depth < {_MAX_DEPTH}"

# WRONG — never interpolate user data
f"WHERE path = '{path}'"  # SQL injection risk
```

### [MUST] Schema DDL is written as multi-line strings inside `stmts` list, executed in a loop
Confidence: 1.0 — exact pattern in `initialize_schema`.

```python
stmts = [
    "CREATE SEQUENCE IF NOT EXISTS file_id_seq START 1",
    """
    CREATE TABLE IF NOT EXISTS files (
        file_id  INTEGER PRIMARY KEY DEFAULT nextval('file_id_seq'),
        ...
    )
    """,
]
for stmt in stmts:
    self._con.execute(stmt)
```

### [MUST] Transitive queries use `WITH RECURSIVE … UNION ALL` CTEs with a `depth < _MAX_DEPTH` guard
Confidence: 1.0 — pattern in `get_dependencies` and `get_dependents`.

### [SHOULD] Dynamic WHERE clause construction: build `conditions: list[str]` and `params: list[Any]`, join with `AND`
Confidence: 0.95

```python
conditions: list[str] = []
params: list[Any] = []
if file_id is not None:
    conditions.append("file_id = ?")
    params.append(file_id)
where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
rows = self._con.execute(
    f"SELECT * FROM symbols {where} ORDER BY symbol_id",  # noqa: S608
    params,
).fetchall()
```

---

## 12. Tree-Sitter Extractor Patterns

### [MUST] Extractor helper functions that accept tree-sitter nodes are untyped: `def _fn(node) -> str:`
Reason: `tree_sitter` nodes have no stub types in the current language pack; typing them as `Any` triggers noise.
Pattern: always annotate with `# type: ignore[no-untyped-def]` on the function signature.
Confidence: 1.0 — identical in Python, Go, TypeScript, Java, C++ extractors.

```python
def _node_text(node) -> str:  # type: ignore[no-untyped-def]
    """Decode a tree-sitter node's byte text to a UTF-8 string."""
    return node.text.decode("utf-8") if node.text else ""
```

### [MUST] The `_node_text(node) -> str` helper is duplicated in each extractor module — do not consolidate into base
Reason: each extractor is a standalone module; sharing would create a cross-extractor dependency.
Confidence: 1.0 — seen in all 5 extractors.

### [MUST] Parser is obtained via `get_parser("language_name")` from `tree_sitter_language_pack`
Confidence: 1.0

### [SHOULD] Guard `extract()` against empty source before parsing: `if not source.strip(): return result`
Confidence: 1.0

---

## 13. Section Separators in Source Files

### [SHOULD] Group logically related methods with `# ------------------------------------------------------------------` banners
Confidence: 0.92 — used consistently in `DuckDBStore`, `GraphBuilder`, `Palace`, `StructuralPlanner`.

Pattern: 66-dash line, followed by `# Section Name`, followed by another 66-dash line:

```python
# ------------------------------------------------------------------
# File operations
# ------------------------------------------------------------------

def upsert_file(self, record: FileRecord) -> int: ...
```

### [SHOULD] Module-level section banners for grouped helpers use `# ---------------------------------------------------------------------------`
Confidence: 0.85 — used in `planner.py`, test files.

```python
# ---------------------------------------------------------------------------
# Stop words — common English words...
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset(...)
```

---

## 14. Test Patterns

### [MUST] Test classes: `TestXxx` (PascalCase noun), test methods: `test_yyy_action_result` (snake_case)
Confidence: 1.0

```python
class TestFileCRUD:
    def test_insert_and_retrieve_by_path(self, store: DuckDBStore) -> None: ...
    def test_get_file_by_path_missing_returns_none(self, store: DuckDBStore) -> None: ...
```

### [MUST] Test docstrings follow gate-tag pattern: `T_N.M: One sentence what the test proves.`
Confidence: 1.0

```python
def test_transitive_deps_returns_b_c_d_with_depths(self, store: DuckDBStore) -> None:
    """T_2.6: get_dependencies(A, transitive=True) returns B@1, C@2, D@3."""
```

### [MUST] Fixtures are pytest functions decorated with `@pytest.fixture`; return type annotated
Confidence: 1.0

```python
@pytest.fixture
def store() -> DuckDBStore:
    """Fresh in-memory DuckDB store with schema initialised."""
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s
```

### [MUST] In-memory DuckDB for unit tests: `DuckDBStore(":memory:")` — never a real file path
Confidence: 1.0

### [SHOULD] Integration tests use `tmp_path` + `shutil.copytree(SAMPLE_PROJECT, project)` to avoid polluting fixtures
Confidence: 0.95

```python
def test_cli_init_sample_project(self, cli_runner: CliRunner, tmp_path: Path) -> None:
    project = tmp_path / "sample"
    shutil.copytree(SAMPLE_PROJECT, project)
    result = cli_runner.invoke(app, ["init", str(project), "--no-progress"])
    assert result.exit_code == 0
```

### [SHOULD] Test helper factories use `_make_xxx(**kwargs)` convention with sensible defaults
Confidence: 0.95

```python
def _file(path: str, **kwargs) -> FileRecord:
    """Minimal FileRecord with sensible defaults for test use."""
    defaults = dict(language="python", size_bytes=100, line_count=10, hash="abc123")
    defaults.update(kwargs)
    return FileRecord(path=path, **defaults)
```

### [SHOULD] Setup shared per-test-class state in `setup_method(self)`, not in `__init__`
Confidence: 0.90 — used in `TestPythonSymbols`, `TestParsingEngineDetectLanguages`.

```python
class TestPythonSymbols:
    def setup_method(self):
        self.extractor = PythonExtractor()
```

---

## 15. Class Architecture Patterns

### [MUST] Orchestrator/facade classes use a three-lifecycle pattern: `__init__` → `open/init` → `close`
Confidence: 0.95 — `Palace` class:

```python
class Palace:
    def __init__(self, config: PalaceConfig) -> None: ...
    def open(self) -> None: ...      # opens DB, no re-index
    def init(self, ...) -> BuildStats: ...  # creates DB, runs full pipeline
    def close(self) -> None: ...    # closes DB
```

### [MUST] CLI commands open and close Palace inside a `try...finally` block
Confidence: 1.0 — pattern in all 3 non-init commands.

```python
palace = Palace(config)
palace.open()
try:
    _run_symbols(palace=palace, ...)
finally:
    palace.close()
```

### [SHOULD] Large classes use `@staticmethod` for pure helpers with no `self` dependencies
Confidence: 0.90 — `GraphBuilder._hash_file`, `DuckDBStore._row_to_dict`, `DuckDBStore._file_columns`.

---

## 16. Inline Type Suppressors

### [MUST] Use `# type: ignore[attr-defined]` when accessing Protocol-attributed objects via dict access
Confidence: 0.95 — seen in `engine.py`:

```python
self._extractors[extractor.language] = extractor  # type: ignore[attr-defined]
extractor.extract(raw, file_path)  # type: ignore[attr-defined]
```

### [MUST] Use `# noqa: BLE001` when catching broad `Exception` in extractors
Confidence: 1.0

### [MUST] Use `# noqa: S608` when building dynamic SQL with f-strings for structural (non-data) parts
Confidence: 1.0

### [MUST] Use `# noqa: UP007` for `Optional[X]` in Typer command parameter signatures
Confidence: 1.0

---

## 17. Line Length and Formatting

### [MUST] Maximum line length: 100 characters (`pyproject.toml [tool.ruff] line-length = 100`)
Confidence: 1.0

### [SHOULD] Multi-argument calls exceeding 100 chars: one argument per line with trailing comma
Confidence: 0.88

```python
stats = builder.build(extractions, self.config.root)  # short — stays on one line

# Long call — one arg per line
row = self._con.execute(
    """
    INSERT INTO files(path, language, size_bytes, line_count, hash)
    VALUES (?, ?, ?, ?, ?)
    ...
    """,
    [record.path, record.language, record.size_bytes, record.line_count, record.hash],
).fetchone()
```

---

## 18. Hard Guardrails (Never Do)

1. **No `from typing import Dict, List, Tuple, Set`** — use lowercase builtins.
2. **No `class Foo(str, Enum)`** — always use `StrEnum`.
3. **No bare `except:`** or `except Exception:` without `# noqa: BLE001` — only in extractor `extract()`.
4. **No `print()`** in source code — use `console.print()` (CLI) or `result.errors.append()` (library).
5. **No `sys.exit()`** in CLI code — use `raise typer.Exit(code)`.
6. **No missing `from __future__ import annotations`** — every `.py` file, no exceptions.
7. **No missing module docstring** — every `.py` file, no exceptions.
8. **No mutable default arguments in function signatures** — use `None` sentinel with `if x is None: x = []`.
9. **No `Optional` without `# noqa: UP007`** outside Typer command signatures.
10. **No user data interpolated into DuckDB SQL strings** — always use `?` parameters.
11. **No `NamedTuple` or `TypedDict`** — use `@dataclass`.
12. **No `assert` in production code** (storage/parsing/graph) for logic guarding — only in CLI helpers and tests.
    Exception: `assert row is not None` after `fetchone()` on RETURNING queries is intentional and accepted.

---

## 19. Code Templates

### New CLI command (e.g., `palace/cli/commands/search.py`):

```python
"""palace search — Search symbols by regex pattern."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from palace.core.config import PalaceConfig
from palace.core.palace import Palace

console = Console()


def search_command(
    pattern: str = typer.Argument(..., help="Regex pattern to search."),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Filter by kind."),  # noqa: UP007
) -> None:
    """Search symbols matching a regex pattern."""
    config = PalaceConfig.discover()
    if config is None:
        console.print(
            "[red]Error:[/red] No palace found.\nRun [bold]palace init[/bold] first."
        )
        raise typer.Exit(1)

    palace = Palace(config)
    palace.open()
    try:
        _run_search(palace=palace, pattern=pattern, kind=kind)
    finally:
        palace.close()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _run_search(palace: Palace, pattern: str, kind: str | None) -> None:
    """Query and render search results."""
    assert palace.store is not None
    ...
```

### New extractor (e.g., `palace/parsing/extractors/rust.py`):

```python
"""Rust symbol extractor using tree-sitter for Code Palace."""

from __future__ import annotations

from pathlib import Path

from tree_sitter_language_pack import get_parser

from palace.core.models import SymbolKind
from palace.parsing.extractors.base import (
    FileExtraction,
    ImportInfo,
    SymbolInfo,
)


def _node_text(node) -> str:  # type: ignore[no-untyped-def]
    """Decode a tree-sitter node's byte text to a UTF-8 string."""
    return node.text.decode("utf-8") if node.text else ""


def _extract_symbols(root_node) -> list[SymbolInfo]:  # type: ignore[no-untyped-def]
    """Walk source nodes and extract all Rust symbols."""
    symbols: list[SymbolInfo] = []
    # ... implementation
    return symbols


def _extract_imports(root_node) -> list[ImportInfo]:  # type: ignore[no-untyped-def]
    """Extract use declarations from a Rust source file."""
    imports: list[ImportInfo] = []
    # ... implementation
    return imports


class RustExtractor:
    """Extracts symbols and imports from Rust source files."""

    language: str = "rust"
    extensions: list[str] = [".rs"]

    def __init__(self) -> None:
        self._parser = get_parser("rust")

    def extract(self, source: bytes, file_path: Path) -> FileExtraction:
        """Parse source bytes and return all symbols and imports found."""
        result = FileExtraction(path=file_path, language=self.language)
        if not source.strip():
            return result
        try:
            tree = self._parser.parse(source)
            root = tree.root_node
            if root.has_error:
                result.errors.append("Syntax errors detected in source")
            result.symbols = _extract_symbols(root)
            result.imports = _extract_imports(root)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Parse error: {exc}")
        return result
```

### New unit test file:

```python
"""T_N gate tests — <Component> validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import FileRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    """Fresh in-memory DuckDB store with schema initialised."""
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file(path: str, **kwargs) -> FileRecord:
    """Minimal FileRecord with sensible defaults for test use."""
    defaults = dict(language="python", size_bytes=100, line_count=10, hash="abc123")
    defaults.update(kwargs)
    return FileRecord(path=path, **defaults)


# ---------------------------------------------------------------------------
# T_N.1 — Description of test group
# ---------------------------------------------------------------------------


class TestSomething:
    """T_N.1 — Brief description."""

    def test_does_the_thing(self, store: DuckDBStore) -> None:
        """T_N.1: One-sentence gate description."""
        # arrange
        ...
        # act
        result = ...
        # assert
        assert result == expected
```
