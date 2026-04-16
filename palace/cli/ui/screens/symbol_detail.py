"""SymbolDetailScreen — lists all symbols defined in a single file."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, Static


class SymbolDetailScreen(Screen):
    """A full-screen overlay showing symbols defined in one file.

    Pushed by FileListScreen when the user selects a file.  Each row shows
    name, kind, line range, and signature so the developer can orient quickly.
    """

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
    ]

    def __init__(
        self,
        file_id: int,
        file_path: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.file_id = file_id
        self.file_path = file_path or f"file {file_id}"

    def compose(self) -> ComposeResult:
        """Build initial widget tree; symbols are populated in on_mount."""
        yield Header()
        yield ListView(id="symbol-list")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the symbol list after mounting."""
        palace = self.app.palace  # type: ignore[attr-defined]
        symbols: list[dict] = (
            palace.store.get_symbols(file_id=self.file_id) if palace.store else []
        )
        list_view = self.query_one("#symbol-list", ListView)

        if not symbols:
            list_view.mount(
                ListItem(Static("No symbols found in this file."), id="empty-state")
            )
            return

        for sym in symbols:
            name: str = sym.get("name") or "<unnamed>"
            kind: str = sym.get("kind") or "?"
            line_start: int | None = sym.get("line_start")
            line_end: int | None = sym.get("line_end")
            signature: str = sym.get("signature") or ""

            # Build a compact one-line label.
            line_range = (
                f"L{line_start}-{line_end}"
                if line_start is not None and line_end is not None
                else ""
            )
            label_parts = [f"{kind}  {name}"]
            if line_range:
                label_parts.append(line_range)
            if signature:
                # Truncate long signatures to keep rows readable.
                sig_display = signature[:60] + "…" if len(signature) > 60 else signature
                label_parts.append(sig_display)

            label_text = "  │  ".join(label_parts)
            list_view.mount(
                ListItem(
                    Static(label_text, classes="symbol-item"),
                    id=f"sym-{sym.get('symbol_id', name)}",
                )
            )
