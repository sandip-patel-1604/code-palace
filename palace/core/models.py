"""Core domain models and enumerations for Code Palace."""

from __future__ import annotations

from enum import StrEnum


class SymbolKind(StrEnum):
    """Types of symbols extracted from source code ASTs."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"
    STRUCT = "struct"
    VARIABLE = "variable"
    CONSTANT = "constant"
    PROPERTY = "property"
    DECORATOR = "decorator"
    MODULE = "module"


class EdgeType(StrEnum):
    """Types of relationships between files and symbols."""

    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    CONTAINS = "contains"
    NESTS = "nests"
    REFERENCES = "references"
    EXPORTS = "exports"
    TYPE_REFERENCES = "type_ref"


# Map file extensions to language names
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
}

SUPPORTED_LANGUAGES: set[str] = {"python", "typescript", "javascript", "go", "java", "cpp"}
