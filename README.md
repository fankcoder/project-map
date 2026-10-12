# Project Map

[English](README.md) | [简体中文](README.zh-CN.md)

Project Map is a local Codex plugin for quickly orienting an agent in an unfamiliar repository. It builds a Markdown architecture index and validates that the index still matches the source tree before it is reused.

It is intentionally dependency-free: the analyzer uses only Python's standard library and never imports or executes the target project.

## Install and use in Codex

Project Map is a skill-only plugin: it runs locally, needs no API key or MCP connection, and never uploads source code. For the normal GitHub installation, register the repository marketplace:

```bash
codex plugin marketplace add fankcoder/project-map
codex plugin marketplace list
```

Start `codex`, enter `/plugins`, choose **Project Map Development**, and install `project-map`. Start a new Codex session after installation so the bundled skill is discovered. Codex plugins are currently supported in Codex CLI and the ChatGPT desktop app, not the IDE extension.

To refresh the marketplace after a new release, run `codex plugin marketplace upgrade project-map-local`, review the plugin in `/plugins`, and start another new session.

In a repository you want Codex to modify, ask directly:

```text
Use $project-map to orient yourself in this repository, validate or update the project map, then explain the relevant architecture before editing.
```

The skill can also be discovered automatically when Codex needs to understand an unfamiliar repository. It validates an existing map before reading it, updates stale maps incrementally, and still requires current source files to be read before edits. Use `$project-map` when you want deterministic activation.

### Recommended Codex workflow

1. Open the target repository in Codex and start a new session after installing or updating the plugin.
2. Begin with: `Use $project-map to inspect this repository before making changes.`
3. Ask Codex to summarize the map's Snapshot, Changes Since Previous Map, Components, and Entry Points sections first.
4. For a focused task, name the feature or path: `Use the project map to locate the authentication flow, then read the current source and tests.`
5. Before structural edits, ask Codex to validate the map and update it if stale.
6. After a branch switch, rebase, or substantial code change, ask: `Run the project map update, summarize added/changed/removed files, then continue.`

The map is a navigation index, not a replacement for source review. A good prompt asks Codex to use the map to narrow the search, then verify behavior in the current source and tests.

### Local plugin testing

To develop or test a local checkout instead of the GitHub version:

```bash
codex plugin marketplace add /absolute/path/to/project-map
codex plugin marketplace list
```

Open `/plugins`, install the local **Project Map Development** entry, and start a new session after changing plugin files.

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

## Roadmap

The current release focuses on a trustworthy, low-cost project map. The next useful capabilities are planned as separate workflows rather than one oversized skill:

- Task-focused context packs that return only the modules, symbols, tests, and dependencies relevant to a request.
- Impact analysis that lists reverse dependents, likely entry points, affected tests, and change risk.
- Layered Markdown maps so a session can load a small index first and open component details only when needed.
- Architecture rules that detect forbidden dependency directions in CI or before a structural edit.

These are design directions, not features provided by the current release.

## Plugin layout

The root `plugin.json` is the portable Agent Plugins manifest used by Codex. `.codex-plugin/plugin.json` is the supported compatibility fallback. `skills/project-map/SKILL.md` tells Codex when and how to use the map, and `scripts/project_map.py` is the executable implementation.

Official packaging and installation details are documented in [OpenAI's plugin guide](https://developers.openai.com/plugins/build/plugins).
