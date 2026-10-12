#!/usr/bin/env python3
"""Generate and validate a local, dependency-free project architecture map."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ANALYZER_VERSION = "0.3.0"
DEFAULT_MAP = Path(".project-map/project-map.md")
MAX_TREE_FILES = 500
MAX_RELATIONSHIPS = 500
MAX_SYMBOLS = 800
MAX_DEPENDENCY_NODES = 800
MAX_DEPENDENCY_DEPTH = 30
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".tox", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".project-map",
    "dist", "build",
}
PYTHON_SUFFIXES = {".py", ".pyi"}
JAVASCRIPT_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs"}
TYPESCRIPT_SUFFIXES = {".ts", ".tsx"}
SHELL_SUFFIXES = {".sh", ".bash", ".zsh", ".fish"}
SYSTEMD_SUFFIXES = {
    ".service", ".socket", ".timer", ".target", ".mount", ".path",
}
SOURCE_SUFFIXES = (
    PYTHON_SUFFIXES | JAVASCRIPT_SUFFIXES | TYPESCRIPT_SUFFIXES
    | SHELL_SUFFIXES | SYSTEMD_SUFFIXES
)
IMPORTANT_FILES = {
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "package.json",
    "tsconfig.json", "Cargo.toml", "manage.py", "Dockerfile", "Makefile",
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "CMakeLists.txt", "go.mod", "go.sum", "pom.xml", "build.gradle",
    "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "Procfile",
}
VERSION_FILES = ("pyproject.toml", "package.json", "Cargo.toml")


@dataclass
class Symbol:
    kind: str
    name: str
    line: int
    end_line: int
    children: list["Symbol"] = field(default_factory=list)
    doc: str = ""


@dataclass
class FileInfo:
    path: str
    size: int
    digest: str
    language: str
    imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    parse_error: str | None = None


def symbol_to_record(symbol: Symbol) -> dict:
    return {
        "kind": symbol.kind,
        "name": symbol.name,
        "line": symbol.line,
        "end_line": symbol.end_line,
        "children": [symbol_to_record(child) for child in symbol.children],
        "doc": symbol.doc,
    }


def symbol_from_record(record: object) -> Symbol | None:
    if not isinstance(record, dict):
        return None
    kind = record.get("kind")
    name = record.get("name")
    line = record.get("line")
    end_line = record.get("end_line")
    children = record.get("children", [])
    doc = record.get("doc", "")
    if not (
        isinstance(kind, str)
        and isinstance(name, str)
        and isinstance(line, int)
        and isinstance(end_line, int)
        and isinstance(children, list)
        and isinstance(doc, str)
    ):
        return None
    converted_children = [symbol_from_record(child) for child in children]
    if any(child is None for child in converted_children):
        return None
    return Symbol(kind, name, line, end_line, converted_children, doc)


def file_to_record(info: FileInfo) -> dict:
    return {
        "sha256": info.digest,
        "size": info.size,
        "language": info.language,
        "imports": info.imports,
        "symbols": [symbol_to_record(symbol) for symbol in info.symbols],
        "parse_error": info.parse_error,
    }


def file_from_record(path: str, record: object) -> FileInfo | None:
    if not isinstance(record, dict):
        return None
    digest_value = record.get("sha256")
    size = record.get("size")
    language = record.get("language")
    imports = record.get("imports")
    symbols = record.get("symbols")
    parse_error = record.get("parse_error")
    if not (
        isinstance(digest_value, str)
        and isinstance(size, int)
        and isinstance(language, str)
        and isinstance(imports, list)
        and all(isinstance(item, str) for item in imports)
        and isinstance(symbols, list)
        and (parse_error is None or isinstance(parse_error, str))
    ):
        return None
    converted_symbols = [symbol_from_record(symbol) for symbol in symbols]
    if any(symbol is None for symbol in converted_symbols):
        return None
    return FileInfo(
        path,
        size,
        digest_value,
        language,
        list(imports),
        converted_symbols,
        parse_error,
    )


def run_git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def git_files(root: Path) -> list[str] | None:
    output = run_git(root, "ls-files", "-co", "--exclude-standard", "-z")
    if output is None:
        return None
    # Git's -z output is not representable as text when a filename contains a
    # surrogate. Such a file is not useful input for this human-facing map.
    return [item for item in output.split("\0") if item]


def discover_files(root: Path) -> list[Path]:
    tracked = git_files(root)
    if tracked is not None:
        candidates = [root / item for item in tracked]
    else:
        candidates = []
        for current, dirs, names in os.walk(root):
            dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
            candidates.extend(Path(current, name) for name in names)
    selected = []
    for path in candidates:
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if (
            path.suffix.lower() in SOURCE_SUFFIXES
            or path.name in IMPORTANT_FILES
            or is_shell_script(path)
        ):
            selected.append(path)
    return sorted(selected, key=lambda item: item.relative_to(root).as_posix())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_shell_script(path: Path) -> bool:
    if path.suffix:
        return False
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(160).lower()
    except OSError:
        return False
    return first_line.startswith(b"#!") and bool(
        re.search(rb"(?:^|[/\s])(?:sh|bash|zsh|fish)(?:\s|$)", first_line)
    )


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def source_fingerprint(files: list[FileInfo]) -> str:
    hasher = hashlib.sha256()
    for info in sorted(files, key=lambda item: item.path):
        hasher.update(info.path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(info.digest.encode("ascii"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def project_versions(root: Path) -> dict[str, str]:
    """Read declared project versions without importing project code."""
    versions = {}
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(read_text(pyproject))
            version = data.get("project", {}).get("version")
            if isinstance(version, str):
                versions["pyproject.toml"] = version
        except (tomllib.TOMLDecodeError, OSError):
            versions["pyproject.toml"] = "<unreadable>"
    package = root / "package.json"
    if package.is_file():
        try:
            data = json.loads(read_text(package))
            version = data.get("version")
            if isinstance(version, str):
                versions["package.json"] = version
        except (json.JSONDecodeError, OSError):
            versions["package.json"] = "<unreadable>"
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        try:
            data = tomllib.loads(read_text(cargo))
            version = data.get("package", {}).get("version")
            if isinstance(version, str):
                versions["Cargo.toml"] = version
        except (tomllib.TOMLDecodeError, OSError):
            versions["Cargo.toml"] = "<unreadable>"
    return versions


def clean_doc(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().split())[:180]


def python_symbols(tree: ast.AST) -> list[Symbol]:
    def convert(node: ast.AST) -> Symbol | None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async function" if isinstance(node, ast.AsyncFunctionDef) else "function"
        elif isinstance(node, ast.ClassDef):
            kind = "class"
        else:
            return None
        children = []
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                converted = convert(child)
                if converted:
                    children.append(converted)
        return Symbol(kind, node.name, node.lineno, getattr(node, "end_lineno", node.lineno), children,
                      clean_doc(ast.get_docstring(node)))

    return [item for node in tree.body if (item := convert(node))]


def python_imports(tree: ast.AST) -> list[str]:
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            if node.module is None:
                values.extend(prefix + alias.name for alias in node.names)
            else:
                values.append(prefix)
    return sorted(set(values))


JS_MODULE_RE = re.compile(
    r"(?:import|export)\s+(?:[^;\n]*?\s+from\s+)?['\"]([^'\"]+)['\"]"
)
JS_REQUIRE_RE = re.compile(r"(?:require|import)\(\s*['\"]([^'\"]+)['\"]\s*\)")
EXPORT_RE = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)", re.MULTILINE)
FUNCTION_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE)
CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", re.MULTILINE)


def line_for(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def javascript_data(text: str) -> tuple[list[str], list[Symbol]]:
    imports = {match.group(1) for match in JS_MODULE_RE.finditer(text)}
    imports.update(match.group(1) for match in JS_REQUIRE_RE.finditer(text))
    symbols = []
    seen = set()
    for pattern, kind in ((CLASS_RE, "class"), (FUNCTION_RE, "function"), (EXPORT_RE, "export")):
        for match in pattern.finditer(text):
            name = match.group(1)
            key = (name, line_for(text, match.start()))
            if key in seen:
                continue
            seen.add(key)
            line = key[1]
            symbols.append(Symbol(kind, name, line, line))
    return sorted(imports), sorted(symbols, key=lambda item: (item.line, item.name))


SHELL_FUNCTION_RE = re.compile(
    r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\s*\))?\s*\{",
    re.MULTILINE,
)
SHELL_COMMANDS = {"sh", "bash", "zsh", "fish"}
SYSTEMD_RELATION_KEYS = {"After", "Before", "Wants", "Requires", "Unit"}
SYSTEMD_EXEC_KEYS = {
    "ExecStart", "ExecStartPre", "ExecStartPost", "ExecStop", "ExecStopPost",
    "ExecReload", "EnvironmentFile",
}


def shell_tokens(value: str) -> list[str]:
    try:
        return shlex.split(value, comments=True, posix=True)
    except ValueError:
        return []


def looks_like_local_reference(value: str) -> bool:
    cleaned = value.lstrip("-@:+!")
    suffix = Path(cleaned).suffix.lower()
    return (
        cleaned.startswith(("./", "../", "/", "$"))
        or "/" in cleaned
        or "\\" in cleaned
        or suffix in SHELL_SUFFIXES
        or suffix in SYSTEMD_SUFFIXES
    )


def shell_data(text: str) -> tuple[list[str], list[Symbol]]:
    symbols = [
        Symbol("function", match.group(1), line_for(text, match.start()),
               line_for(text, match.start()))
        for match in SHELL_FUNCTION_RE.finditer(text)
    ]
    imports = set()
    for line in text.splitlines():
        tokens = shell_tokens(line)
        if not tokens:
            continue
        if tokens[0] in {"source", "."} and len(tokens) > 1:
            imports.add(tokens[1])
            continue
        command_index = 1 if tokens[0] == "exec" and len(tokens) > 1 else 0
        command = posixpath.basename(tokens[command_index])
        if command in SHELL_COMMANDS:
            for token in tokens[command_index + 1:]:
                if token.startswith("-"):
                    continue
                imports.add(token)
                break
        elif looks_like_local_reference(tokens[command_index]):
            imports.add(tokens[command_index])
    return sorted(imports), symbols


def systemd_data(text: str) -> tuple[list[str], list[Symbol]]:
    imports = set()
    symbols = []
    logical_lines = []
    pending = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        pending += stripped
        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        logical_lines.append(pending)
        pending = ""
    if pending:
        logical_lines.append(pending)

    for line_number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"\s*\[([^]]+)\]", line)
        if match:
            symbols.append(Symbol("section", match.group(1), line_number, line_number))

    for line in logical_lines:
        if "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in SYSTEMD_RELATION_KEYS:
            imports.update(value.split())
        elif key in SYSTEMD_EXEC_KEYS:
            for token in shell_tokens(value):
                if looks_like_local_reference(token):
                    imports.add(token.lstrip("-@:+!"))
    return sorted(imports), symbols


def analyze_file(root: Path, path: Path) -> FileInfo:
    relative = path.relative_to(root).as_posix()
    data = read_text(path)
    info = FileInfo(relative, path.stat().st_size, digest(path), "config")
    suffix = path.suffix.lower()
    if suffix in PYTHON_SUFFIXES:
        info.language = "python"
        try:
            tree = ast.parse(data, filename=relative)
            info.imports = python_imports(tree)
            info.symbols = python_symbols(tree)
        except SyntaxError as error:
            info.parse_error = f"line {error.lineno}: {error.msg}"
    elif suffix in JAVASCRIPT_SUFFIXES | TYPESCRIPT_SUFFIXES:
        info.language = "javascript" if suffix in JAVASCRIPT_SUFFIXES else "typescript"
        info.imports, info.symbols = javascript_data(data)
    elif suffix in SHELL_SUFFIXES or is_shell_script(path):
        info.language = "shell"
        info.imports, info.symbols = shell_data(data)
    elif suffix in SYSTEMD_SUFFIXES:
        info.language = "systemd"
        info.imports, info.symbols = systemd_data(data)
    return info


def git_commit(root: Path) -> str | None:
    return run_git(root, "rev-parse", "HEAD")


def git_change_candidates(
    root: Path, previous_commit: object, current_commit: str | None
) -> set[str] | None:
    """Return paths Git says may differ, including working tree changes."""
    if not isinstance(previous_commit, str) or not current_commit:
        return None
    committed = run_git(
        root, "diff", "--name-only", "--no-renames", previous_commit,
        current_commit, "--",
    )
    working = run_git(
        root, "status", "--porcelain=v1", "--untracked-files=all",
    )
    if committed is None or working is None:
        return None
    candidates = {line for line in committed.splitlines() if line}
    for line in working.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            old_path, new_path = path.split(" -> ", 1)
            candidates.update((old_path, new_path))
        else:
            candidates.add(path)
    return candidates


def rel_import(source: str, imported: str, known: set[str]) -> str | None:
    if not imported or imported.startswith(("@", "http")):
        return None
    source_parts = source.rsplit("/", 1)[0].split("/") if "/" in source else []
    normalized = imported.strip().strip("'\"").replace("\\", "/")
    cleaned = re.sub(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/", "", normalized)
    imported_suffix = Path(cleaned).suffix.lower()
    source_suffix = Path(source).suffix.lower()
    file_reference = (
        "/" in normalized
        or normalized.startswith("$")
        or imported_suffix in SHELL_SUFFIXES
        or (
            source_suffix in SHELL_SUFFIXES | SYSTEMD_SUFFIXES
            and imported_suffix in SYSTEMD_SUFFIXES
        )
    )
    if normalized.startswith(("./", "../")):
        base = "/".join(source_parts)
        name = posixpath.normpath(posixpath.join(base, normalized))
    elif normalized.startswith(".") and not file_reference:
        level = len(normalized) - len(normalized.lstrip("."))
        module = normalized[level:]
        base = source_parts[:max(0, len(source_parts) - level + 1)]
        name = "/".join(base + ([module.replace(".", "/")] if module else []))
    elif file_reference:
        name = cleaned.lstrip("/")
    else:
        name = normalized.replace(".", "/")

    def probes(base: str) -> list[str]:
        suffixes = tuple(sorted(SOURCE_SUFFIXES))
        return [
            base,
            *(base + suffix for suffix in suffixes),
            f"{base}/__init__.py",
            *(f"{base}/index{suffix}" for suffix in sorted(JAVASCRIPT_SUFFIXES | TYPESCRIPT_SUFFIXES)),
        ]

    candidates = [name]
    if source_parts and not normalized.startswith("."):
        candidates.insert(0, posixpath.join(*source_parts, name))
        # Try progressively deeper module roots. This resolves both common
        # src/package layouts and sibling imports without project execution.
        candidates.extend(
            posixpath.join(*source_parts[:depth], name)
            for depth in range(1, len(source_parts) + 1)
        )
    for candidate in candidates:
        for probe in probes(candidate):
            if probe in known:
                return probe
    if file_reference:
        basename = posixpath.basename(cleaned)
        matches = sorted(path for path in known if posixpath.basename(path) == basename)
        if len(matches) == 1:
            return matches[0]
    return None


def render_symbol(symbol: Symbol, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    line = f"{prefix}- `{symbol.kind} {symbol.name}` (L{symbol.line}"
    if symbol.end_line != symbol.line:
        line += f"-L{symbol.end_line}"
    line += ")"
    if symbol.doc:
        line += f": {symbol.doc}"
    lines = [line]
    for child in symbol.children:
        lines.extend(render_symbol(child, indent + 1))
    return lines


def tree_lines(root: Path, files: list[FileInfo]) -> list[str]:
    def render(node: dict, prefix: str = "") -> list[str]:
        lines = []
        entries = sorted(node.items(), key=lambda item: (not isinstance(item[1], dict), item[0].lower()))
        for index, (name, value) in enumerate(entries):
            branch = "└── " if index == len(entries) - 1 else "├── "
            if isinstance(value, dict):
                lines.append(f"{prefix}{branch}{name}/")
                lines.extend(render(value, prefix + ("    " if index == len(entries) - 1 else "│   ")))
            else:
                label = value.language
                lines.append(f"{prefix}{branch}{name} [{label}, {value.size} bytes]")
        return lines

    visible = files[:MAX_TREE_FILES]
    tree = {}
    for info in visible:
        cursor = tree
        parts = info.path.split("/")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = info
    lines = render(tree)
    if len(files) > len(visible):
        lines.append(f"... {len(files) - len(visible)} more indexed files omitted")
    return lines


def component_lines(files: list[FileInfo]) -> list[str]:
    groups: dict[str, list[FileInfo]] = {}
    for info in files:
        component = info.path.split("/", 1)[0]
        groups.setdefault(component, []).append(info)
    role_hints = {
        "api": "request boundary", "app": "application", "apps": "applications",
        "cli": "command-line interface", "config": "configuration", "docs": "documentation",
        "models": "domain or data models", "scripts": "automation", "src": "main source",
        "test": "tests", "tests": "tests", "web": "web interface",
    }
    lines = []
    for name, items in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        languages = ", ".join(sorted({item.language for item in items}))
        hint = role_hints.get(name.lower(), "project component")
        lines.append(f"- `{name}`: {hint}; {len(items)} indexed file(s); {languages}")
    return lines


def dependency_trees(edges: list[tuple[str, str]], entry_points: list[str]) -> list[str]:
    graph: dict[str, set[str]] = {}
    incoming: dict[str, int] = {}
    for source, target in edges:
        graph.setdefault(source, set()).add(target)
        incoming[target] = incoming.get(target, 0) + 1
        incoming.setdefault(source, incoming.get(source, 0))
    roots = sorted(set(entry_points) | {
        node for node, count in incoming.items() if count == 0
    })
    if not roots:
        roots = sorted(graph)[:10]

    rendered = 0

    def walk(node: str, prefix: str, ancestors: frozenset[str], depth: int) -> list[str]:
        nonlocal rendered
        if depth >= MAX_DEPENDENCY_DEPTH:
            return [f"{prefix}... depth limit reached"]
        children = sorted(graph.get(node, set()))
        lines = []
        for index, child in enumerate(children):
            if rendered >= MAX_DEPENDENCY_NODES:
                lines.append(f"{prefix}... dependency tree limit reached")
                break
            last = index == len(children) - 1
            branch = "└── " if last else "├── "
            suffix = " (cycle)" if child in ancestors else ""
            lines.append(f"{prefix}{branch}{child}{suffix}")
            rendered += 1
            if child not in ancestors:
                continuation = "    " if last else "│   "
                lines.extend(walk(
                    child, prefix + continuation, ancestors | {child}, depth + 1
                ))
        return lines

    lines = []
    for root in roots[:20]:
        if rendered >= MAX_DEPENDENCY_NODES:
            lines.append("... dependency tree limit reached")
            break
        lines.append(root)
        rendered += 1
        lines.extend(walk(root, "", frozenset({root}), 0))
    return lines


def hotspot_lines(edges: list[tuple[str, str]]) -> list[str]:
    dependents: dict[str, set[str]] = {}
    for source, target in edges:
        dependents.setdefault(target, set()).add(source)
    ranked = sorted(dependents.items(), key=lambda item: (-len(item[1]), item[0]))
    return [
        f"- `{target}`: imported by {len(sources)} indexed module(s)"
        for target, sources in ranked[:20]
    ]


def display_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def build_map(root: Path, files: list[FileInfo], generated_at: str, commit: str | None,
              versions: dict[str, str], manifest_path: Path,
              changes: dict | None = None) -> str:
    known = {item.path for item in files}
    edges = []
    for info in files:
        for imported in info.imports:
            target = rel_import(info.path, imported, known)
            if target and target != info.path:
                edges.append((info.path, target))
    entry_points = []
    shell_entry_points = {
        "install.sh", "start.sh", "run.sh", "entrypoint.sh", "deploy.sh", "setup.sh",
    }
    for info in files:
        name = Path(info.path).name
        if (
            name in {
                "__main__.py", "manage.py", "main.py", "app.py", "cli.py",
                "index.js", "index.ts",
            }
            or name in shell_entry_points
            or Path(info.path).suffix.lower() in SYSTEMD_SUFFIXES
        ):
            entry_points.append(info.path)

    fingerprint = source_fingerprint(files)
    language_counts = {}
    for info in files:
        language_counts[info.language] = language_counts.get(info.language, 0) + 1
    language_summary = ", ".join(
        f"`{language}: {count}`" for language, count in sorted(language_counts.items())
    ) or "none"
    meta = {
        "analyzer": ANALYZER_VERSION,
        "generated_at": generated_at,
        "git_commit": commit,
        "source_fingerprint": fingerprint,
    }
    lines = [
        "# Project Map", "", 
        f"<!-- project-map: {json.dumps(meta, sort_keys=True)} -->",
        "This is a generated navigation index. Validate it before relying on it; read source files before editing. FRESH means the indexed files match, not that every repository file is covered.", "",
        "## Snapshot", "",
        f"- Analyzer: `{ANALYZER_VERSION}`",
        f"- Generated (UTC): `{generated_at}`",
        f"- Git commit: `{commit or 'not a Git repository'}`",
        f"- Source fingerprint: `{fingerprint}`",
        f"- Indexed files: `{len(files)}`",
        f"- Declared project versions: `{json.dumps(versions, sort_keys=True) if versions else 'none detected'}`",
        f"- Source hashes and analysis cache: `{display_path(root, manifest_path)}`", "",
        "## Coverage", "",
        f"- Indexed languages in this map: {language_summary}",
        "- Discoverable source types: Python (`.py`, `.pyi`); JavaScript/TypeScript (`.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`); Shell (`.sh`, `.bash`, `.zsh`, `.fish`, and extensionless shell shebang files); systemd (`.service`, `.socket`, `.timer`, `.target`, `.mount`, `.path`).",
        "- Selected project files: `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `package.json`, `tsconfig.json`, `Cargo.toml`, `manage.py`, `Dockerfile`, `Makefile`, Compose files, `CMakeLists.txt`, Go modules, Maven/Gradle files, and `Procfile`.",
        "- Freshness scope: only files listed in this map and manifest. Unlisted repository files are not validated.",
        "- Parsing scope: Python uses the standard-library AST; JavaScript/TypeScript, Shell, and systemd relationships are conservative and may be incomplete.", "",
    ]
    if changes is not None:
        lines.extend([
            "## Changes Since Previous Map", "",
            f"- Previous Git commit: `{changes.get('from_commit') or 'unavailable'}`",
            f"- Current Git commit: `{changes.get('to_commit') or 'working tree'}`",
        ])
        for label, key in (("Added", "added"), ("Changed", "changed"), ("Removed", "removed")):
            values = changes.get(key, [])
            lines.append(
                f"- {label}: " + (
                    ", ".join(f"`{value}`" for value in values[:20])
                    if values else "none"
                )
            )
            if len(values) > 20:
                lines.append(f"  - ... {len(values) - 20} more")
        lines.append("")
    lines.extend([
        "## Components", "", *component_lines(files), "",
        "## Repository Tree", "", "```text",
        *tree_lines(root, files), "```", "",
        "## Entry Points", "",
    ])
    if entry_points:
        lines.extend(f"- `{item}`" for item in sorted(set(entry_points)))
    else:
        lines.append("- No conventional entry point detected.")
    lines.extend(["", "## Module Relationships", ""])
    if edges:
        unique_edges = sorted(set(edges))
        lines.extend(
            f"- `{source}` -> `{target}`"
            for source, target in unique_edges[:MAX_RELATIONSHIPS]
        )
        if len(unique_edges) > MAX_RELATIONSHIPS:
            lines.append(
                f"- ... {len(unique_edges) - MAX_RELATIONSHIPS} more relationships omitted"
            )
    else:
        lines.append("- No local import relationships resolved.")
    lines.extend(["", "## Dependency Trees", "", "```text"])
    lines.extend(dependency_trees(sorted(set(edges)), entry_points) or [
        "No dependency tree detected."
    ])
    lines.extend(["```", "", "## Change Hotspots", ""])
    lines.extend(hotspot_lines(edges) or ["- No imported local modules detected."])
    lines.extend(["", "## Symbols", ""])
    remaining_symbols = MAX_SYMBOLS
    for info in files:
        if remaining_symbols <= 0:
            break
        if not info.symbols and not info.parse_error:
            continue
        lines.append(f"### `{info.path}`")
        if info.parse_error:
            lines.append(f"- Parse warning: `{info.parse_error}`")
        for symbol in info.symbols[:remaining_symbols]:
            lines.extend(render_symbol(symbol))
        remaining_symbols -= len(info.symbols)
        lines.append("")
    total_symbols = sum(len(info.symbols) for info in files)
    if total_symbols > MAX_SYMBOLS:
        lines.append(f"_... {total_symbols - MAX_SYMBOLS} more top-level symbols omitted._")
        lines.append("")
    lines.extend([
        "## Change Guide", "",
        "1. Run `project_map.py check .` after changing branches or before structural edits.",
        "2. Use the tree and relationships to find candidate modules, then read those files directly.",
        "3. Run `project_map.py update .` after source changes to reuse unchanged analysis.",
        "4. Treat a stale or unknown snapshot as untrusted.", "",
    ])
    return "\n".join(lines)


def manifest_for(root: Path, files: list[FileInfo], generated_at: str, commit: str | None,
                 versions: dict[str, str]) -> dict:
    return {
        "analyzer": ANALYZER_VERSION,
        "generated_at": generated_at,
        "git_commit": commit,
        "source_fingerprint": source_fingerprint(files),
        "project_versions": versions,
        "project": root.name,
        "files": {item.path: file_to_record(item) for item in files},
    }


def output_paths(root: Path, output: str | None) -> tuple[Path, Path]:
    map_path = (root / output) if output else root / DEFAULT_MAP
    manifest_path = map_path.with_name("project-map.manifest.json")
    return map_path, manifest_path


def write_outputs(map_path: Path, manifest_path: Path, document: str,
                  manifest: dict) -> bool:
    try:
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(document + "\n", encoding="utf-8")
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as error:
        print(
            f"ERROR: cannot write project map to {map_path} and {manifest_path}: {error}",
            file=sys.stderr,
        )
        return False
    return True


def generate(root: Path, output: str | None) -> int:
    root = root.resolve()
    files = [analyze_file(root, path) for path in discover_files(root)]
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    commit = git_commit(root)
    versions = project_versions(root)
    map_path, manifest_path = output_paths(root, output)
    document = build_map(
        root, files, generated_at, commit, versions, manifest_path
    )
    manifest = manifest_for(root, files, generated_at, commit, versions)
    if not write_outputs(map_path, manifest_path, document, manifest):
        return 2
    print(f"WROTE {map_path}")
    print(f"WROTE {manifest_path}")
    print(f"INDEXED {len(files)} files")
    return 0


def load_manifest(manifest_path: Path) -> dict | None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return manifest if isinstance(manifest, dict) else None


def update(root: Path, output: str | None) -> int:
    root = root.resolve()
    map_path, manifest_path = output_paths(root, output)
    previous = load_manifest(manifest_path)
    if not map_path.is_file() or previous is None:
        print("NO CACHE: generating a full map")
        return generate(root, output)

    previous_files = previous.get("files", {})
    if not isinstance(previous_files, dict):
        print("INVALID CACHE: generating a full map")
        return generate(root, output)

    paths = discover_files(root)
    current_paths = {
        path.relative_to(root).as_posix(): path
        for path in paths
    }
    current_commit = git_commit(root)
    git_candidates = git_change_candidates(
        root, previous.get("git_commit"), current_commit
    )
    if previous.get("analyzer") != ANALYZER_VERSION:
        git_candidates = set(current_paths)
    elif git_candidates is None:
        git_candidates = set(current_paths)
    git_candidates.update(set(current_paths) - set(previous_files))

    files = []
    reused = 0
    reparsed = 0
    added = sorted(set(current_paths) - set(previous_files))
    removed = sorted(set(previous_files) - set(current_paths))
    changed = []
    for relative, path in sorted(current_paths.items()):
        record = previous_files.get(relative)
        cached = file_from_record(relative, record)
        # Git narrows the expected change set, while hashing every indexed file
        # protects against assume-unchanged flags and other hidden worktree edits.
        current_digest = digest(path)
        old_digest = record.get("sha256") if isinstance(record, dict) else None
        if current_digest == old_digest and cached is not None:
            files.append(cached)
            reused += 1
            continue
        files.append(analyze_file(root, path))
        reparsed += 1
        if relative in previous_files and current_digest != old_digest:
            changed.append(relative)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    versions = project_versions(root)
    changes = {
        "from_commit": previous.get("git_commit"),
        "to_commit": current_commit,
        "added": added,
        "changed": sorted(changed),
        "removed": removed,
    }
    document = build_map(
        root, files, generated_at, current_commit, versions, manifest_path, changes
    )
    manifest = manifest_for(root, files, generated_at, current_commit, versions)
    if not write_outputs(map_path, manifest_path, document, manifest):
        return 2
    print(f"WROTE {map_path}")
    print(f"WROTE {manifest_path}")
    print(f"REUSED {reused} analyses")
    print(f"REPARSED {reparsed} files")
    print(f"REMOVED {len(removed)} files")
    print(f"GIT CANDIDATES {len(git_candidates)} paths")
    return 0


def parse_map_meta(map_path: Path) -> dict | None:
    if not map_path.is_file():
        return None
    match = re.search(r"<!-- project-map: (\{.*?\}) -->", map_path.read_text(encoding="utf-8", errors="replace"))
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def validate(root: Path, output: str | None) -> int:
    root = root.resolve()
    map_path, manifest_path = output_paths(root, output)
    if not map_path.is_file() or not manifest_path.is_file():
        print(f"MISSING: generate {map_path}")
        return 2
    try:
        manifest = load_manifest(manifest_path)
    except OSError as error:
        print(f"UNKNOWN: invalid manifest ({error})")
        return 2
    if manifest is None:
        print("UNKNOWN: invalid manifest")
        return 2
    meta = parse_map_meta(map_path)
    if not meta or meta.get("analyzer") != ANALYZER_VERSION:
        print("STALE: map metadata is missing or analyzer version changed")
        return 1
    current_versions = project_versions(root)
    if manifest.get("project_versions", {}) != current_versions:
        print(f"STALE: declared project versions changed ({manifest.get('project_versions', {})} -> {current_versions})")
        return 1
    expected = manifest.get("files", {})
    current = {path.relative_to(root).as_posix(): path for path in discover_files(root)}
    changed = []
    current_digests = {}
    for path, record in expected.items():
        if path not in current:
            changed.append(path)
            continue
        current_digests[path] = digest(current[path])
        if not isinstance(record, dict) or current_digests[path] != record.get("sha256"):
            changed.append(path)
    for path in current:
        if path not in expected:
            changed.append(path)
            current_digests[path] = digest(current[path])
    if changed:
        print(f"STALE: {len(changed)} indexed file(s) changed")
        for path in sorted(changed)[:20]:
            print(f"  {path}")
        return 1
    current_infos = [
        FileInfo(path, current[path].stat().st_size, digest_value, "")
        for path, digest_value in current_digests.items()
    ]
    current_fingerprint = source_fingerprint(current_infos)
    if manifest.get("source_fingerprint") != current_fingerprint or \
            meta.get("source_fingerprint") != current_fingerprint:
        print("STALE: source fingerprint does not match the map and manifest")
        return 1
    current_commit = git_commit(root)
    print(
        f"FRESH: {map_path} matches {len(expected)} indexed files at "
        f"{current_commit or 'working tree'}; unindexed repository files are outside this check"
    )
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("map", "update", "check"):
        sub = subparsers.add_parser(command)
        sub.add_argument("root", nargs="?", default=".")
        sub.add_argument("--output", help="Markdown path relative to root")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if args.command == "map":
        return generate(root, args.output)
    if args.command == "update":
        return update(root, args.output)
    return validate(root, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
