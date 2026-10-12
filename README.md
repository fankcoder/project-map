# Project Map

[English](README.md) | [简体中文](README.zh-CN.md)

Project Map is a local Codex plugin for quickly orienting an agent in an unfamiliar repository. It builds a Markdown architecture index and validates that the index still matches the source tree before it is reused.

It is intentionally dependency-free: the analyzer uses only Python's standard library and never imports or executes the target project.

## Install for Codex

This repository includes a repo marketplace at `.agents/plugins/marketplace.json`. After cloning it, register that local marketplace:

```bash
codex plugin marketplace add /absolute/path/to/project-map
codex plugin marketplace list
```

Start `codex`, enter `/plugins`, choose **Project Map Development**, and install `project-map`. Start a new Codex session after installation so the bundled skill is discovered. Codex plugins are currently supported in Codex CLI and the ChatGPT desktop app, not the IDE extension.

The plugin can then be selected explicitly with `$project-map`, or discovered automatically when Codex needs to understand an unfamiliar repository. It validates an existing map before reading it and regenerates stale maps before architectural work.

## Direct CLI use

```bash
python3 scripts/project_map.py map /path/to/repository
python3 scripts/project_map.py update /path/to/repository
python3 scripts/project_map.py check /path/to/repository
```

The default outputs are `.codex/project-map.md` and `.codex/project-map.manifest.json` inside the target repository. Add the `.codex/` files to `.gitignore` if the map is personal, or commit them when a team wants a shared orientation document.

The generated Markdown is deliberately bounded for token efficiency. It summarizes components, a filtered tree, entry points, local dependency trees, change hotspots, and public symbols. The manifest still hashes every indexed source file so omitted display details cannot hide staleness.

`update` compares the Git commit and working tree with the previous manifest, verifies content with SHA-256, reparses only changed or added files, and reuses cached analysis for unchanged files. The refreshed map includes a compact summary of files added, changed, or removed since the previous map. If the cache is missing or incompatible, it safely falls back to a full generation.

## Supported evidence

- Git-tracked files when the target is a Git repository, with a safe filesystem fallback.
- Python modules, imports, classes, functions, methods, docstrings, and line ranges via `ast`.
- JavaScript and TypeScript imports, exports, classes, functions, and line ranges using conservative standard-library parsing.
- Common project metadata such as `pyproject.toml`, `package.json`, `Cargo.toml`, `manage.py`, and `__main__.py`.
- A manifest containing analyzer version, Git commit, file hashes, reusable analysis, and generated timestamp.
- Declared project versions from `pyproject.toml`, `package.json`, or `Cargo.toml` when present.

The map is a navigation index. The validator deliberately reports stale data instead of silently trusting it.

## Plugin layout

The root `plugin.json` is the portable Agent Plugins manifest used by Codex. `.codex-plugin/plugin.json` is the supported compatibility fallback. `skills/project-map/SKILL.md` tells Codex when and how to use the map, and `scripts/project_map.py` is the executable implementation.

Official packaging and installation details are documented in [OpenAI's plugin guide](https://developers.openai.com/plugins/build/plugins).
