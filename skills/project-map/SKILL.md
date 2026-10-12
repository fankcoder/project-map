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

2. If no map exists, or the validator reports `STALE`, generate one:

   ```bash
   python3 "<plugin-root>/scripts/project_map.py" map .
   ```

3. Read `.codex/project-map.md`. Use its components, dependency trees, change hotspots, entry points, and symbols to choose where to investigate.

4. Read the current source files named by the map before modifying them. The map identifies likely relationships; it does not prove behavior.

## Keeping the map trustworthy

- Run `check` after switching branches, rebasing, or making a structural change.
- Regenerate after source changes that alter imports, public symbols, configuration, or entry points.
- Do not hand-edit the generated map. It contains a manifest of source hashes and the Git commit used to build it.
- Treat `UNKNOWN` and `STALE` results as a stop for architectural edits until the map is regenerated.

## What the generator records

The generator is local-only and uses Python's standard library. It records a filtered file tree, Python and JavaScript/TypeScript symbols, import edges, likely entry points, and per-file SHA-256 hashes. It does not execute project code, install packages, call an API, or upload source files.

When reporting a change, cite the source path and line number rather than treating a map summary as evidence.
