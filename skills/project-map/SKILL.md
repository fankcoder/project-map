---
name: project-map
description: Use when working in an unfamiliar repository or when a repository architecture map may be stale. Generate or validate a local project map before making structural changes, then use the map as a navigation index and verify relevant source files before editing.
---

# Project Map

This skill keeps a compact, local architecture map for an existing repository. It is a navigation aid, not a substitute for reading the source that will be changed.

## Before editing

1. Resolve the plugin root as two directories above this `SKILL.md`, then run:

   ```bash
   python3 "<plugin-root>/scripts/project_map.py" check .
   ```

2. If the validator reports `MISSING`, generate a full map:

   ```bash
   python3 "<plugin-root>/scripts/project_map.py" map .
   ```

   If it reports `STALE`, incrementally update the existing map:

   ```bash
   python3 "<plugin-root>/scripts/project_map.py" update .
   ```

3. Read the Snapshot, Changes Since Previous Map (when present), Components, and Entry Points sections of `.codex/project-map.md` first. Search within the map for relevant paths or symbols and load only the matching sections. Read the entire map only when the task genuinely requires repository-wide understanding.

4. Read the current source files named by the map before modifying them. The map identifies likely relationships; it does not prove behavior.

## Keeping the map trustworthy

- Run `check` after switching branches, rebasing, or making a structural change.
- Run `update` after source changes. It reuses cached analysis only when file hashes still match.
- Do not hand-edit the generated map. It contains a manifest of source hashes and the Git commit used to build it.
- Treat `UNKNOWN` and `STALE` results as a stop for architectural edits until the map is regenerated.

## What the generator records

The generator is local-only and uses Python's standard library. It records a filtered file tree, Python and JavaScript/TypeScript symbols, import edges, likely entry points, per-file SHA-256 hashes, and reusable per-file analysis. Incremental updates use Git commits to identify expected changes and hash every indexed file before reusing cached analysis. It does not execute project code, install packages, call an API, or upload source files.

When reporting a change, cite the source path and line number rather than treating a map summary as evidence.
