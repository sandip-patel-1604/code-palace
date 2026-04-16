"""SearchOverlay — floating search input with live results."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from palace.cli.ui.screens.symbol_detail import SymbolDetailScreen


class SearchOverlay(Screen):
    """A full-screen search overlay.

    Activated by pressing / in PalaceApp.  Submitting the input runs a
    SemanticSearch (if embeddings are available) or falls back to a name-glob
    keyword search against the DuckDB store.  Selecting a result navigates to
    the SymbolDetailScreen for the matching file.
    """

    BINDINGS = [
        Binding("escape", "app.back", "Close search"),
    ]

    def compose(self) -> ComposeResult:
        """Build the search overlay layout."""
        yield Header()
        yield Input(placeholder="Search symbols…", id="search-input")
        yield ListView(id="search-results")
        yield Footer()

    # Store item-id → file_id mapping so we can navigate on selection.
    _result_file_ids: dict[str, int]

    def on_mount(self) -> None:
        """Initialise result map and focus the input."""
        self._result_file_ids = {}
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Run a search when the user presses Enter."""
        query = event.value.strip()
        if not query:
            return
        self._run_search(query)

    def _run_search(self, query: str) -> None:
        """Execute semantic search if available, else keyword fallback."""
        palace = self.app.palace  # type: ignore[attr-defined]
        results: list[dict] = []

        # Attempt semantic search first; fall back to keyword if unavailable.
        if palace.vector_store is not None:
            try:
                from palace.semantic.embeddings import MockEmbeddingEngine
                from palace.semantic.search import SemanticSearch

                engine = MockEmbeddingEngine()
                searcher = SemanticSearch(palace.vector_store, engine)
                if searcher.available():
                    results = searcher.search(query, limit=20)
            except Exception:  # noqa: BLE001
                results = []

        if not results and palace.store is not None:
            # Keyword fallback: SQL LIKE search on symbol names.
            results = palace.store.get_symbols(name_pattern=f"%{query}%")

        self._render_results(results)

    def _render_results(self, results: list[dict]) -> None:
        """Clear the list and re-populate with new results."""
        list_view = self.query_one("#search-results", ListView)
        list_view.clear()
        self._result_file_ids = {}

        if not results:
            list_view.mount(ListItem(Static("No results found."), id="no-results"))
            return

        for idx, sym in enumerate(results):
            name: str = sym.get("name") or "<unnamed>"
            kind: str = sym.get("kind") or "?"
            file_id: int | None = sym.get("file_id")
            # SemanticSearch returns file_path; store returns file_id.
            file_path: str = sym.get("file_path") or ""
            item_id = f"result-{idx}"
            label = f"{kind}  {name}"
            if file_path:
                label += f"  —  {file_path}"
            list_view.mount(
                ListItem(Static(label, classes="file-item"), id=item_id)
            )
            if file_id is not None:
                self._result_file_ids[item_id] = file_id

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Navigate to the file/symbol when a result is selected."""
        item_id = event.item.id or ""
        file_id = self._result_file_ids.get(item_id)
        if file_id is None:
            return
        # Pop self off first, then push detail so back returns to domain map.
        self.app.pop_screen()
        self.app.push_screen(SymbolDetailScreen(file_id=file_id))
