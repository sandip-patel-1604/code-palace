# Code Palace — Product Vision

> **Navigate any codebase like you built it.**

## The Problem

Every developer hits this weekly:

> "I just got assigned a ticket on a codebase I don't fully know. Where do I even start?"

Senior engineers answer it from tribal knowledge — a mental map of the codebase built over months. Juniors flounder for hours reading files, tracing imports, asking teammates. No tool solves this today.

**Existing tools and their gaps:**

| Tool | What It Does | What It Doesn't Do |
|---|---|---|
| Sourcegraph | Text/symbol search | Doesn't reason about change plans |
| GitHub Copilot | Autocomplete with context | Doesn't understand codebase structure |
| Cursor | AI editing with context window | IDE-locked, no structural model |
| ast-grep | Structural pattern matching | No semantic understanding |
| LSP/ctags | Go-to-definition, references | No cross-cutting reasoning |
| Aider | Repo-map for LLM context (tree-sitter + graph ranking) | Helps AI write code, not humans understand code |
| Greptile | Full codebase knowledge graph for analysis | Hosted SaaS, sends code to cloud, no offline/TUI |

**The gap**: None of these can answer *"I need to add feature X — what files do I touch, in what order, following which patterns?"* That requires a **causal model** of the codebase, not a search index.

---

## The Vision

Code Palace externalizes the mental model that senior engineers carry in their heads. It:

1. **Fingerprints** any codebase — parses every file, builds a multi-layer graph
2. **Discovers** domain structure — clusters code into named domains automatically
3. **Reasons** about changes — given a task, produces an ordered change plan grounded in the actual code
4. **Navigates** visually — a beautiful TUI for exploring the codebase spatially

The core innovation is the **Palace Graph** — not a flat index, but a six-layer structural + semantic + temporal model that enables reasoning, not just retrieval.

---

## The Palace Graph — A Multi-Layer Mental Model

```
Layer 6: BEHAVIORAL    — control flow, data flow, side effects, I/O boundaries
Layer 5: TEMPORAL      — git history, co-change, churn, ownership
Layer 4: SEMANTIC      — embeddings, concept clusters, domain groupings
Layer 3: RELATIONAL    — imports, calls, inherits, implements, references
Layer 2: SYMBOLIC      — functions, classes, types, interfaces, exports
Layer 1: STRUCTURAL    — files, directories, modules, packages
```

Each layer answers different questions:

- **Structural**: "What files exist and how are they organized?"
- **Symbolic**: "What are the building blocks (functions, classes, types)?"
- **Relational**: "What depends on what? What calls what?"
- **Semantic**: "What code is conceptually related, even if structurally distant?"
- **Temporal**: "What changes together? Who knows this code? Where are the hotspots?"
- **Behavioral**: "What does this code actually DO? Where are the side effects?"

Combined, they answer: **"Given this task, what's the change plan?"**

### Auto-Discovered Domain Clusters

The magic: automatically discover the "table of contents" for any codebase by combining:

1. **Directory structure** (heuristic, often wrong but useful starting signal)
2. **Import graph communities** (Louvain/Leiden algorithm on the dependency graph)
3. **Co-change frequency** (files that always change together = implicit module)
4. **Semantic similarity** (identifier names, docstrings, comments, code embeddings)

Then cluster and auto-name them. The result: a domain map nobody had to manually write.

---

## The Eight Core Commands

### 1. `palace init` — Zero-Config Fingerprinting

```bash
$ cd any-repo && palace init

  Indexing codebase...
   Detected: Python 3.11, TypeScript 5.x, Docker
   Parsed: 1,247 files, 8,932 symbols
   Built: dependency graph (12,847 edges)
   Clustered: 6 domain groups
   Embedded: 8,932 chunks (local model, no API key needed)

   Palace ready in 14.2s -> .palace/
```

Works on ANY repo, ANY language, NO config, NO API key for core features.

### 2. `palace plan <task>` — The Killer Feature

```bash
$ palace plan "add webhook notifications when a pipeline job fails"

  Change Plan: Add webhook notifications on pipeline failure

  Domain: Data Pipeline + Notification System
  Pattern: Follows existing event handler pattern (see: events/handlers/)

  Files to create:
    src/events/handlers/webhook_notify.py
       - WebhookNotifyHandler following BaseHandler pattern
       - Triggered on PipelineFailedEvent

    src/notifications/webhook.py
       - Webhook delivery with retry logic (match existing email pattern)

  Files to modify:
    src/pipeline/runner.py:187
       - Emit PipelineFailedEvent on job failure
       - Event bus already wired (see line 34)

    src/config/settings.py:94
       - Add WEBHOOK_URL, WEBHOOK_SECRET, WEBHOOK_RETRY_COUNT
       - Follow existing pattern: EMAIL_* vars on line 78

    src/events/registry.py:12
       - Register WebhookNotifyHandler for PipelineFailedEvent

  Files to create (tests):
    tests/events/test_webhook_notify.py
       - Follow test pattern from tests/events/test_email_notify.py

  Dependencies:
    httpx (already installed — used in src/clients/)

  Risk: Low — event system is decoupled, narrow blast radius
```

This is the feature people will screenshot and share.

### 3. `palace explore` — Interactive TUI Navigator

Full-screen terminal UI (built with Textual) for visual navigation:
- Navigate the domain map, drill into clusters -> modules -> symbols
- See relationships as you drill down
- Semantic search from anywhere
- View call chains, dependency paths
- Think lazygit but for codebase understanding

### 4. `palace impact <symbol>` — Blast Radius Analysis

```bash
$ palace impact src/core/models.py:User

  Direct dependents:     14 files
  Transitive dependents: 47 files
  Test coverage:         72% (3 uncovered paths)
  Co-change frequency:   Usually changed with auth/permissions.py
  Last 10 changes by:    alice (6), bob (3), charlie (1)
  Risk: HIGH — core model, wide blast radius
```

### 5. `palace explain <path>` — Understand Any Code

```bash
$ palace explain src/pipeline/

  The pipeline module implements a batch ETL system:
  1. Ingest: workers/ingest.py pulls from S3 (triggered by SQS)
  2. Transform: transformers/ apply cleaning rules per data source
  3. Load: loaders/postgres.py writes to the analytics DB

  Key patterns:
  - Strategy pattern for transformers (each implements BaseTransformer)
  - Retry logic in workers/retry.py with exponential backoff
  - All config flows from config/pipeline.yaml

  Gotchas:
  - transform_batch() has a subtle ordering dependency (see line 142)
  - The S3 client is mocked differently in tests vs staging
```

### 6. `palace onboard` — Auto-Generated Codebase Tour

Generates a guided walkthrough for new developers. Every team wants this and nobody has time to write it. Covers: architecture overview, domain map, key entry points, patterns used, common gotchas.

### 7. `palace health` — Codebase Health Dashboard

Complexity hotspots, dead code, circular dependencies, test gaps, churn analysis, ownership distribution.

### 8. `palace diff` — PR Impact Analysis

```bash
$ palace diff HEAD~3..HEAD

  Diff Impact: 3 commits, 12 files changed

  Domains affected:
    Data Pipeline (HIGH) — 7 files, core transform logic modified
    Auth System (LOW) — 1 config file

  Blast radius:       23 files transitively affected
  Patterns followed:  ✓ BaseTransformer pattern maintained
  Patterns violated:  ⚠ New transformer skips validation step (see line 142)

  Suggested tests:
    tests/pipeline/test_transforms.py
    tests/pipeline/test_batch.py
    tests/integration/test_etl_pipeline.py

  Risk: MEDIUM — pipeline domain heavily affected, but tests exist
```

Understand the impact of any set of changes — in PRs, CI, or local development.

---

## The Zero-Dependency Principle

Critical for adoption. The core must work with:

- **No Docker**
- **No database server** — embedded DuckDB + embedded vector search
- **No API key** — local embeddings via ONNX runtime
- **Just `pip install code-palace`**

LLM features (`plan`, `explain`, `onboard`) enhance with an API key but degrade gracefully:

| Feature | Without API Key | With API Key |
|---|---|---|
| `palace init` | Full indexing | Same |
| `palace domains` | Graph-based clustering | + LLM-named clusters |
| `palace search` | Semantic vector search | Same |
| `palace deps` | Full dependency graph | Same |
| `palace impact` | Full graph traversal | + Natural language summary |
| `palace plan` | Structural analysis only | + Full change plan with rationale |
| `palace explain` | Symbol listing + metrics | + Natural language explanation |
| `palace explore` | Full TUI | Same |

---

## Technology Stack

```
CLI Framework:     Typer + Rich (beautiful output, good DX)
TUI:               Textual (by the Rich team — gorgeous terminal apps)
AST Parsing:       tree-sitter (Python bindings, 100+ languages)
Graph Storage:     DuckDB (embedded, fast, SQL + recursive CTEs for traversal)
Vector Storage:    LanceDB (embedded, columnar, vector search, no server)
Embeddings:        ONNX Runtime + UniXcoder (local, no API key, best code retrieval quality)
                   Alternative: Nomic Embed Code (fully open-source)
                   Optional: OpenAI/Voyage AI embeddings for higher quality
LLM:               Pluggable provider: Claude API, OpenAI API, or Ollama (local, no API key)
                   (optional — core features work without any LLM)
Git Analysis:      gitpython or subprocess (git log/blame/diff)
Language:          Python 3.10+ (Ubuntu 18.04 LTS compatible, largest contributor pool)
Testing:           pytest + hypothesis for property-based testing
Packaging:         pyproject.toml + hatch, publish to PyPI
```

### Why These Choices

**Python over Rust**: Contributor pool. A Rust rewrite for hot paths (parsing, graph traversal) can come later — the ruff/uv playbook. Ship fast, optimize later.

**LanceDB over Qdrant/Chroma**: Embedded (no server), columnar (fast scans), supports filtered vector search. Zero infrastructure.

**DuckDB over SQLite/Neo4j**: Embedded like SQLite but with analytical query performance and recursive CTEs for graph traversal. No server, no config.

**tree-sitter over language-specific parsers**: One engine, 100+ languages. Battle-tested (used by GitHub, Neovim, Helix). Python bindings are solid.

---

## Competitive Positioning

### What Makes Code Palace Different

| Dimension | Sourcegraph / LSP | Aider | Greptile | Code Palace |
|---|---|---|---|---|
| **Approach** | Retrieval (find code) | LLM context feeding | Knowledge graph analysis | Reasoning (plan changes) |
| **Model** | Flat index | AST repo-map (1 layer) | Codebase knowledge graph | Six-layer palace graph |
| **Domain understanding** | None | None | API-based | Auto-discovered clusters |
| **Output** | "Here are matching results" | Better LLM code edits | PR review comments | "Here's your ordered change plan" |
| **Setup** | Server + config | `pip install` | SaaS + API key | `pip install` + `palace init` |
| **Privacy** | Self-hosted or cloud | Local | Cloud (code sent to server) | Fully local, zero infrastructure |
| **TUI** | No | No | No | First-class interactive explorer |

### Key Differentiators

**vs. Aider**: Aider builds a repo-map to help *AI* write code in your repo. Code Palace builds a full mental model to help *YOU* understand any repo. Aider is a pair programmer; Code Palace is a codebase navigator.

**vs. Greptile**: Greptile requires sending your code to their cloud servers. Code Palace runs entirely locally — `pip install`, no server, no API key for core features. Greptile targets enterprise CI/PR review; Code Palace targets individual developer exploration.

**vs. Cursor/Copilot**: IDE-locked, no structural model, no offline capability. Code Palace works in any terminal, on any machine, with any editor.

### Star-Worthy Factors (Lessons From Top Repos)

| Factor | How We Hit It |
|---|---|
| **Zero friction** (like ripgrep, fzf) | `pip install code-palace && palace init` — done |
| **Beautiful output** (like lazygit, btop) | Rich + Textual TUI |
| **Universally useful** (like jq) | Works on any language, any repo |
| **Solves real daily pain** (like ruff) | The "where do I start?" problem |
| **Demo-able** (tweetable screenshots) | `palace plan` output is inherently shareable |
| **Active development** (visible momentum) | Monthly milestones, clear roadmap |
| **Local-first AI** (like Ollama) | No API key needed, full offline capability |

---

## Phased Roadmap

### Phase 1: Foundation + First Impression (Month 1) — Ship v0.1
**Goal**: Parse any codebase into a queryable symbol graph. Make `palace plan` work without an LLM.

- `palace init` — tree-sitter multi-language parsing (Python, TypeScript, Go, Java)
- `palace symbols` — list and search symbols
- `palace deps` — file and symbol dependency queries
- `palace plan` (structural-only) — file-level change plan without LLM, using graph analysis
- DuckDB storage with clean schema
- CLI skeleton with Typer + Rich — beautiful output from day 1
- Test infrastructure with pytest
- **Ship to PyPI. Even without AI, a fast structural indexer with change plans is useful.**

### Phase 2: The Star Magnet (Month 2) — Ship v0.2
**Goal**: Visual exploration + semantic search. This is the launch moment.

- `palace domains` — auto-discovered domain clustering
- `palace impact` — blast radius analysis via graph traversal
- `palace explore` — full-screen Textual TUI *(moved up — TUIs are star magnets)*
- `palace search` — semantic search with local embeddings (LanceDB + ONNX)
- `palace diff` — impact analysis on git diff ranges (PR workflow integration)
- Git history integration (co-change analysis, ownership)
- **🚀 LAUNCH: HN/Reddit post with GIF of `palace explore` + `palace plan`. This is the viral moment.**

### Phase 3: Intelligence + MCP (Month 3) — Ship v0.3
**Goal**: LLM-powered reasoning and AI tool integration.

- `palace plan` with LLM — full change plans with rationale (Claude / OpenAI / Ollama)
- `palace explain` — natural language codebase explanations
- `palace onboard` — auto-generated codebase guide
- `palace serve` — MCP server mode (use palace as a tool in Claude Code, Cursor, Windsurf)
- Graceful degradation without API key
- Pattern detection (how does this codebase implement cross-cutting concerns?)
- **Second viral push: "Now palace plan writes your change plan with AI" + MCP integration demo.**

### Phase 4: Ecosystem (Month 4) — Ship v0.4
**Goal**: Embed Code Palace into developer workflows.

- `palace health` — complexity hotspots, dead code, circular deps, test gaps, churn
- VS Code extension (sidebar palace explorer)
- GitHub Actions integration (PR impact analysis in CI)
- `palace review` — AI-powered PR review grounded in codebase structure
- `palace watch` — incremental re-indexing on file changes
- Rust and C++ language support (tree-sitter extractors)

### Phase 5+: Advanced (Months 5+)
- Multi-repo and monorepo support
- Architecture pattern detection and enforcement
- Custom palace configurations and templates
- Plugin system for language-specific deep analysis
- LSP server (palace as a language server for any IDE)
- Team features (shared palaces, expertise mapping)

---

## Launch Strategy

### README as Marketing Page

The README is not documentation — it is a landing page. For record-breaking stars:

1. **Hero section**: Animated GIF/SVG of `palace explore` TUI + `palace plan` output in the first 3 seconds of scrolling
2. **One-liner install + demo**: `pip install code-palace && cd any-repo && palace init && palace plan "add user authentication"`
3. **Competitive comparison table**: Show the gap vs. Sourcegraph, Aider, Greptile, Cursor
4. **"Featured in" badges**: Add after first HN/Reddit feature

### Launch Timeline

| Milestone | Channel | Content |
|---|---|---|
| v0.1 release | Twitter/X, Reddit r/python | "Fast codebase indexer with zero-config change plans" |
| v0.2 release (THE launch) | Hacker News, Reddit r/programming, r/commandline | GIF of `palace explore` TUI + `palace plan` demo |
| v0.3 release | Twitter/X, AI dev communities | "palace plan now uses AI — and works with Claude Code via MCP" |
| Ongoing | GitHub Discussions, Discord | Community engagement, feature requests, contributor onboarding |

### Demo Asset Checklist

- [ ] Animated SVG of `palace init` on a real open-source repo (e.g., Flask, FastAPI)
- [ ] GIF of `palace explore` TUI navigation (the hero image)
- [ ] Screenshot of `palace plan` output (the tweetable moment)
- [ ] Side-by-side comparison: "Before Code Palace" (grep + find) vs "After" (palace plan)
- [ ] 90-second YouTube demo video

---

## Project Structure (Target)

```
code-palace/
  palace/                      # Core Python package
    __init__.py
    cli/                       # CLI interface (Typer + Rich)
      __init__.py
      main.py
      commands/
        init.py                # palace init
        plan.py                # palace plan
        explore.py             # palace explore (TUI)
        search.py              # palace search
        impact.py              # palace impact
        explain.py             # palace explain
        onboard.py             # palace onboard
        health.py              # palace health
        domains.py             # palace domains
        symbols.py             # palace symbols
        deps.py                # palace deps
        diff.py                # palace diff
        serve.py               # palace serve (MCP server)
      ui/                      # Rich/Textual TUI components
    core/                      # Core abstractions
      palace.py                # Palace graph orchestrator
      graph.py                 # Multi-layer graph model
      config.py                # Palace configuration
    parsing/                   # Language parsers
      engine.py                # tree-sitter orchestrator
      extractors/              # Per-language symbol extractors
        python.py
        typescript.py
        go.py
        rust.py
        java.py
        cpp.py
      patterns/                # Architecture pattern detectors
    graph/                     # Graph construction and queries
      builder.py               # Builds the palace graph from parsed data
      layers.py                # Structural, symbolic, relational, semantic, temporal, behavioral
      traversal.py             # Graph algorithms (impact, reachability, shortest path)
      clustering.py            # Domain/concept clustering (Louvain, semantic)
    semantic/                  # Semantic understanding
      embeddings.py            # Code embedding generation (ONNX local + optional API)
      search.py                # Vector similarity search
      concepts.py              # Concept extraction and auto-naming
    temporal/                  # Git history analysis
      history.py               # Git log parsing
      cochange.py              # Co-change analysis (files that change together)
      ownership.py             # Code ownership and expertise mapping
      churn.py                 # Hotspot detection (high-churn files)
    intelligence/              # LLM-powered features (optional, requires API key)
      planner.py               # Task -> ordered change plan
      explainer.py             # Natural language code explanation
      reviewer.py              # PR/change analysis
      onboarder.py             # Codebase onboarding guide generation
      providers/               # LLM provider implementations
        claude.py              # Anthropic Claude API
        openai.py              # OpenAI GPT API
        ollama.py              # Ollama (local models, no API key)
    storage/                   # Persistence
      store.py                 # Abstract store interface
      duckdb_store.py          # DuckDB graph + metadata storage
      vector_store.py          # LanceDB vector storage
  tests/
    unit/
    integration/
    fixtures/                  # Sample codebases for testing
  docs/
  pyproject.toml
  README.md
  LICENSE                      # MIT
  .palace/                     # Generated palace data (gitignored)
```

---

## Open Questions

### Resolved Decisions

- [x] **`palace plan` without LLM?** → Yes. Phase 1 ships structural-only change plans. LLM enhancement adds rationale in Phase 3.
- [x] **Local embeddings quality?** → Acceptable for v0.1 with UniXcoder. API embeddings optional.
- [x] **Phase 1 languages?** → Python, TypeScript, Go, Java. Rust and C++ deferred to Phase 4.
- [x] **TUI timing?** → Moved to Phase 2. TUI GIF is the #1 star driver.
- [x] **LLM abstraction?** → Pluggable provider protocol: Claude + OpenAI + Ollama (local).
- [x] **`.palace/` committed?** → Gitignored by default. `palace export` command for team sharing.
- [x] **MCP vs Claude Code skill?** → MCP server (`palace serve`). Standard protocol, works with all AI tools.

### Open

- [ ] Pricing model for a hosted/SaaS version? Or stay fully open source?
- [ ] How to handle monorepos with mixed languages and build systems?
- [ ] Incremental indexing strategy — how to efficiently update the palace on file changes?
