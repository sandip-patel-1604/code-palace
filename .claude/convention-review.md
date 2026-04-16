# Convention Review Queue

> Items here require human decision before Claude acts on them.
> Sorted: security > design > efficiency > consistency.
> Do not delete resolved items — mark them `[DECIDED: ...]`.

---

## Scan: 2026-04-15 (initial, 10-file pass)

### [EFFICIENCY] `Optional[X]` vs `X | None` inconsistency
[from initial scan]

**Current convention**: CLI command parameters use `Optional[X]` with `# noqa: UP007`
to satisfy Typer's runtime inspection; dataclass fields and return types use `X | None`.

**Proposed**: Consolidate to `X | None` everywhere now that Python 3.10 is the floor.
Typer ≥ 0.9 handles `X | None` correctly via `get_type_hints(include_extras=True)`.

**Cost**: Remove all `# noqa: UP007` suppressors in CLI command files. Low risk.

**Files affected**: `palace/cli/commands/init.py`, `symbols.py`, `deps.py`, `plan.py`

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

### [CONSISTENCY] Module docstring punctuation
[from initial scan]

**Observation**: 9/10 files end module docstrings without a trailing period.
`store.py` ends with a period: `"""Store protocol and data record types for Code Palace storage layer."""`

**Proposed**: Standardise — drop trailing periods from module docstrings to match majority.

**Cost**: Trivial one-liner changes.

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

### [EFFICIENCY] `dict` return type in `Store` protocol is too loose
[from initial scan]

**Current**: `get_symbols(...) -> list[dict]`, `get_edges(...) -> list[dict]`

**Proposed**: Introduce typed `SymbolRow`, `EdgeRow` TypedDicts so callers get autocomplete
and mypy catches key typos.

**Cost**: New types file; callers need updating when the storage layer is implemented.
Breaks the "plain dicts" flexibility note in the docstring.

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

## Scan: 2026-04-15 (full, 28-file pass)

### [CONSISTENCY] CR-001: `_node_text` duplicated across all 5 extractor modules

**Observed in**: `python.py`, `go.py`, `typescript.py`, `java.py`, `cpp.py` — identical 2-line function.

**Current convention reason**: Each extractor is intentionally standalone. Consolidating would
create a cross-extractor import chain that is harder to sever for future removal of languages.

**Proposed**: Extract to a `palace/parsing/extractors/_utils.py` private module. Since it
stays inside the `extractors` subpackage and is a private module (`_utils`), it doesn't violate
the standalone-module principle.

**Tradeoff**: A bug fix (e.g., encoding handling change) would currently need 5 edits.
Adding `_utils.py` reduces that to 1 edit. Import cost: one additional line per extractor.

**Files affected**: All 5 extractor files + new `_utils.py`

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

### [CONSISTENCY] CR-002: `_short_path` duplicated in `symbols.py` and `deps.py`

**Observed in**: `palace/cli/commands/symbols.py:181` and `palace/cli/commands/deps.py:163` —
identical function body.

**Proposed**: Move to `palace/cli/commands/__init__.py` or a new `palace/cli/_utils.py`.

**Cost**: One additional import per command file. Low risk.

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

### [DESIGN] CR-003: `GraphBuilder` and `StructuralPlanner` depend on `DuckDBStore` directly, not `Store` Protocol

**Observed in**: `palace/graph/builder.py:37`, `palace/graph/planner.py:87`, `palace/graph/traversal.py:12`.

All three graph-layer components import `DuckDBStore` directly instead of the `Store` Protocol
defined in `palace/storage/store.py`. This couples the graph layer to the storage implementation,
making it impossible to test with a mock store without monkeypatching.

**Proposed**: Change all three to accept `Store` (Protocol) as their type annotation.

**Cost**: Import change + mypy may need `# type: ignore` on duck-typed attribute access that isn't
in the Protocol (e.g., `.get_imports()`). The `Store` Protocol may need those methods added.

**Files affected**: `builder.py`, `planner.py`, `traversal.py`, `store.py` (Protocol additions)

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

### [EFFICIENCY] CR-004: `_path_for` in `traversal.py` is O(N) per tree node

**Observed in**: `palace/graph/traversal.py:97` — `get_dependency_tree` calls `_path_for`
which scans all files for each recursive node, producing O(N×M) behaviour.

**Proposed**: Build a `{file_id: path}` dict once before recursion and pass it down.

**Cost**: Trivial refactor. The code comment already acknowledges this is acceptable for now.
Only relevant at scale (>5,000 indexed files).

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

### [CONSISTENCY] CR-005: `setup_method` in test classes lacks return type annotation

**Observed in**: `test_python_extractor.py`, `test_parsing_engine.py` — `setup_method(self)` has
no `-> None` annotation.

**Proposed**: Add `-> None` to all `setup_method` definitions to satisfy `mypy strict=true`.

**Cost**: Trivial. 2–3 line edits.

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer

---

### [CONSISTENCY] CR-006: Module docstring period inconsistency (expanded observation)

**Observed**: The previous scan found 1/10 files with a trailing period. The full 28-file scan shows:
- `palace/storage/store.py` ends with a period: `"""Store protocol and data record types for Code Palace storage layer."""`
- All others do NOT end with a period.

**Decision**: [ ] Accept  [ ] Reject  [ ] Defer (from initial scan — still pending)

---

*Last updated: 2026-04-15 by project-style-guard (full 28-file scan)*
