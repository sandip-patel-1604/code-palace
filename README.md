# Code Palace

> Navigate any codebase like you built it.

[![PyPI version](https://img.shields.io/pypi/v/code-palace.svg)](https://pypi.org/project/code-palace/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-173%20passing-brightgreen.svg)](https://github.com/sandip-patel-1604/code-palace)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

Code Palace parses any codebase into a queryable **symbol graph**, enabling structural reasoning about changes — no LLM, no Docker, no API key required.

```bash
pip install code-palace
cd any-repo
palace init
palace plan "add user authentication"
```

---

## The Problem

Modern codebases are too large to hold in your head. When you need to make a change, you spend the first hour just mapping the terrain — which file owns what, what calls what, what breaks if you move this.

Existing tools solve adjacent problems:

- **Sourcegraph / Greptile** — great at text search, built for search, not structural reasoning
- **Cursor / Aider** — LLM-powered, context-window-bound, require API keys and internet access
- **Language servers** — IDE-specific, require running editors, not scriptable

Code Palace fills the gap between "search" and "understand." It gives you a deterministic, offline, CLI-native structural model of your codebase — so you can ask _structural_ questions and get precise, deterministic answers before you write a single line.

---

## Install

```bash
pip install code-palace
```

Requires Python 3.10+. No other system dependencies.

---

## Quick Start

```bash
cd any-repo
palace init                                    # parse and index the codebase
palace symbols --kind class                    # browse symbols
palace deps app.py --transitive                # trace dependency trees
palace plan "add user authentication"          # structural change plan
```

---

## Commands

### `palace init`

Parse and index your codebase into a local `.palace/` directory. Runs in seconds.

```
╭──────────────────────────── Palace Init ────────────────────────────╮
│   Root:       /home/user/my-project                                │
│   Languages:  Cpp (2), Go (2), Java (2), Python (4), Typescript (3)│
│                                                                    │
│ Summary                                                            │
│ ├── Files:     13                                                  │
│ ├── Symbols:   72                                                  │
│ ├── Edges:     8                                                   │
│ ├── Imports:   22 (8 resolved)                                     │
│ └── Duration:  0.1s                                                │
│   Palace ready → .palace/                                          │
╰────────────────────────────────────────────────────────────────────╯
```

The index is stored locally in `.palace/` as an embedded DuckDB database. Re-run `palace init` whenever your codebase changes.

---

### `palace symbols`

List and filter every symbol in the indexed codebase. Filter by kind, name, or file.

```bash
palace symbols --kind class
```

```
Symbols — 8 results (showing 8)
┏━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━┓
┃ Kind  ┃ Name           ┃ File                             ┃ Line ┃ Signature ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━┩
│ class │ Application    │ app.py                           │   13 │           │
│ class │ Handler        │ cpp_src/handler.h                │   12 │           │
│ class │ Application    │ cpp_src/main.cpp                 │    6 │           │
│ class │ App            │ java_src/App.java                │    4 │           │
│ class │ UserService    │ java_src/service/UserService.ja… │    6 │           │
│ class │ UserService    │ service.py                       │    8 │           │
│ class │ UserApi        │ ts_src/api.ts                    │    8 │           │
│ class │ UserController │ ts_src/index.ts                  │    4 │           │
└───────┴────────────────┴──────────────────────────────────┴──────┴───────────┘
```

Available kinds: `function`, `class`, `method`, `interface`, `type`, `variable`, and more — depends on language.

---

### `palace deps`

Trace the import graph for any file, with optional transitive expansion.

```bash
palace deps app.py --transitive
```

```
app.py
├── config.py  python
├── model.py  python
└── service.py  python
    └── model.py

Direct: 3 files | Transitive: 3 files
```

Useful for blast-radius analysis before a refactor: know exactly which files will be affected before you touch anything.

---

### `palace plan`

Given a plain-English task description, Code Palace ranks the files most likely to be involved — ordered by dependency depth and symbol relevance.

```bash
palace plan "add user authentication"
```

```
╭───────────────────────────────────────────────────╮
│ Structural Change Plan: "add user authentication" │
╰───────────────────────────────────────────────────╯

  Keywords: add, user, authentication

  Files likely involved (by dependency order):

   1. go_src/handler.go
      Matched: User, Greet, validate, NewUser
      Reason: symbol names: user
   2. java_src/service/UserService.java
      Matched: UserService, name, MAX_USERS, getName, listUsers
      Reason: path matches: user; symbol names: user
   3. service.py
      Matched: UserService, __init__, add_user, get_user, _validate
      Reason: symbol names: add, user
   4. ts_src/types.ts
      Matched: IUser, UserId, UserName, UserRole
      Reason: symbol names: user
   5. ts_src/api.ts
      Matched: IUserRepository, UserApi, constructor, findById, findAll
      Reason: symbol names: user
   6. ts_src/index.ts
      Matched: UserController, constructor, getUser, listUsers, formatUser
      Reason: symbol names: user

  Note: Structural analysis only. Use an API key for
  AI-powered change plans with rationale.
```

This is pure structural analysis — no LLM call, no network request, no hallucination. It reasons from the actual symbol graph.

---

## Supported Languages

| Language   | Functions | Classes | Methods | Interfaces | Types | Imports |
|------------|:---------:|:-------:|:-------:|:----------:|:-----:|:-------:|
| Python     | yes       | yes     | yes     | —          | —     | yes     |
| TypeScript | yes       | yes     | yes     | yes        | yes   | yes     |
| Go         | yes       | —       | yes     | yes        | yes   | yes     |
| Java       | yes       | yes     | yes     | yes        | —     | yes     |
| C++        | yes       | yes     | yes     | —          | —     | yes     |

More languages are on the roadmap. Parsing is powered by [tree-sitter](https://tree-sitter.github.io/) via `tree-sitter-language-pack` — adding a language is a matter of adding a grammar and a symbol extractor.

---

## How It Works

Code Palace builds a **Palace Graph** — a three-layer structural model stored in an embedded DuckDB database.

```
┌─────────────────────────────────────────────────┐
│  Layer 3 — Relational                           │
│  imports · calls · inherits · implements        │
├─────────────────────────────────────────────────┤
│  Layer 2 — Symbolic                             │
│  functions · classes · methods · interfaces     │
├─────────────────────────────────────────────────┤
│  Layer 1 — Structural                           │
│  files · directories · modules                  │
└─────────────────────────────────────────────────┘
```

**Parsing — tree-sitter**
Every supported language is parsed by a tree-sitter grammar, which produces a concrete syntax tree. Code Palace walks that tree to extract symbols and edges. Tree-sitter is incremental, error-tolerant, and fast — the same parser that powers Neovim's syntax highlighting.

**Storage — DuckDB**
The graph is stored in a single embedded DuckDB file at `.palace/palace.db`. No server process, no migrations, no configuration. DuckDB's recursive CTEs handle transitive dependency queries natively.

**Querying — Typer + Rich**
The CLI is built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/). Every command returns structured output that is also machine-readable for scripting.

---

## Zero Dependencies

Code Palace has no operational dependencies beyond the Python package itself.

| Requirement    | Code Palace | Sourcegraph | Greptile | Cursor/Aider |
|----------------|:-----------:|:-----------:|:--------:|:------------:|
| Docker         | no          | yes         | no       | no           |
| Database server| no          | yes         | no       | no           |
| API key        | no          | yes         | yes      | yes          |
| Internet access| no          | yes         | yes      | yes          |
| IDE plugin     | no          | optional    | no       | yes          |

Install once, run anywhere, work offline.

---

## Competitive Comparison

| Capability                        | Code Palace | Sourcegraph | Greptile | Cursor / Aider |
|-----------------------------------|:-----------:|:-----------:|:--------:|:--------------:|
| Works offline                     | yes         | no          | no       | no             |
| Zero config after pip install     | yes         | no          | no       | partial        |
| Structural dependency graph       | yes         | partial     | no       | no             |
| Symbol-level search               | yes         | yes         | partial  | partial        |
| Deterministic (no LLM needed)     | yes         | yes         | no       | no             |
| Change impact analysis            | yes         | no          | no       | no             |
| Polyglot (5+ languages, one tool) | yes         | yes         | yes      | yes            |
| AI-powered rationale              | planned     | no          | yes      | yes            |

The gap Code Palace fills: **deterministic, structural, offline reasoning** — the foundation you need before you hand context to an LLM.

---

## Roadmap

### Phase 2 — Richer navigation (next)
- Terminal UI (TUI) with interactive graph exploration
- Semantic search via local embeddings (no API key)
- Symbol call-graph queries (`who calls this function?`)
- Incremental re-indexing (watch mode)

### Phase 3 — LLM integration
- Optional LLM backend for AI-powered `palace plan` rationale
- MCP (Model Context Protocol) server — expose the Palace Graph as a tool for Claude, GPT-4o, and others
- `palace context` command: assemble minimal, ranked context for LLM prompts

---

## Development

```bash
git clone https://github.com/sandip-patel-1604/code-palace.git
cd code-palace
pip install -e ".[dev]"
pytest
```

The project is built with [Hatch](https://hatch.pypa.io/) and uses `pyproject.toml` for all configuration. The test suite has 173 tests covering parsing, graph construction, query correctness, and CLI output.

```
~4700 lines of Python · 173 tests · 0 external services
```

---

## License

[MIT](LICENSE) — use it however you want.

---

Built by [sandip-patel-1604](https://github.com/sandip-patel-1604) · [GitHub](https://github.com/sandip-patel-1604/code-palace) · [PyPI](https://pypi.org/project/code-palace/)
