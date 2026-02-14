from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoadReport:
    """Resolved values + where they came from (per dotted path)."""

    sources_by_path: dict[str, str]
    values_by_path: dict[str, Any]

    def source_of(self, path: str) -> str | None:
        return self.sources_by_path.get(path)

    def value_of(self, path: str) -> Any:
        return self.values_by_path.get(path)

    def to_lines(self) -> list[str]:
        lines: list[str] = []
        for path in sorted(self.values_by_path.keys()):
            v = self.values_by_path[path]
            src = self.sources_by_path.get(path, "unknown")
            lines.append(f"{path}={v!r} ({src})")
        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_lines())
