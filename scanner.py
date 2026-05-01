from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field

REQ_CALL_RE = re.compile(r"self\.requires\(\s*['\"]([^'\"]+)['\"]")


@dataclass
class ScannedLibrary:
    name: str
    path: str
    version: str | None
    raw_requirements: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_requirements_txt(path: str) -> list[str]:
    reqs: list[str] = []
    if not os.path.exists(path):
        return reqs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            item = line.strip()
            if not item or item.startswith("#"):
                continue
            reqs.append(item)
    return reqs


def _extract_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def parse_conanfile(conanfile_path: str) -> ScannedLibrary:
    folder = os.path.dirname(conanfile_path)
    default_name = os.path.basename(folder)
    with open(conanfile_path, "r", encoding="utf-8") as f:
        text = f.read()

    warnings: list[str] = []
    name: str | None = None
    version: str | None = None
    requirements: list[str] = []

    try:
        tree = ast.parse(text)
    except SyntaxError:
        warnings.append("Could not parse conanfile.py with AST.")
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "name":
                        parsed = _extract_str(node.value)
                        if parsed:
                            name = parsed
                    if isinstance(target, ast.Name) and target.id == "version":
                        parsed = _extract_str(node.value)
                        if parsed:
                            version = parsed
                    if isinstance(target, ast.Name) and target.id == "requires":
                        val = node.value
                        if isinstance(val, ast.List):
                            for elt in val.elts:
                                parsed = _extract_str(elt)
                                if parsed:
                                    requirements.append(parsed)
                        else:
                            parsed = _extract_str(val)
                            if parsed:
                                requirements.append(parsed)

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "requires":
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        requirements.append(node.args[0].value)
                    else:
                        warnings.append("Could not parse dynamic self.requires call.")

    for match in REQ_CALL_RE.findall(text):
        requirements.append(match)

    if not name:
        warnings.append("Could not detect package name; using folder name.")
        name = default_name

    for req in parse_requirements_txt(os.path.join(folder, "requirements.txt")):
        requirements.append(req)

    deduped = list(dict.fromkeys(requirements))
    return ScannedLibrary(name=name, path=folder, version=version, raw_requirements=deduped, warnings=warnings)


def extract_package_name(reference: str) -> str:
    return reference.split("/", 1)[0].strip()


def scan_roots(scan_roots: list[str]) -> dict[str, ScannedLibrary]:
    scanned: dict[str, ScannedLibrary] = {}
    for root in scan_roots:
        if not root or not os.path.isdir(root):
            continue
        for current, _, files in os.walk(root):
            if "conanfile.py" in files:
                conanfile = os.path.join(current, "conanfile.py")
                lib = parse_conanfile(conanfile)
                scanned[lib.name] = lib
    return scanned
