"""User service for sample project."""

from __future__ import annotations

from .model import User


class UserService:
    """Service layer for User domain operations."""

    def __init__(self) -> None:
        self._users: list[User] = []

    def add_user(self, user: User) -> None:
        """Add a user to the service."""
        self._users.append(user)

    def get_user(self, name: str) -> User | None:
        """Retrieve a user by name.  Returns None if not found."""
        for user in self._users:
            if user.name == name:
                return user
        return None

    def _validate(self, user: User) -> bool:
        """Internal validation — not exported."""
        return bool(user.name)
