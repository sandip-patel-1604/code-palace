"""TypeScript symbol extractor using tree-sitter for Code Palace."""

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


def _extract_imports(root_node) -> list[ImportInfo]:  # type: ignore[no-untyped-def]
    """Extract ES module import statements from the program node."""
    imports: list[ImportInfo] = []

    for node in root_node.children:
        if node.type != "import_statement":
            continue

        line = node.start_point[0] + 1
        module_path = ""
        imported_names: list[str] = []

        # Find the module path (string node after 'from')
        for child in node.children:
            if child.type == "string":
                # Get the string_fragment child
                for sub in child.children:
                    if sub.type == "string_fragment":
                        module_path = _node_text(sub)
                        break
                if not module_path:
                    raw = _node_text(child)
                    module_path = raw.strip("'\"`")

        # Find import_clause to determine what's imported
        for child in node.children:
            if child.type == "import_clause":
                # named_imports: { A, B }
                for sub in child.children:
                    if sub.type == "named_imports":
                        for spec in sub.children:
                            if spec.type == "import_specifier":
                                # Could be aliased: A as B — take original name
                                name_node = spec.child_by_field_name("name")
                                if name_node:
                                    imported_names.append(_node_text(name_node))
                                else:
                                    # Fallback: first identifier child
                                    for id_node in spec.children:
                                        if id_node.type == "identifier":
                                            imported_names.append(_node_text(id_node))
                                            break
                    elif sub.type == "namespace_import":
                        # import * as ns from '...'
                        for id_node in sub.children:
                            if id_node.type == "identifier":
                                imported_names.append(f"* as {_node_text(id_node)}")
                                break
                    elif sub.type == "identifier":
                        # import DefaultName from '...'
                        imported_names.append(_node_text(sub))

        if module_path:
            imports.append(
                ImportInfo(
                    module_path=module_path,
                    imported_names=imported_names,
                    line_number=line,
                )
            )

    return imports


def _symbol_from_declaration(
    decl_node,  # type: ignore[no-untyped-def]
    is_exported: bool,
    parent_name: str | None = None,
) -> SymbolInfo | None:
    """Build a SymbolInfo from a top-level declaration node."""
    node_type = decl_node.type

    if node_type == "function_declaration":
        name_node = decl_node.child_by_field_name("name")
        if not name_node:
            return None
        name = _node_text(name_node)
        params_node = decl_node.child_by_field_name("parameters")
        params = _node_text(params_node) if params_node else "()"
        signature = f"{name}{params}"
        return SymbolInfo(
            name=name,
            qualified_name=f"{parent_name}.{name}" if parent_name else name,
            kind=SymbolKind.FUNCTION,
            line_start=decl_node.start_point[0] + 1,
            line_end=decl_node.end_point[0] + 1,
            col_start=decl_node.start_point[1],
            col_end=decl_node.end_point[1],
            signature=signature,
            is_exported=is_exported,
            parent_name=parent_name,
        )

    elif node_type == "class_declaration":
        name_node = decl_node.child_by_field_name("name")
        if not name_node:
            return None
        return SymbolInfo(
            name=_node_text(name_node),
            qualified_name=_node_text(name_node),
            kind=SymbolKind.CLASS,
            line_start=decl_node.start_point[0] + 1,
            line_end=decl_node.end_point[0] + 1,
            col_start=decl_node.start_point[1],
            col_end=decl_node.end_point[1],
            is_exported=is_exported,
            parent_name=parent_name,
        )

    elif node_type == "interface_declaration":
        name_node = decl_node.child_by_field_name("name")
        if not name_node:
            return None
        return SymbolInfo(
            name=_node_text(name_node),
            qualified_name=_node_text(name_node),
            kind=SymbolKind.INTERFACE,
            line_start=decl_node.start_point[0] + 1,
            line_end=decl_node.end_point[0] + 1,
            col_start=decl_node.start_point[1],
            col_end=decl_node.end_point[1],
            is_exported=is_exported,
            parent_name=parent_name,
        )

    elif node_type == "type_alias_declaration":
        name_node = decl_node.child_by_field_name("name")
        if not name_node:
            return None
        return SymbolInfo(
            name=_node_text(name_node),
            qualified_name=_node_text(name_node),
            kind=SymbolKind.TYPE_ALIAS,
            line_start=decl_node.start_point[0] + 1,
            line_end=decl_node.end_point[0] + 1,
            col_start=decl_node.start_point[1],
            col_end=decl_node.end_point[1],
            is_exported=is_exported,
            parent_name=parent_name,
        )

    elif node_type == "enum_declaration":
        name_node = decl_node.child_by_field_name("name")
        if not name_node:
            return None
        return SymbolInfo(
            name=_node_text(name_node),
            qualified_name=_node_text(name_node),
            kind=SymbolKind.ENUM,
            line_start=decl_node.start_point[0] + 1,
            line_end=decl_node.end_point[0] + 1,
            col_start=decl_node.start_point[1],
            col_end=decl_node.end_point[1],
            is_exported=is_exported,
            parent_name=parent_name,
        )

    elif node_type == "lexical_declaration":
        # Handles: const arrowFn = (x) => ...
        for child in decl_node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node and value_node.type == "arrow_function":
                    name = _node_text(name_node)
                    params_node = value_node.child_by_field_name("parameters")
                    params = _node_text(params_node) if params_node else "()"
                    return SymbolInfo(
                        name=name,
                        qualified_name=name,
                        kind=SymbolKind.FUNCTION,
                        line_start=decl_node.start_point[0] + 1,
                        line_end=decl_node.end_point[0] + 1,
                        col_start=decl_node.start_point[1],
                        col_end=decl_node.end_point[1],
                        signature=f"{name}{params}",
                        is_exported=is_exported,
                        parent_name=parent_name,
                    )

    return None


def _extract_methods(class_node, class_name: str) -> list[SymbolInfo]:  # type: ignore[no-untyped-def]
    """Extract method_definition nodes from a class body."""
    methods: list[SymbolInfo] = []
    body_node = class_node.child_by_field_name("body")
    if not body_node:
        return methods

    for child in body_node.children:
        if child.type == "method_definition":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _node_text(name_node)
            params_node = child.child_by_field_name("parameters")
            params = _node_text(params_node) if params_node else "()"
            methods.append(
                SymbolInfo(
                    name=name,
                    qualified_name=f"{class_name}.{name}",
                    kind=SymbolKind.METHOD,
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    col_start=child.start_point[1],
                    col_end=child.end_point[1],
                    signature=f"{name}{params}",
                    is_exported=True,
                    parent_name=class_name,
                )
            )
    return methods


def _extract_symbols(root_node) -> list[SymbolInfo]:  # type: ignore[no-untyped-def]
    """Walk program-level nodes and extract all symbols."""
    symbols: list[SymbolInfo] = []

    for node in root_node.children:
        if node.type == "export_statement":
            # export <declaration>
            # Find the wrapped declaration (skip 'export' keyword and 'default' etc.)
            for child in node.children:
                if child.type in (
                    "function_declaration",
                    "class_declaration",
                    "interface_declaration",
                    "type_alias_declaration",
                    "enum_declaration",
                    "lexical_declaration",
                ):
                    sym = _symbol_from_declaration(child, is_exported=True)
                    if sym:
                        symbols.append(sym)
                        # Extract methods from exported classes
                        if child.type == "class_declaration":
                            symbols.extend(_extract_methods(child, sym.name))

        elif node.type in (
            "function_declaration",
            "class_declaration",
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
            "lexical_declaration",
        ):
            sym = _symbol_from_declaration(node, is_exported=False)
            if sym:
                symbols.append(sym)
                if node.type == "class_declaration":
                    symbols.extend(_extract_methods(node, sym.name))

    return symbols


class TypeScriptExtractor:
    """Extracts symbols and imports from TypeScript source files."""

    language: str = "typescript"
    extensions: list[str] = [".ts", ".tsx"]

    def __init__(self) -> None:
        self._parser = get_parser("typescript")

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
