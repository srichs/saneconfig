from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ConfigError(Exception):
    """Raised when configuration cannot be loaded or coerced."""

    path: str
    expected: str
    value: Any
    source: str
    hint: str | None = None

    def __str__(self) -> str:
        base = (
            f"ConfigError: {self.path} expected {self.expected} but got {self.value!r}\n"
            f"  source: {self.source}"
        )
        if self.hint:
            base += f"\n  hint: {self.hint}"
        return base


@dataclass
class MissingRequiredError(Exception):
    missing_paths: list[str]

    def __str__(self) -> str:
        items = "\n".join(f"  - {p}" for p in self.missing_paths)
        return "ConfigError: missing required configuration values:\n" + items
