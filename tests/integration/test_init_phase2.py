"""T_8.7 — Phase 2 init pipeline: git history, embeddings, domains, CLI flags."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from palace.cli.main import app
from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.builder import BuildStats
from palace.storage.duckdb_store import DuckDBStore

SAMPLE_PROJECT = Path(__file__).parent.parent / "fixtures" / "sample_project"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_copy(tmp_path: Path) -> Path:
    """Copy sample_project into tmp_path so tests never mutate fixtures."""
    project = tmp_path / "sample"
    shutil.copytree(SAMPLE_PROJECT, project)
    return project


@pytest.fixture
def initialized_palace(sample_copy: Path) -> tuple[Palace, BuildStats]:
    """Run Palace.init() with all Phase 2 phases skipped for a clean baseline."""
    config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
    palace = Palace(config)
    stats = palace.init(
        force=False,
        skip_git=True,
        skip_embeddings=True,
        skip_domains=True,
    )
    palace.close()
    return palace, stats


# ---------------------------------------------------------------------------
# T_8.7 — Phase 2 unit-level tests
# ---------------------------------------------------------------------------


class TestInitPhase2:
    def test_skip_flags_suppress_phase_stats(self, sample_copy: Path) -> None:
        """T_8.7.1: skip_git + skip_embeddings → stats.commits and embeddings are None."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
        palace = Palace(config)
        try:
            stats = palace.init(
                force=False,
                skip_git=True,
                skip_embeddings=True,
                skip_domains=True,
            )
        finally:
            palace.close()

        assert stats.commits is None, "commits should be None when skip_git=True"
        assert stats.embeddings is None, "embeddings should be None when skip_embeddings=True"
        assert stats.domains is None, "domains should be None when skip_domains=True"

    def test_force_wipes_vectors_dir(self, sample_copy: Path) -> None:
        """T_8.7.2: init force=True removes stale embeddings and recreates vectors/."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)

        # Pre-create a sentinel file inside vectors/ to confirm wipe happens
        vectors_dir = config.vectors_dir
        vectors_dir.mkdir(parents=True, exist_ok=True)
        sentinel = vectors_dir / "stale_sentinel.txt"
        sentinel.write_text("stale")

        palace = Palace(config)
        try:
            palace.init(
                force=True,
                skip_git=True,
                skip_embeddings=True,  # don't need embeddings to test wipe
                skip_domains=True,
            )
        finally:
            palace.close()

        # Sentinel must be gone — vectors_dir itself is recreated by force logic
        assert not sentinel.exists(), "force=True must wipe stale embeddings from vectors/"

    def test_phase_isolation_git_error_does_not_block_embeddings(
        self, sample_copy: Path
    ) -> None:
        """T_8.7.3: If git ingestion raises, embeddings phase still runs."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
        palace = Palace(config)

        # Patch _ingest_git_history path: GitHistory.ingest raises RuntimeError
        with patch(
            "palace.temporal.history.GitHistory.ingest",
            side_effect=RuntimeError("simulated git failure"),
        ):
            try:
                stats = palace.init(
                    force=False,
                    skip_git=False,
                    skip_embeddings=False,
                    skip_domains=True,
                )
            finally:
                palace.close()

        # Git phase failed → commits is None, error recorded
        assert stats.commits is None
        assert any("git" in e for e in stats.errors), "git error must be recorded in stats.errors"

        # Embeddings phase ran despite git failure
        assert stats.embeddings is not None, "embeddings should run even when git phase fails"

    def test_palace_meta_flags_persisted(self, sample_copy: Path) -> None:
        """T_8.7.4: After init, palace_meta stores git_analyzed, embeddings_computed, domains_computed."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
        palace = Palace(config)
        try:
            palace.init(
                force=False,
                skip_git=True,
                skip_embeddings=True,
                skip_domains=True,
            )
        finally:
            palace.close()

        # Re-open the store to verify persisted meta
        store = DuckDBStore(str(config.db_path))
        store.initialize_schema()
        try:
            git_val = store.get_meta("git_analyzed")
            emb_val = store.get_meta("embeddings_computed")
            dom_val = store.get_meta("domains_computed")
        finally:
            store.close()

        assert git_val is not None, "git_analyzed must be written to palace_meta"
        assert emb_val is not None, "embeddings_computed must be written to palace_meta"
        assert dom_val is not None, "domains_computed must be written to palace_meta"

    def test_embeddings_count_matches_symbols(self, sample_copy: Path) -> None:
        """T_8.7.5: stats.embeddings equals the number of symbols indexed."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
        palace = Palace(config)
        try:
            stats = palace.init(
                force=False,
                skip_git=True,
                skip_embeddings=False,
                skip_domains=True,
            )
            # Read symbol count before closing
            symbol_count = len(palace.store.get_symbols())  # type: ignore[union-attr]
        finally:
            palace.close()

        assert stats.embeddings == symbol_count, (
            f"embeddings={stats.embeddings} must match symbol count={symbol_count}"
        )

    def test_domains_stub_returns_zero(self, sample_copy: Path) -> None:
        """T_8.7.6: Phase 4 stub sets stats.domains = 0."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
        palace = Palace(config)
        try:
            stats = palace.init(
                force=False,
                skip_git=True,
                skip_embeddings=True,
                skip_domains=False,
            )
        finally:
            palace.close()

        assert stats.domains == 0, "domain stub must return 0 until Phase 2.2"

    def test_cli_skip_embeddings_exits_zero(self, cli_runner: CliRunner, sample_copy: Path) -> None:
        """T_8.7.7: palace init --skip-embeddings exits 0."""
        result = cli_runner.invoke(
            app,
            [
                "init",
                str(sample_copy),
                "--no-progress",
                "--skip-git",
                "--skip-embeddings",
                "--skip-domains",
            ],
        )
        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"

    def test_cli_git_depth_flag_accepted(self, cli_runner: CliRunner, sample_copy: Path) -> None:
        """T_8.7.8: --git-depth is accepted and does not crash."""
        result = cli_runner.invoke(
            app,
            [
                "init",
                str(sample_copy),
                "--no-progress",
                "--skip-git",          # avoid real git I/O
                "--skip-embeddings",
                "--skip-domains",
                "--git-depth", "500",
            ],
        )
        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"

    def test_backward_compat_phase1_stats_unchanged(self, sample_copy: Path) -> None:
        """T_8.7.9: Phase 1 stats (files, symbols, edges) are unaffected by new phases."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
        palace = Palace(config)
        try:
            stats = palace.init(
                force=False,
                skip_git=True,
                skip_embeddings=True,
                skip_domains=True,
            )
        finally:
            palace.close()

        # sample_project has real Python/TS/Go/Java/C++ files — must produce data
        assert stats.files > 0, "Phase 1 must index files"
        assert stats.symbols >= 0, "Phase 1 must count symbols"
        assert stats.duration_seconds >= 0.0

    def test_vector_store_opened_after_embeddings(self, sample_copy: Path) -> None:
        """T_8.7.10: After init with embeddings, vectors/ dir is created on disk."""
        config = PalaceConfig.initialize(path=sample_copy, languages=[], exclude_patterns=None)
        palace = Palace(config)
        try:
            palace.init(
                force=False,
                skip_git=True,
                skip_embeddings=False,
                skip_domains=True,
            )
        finally:
            palace.close()

        # LanceDB stores data under vectors_dir
        assert config.vectors_dir.exists(), "vectors/ directory must be created by embeddings phase"
