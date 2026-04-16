"""DomainMapView — lists all domain clusters in a scrollable ListView."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Label, ListItem, ListView, Static


class DomainMapView(ListView):
    """Shows all indexed domains as clickable list items.

    Queries palace.store.get_domains() on mount.  Each item carries the
    domain_id as metadata so the parent app can push a FileListScreen.
    Displays an empty-state message when no domains have been indexed.
    """

    # Map from widget id → domain_id, populated during mount so the
    # on_list_view_selected handler in PalaceApp can look up the domain.
    domain_ids: dict[str, int]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.domain_ids = {}

    def on_mount(self) -> None:
        """Populate the list from the store after the widget is attached."""
        # self.app.palace is set by PalaceApp before compose runs.
        palace = self.app.palace  # type: ignore[attr-defined]
        domains: list[dict] = palace.store.get_domains() if palace.store else []

        if not domains:
            self.mount(
                ListItem(
                    Static("No domains found. Run palace init."),
                    id="empty-state",
                )
            )
            return

        for domain in domains:
            domain_id: int = domain["domain_id"]
            name: str = domain.get("name") or f"Domain {domain_id}"
            # Fetch file count for this domain from the store.
            files = palace.store.get_domain_files(domain_id)
            file_count = len(files)
            item_id = f"domain-{domain_id}"
            self.domain_ids[item_id] = domain_id
            self.mount(
                ListItem(
                    Static(f"{name}  [{file_count} files]", classes="domain-card"),
                    id=item_id,
                )
            )
