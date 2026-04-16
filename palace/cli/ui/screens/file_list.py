"""FileListScreen — shows files belonging to a single domain."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static


class FileListScreen(Screen):
    """A full-screen overlay listing all files in a domain.

    Pushed onto the screen stack by PalaceApp when the user selects a domain
    in DomainMapView.  Pressing Escape pops back to the domain map.
    """

    BINDINGS = [
        Binding("escape", "app.back", "Back"),
    ]

    # Map from item id → file_id for the on_list_view_selected handler.
    file_ids: dict[str, int]

    def __init__(self, domain_id: int, domain_name: str = "", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.domain_id = domain_id
        self.domain_name = domain_name or f"Domain {domain_id}"
        self.file_ids = {}

    def compose(self) -> ComposeResult:
        """Build initial widget tree; list is populated in on_mount."""
        yield Header()
        yield ListView(id="file-list")
        yield Footer()

    def on_mount(self) -> None:
        """Populate the file list after mounting."""
        palace = self.app.palace  # type: ignore[attr-defined]
        files: list[dict] = (
            palace.store.get_domain_files(self.domain_id) if palace.store else []
        )
        list_view = self.query_one("#file-list", ListView)

        if not files:
            list_view.mount(
                ListItem(Static("No files in this domain."), id="empty-state")
            )
            return

        for file_record in files:
            file_id: int = file_record["file_id"]
            path: str = file_record.get("path") or f"file {file_id}"
            item_id = f"file-{file_id}"
            self.file_ids[item_id] = file_id
            list_view.mount(
                ListItem(
                    Static(path, classes="file-item"),
                    id=item_id,
                )
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Push SymbolDetailScreen when a file is selected."""
        item_id = event.item.id or ""
        file_id = self.file_ids.get(item_id)
        if file_id is None:
            return
        from palace.cli.ui.screens.symbol_detail import SymbolDetailScreen

        # Derive a display-friendly path label from the item's Static child.
        path_label = ""
        statics = event.item.query(Static)
        if statics:
            path_label = str(statics.first().renderable)

        self.app.push_screen(SymbolDetailScreen(file_id=file_id, file_path=path_label))
