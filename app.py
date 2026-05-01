from __future__ import annotations

from pathlib import Path

import yaml
from flask import Flask, jsonify, redirect, render_template, request, url_for

from model import VALID_STATUSES, Library, normalize_status, to_library, to_progress_dict
from scanner import extract_package_name, scan_roots

BASE_DIR = Path(__file__).resolve().parent
PROGRESS_FILE = BASE_DIR / "migration-progress.yml"

app = Flask(__name__)


def load_progress(path: Path = PROGRESS_FILE) -> dict:
    if not path.exists():
        return {"scan_roots": ["D:/code"], "libraries": {}}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("scan_roots", ["D:/code"])
    data.setdefault("libraries", {})
    return data


def save_progress(data: dict, path: Path = PROGRESS_FILE) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def classify_dependencies(libraries: dict[str, Library]) -> None:
    names = set(libraries.keys())
    for lib in libraries.values():
        internal: list[str] = []
        external: list[str] = []
        for req in lib.raw_requirements:
            package = extract_package_name(req)
            if package in names:
                internal.append(package)
            else:
                external.append(req)
        lib.internal_dependencies = sorted(set(internal))
        lib.external_dependencies = sorted(set(external))

    for lib in libraries.values():
        lib.blocked_by = sorted([dep for dep in lib.internal_dependencies if libraries[dep].status != "done"])

    for lib in libraries.values():
        lib.dependents = sorted([name for name, other in libraries.items() if lib.name in other.internal_dependencies])


def detect_cycle(libraries: dict[str, Library]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        visiting.add(node)
        stack.append(node)
        for nxt in libraries[node].internal_dependencies:
            if nxt not in libraries:
                continue
            if nxt in visiting:
                idx = stack.index(nxt)
                return stack[idx:] + [nxt]
            if nxt not in visited:
                found = dfs(nxt)
                if found:
                    return found
        visiting.remove(node)
        visited.add(node)
        stack.pop()
        return None

    for node in libraries:
        if node not in visited:
            found = dfs(node)
            if found:
                return found
    return []


def merge_scan_results(existing_progress: dict, scanned_libraries: dict) -> dict:
    existing_libs = existing_progress.get("libraries", {})
    merged: dict = {}

    for name, scanned in scanned_libraries.items():
        existing = existing_libs.get(name, {})
        status = normalize_status(existing.get("status", "not_started"))
        notes = existing.get("notes", "")
        merged[name] = {
            "path": scanned.path,
            "version": scanned.version,
            "status": status,
            "notes": notes,
            "dependencies": {
                "internal": [],
                "external": [],
            },
            "raw_requirements": scanned.raw_requirements,
            "warnings": scanned.warnings,
        }

    existing_progress["libraries"] = merged
    return existing_progress


def build_libraries(progress: dict) -> tuple[dict[str, Library], list[str]]:
    libraries = {name: to_library(name, data) for name, data in progress.get("libraries", {}).items()}
    classify_dependencies(libraries)
    cycle = detect_cycle(libraries)
    cycle_warning = []
    if cycle:
        cycle_warning = [f"Possible dependency cycle detected: {' -> '.join(cycle)}"]
    return libraries, cycle_warning


def summary(libraries: dict[str, Library]) -> dict:
    ready = [lib for lib in libraries.values() if lib.is_ready]
    blocked_dep = [lib for lib in libraries.values() if lib.derived_state == "blocked_by_dependencies" and lib.status != "done"]
    return {
        "total": len(libraries),
        "done": sum(1 for l in libraries.values() if l.status == "done"),
        "in_progress": sum(1 for l in libraries.values() if l.status == "in_progress"),
        "not_started": sum(1 for l in libraries.values() if l.status == "not_started"),
        "blocked": sum(1 for l in libraries.values() if l.status == "blocked"),
        "ready": len(ready),
        "blocked_by_dependencies": len(blocked_dep),
        "ready_names": sorted([l.name for l in ready]),
    }


@app.get("/")
def index():
    progress = load_progress()
    libraries, cycle_warning = build_libraries(progress)
    filter_by = request.args.get("filter", "all")

    items = list(libraries.values())
    if filter_by == "ready":
        items = [l for l in items if l.is_ready]
    elif filter_by == "blocked":
        items = [l for l in items if l.status == "blocked" or l.derived_state == "blocked_by_dependencies"]
    elif filter_by == "done":
        items = [l for l in items if l.status == "done"]
    elif filter_by == "in_progress":
        items = [l for l in items if l.status == "in_progress"]
    elif filter_by == "not_started":
        items = [l for l in items if l.status == "not_started"]

    items.sort(key=lambda x: x.name)
    return render_template(
        "index.html",
        libraries=items,
        summary=summary(libraries),
        statuses=VALID_STATUSES,
        filter_by=filter_by,
        cycle_warning=cycle_warning,
    )


@app.get("/library/<name>")
def library_detail(name: str):
    progress = load_progress()
    libraries, cycle_warning = build_libraries(progress)
    lib = libraries.get(name)
    if not lib:
        return "Library not found", 404
    return render_template("library.html", lib=lib, libraries=libraries, statuses=VALID_STATUSES, cycle_warning=cycle_warning)


@app.post("/library/<name>/update")
def update_library(name: str):
    progress = load_progress()
    if name not in progress.get("libraries", {}):
        return "Library not found", 404
    status = normalize_status(request.form.get("status", "not_started"))
    notes = request.form.get("notes", "")
    progress["libraries"][name]["status"] = status
    progress["libraries"][name]["notes"] = notes
    save_progress(progress)
    return redirect(url_for("library_detail", name=name))


@app.post("/scan")
def rescan():
    progress = load_progress()
    scanned = scan_roots(progress.get("scan_roots", []))
    progress = merge_scan_results(progress, scanned)

    libraries, _ = build_libraries(progress)
    for name, lib in libraries.items():
        progress["libraries"][name] = to_progress_dict(lib)

    save_progress(progress)
    return redirect(url_for("index"))


@app.get("/graph")
def graph():
    progress = load_progress()
    libraries, cycle_warning = build_libraries(progress)
    lines = ["graph TD"]
    for lib in sorted(libraries.values(), key=lambda l: l.name):
        label = f"{lib.name} [{lib.status}]"
        lines.append(f"    {lib.name}[\"{label}\"]")
        for dep in lib.internal_dependencies:
            lines.append(f"    {lib.name} --> {dep}")
    mermaid = "\n".join(lines)
    return render_template("graph.html", mermaid=mermaid, cycle_warning=cycle_warning)


@app.get("/api/libraries")
def api_libraries():
    progress = load_progress()
    libraries, _ = build_libraries(progress)
    return jsonify({k: to_progress_dict(v) for k, v in libraries.items()})


@app.get("/api/summary")
def api_summary():
    progress = load_progress()
    libraries, _ = build_libraries(progress)
    return jsonify(summary(libraries))


if __name__ == "__main__":
    app.run(debug=True)
