from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_STATUSES = [
    "not_started",
    "in_progress",
    "conanfile_converted",
    "builds_locally",
    "uploaded_to_conan2",
    "consumer_verified",
    "done",
    "blocked",
]


@dataclass
class Library:
    name: str
    path: str
    version: str | None = None
    status: str = "not_started"
    notes: str = ""
    internal_dependencies: list[str] = field(default_factory=list)
    external_dependencies: list[str] = field(default_factory=list)
    raw_requirements: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_done(self) -> bool:
        return self.status == "done"

    @property
    def derived_state(self) -> str:
        if self.is_done:
            return "complete"
        if self.blocked_by:
            return "blocked_by_dependencies"
        return "ready"

    @property
    def is_ready(self) -> bool:
        return self.status not in {"done", "blocked"} and not self.blocked_by


def normalize_status(status: str) -> str:
    if status in VALID_STATUSES:
        return status
    return "not_started"


def to_library(name: str, data: dict[str, Any]) -> Library:
    return Library(
        name=name,
        path=data.get("path", ""),
        version=data.get("version"),
        status=normalize_status(data.get("status", "not_started")),
        notes=data.get("notes", ""),
        internal_dependencies=list(data.get("dependencies", {}).get("internal", [])),
        external_dependencies=list(data.get("dependencies", {}).get("external", [])),
        raw_requirements=list(data.get("raw_requirements", [])),
        warnings=list(data.get("warnings", [])),
    )


def to_progress_dict(lib: Library) -> dict[str, Any]:
    return {
        "path": lib.path,
        "version": lib.version,
        "status": lib.status,
        "notes": lib.notes,
        "dependencies": {
            "internal": lib.internal_dependencies,
            "external": lib.external_dependencies,
        },
        "raw_requirements": lib.raw_requirements,
        "warnings": lib.warnings,
    }
