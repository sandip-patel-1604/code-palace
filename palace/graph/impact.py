"""Impact analysis — blast-radius assessment for files and symbols."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from palace.core.logging import get_logger

if TYPE_CHECKING:
    from palace.storage.duckdb_store import DuckDBStore

logger = get_logger(__name__)


@dataclass
class ImpactResult:
    """Result of a blast-radius analysis."""

    file_id: int
    path: str
    direct_dependents: int = 0
    transitive_dependents: int = 0
    domain_impact: list[dict] = field(default_factory=list)
    cochange_partners: list[dict] = field(default_factory=list)
    ownership: list[dict] = field(default_factory=list)
    churn: dict | None = None
    test_files: list[str] = field(default_factory=list)
    risk: str = "LOW"


class ImpactAnalyzer:
    """Compute blast radius for a file or symbol."""

    def __init__(self, store: DuckDBStore) -> None:
        self._store = store

    def analyze_file(self, file_id: int, depth: int = 10) -> ImpactResult:
        """Full blast-radius analysis for a file."""
        file_row = self._file_for_id(file_id)
        path = file_row["path"] if file_row else ""

        # 1. Dependents
        direct = self._store.get_dependents(file_id, transitive=False)
        transitive = self._store.get_dependents(file_id, transitive=True)

        # 2. Domain impact — unique domains among transitive dependents
        domain_counts: dict[str, int] = {}
        for dep in transitive:
            dom = self._store.get_file_domain(dep["file_id"])
            if dom is not None:
                name = dom["name"]
                domain_counts[name] = domain_counts.get(name, 0) + 1
        domain_impact = [
            {"name": n, "file_count": c}
            for n, c in sorted(domain_counts.items(), key=lambda x: -x[1])
        ]

        # 3. Co-change partners (graceful if no git data)
        try:
            cochange = self._store.get_cochange_pairs(file_id, min_co_commits=2)
        except Exception:
            logger.debug("No cochange data for file_id=%d", file_id)
            cochange = []

        # 4. Ownership (graceful if no git data)
        try:
            ownership = self._store.get_file_ownership(file_id)
        except Exception:
            logger.debug("No ownership data for file_id=%d", file_id)
            ownership = []

        # 5. Churn (graceful if no git data)
        try:
            churn_list = self._store.get_churn(file_id=file_id, days=90)
            churn = churn_list[0] if churn_list else None
        except Exception:
            logger.debug("No churn data for file_id=%d", file_id)
            churn = None

        # 6. Test files among dependents
        test_files = [
            dep["path"] for dep in transitive
            if "test" in dep["path"].lower()
        ]

        # 7. Risk score
        churn_count = churn["change_count"] if churn else 0
        risk = _assess_risk(len(direct), len(transitive), churn_count, len(test_files))

        return ImpactResult(
            file_id=file_id,
            path=path,
            direct_dependents=len(direct),
            transitive_dependents=len(transitive),
            domain_impact=domain_impact,
            cochange_partners=cochange,
            ownership=ownership,
            churn=churn,
            test_files=test_files,
            risk=risk,
        )

    def analyze_symbol(self, file_id: int, symbol_name: str) -> ImpactResult | None:
        """Analyze impact for a specific symbol. Returns None if not found."""
        symbols = self._store.get_symbols(file_id=file_id, name_pattern=symbol_name)
        if not symbols:
            return None
        return self.analyze_file(file_id)

    def _file_for_id(self, file_id: int) -> dict | None:
        """Look up a file row by id via O(1) index lookup."""
        return self._store.get_file_by_id(file_id)


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------


def _assess_risk(direct: int, transitive: int, churn_count: int, test_count: int) -> str:
    """Compute risk level from impact metrics.

    Score components:
      dependents:  min(direct/5, 3)      — up to 3 points
      transitive:  min(transitive/20, 3)  — up to 3 points
      churn:       min(churn/10, 2)       — up to 2 points
      tests:       -min(tests, 2)         — up to -2 points (reduces risk)

    HIGH >= 5, MEDIUM >= 2, else LOW.
    """
    score = (
        min(direct / 5, 3.0)
        + min(transitive / 20, 3.0)
        + min(churn_count / 10, 2.0)
        - min(test_count, 2)
    )
    if score >= 5:
        return "HIGH"
    if score >= 2:
        return "MEDIUM"
    return "LOW"
