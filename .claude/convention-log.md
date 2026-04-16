# Convention Log — Audit Trail

---

## 2026-04-15 — Initial Full Scan

**Trigger**: Mode A — no `.claude/style-guide.md` existed.
**Tool**: project-style-guard (claude-sonnet-4-6)
**Files sampled**: 10 of 21 source files
**Files analysed**:
- `palace/__init__.py`
- `palace/cli/main.py`
- `palace/cli/commands/init.py`
- `palace/cli/commands/symbols.py`
- `palace/cli/commands/deps.py`
- `palace/core/models.py`
- `palace/core/config.py`
- `palace/storage/store.py`
- `tests/conftest.py`
- `tests/unit/test_skeleton.py`

**Rules generated**: 12 MUST, 6 SHOULD, 3 MAY
**Review items queued**: 3
**Drift events**: none (first scan)

**Key findings**:
- 100% consistency on `from __future__ import annotations` + module docstring header pattern.
- `StrEnum` used exclusively — no `str, Enum` anti-pattern found.
- `@dataclass` + `@runtime_checkable Protocol` is the established data-modelling pattern.
- Typer CLI commands consistently use `Optional[X]` + `# noqa: UP007` for parameter types.
- Test docstrings follow `T_N.M: sentence.` gate-test naming.
- Single author; single commit — authority weighting applied uniformly.

**Changes from previous scan**: N/A (first scan)

---

## 2026-04-15 — Full 28-File Rescan

**Trigger**: Explicit user request for a comprehensive style-guard pass across all packages.
**Tool**: project-style-guard (claude-sonnet-4-6)
**Files sampled**: 28 of ~30 source files
**Files analysed**:

palace/ core:
- `palace/__init__.py`
- `palace/core/models.py`
- `palace/core/config.py`
- `palace/core/palace.py`

palace/ cli:
- `palace/cli/main.py`
- `palace/cli/commands/init.py`
- `palace/cli/commands/symbols.py`
- `palace/cli/commands/deps.py`
- `palace/cli/commands/plan.py`

palace/ storage:
- `palace/storage/store.py`
- `palace/storage/duckdb_store.py`

palace/ parsing:
- `palace/parsing/engine.py`
- `palace/parsing/extractors/base.py`
- `palace/parsing/extractors/python.py`
- `palace/parsing/extractors/go.py`
- `palace/parsing/extractors/typescript.py`
- `palace/parsing/extractors/java.py` (partial — first 50 lines)

palace/ graph:
- `palace/graph/builder.py`
- `palace/graph/traversal.py`
- `palace/graph/planner.py`
- `palace/graph/layers.py`

tests/:
- `tests/conftest.py`
- `tests/unit/test_skeleton.py`
- `tests/unit/test_duckdb_store.py`
- `tests/unit/test_python_extractor.py`
- `tests/unit/test_parsing_engine.py`
- `tests/integration/test_full_pipeline.py`
- `tests/integration/test_init.py`
- `tests/integration/test_symbols_command.py` (partial — first 50 lines)

**Rules generated**: 18 MUST, 9 SHOULD, 4 MAY (updated from 12/6/3)
**Review items added**: 6 new items (CR-001 through CR-006)
**Drift events**: None — all conventions from initial scan confirmed.

**Key findings / additions vs. initial scan**:
- Confirmed `# type: ignore[no-untyped-def]` is mandatory on all tree-sitter node helper functions.
- Confirmed `# noqa: BLE001` suppressor is required on all extractor `except Exception` catches.
- Confirmed `# noqa: S608` is used when f-string dynamic SQL is structural (not user data).
- Confirmed section separators (`# --` 66-dash banners) are a consistent structural pattern.
- Confirmed Typer CLI commands use `try...finally` to guarantee `palace.close()` is called.
- Confirmed `DuckDBStore(":memory:")` is the universal pattern for unit test store fixtures.
- Confirmed `shutil.copytree(SAMPLE_PROJECT, tmp_path / "project")` pattern for integration tests.
- Confirmed `_node_text` is intentionally duplicated per extractor (documented as MUST in guide).
- Confirmed `frozenset` for module-level stop-word sets; `set` for local mutable lookup sets.
- New MUST rules added: extractor Protocol shape, DuckDB query patterns, Rich output patterns,
  tree-sitter node typing, inline noqa patterns, try-finally lifecycle pattern.

**Changes to style-guide.md**:
- Sections 1–14 fully rewritten with real code examples from all 28 files.
- Added sections 12 (DuckDB patterns), 13 (tree-sitter patterns), 14 (section separators),
  15 (class architecture), 16 (type suppressors), and 19 (templates updated).
- Guardrails expanded from 8 to 12 items.
- Files sampled count updated: 10 → 28.
- Confidence scores updated based on full evidence.
