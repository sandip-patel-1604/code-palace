"""Java symbol extractor using tree-sitter for Code Palace."""

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


def _get_package(root_node) -> str:  # type: ignore[no-untyped-def]
    """Extract the package name from a program node, or empty string."""
    for child in root_node.children:
        if child.type == "package_declaration":
            for sub in child.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return _node_text(sub)
    return ""


def _has_modifier(modifiers_node, modifier: str) -> bool:  # type: ignore[no-untyped-def]
    """Check whether a modifiers node contains a specific modifier keyword."""
    if modifiers_node is None:
        return False
    for child in modifiers_node.children:
        if _node_text(child) == modifier:
            return True
    return False


def _find_modifiers(node) -> object | None:  # type: ignore[no-untyped-def]
    """Find the modifiers child node by type (not by field name, which is unset)."""
    for child in node.children:
        if child.type == "modifiers":
            return child
    return None


def _is_exported(node) -> bool:  # type: ignore[no-untyped-def]
    """Return True if the node has 'public' in its modifiers."""
    modifiers = _find_modifiers(node)
    return _has_modifier(modifiers, "public")


def _extract_imports(root_node) -> list[ImportInfo]:  # type: ignore[no-untyped-def]
    """Extract import_declaration nodes from a Java program."""
    imports: list[ImportInfo] = []

    for node in root_node.children:
        if node.type != "import_declaration":
            continue

        line = node.start_point[0] + 1
        module_path = ""

        for child in node.children:
            if child.type == "scoped_identifier":
                module_path = _node_text(child)
            elif child.type == "identifier":
                module_path = _node_text(child)

        if module_path:
            # Split last segment as the imported name
            parts = module_path.rsplit(".", 1)
            if len(parts) == 2:
                imports.append(
                    ImportInfo(
                        module_path=parts[0],
                        imported_names=[parts[1]],
                        line_number=line,
                    )
                )
            else:
                imports.append(
                    ImportInfo(
                        module_path=module_path,
                        line_number=line,
                    )
                )

    return imports


def _extract_class_members(
    class_body_node,  # type: ignore[no-untyped-def]
    class_name: str,
    package: str,
) -> list[SymbolInfo]:
    """Extract methods and fields from a Java class body."""
    members: list[SymbolInfo] = []
    qualified_prefix = f"{package}.{class_name}" if package else class_name

    for child in class_body_node.children:
        if child.type == "method_declaration":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _node_text(name_node)
            params_node = child.child_by_field_name("parameters")
            params = _node_text(params_node) if params_node else "()"
            exported = _is_exported(child)

            members.append(
                SymbolInfo(
                    name=name,
                    qualified_name=f"{qualified_prefix}.{name}",
                    kind=SymbolKind.METHOD,
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    col_start=child.start_point[1],
                    col_end=child.end_point[1],
                    signature=f"{name}{params}",
                    is_exported=exported,
                    parent_name=class_name,
                )
            )

        elif child.type == "field_declaration":
            modifiers = _find_modifiers(child)
            is_final = _has_modifier(modifiers, "final")
            exported = _has_modifier(modifiers, "public")

            # A field_declaration may declare multiple variables
            for sub in child.children:
                if sub.type == "variable_declarator":
                    var_name_node = sub.child_by_field_name("name")
                    if var_name_node:
                        var_name = _node_text(var_name_node)
                        kind = SymbolKind.CONSTANT if is_final else SymbolKind.VARIABLE
                        members.append(
                            SymbolInfo(
                                name=var_name,
                                qualified_name=f"{qualified_prefix}.{var_name}",
                                kind=kind,
                                line_start=child.start_point[0] + 1,
                                line_end=child.end_point[0] + 1,
                                col_start=child.start_point[1],
                                col_end=child.end_point[1],
                                is_exported=exported,
                                parent_name=class_name,
                            )
                        )

    return members


def _extract_symbols(root_node, package: str) -> list[SymbolInfo]:  # type: ignore[no-untyped-def]
    """Walk program-level nodes and extract all Java symbols."""
    symbols: list[SymbolInfo] = []

    for node in root_node.children:
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = _node_text(name_node)
            qualified = f"{package}.{name}" if package else name
            exported = _is_exported(node)

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.CLASS,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    is_exported=exported,
                )
            )
            body_node = node.child_by_field_name("body")
            if body_node:
                symbols.extend(_extract_class_members(body_node, name, package))

        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = _node_text(name_node)
            qualified = f"{package}.{name}" if package else name
            exported = _is_exported(node)

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.INTERFACE,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    is_exported=exported,
                )
            )

        elif node.type == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = _node_text(name_node)
            qualified = f"{package}.{name}" if package else name
            exported = _is_exported(node)

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.ENUM,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    is_exported=exported,
                )
            )

    return symbols


class JavaExtractor:
    """Extracts symbols and imports from Java source files."""

    language: str = "java"
    extensions: list[str] = [".java"]

    def __init__(self) -> None:
        self._parser = get_parser("java")

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

            package = _get_package(root)
            result.symbols = _extract_symbols(root, package)
            result.imports = _extract_imports(root)

        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Parse error: {exc}")

        return result
