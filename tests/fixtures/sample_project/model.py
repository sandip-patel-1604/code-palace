"""Domain model definitions for sample project."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class User:
    """Represents a single user entity."""

    name: str
    email: str
    tags: list[str] = field(default_factory=list)

    def display_name(self) -> str:
        """Return a formatted display name."""
        return f"{self.name} <{self.email}>"


@dataclass
class Group:
    """A named collection of users."""

    title: str
    members: list[User] = field(default_factory=list)
