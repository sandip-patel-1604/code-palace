"""Palace configuration — discovery, initialization, and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from palace.core.models import EXTENSION_TO_LANGUAGE, SUPPORTED_LANGUAGES

PALACE_DIR_NAME = ".palace"
CONFIG_FILE_NAME = "config.json"
DB_FILE_NAME = "palace.duckdb"

# Directories always excluded from indexing
DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    ".git",
    ".palace",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".egg-info",
    "vendor",
    ".next",
    "target",
]


@dataclass
class PalaceConfig:
    """Configuration for a Palace instance rooted at a specific directory."""

    root: Path
    palace_dir: Path
    db_path: Path
    languages: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)

    @property
    def vectors_dir(self) -> Path:
        """Path to the LanceDB vectors directory — derived, never serialized."""
        return self.palace_dir / "vectors"

    @classmethod
    def discover(cls, path: Path | None = None) -> PalaceConfig | None:
        """Walk up from `path` to find an existing .palace/ directory.

        Returns None if no palace is found.
        """
        start = (path or Path.cwd()).resolve()
        current = start

        while True:
            palace_dir = current / PALACE_DIR_NAME
            if palace_dir.is_dir():
                config_path = palace_dir / CONFIG_FILE_NAME
                if config_path.exists():
                    data = json.loads(config_path.read_text())
                    return cls(
                        root=current,
                        palace_dir=palace_dir,
                        db_path=palace_dir / DB_FILE_NAME,
                        languages=data.get("languages", []),
                        exclude_patterns=data.get("exclude_patterns", list(DEFAULT_EXCLUDE_PATTERNS)),
                    )
                return cls(
                    root=current,
                    palace_dir=palace_dir,
                    db_path=palace_dir / DB_FILE_NAME,
                )
            parent = current.parent
            if parent == current:
                break
            current = parent

        return None

    @classmethod
    def initialize(
        cls,
        path: Path | None = None,
        languages: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> PalaceConfig:
        """Create .palace/ directory and config.json at the given path."""
        root = (path or Path.cwd()).resolve()
        palace_dir = root / PALACE_DIR_NAME
        palace_dir.mkdir(exist_ok=True)

        excludes = exclude_patterns if exclude_patterns is not None else list(DEFAULT_EXCLUDE_PATTERNS)
        detected = languages if languages is not None else []

        config = cls(
            root=root,
            palace_dir=palace_dir,
            db_path=palace_dir / DB_FILE_NAME,
            languages=detected,
            exclude_patterns=excludes,
        )
        config.save()
        return config

    def save(self) -> None:
        """Persist configuration to config.json."""
        data = {
            "languages": self.languages,
            "exclude_patterns": self.exclude_patterns,
        }
        config_path = self.palace_dir / CONFIG_FILE_NAME
        config_path.write_text(json.dumps(data, indent=2) + "\n")

    def detect_languages(self) -> dict[str, int]:
        """Scan root for files with known extensions. Returns {language: file_count}."""
        counts: dict[str, int] = {}
        exclude_set = set(self.exclude_patterns)

        for file_path in self.root.rglob("*"):
            if not file_path.is_file():
                continue
            # Skip excluded directories
            if any(part in exclude_set for part in file_path.relative_to(self.root).parts):
                continue
            ext = file_path.suffix
            lang = EXTENSION_TO_LANGUAGE.get(ext)
            if lang and lang in SUPPORTED_LANGUAGES:
                counts[lang] = counts.get(lang, 0) + 1

        return counts
