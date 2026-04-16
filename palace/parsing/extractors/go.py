"""Go symbol extractor using tree-sitter for Code Palace."""

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


def _is_exported(name: str) -> bool:
    """In Go, identifiers starting with uppercase are exported."""
    return bool(name) and name[0].isupper()


def _extract_imports(root_node) -> list[ImportInfo]:  # type: ignore[no-untyped-def]
    """Extract import declarations from a Go source file."""
    imports: list[ImportInfo] = []

    for node in root_node.children:
        if node.type != "import_declaration":
            continue

        line = node.start_point[0] + 1

        for child in node.children:
            if child.type == "import_spec_list":
                # grouped: import ( "a" "b" )
                for spec in child.children:
                    if spec.type == "import_spec":
                        path = _extract_import_path(spec)
                        if path:
                            alias = _extract_import_alias(spec)
                            imports.append(
                                ImportInfo(
                                    module_path=path,
                                    alias=alias,
                                    line_number=line,
                                )
                            )
            elif child.type == "import_spec":
                # single: import "foo"
                path = _extract_import_path(child)
                if path:
                    alias = _extract_import_alias(child)
                    imports.append(
                        ImportInfo(
                            module_path=path,
                            alias=alias,
                            line_number=line,
                        )
                    )

    return imports


def _extract_import_path(spec_node) -> str:  # type: ignore[no-untyped-def]
    """Get the string path from an import_spec node."""
    for child in spec_node.children:
        if child.type == "interpreted_string_literal":
            raw = _node_text(child)
            return raw.strip('"')
    return ""


def _extract_import_alias(spec_node) -> str | None:  # type: ignore[no-untyped-def]
    """Get the alias (dot or identifier) from an import_spec, if present."""
    for child in spec_node.children:
        if child.type == "package_identifier":
            text = _node_text(child)
            if text == ".":
                return "."
            return text
    return None


def _get_receiver_type(method_node) -> str | None:  # type: ignore[no-untyped-def]
    """Extract the receiver type name from a method_declaration."""
    # First parameter_list is the receiver: (u *User) or (u User)
    receiver_list = None
    for child in method_node.children:
        if child.type == "parameter_list":
            receiver_list = child
            break

    if not receiver_list:
        return None

    for child in receiver_list.children:
        if child.type == "parameter_declaration":
            for sub in child.children:
                if sub.type == "type_identifier":
                    return _node_text(sub)
                elif sub.type == "pointer_type":
                    for ptr_child in sub.children:
                        if ptr_child.type == "type_identifier":
                            return _node_text(ptr_child)
    return None


def _extract_symbols(root_node) -> list[SymbolInfo]:  # type: ignore[no-untyped-def]
    """Walk source_file nodes and extract all Go symbols."""
    symbols: list[SymbolInfo] = []

    for node in root_node.children:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = _node_text(name_node)
            params_node = node.child_by_field_name("parameters")
            params = _node_text(params_node) if params_node else "()"
            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=name,
                    kind=SymbolKind.FUNCTION,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    signature=f"func {name}{params}",
                    is_exported=_is_exported(name),
                )
            )

        elif node.type == "method_declaration":
            # field_identifier is the method name in Go's AST
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = _node_text(name_node)
            receiver_type = _get_receiver_type(node)
            params_node = node.child_by_field_name("parameters")
            params = _node_text(params_node) if params_node else "()"
            qualified = f"{receiver_type}.{name}" if receiver_type else name
            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.METHOD,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    signature=f"func ({receiver_type}) {name}{params}",
                    is_exported=_is_exported(name),
                    parent_name=receiver_type,
                )
            )

        elif node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    _process_type_spec(child, symbols)

        elif node.type == "const_declaration":
            line = node.start_point[0] + 1
            for child in node.children:
                if child.type == "const_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = _node_text(name_node)
                        symbols.append(
                            SymbolInfo(
                                name=name,
                                qualified_name=name,
                                kind=SymbolKind.CONSTANT,
                                line_start=node.start_point[0] + 1,
                                line_end=node.end_point[0] + 1,
                                col_start=node.start_point[1],
                                col_end=node.end_point[1],
                                is_exported=_is_exported(name),
                            )
                        )

        elif node.type == "var_declaration":
            for child in node.children:
                if child.type == "var_spec":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = _node_text(name_node)
                        symbols.append(
                            SymbolInfo(
                                name=name,
                                qualified_name=name,
                                kind=SymbolKind.VARIABLE,
                                line_start=node.start_point[0] + 1,
                                line_end=node.end_point[0] + 1,
                                col_start=node.start_point[1],
                                col_end=node.end_point[1],
                                is_exported=_is_exported(name),
                            )
                        )

    return symbols


def _process_type_spec(type_spec_node, symbols: list[SymbolInfo]) -> None:  # type: ignore[no-untyped-def]
    """Process a type_spec and append the appropriate SymbolInfo."""
    name_node = type_spec_node.child_by_field_name("name")
    if not name_node:
        return

    name = _node_text(name_node)

    # Determine kind from the type body
    kind = SymbolKind.TYPE_ALIAS
    for child in type_spec_node.children:
        if child.type == "struct_type":
            kind = SymbolKind.STRUCT
            break
        elif child.type == "interface_type":
            kind = SymbolKind.INTERFACE
            break

    symbols.append(
        SymbolInfo(
            name=name,
            qualified_name=name,
            kind=kind,
            line_start=type_spec_node.start_point[0] + 1,
            line_end=type_spec_node.end_point[0] + 1,
            col_start=type_spec_node.start_point[1],
            col_end=type_spec_node.end_point[1],
            is_exported=_is_exported(name),
        )
    )


class GoExtractor:
    """Extracts symbols and imports from Go source files."""

    language: str = "go"
    extensions: list[str] = [".go"]

    def __init__(self) -> None:
        self._parser = get_parser("go")

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
