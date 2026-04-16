"""Main application entry point for sample project."""

from __future__ import annotations

import os
from pathlib import Path

from .service import UserService
from .model import User
from .config import MAX_RETRIES


class Application:
    """Top-level application class."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._service = UserService()

    def run(self) -> int:
        """Start the application.  Returns exit code."""
        return 0

    def _internal_setup(self) -> None:
        """Configure internal state before running."""
        pass


def create_app(name: str) -> Application:
    """Factory function for Application instances."""
    return Application(name)


def _private_helper(x: int) -> int:
    """Not part of public API."""
    return x * 2


app_version = "1.0.0"
_internal_counter = 0
