"""Python symbol extractor using tree-sitter for Code Palace."""

from __future__ import annotations

from pathlib import Path

from tree_sitter_language_pack import get_parser

from palace.core.models import SymbolKind
from palace.parsing.extractors.base import (
    Extractor,
    FileExtraction,
    ImportInfo,
    SymbolInfo,
)


def _node_text(node) -> str:  # type: ignore[no-untyped-def]
    """Decode a tree-sitter node's byte text to a UTF-8 string."""
    return node.text.decode("utf-8") if node.text else ""


def _get_docstring(block_node) -> str | None:  # type: ignore[no-untyped-def]
    """Extract the first string literal from a block as a docstring."""
    for child in block_node.children:
        if child.type == "expression_statement":
            for expr in child.children:
                if expr.type == "string":
                    raw = _node_text(expr)
                    # Strip surrounding quotes (single, double, triple)
                    for q in ('"""', "'''", '"', "'"):
                        if raw.startswith(q) and raw.endswith(q) and len(raw) > 2 * len(q):
                            return raw[len(q) : -len(q)].strip()
                    return raw.strip()
        elif child.type == "string":
            # Direct string child (rare, but handle it)
            raw = _node_text(child)
            for q in ('"""', "'''", '"', "'"):
                if raw.startswith(q) and raw.endswith(q) and len(raw) > 2 * len(q):
                    return raw[len(q) : -len(q)].strip()
    return None


def _build_signature(func_node) -> str:  # type: ignore[no-untyped-def]
    """Build a readable signature string from a function_definition node."""
    name_node = func_node.child_by_field_name("name")
    params_node = func_node.child_by_field_name("parameters")
    return_node = func_node.child_by_field_name("return_type")

    name = _node_text(name_node) if name_node else "?"
    params = _node_text(params_node) if params_node else "()"
    ret = ""
    if return_node:
        ret = f" -> {_node_text(return_node)}"
    return f"{name}{params}{ret}"


def _extract_imports(root_node) -> list[ImportInfo]:  # type: ignore[no-untyped-def]
    """Walk top-level import statements and build ImportInfo records."""
    imports: list[ImportInfo] = []

    for node in root_node.children:
        if node.type == "import_statement":
            # import foo, import foo as bar, import foo.bar
            line = node.start_point[0] + 1
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(
                        ImportInfo(
                            module_path=_node_text(child),
                            imported_names=[],
                            line_number=line,
                        )
                    )
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    module_path = _node_text(name_node) if name_node else ""
                    alias = _node_text(alias_node) if alias_node else None
                    imports.append(
                        ImportInfo(
                            module_path=module_path,
                            imported_names=[],
                            alias=alias,
                            line_number=line,
                        )
                    )

        elif node.type == "import_from_statement":
            line = node.start_point[0] + 1
            is_relative = False
            module_path = ""
            imported_names: list[str] = []

            for child in node.children:
                if child.type == "relative_import":
                    is_relative = True
                    # Collect dot prefix + optional module name
                    dots = ""
                    mod = ""
                    for sub in child.children:
                        if sub.type == "import_prefix":
                            dots = _node_text(sub)
                        elif sub.type == "dotted_name":
                            mod = _node_text(sub)
                    module_path = dots + mod
                elif child.type == "dotted_name":
                    # The module being imported from (absolute)
                    if module_path == "":
                        module_path = _node_text(child)
                    else:
                        # It's a name being imported: dotted_name after 'import'
                        imported_names.append(_node_text(child))
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        imported_names.append(_node_text(name_node))
                elif child.type == "wildcard_import":
                    imported_names.append("*")

            # For `from x import y` — the y is in a dotted_name that appears
            # after `import` keyword; we need to re-scan carefully
            # Re-scan: split on 'import' keyword position
            saw_import_kw = False
            module_path_set = False
            imported_names = []
            for child in node.children:
                if child.type == "from":
                    continue
                if child.type == "import":
                    saw_import_kw = True
                    continue
                if child.type in ("relative_import",) and not saw_import_kw:
                    is_relative = True
                    dots = ""
                    mod = ""
                    for sub in child.children:
                        if sub.type == "import_prefix":
                            dots = _node_text(sub)
                        elif sub.type == "dotted_name":
                            mod = _node_text(sub)
                    module_path = dots + mod
                    module_path_set = True
                elif child.type == "dotted_name" and not saw_import_kw:
                    module_path = _node_text(child)
                    module_path_set = True
                elif child.type == "dotted_name" and saw_import_kw:
                    imported_names.append(_node_text(child))
                elif child.type == "aliased_import" and saw_import_kw:
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        imported_names.append(_node_text(name_node))
                elif child.type == "wildcard_import":
                    imported_names.append("*")

            imports.append(
                ImportInfo(
                    module_path=module_path,
                    imported_names=imported_names,
                    is_relative=is_relative,
                    line_number=line,
                )
            )

    return imports


def _extract_symbols(
    root_node,  # type: ignore[no-untyped-def]
    parent_name: str | None = None,
    is_class_body: bool = False,
) -> list[SymbolInfo]:
    """Recursively extract symbols from a node's children."""
    symbols: list[SymbolInfo] = []

    for node in root_node.children:
        if node.type == "function_definition":
            kind = SymbolKind.METHOD if is_class_body else SymbolKind.FUNCTION
            name_node = node.child_by_field_name("name")
            name = _node_text(name_node) if name_node else ""
            if not name:
                continue

            body_node = node.child_by_field_name("body")
            docstring = _get_docstring(body_node) if body_node else None
            signature = _build_signature(node)
            is_exported = not name.startswith("_")

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=f"{parent_name}.{name}" if parent_name else name,
                    kind=kind,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    signature=signature,
                    docstring=docstring,
                    is_exported=is_exported,
                    parent_name=parent_name,
                )
            )

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            name = _node_text(name_node) if name_node else ""
            if not name:
                continue

            body_node = node.child_by_field_name("body")
            docstring = _get_docstring(body_node) if body_node else None
            is_exported = not name.startswith("_")

            symbols.append(
                SymbolInfo(
                    name=name,
                    qualified_name=f"{parent_name}.{name}" if parent_name else name,
                    kind=SymbolKind.CLASS,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    col_start=node.start_point[1],
                    col_end=node.end_point[1],
                    docstring=docstring,
                    is_exported=is_exported,
                    parent_name=parent_name,
                )
            )
            # Recurse into class body to capture methods
            if body_node:
                nested = _extract_symbols(body_node, parent_name=name, is_class_body=True)
                symbols.extend(nested)

        elif node.type == "assignment" and not is_class_body and parent_name is None:
            # Module-level assignments (variables)
            lhs = node.child_by_field_name("left")
            if lhs and lhs.type == "identifier":
                var_name = _node_text(lhs)
                is_exported = not var_name.startswith("_")
                symbols.append(
                    SymbolInfo(
                        name=var_name,
                        qualified_name=var_name,
                        kind=SymbolKind.VARIABLE,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        col_start=node.start_point[1],
                        col_end=node.end_point[1],
                        is_exported=is_exported,
                    )
                )

        elif node.type == "block":
            # Recurse into block nodes (e.g. function body containing nested defs)
            nested = _extract_symbols(node, parent_name=parent_name, is_class_body=is_class_body)
            symbols.extend(nested)

    return symbols


class PythonExtractor:
    """Extracts symbols and imports from Python source files."""

    language: str = "python"
    extensions: list[str] = [".py", ".pyi"]

    def __init__(self) -> None:
        self._parser = get_parser("python")

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
