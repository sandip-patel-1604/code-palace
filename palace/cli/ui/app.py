"""PalaceApp — the root Textual application for the explore command."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from palace.cli.ui.screens.domain_map import DomainMapView


class PalaceApp(App):
    """Interactive TUI explorer for a Code Palace index.

    Entry point: instantiate with a live Palace object, then call .run().
    Navigation model:
      - Root view: DomainMapView (domain list)
      - Select domain → FileListScreen (pushed onto stack)
      - Select file   → SymbolDetailScreen (pushed onto stack)
      - / key         → SearchOverlay (pushed onto stack)
      - Escape        → pop_screen() back one level
      - q             → quit
    """

    TITLE = "Code Palace"
    CSS = """
    Screen { background: $surface; }
    #main { height: 1fr; }
    .domain-card { padding: 1; margin: 1; background: $panel; }
    .file-item { padding: 0 1; }
    .symbol-item { padding: 0 2; color: $text-muted; }
    #search-input { dock: top; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("/", "search", "Search"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, palace: object, **kwargs: object) -> None:
        super().__init__(**kwargs)
        # Stored as instance attribute so all screens can reach it via
        # self.app.palace without importing Palace here (avoids circularity).
        self.palace = palace

    def compose(self) -> ComposeResult:
        """Build the root widget tree."""
        yield Header()
        yield DomainMapView(id="main")
        yield Footer()

    def on_list_view_selected(self, event: object) -> None:
        """Delegate domain selection from DomainMapView to FileListScreen."""
        from textual.widgets import ListView

        if not isinstance(event, ListView.Selected):
            return

        # Only handle selections originating from DomainMapView (#main).
        if event.list_view.id != "main":
            return

        domain_map: DomainMapView = self.query_one("#main", DomainMapView)
        item_id = event.item.id or ""
        domain_id = domain_map.domain_ids.get(item_id)
        if domain_id is None:
            return

        from palace.cli.ui.screens.file_list import FileListScreen

        # Extract name from the item label for the screen header.
        from textual.widgets import Static

        statics = event.item.query(Static)
        domain_name = str(statics.first().renderable) if statics else ""
        self.push_screen(FileListScreen(domain_id=domain_id, domain_name=domain_name))

    def action_search(self) -> None:
        """Push the SearchOverlay onto the screen stack."""
        from palace.cli.ui.widgets.search_overlay import SearchOverlay

        self.push_screen(SearchOverlay())

    def action_back(self) -> None:
        """Pop the topmost screen, but never the root."""
        if len(self.screen_stack) > 1:
            self.pop_screen()
