import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "project_map.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class ProjectMapTests(unittest.TestCase):
    def test_map_and_check_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pkg").mkdir()
            (root / "pkg" / "__init__.py").write_text(
                "from .service import run\n", encoding="utf-8"
            )
            (root / "pkg" / "service.py").write_text(
                '"""Service docs."""\n\ndef run(value: str) -> str:\n'
                '    """Run the service."""\n    return value\n',
                encoding="utf-8",
            )
            generated = run("map", str(root))
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertIn("INDEXED 2 files", generated.stdout)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("`function run`", document)
            self.assertIn("`pkg/__init__.py` -> `pkg/service.py`", document)
            self.assertIn("## Dependency Trees", document)
            self.assertIn("└── pkg/service.py", document)
            checked = run("check", str(root))
            self.assertEqual(checked.returncode, 0, checked.stdout)
            (root / "pkg" / "service.py").write_text(
                "def changed():\n    return True\n", encoding="utf-8"
            )
            stale = run("check", str(root))
            self.assertEqual(stale.returncode, 1)
            self.assertIn("STALE", stale.stdout)

    def test_typescript_relative_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "index.ts").write_text(
                "import { run } from './service';\nexport function main() { run(); }\n",
                encoding="utf-8",
            )
            (root / "src" / "service.ts").write_text(
                "export function run() { return true; }\n", encoding="utf-8"
            )
            self.assertEqual(run("map", str(root)).returncode, 0)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("`src/index.ts` -> `src/service.ts`", document)

    def test_python_relative_alias_and_src_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "sample").mkdir(parents=True)
            (root / "src" / "sample" / "__init__.py").write_text(
                "from . import service\n", encoding="utf-8"
            )
            (root / "src" / "sample" / "api.py").write_text(
                "from sample.service import run\n", encoding="utf-8"
            )
            (root / "src" / "sample" / "service.py").write_text(
                "def run():\n    return True\n", encoding="utf-8"
            )
            self.assertEqual(run("map", str(root)).returncode, 0)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn(
                "`src/sample/__init__.py` -> `src/sample/service.py`", document
            )
            self.assertIn(
                "`src/sample/api.py` -> `src/sample/service.py`", document
            )

    def test_typescript_index_and_tsx_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "feature").mkdir(parents=True)
            (root / "src" / "index.ts").write_text(
                "import Widget from './Widget';\nimport './feature';\n",
                encoding="utf-8",
            )
            (root / "src" / "Widget.tsx").write_text(
                "export default function Widget() { return null; }\n",
                encoding="utf-8",
            )
            (root / "src" / "feature" / "index.ts").write_text(
                "export const enabled = true;\n", encoding="utf-8"
            )
            self.assertEqual(run("map", str(root)).returncode, 0)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("`src/index.ts` -> `src/Widget.tsx`", document)
            self.assertIn("`src/index.ts` -> `src/feature/index.ts`", document)

    def test_manifest_has_hashes_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                "[project]\nname = 'fixture'\nversion = '1.2.3'\n",
                encoding="utf-8",
            )
            (root / "main.py").write_text(
                "def main():\n    return 0\n", encoding="utf-8"
            )
            self.assertEqual(run("map", str(root)).returncode, 0)
            manifest = json.loads(
                (root / ".project-map" / "project-map.manifest.json").read_text()
            )
            self.assertEqual(manifest["analyzer"], "0.3.0")
            self.assertEqual(
                manifest["project_versions"], {"pyproject.toml": "1.2.3"}
            )
            self.assertEqual(len(manifest["source_fingerprint"]), 64)
            self.assertTrue(manifest["files"]["main.py"]["sha256"])
            self.assertEqual(manifest["files"]["main.py"]["language"], "python")
            self.assertTrue(manifest["files"]["main.py"]["symbols"])
            (root / "pyproject.toml").write_text(
                "[project]\nname = 'fixture'\nversion = '1.2.4'\n",
                encoding="utf-8",
            )
            stale = run("check", str(root))
            self.assertEqual(stale.returncode, 1)
            self.assertIn("declared project versions changed", stale.stdout)

    def test_map_metadata_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("value = 1\n", encoding="utf-8")
            self.assertEqual(run("map", str(root)).returncode, 0)
            map_path = root / ".project-map" / "project-map.md"
            document = map_path.read_text(encoding="utf-8")
            map_path.write_text(
                document.replace(
                    '"source_fingerprint": "',
                    '"source_fingerprint": "tampered-',
                    1,
                ),
                encoding="utf-8",
            )
            stale = run("check", str(root))
            self.assertEqual(stale.returncode, 1)
            self.assertIn("source fingerprint does not match", stale.stdout)

    def test_incremental_update_reuses_unchanged_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.py").write_text("def one():\n    return 1\n", encoding="utf-8")
            (root / "two.py").write_text("def two():\n    return 2\n", encoding="utf-8")
            self.assertEqual(run("map", str(root)).returncode, 0)

            (root / "two.py").write_text("def changed():\n    return 3\n", encoding="utf-8")
            (root / "three.py").write_text("def three():\n    return 3\n", encoding="utf-8")
            updated = run("update", str(root))
            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertIn("REUSED 1 analyses", updated.stdout)
            self.assertIn("REPARSED 2 files", updated.stdout)

            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("## Changes Since Previous Map", document)
            self.assertIn("- Added: `three.py`", document)
            self.assertIn("- Changed: `two.py`", document)
            self.assertIn("`function changed`", document)
            self.assertEqual(run("check", str(root)).returncode, 0)

    def test_incremental_update_tracks_git_commits_and_removals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Test"],
                check=True,
            )
            (root / "keep.py").write_text("value = 1\n", encoding="utf-8")
            (root / "remove.py").write_text("value = 2\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "initial"], check=True
            )
            first_commit = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertEqual(run("map", str(root)).returncode, 0)

            (root / "remove.py").unlink()
            (root / "keep.py").write_text("value = 3\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "change"], check=True
            )
            second_commit = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()

            updated = run("update", str(root))
            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertIn("REPARSED 1 files", updated.stdout)
            self.assertIn("REMOVED 1 files", updated.stdout)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn(f"- Previous Git commit: `{first_commit}`", document)
            self.assertIn(f"- Current Git commit: `{second_commit}`", document)
            self.assertIn("- Removed: `remove.py`", document)

    def test_incremental_update_hashes_git_hidden_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Test"],
                check=True,
            )
            source = root / "hidden.py"
            source.write_text("def old():\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "initial"], check=True
            )
            self.assertEqual(run("map", str(root)).returncode, 0)
            subprocess.run(
                ["git", "-C", str(root), "update-index", "--assume-unchanged", "hidden.py"],
                check=True,
            )
            source.write_text("def new():\n    return 2\n", encoding="utf-8")

            updated = run("update", str(root))
            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertIn("REPARSED 1 files", updated.stdout)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("- Changed: `hidden.py`", document)
            self.assertIn("`function new`", document)

    def test_incremental_update_upgrades_legacy_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
            self.assertEqual(run("map", str(root)).returncode, 0)
            manifest_path = root / ".project-map" / "project-map.manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["analyzer"] = "0.1.0"
            manifest["files"]["main.py"] = {
                "sha256": manifest["files"]["main.py"]["sha256"],
                "size": manifest["files"]["main.py"]["size"],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            updated = run("update", str(root))
            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertIn("REPARSED 1 files", updated.stdout)
            upgraded = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(upgraded["analyzer"], "0.3.0")
            self.assertEqual(upgraded["files"]["main.py"]["language"], "python")

    def test_shell_functions_scripts_and_extensionless_shebang(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "install.sh").write_text(
                "#!/bin/sh\nsource_dir=$(dirname \"$0\")\n"
                "prepare() { :; }\nsource ./library.sh\n"
                "sh \"$source_dir/setup-helper.sh\"\n",
                encoding="utf-8",
            )
            (scripts / "library.sh").write_text(
                "function load { :; }\n", encoding="utf-8"
            )
            (scripts / "setup-helper.sh").write_text(
                "#!/bin/sh\n", encoding="utf-8"
            )
            (root / "bootstrap").write_text(
                "#!/usr/bin/env bash\n./scripts/install.sh\n", encoding="utf-8"
            )

            generated = run("map", str(root))
            self.assertEqual(generated.returncode, 0, generated.stderr)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("`function prepare`", document)
            self.assertIn("`function load`", document)
            self.assertIn("`scripts/install.sh` -> `scripts/library.sh`", document)
            self.assertIn(
                "`scripts/install.sh` -> `scripts/setup-helper.sh`", document
            )
            self.assertIn("`bootstrap` -> `scripts/install.sh`", document)
            manifest = json.loads(
                (root / ".project-map" / "project-map.manifest.json").read_text()
            )
            self.assertEqual(manifest["files"]["bootstrap"]["language"], "shell")

    def test_systemd_sections_unit_and_script_relationships(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "units").mkdir()
            (root / "scripts").mkdir()
            (root / "scripts" / "start-app.sh").write_text(
                "#!/bin/sh\n", encoding="utf-8"
            )
            (root / "units" / "app.service").write_text(
                "[Unit]\nAfter=network.target helper.service\n"
                "[Service]\nExecStart=/usr/local/sbin/start-app.sh\n",
                encoding="utf-8",
            )
            (root / "units" / "helper.service").write_text(
                "[Service]\nExecStart=/bin/true\n", encoding="utf-8"
            )
            (root / "units" / "app.timer").write_text(
                "[Timer]\nUnit=app.service\n", encoding="utf-8"
            )

            generated = run("map", str(root))
            self.assertEqual(generated.returncode, 0, generated.stderr)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("`section Unit`", document)
            self.assertIn("`section Service`", document)
            self.assertIn("`units/app.service` -> `units/helper.service`", document)
            self.assertIn("`units/app.service` -> `scripts/start-app.sh`", document)
            self.assertIn("`units/app.timer` -> `units/app.service`", document)
            self.assertIn("- `units/app.service`", document)

    def test_custom_output_is_reported_and_required_for_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("value = 1\n", encoding="utf-8")
            output = "output/project-map.md"
            generated = run("map", str(root), "--output", output)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            document = (root / output).read_text(encoding="utf-8")
            self.assertIn("`output/project-map.manifest.json`", document)
            self.assertNotIn(".codex/project-map.manifest.json", document)
            self.assertEqual(
                run("check", str(root), "--output", output).returncode, 0
            )
            default_check = run("check", str(root))
            self.assertEqual(default_check.returncode, 2)
            self.assertIn("MISSING", default_check.stdout)

    def test_output_path_error_is_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("value = 1\n", encoding="utf-8")
            (root / "blocked").write_text("not a directory\n", encoding="utf-8")
            generated = run(
                "map", str(root), "--output", "blocked/project-map.md"
            )
            self.assertEqual(generated.returncode, 2)
            self.assertIn("ERROR: cannot write project map", generated.stderr)
            self.assertNotIn("Traceback", generated.stderr)

    def test_coverage_and_freshness_scope_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("value = 1\n", encoding="utf-8")
            self.assertEqual(run("map", str(root)).returncode, 0)
            document = (root / ".project-map" / "project-map.md").read_text()
            self.assertIn("## Coverage", document)
            self.assertIn("FRESH means the indexed files match", document)
            self.assertIn("only files listed in this map and manifest", document)
            checked = run("check", str(root))
            self.assertEqual(checked.returncode, 0, checked.stdout)
            self.assertIn("unindexed repository files are outside this check", checked.stdout)


if __name__ == "__main__":
    unittest.main()
