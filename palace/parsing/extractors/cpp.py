"""C++ symbol extractor using tree-sitter for Code Palace."""

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


def _is_static(node) -> bool:  # type: ignore[no-untyped-def]
    """Return True if the node has a 'static' storage-class specifier child."""
    for child in node.children:
        if child.type == "storage_class_specifier" and _node_text(child) == "static":
            return True
    return False


def _find_child_of_type(node, type_name: str):  # type: ignore[no-untyped-def]
    """Return the first child node with the given type, or None."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _extract_includes(root_node) -> list[ImportInfo]:  # type: ignore[no-untyped-def]
    """Walk top-level preproc_include nodes and build ImportInfo records."""
    includes: list[ImportInfo] = []

    for node in root_node.children:
        if node.type != "preproc_include":
            continue

        line = node.start_point[0] + 1

        for child in node.children:
            if child.type == "string_literal":
                # Local include: #include "foo.h"  — find string_content child
                content_node = _find_child_of_type(child, "string_content")
                if content_node:
                    includes.append(
                        ImportInfo(
                            module_path=_node_text(content_node),
                            is_relative=True,
                            line_number=line,
                        )
                    )
            elif child.type == "system_lib_string":
                # System include: #include <iostream>  — strip angle brackets from text
                raw = _node_text(child)
                path = raw.strip("<>")
                includes.append(
                    ImportInfo(
                        module_path=path,
                        is_relative=False,
                        line_number=line,
                    )
                )

    return includes


def _get_function_name_from_declarator(declarator_node) -> str:  # type: ignore[no-untyped-def]
    """Extract the base function name from a function_declarator node.

    Handles both simple identifiers and qualified names (Foo::bar).
    Prefers field_identifier over identifier (class method declarations in AST).
    """
    for child in declarator_node.children:
        if child.type in ("identifier", "field_identifier"):
            return _node_text(child)
        elif child.type == "qualified_identifier":
            # e.g. Application::run — return just the last segment
            name_child = _find_child_of_type(child, "identifier")
            if not name_child:
                name_child = _find_child_of_type(child, "field_identifier")
            if name_child:
                return _node_text(name_child)
    return ""


def _extract_symbols(
    node,  # type: ignore[no-untyped-def]
    namespace: str | None = None,
    parent_name: str | None = None,
    inside_class: bool = False,
) -> list[SymbolInfo]:
    """Recursively extract C++ symbols from a node's children.

    Parameters
    ----------
    node:
        Tree-sitter node whose children to inspect.
    namespace:
        Accumulated namespace prefix for qualified_name building, e.g. "app".
    parent_name:
        Unqualified name of the enclosing class/struct for METHOD attribution.
    inside_class:
        True when we are iterating inside a field_declaration_list — changes
        how function declarations are classified and named.
    """
    symbols: list[SymbolInfo] = []

    for child in node.children:
        # ------------------------------------------------------------------ #
        # namespace_definition  →  recurse into declaration_list              #
        # ------------------------------------------------------------------ #
        if child.type == "namespace_definition":
            ns_id_node = _find_child_of_type(child, "namespace_identifier")
            ns_name = _node_text(ns_id_node) if ns_id_node else ""
            new_ns = f"{namespace}::{ns_name}" if namespace else ns_name
            body = _find_child_of_type(child, "declaration_list")
            if body:
                symbols.extend(
                    _extract_symbols(
                        body,
                        namespace=new_ns,
                        parent_name=parent_name,
                        inside_class=False,
                    )
                )

        # ------------------------------------------------------------------ #
        # class_specifier  →  CLASS symbol, recurse into field_declaration_list
        # ------------------------------------------------------------------ #
        elif child.type == "class_specifier":
            name_node = _find_child_of_type(child, "type_identifier")
            if not name_node:
                continue
            name = _node_text(name_node)
            if not name:
                continue

            qualified = f"{namespace}::{name}" if namespace else name
            exported = not _is_static(child)

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.CLASS,
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    col_start=child.start_point[1],
                    col_end=child.end_point[1],
                    is_exported=exported,
                    parent_name=parent_name,
                )
            )

            # Recurse into field_declaration_list to get methods
            body = _find_child_of_type(child, "field_declaration_list")
            if body:
                symbols.extend(
                    _extract_symbols(
                        body,
                        namespace=namespace,
                        parent_name=name,
                        inside_class=True,
                    )
                )

        # ------------------------------------------------------------------ #
        # struct_specifier  →  STRUCT symbol, recurse into body               #
        # ------------------------------------------------------------------ #
        elif child.type == "struct_specifier":
            name_node = _find_child_of_type(child, "type_identifier")
            if not name_node:
                continue
            name = _node_text(name_node)
            if not name:
                continue

            qualified = f"{namespace}::{name}" if namespace else name
            exported = not _is_static(child)

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.STRUCT,
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    col_start=child.start_point[1],
                    col_end=child.end_point[1],
                    is_exported=exported,
                    parent_name=parent_name,
                )
            )

            # Recurse into field_declaration_list for any nested members
            body = _find_child_of_type(child, "field_declaration_list")
            if body:
                symbols.extend(
                    _extract_symbols(
                        body,
                        namespace=namespace,
                        parent_name=name,
                        inside_class=True,
                    )
                )

        # ------------------------------------------------------------------ #
        # enum_specifier  →  ENUM symbol                                       #
        # ------------------------------------------------------------------ #
        elif child.type == "enum_specifier":
            name_node = _find_child_of_type(child, "type_identifier")
            if not name_node:
                continue
            name = _node_text(name_node)
            if not name:
                continue

            qualified = f"{namespace}::{name}" if namespace else name

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.ENUM,
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    col_start=child.start_point[1],
                    col_end=child.end_point[1],
                    is_exported=not _is_static(child),
                    parent_name=parent_name,
                )
            )

        # ------------------------------------------------------------------ #
        # template_declaration  →  unwrap and recurse on the inner child       #
        # ------------------------------------------------------------------ #
        elif child.type == "template_declaration":
            # The last meaningful child is usually function_definition or
            # class_specifier — just recurse treating template_declaration as
            # a transparent wrapper.
            symbols.extend(
                _extract_symbols(
                    child,
                    namespace=namespace,
                    parent_name=parent_name,
                    inside_class=inside_class,
                )
            )

        # ------------------------------------------------------------------ #
        # function_definition  →  FUNCTION (top-level) or METHOD (in class)   #
        # ------------------------------------------------------------------ #
        elif child.type == "function_definition":
            decl_node = _find_child_of_type(child, "function_declarator")
            if not decl_node:
                continue
            name = _get_function_name_from_declarator(decl_node)
            if not name:
                continue

            kind = SymbolKind.METHOD if inside_class else SymbolKind.FUNCTION
            # Qualified names for out-of-line definitions use the namespace prefix;
            # parent_name is the enclosing class if inside_class=True.
            qualified = f"{namespace}::{name}" if namespace else name
            signature = _node_text(decl_node)
            exported = not _is_static(child)

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=kind,
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    col_start=child.start_point[1],
                    col_end=child.end_point[1],
                    signature=signature,
                    is_exported=exported,
                    parent_name=parent_name,
                )
            )

        # ------------------------------------------------------------------ #
        # declaration  →  forward-declared FUNCTION or module-level CONSTANT  #
        # ------------------------------------------------------------------ #
        elif child.type == "declaration":
            _process_declaration(child, symbols, namespace, parent_name, inside_class)

        # ------------------------------------------------------------------ #
        # field_declaration  →  METHOD (in class body) or skip data members   #
        # ------------------------------------------------------------------ #
        elif child.type == "field_declaration" and inside_class:
            decl_node = _find_child_of_type(child, "function_declarator")
            if not decl_node:
                # Data member — not a method, skip
                continue
            # field_identifier is the name in a class context
            name = ""
            for sub in decl_node.children:
                if sub.type == "field_identifier":
                    name = _node_text(sub)
                    break
            if not name:
                name = _get_function_name_from_declarator(decl_node)
            if not name:
                continue

            qualified = f"{namespace}::{name}" if namespace else name
            signature = _node_text(decl_node)

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=SymbolKind.METHOD,
                    line_start=child.start_point[0] + 1,
                    line_end=child.end_point[0] + 1,
                    col_start=child.start_point[1],
                    col_end=child.end_point[1],
                    signature=signature,
                    is_exported=not _is_static(child),
                    parent_name=parent_name,
                )
            )

    return symbols


def _process_declaration(
    node,  # type: ignore[no-untyped-def]
    symbols: list[SymbolInfo],
    namespace: str | None,
    parent_name: str | None,
    inside_class: bool,
) -> None:
    """Handle a declaration node — either a forward-declared function or a constant."""
    # Case 1: forward-declared function (function_declarator child present, no body)
    decl_node = _find_child_of_type(node, "function_declarator")
    if decl_node:
        name = _get_function_name_from_declarator(decl_node)
        if name:
            kind = SymbolKind.METHOD if inside_class else SymbolKind.FUNCTION
            qualified = f"{namespace}::{name}" if namespace else name
            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=qualified,
                    kind=kind,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    signature=_node_text(decl_node),
                    is_exported=not _is_static(node),
                    parent_name=parent_name,
                )
            )
        return

    # Case 2: module-level const declaration with init_declarator
    if inside_class or parent_name is not None:
        return  # Only handle module/namespace-level constants

    # Check for const qualifier
    has_const = any(
        child.type == "type_qualifier" and _node_text(child) == "const"
        for child in node.children
    )
    if not has_const:
        return

    init_decl = _find_child_of_type(node, "init_declarator")
    if not init_decl:
        return

    name_node = _find_child_of_type(init_decl, "identifier")
    if not name_node:
        return
    name = _node_text(name_node)
    if not name:
        return

    qualified = f"{namespace}::{name}" if namespace else name
    symbols.append(
        SymbolInfo(
            name=name,
            qualified_name=qualified,
            kind=SymbolKind.CONSTANT,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            col_start=node.start_point[1],
            col_end=node.end_point[1],
            is_exported=True,
            parent_name=parent_name,
        )
    )


class CppExtractor:
    """Extracts symbols and imports from C++ source files."""

    language: str = "cpp"
    extensions: list[str] = [".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hxx"]

    def __init__(self) -> None:
        self._parser = get_parser("cpp")

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
            result.imports = _extract_includes(root)

        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Parse error: {exc}")

        return result
