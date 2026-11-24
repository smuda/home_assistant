"""Compile every Home Assistant template in the repo's YAML.

Walks the YAML under the repo's config directories, loads each file
with a loader that tolerates HA's custom tags (`!input`, `!include*`,
`!secret`), and compiles every string holding `{{` or `{%` against
make_env({}). Drafts, `_wip` and `secrets.yaml` are skipped, and a file
that is not valid YAML is reported without its contents. A template that does not compile -- an unknown filter, a
bad tag, an unbalanced bracket -- fails here instead of at runtime on
the live instance.

Compile-only on purpose: globals and entities resolve at render time,
so a template that names a missing global still compiles. That is out
of scope; the behaviour tests render the templates that matter.

Run from the repo root with `make test`, or directly:

    python3 -m unittest discover -s tests/zaptec

Needs jinja2 and pyyaml; `make test` installs them into .venv from
requirements-dev.txt.
"""

import tempfile
import unittest
from pathlib import Path

import jinja2
import yaml

from ha_harness import ROOT, make_env

DIRS = (
    "automations",
    "templates",
    "sensors",
    "helpers",
    "scripts",
    "notify",
    "dashboards",
    "blueprints",
    "config",
)
SKIP_PARTS = {"node_modules", ".git", "_wip"}
SKIP_NAMES = {"secrets.yaml"}


class TolerantLoader(yaml.SafeLoader):
    """SafeLoader that loads any `!tag` as its plain value."""


def _plain(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


TolerantLoader.add_multi_constructor("!", _plain)


def yaml_files(root=ROOT):
    found = []
    for name in DIRS:
        for path in (root / name).rglob("*.yaml"):
            rel = path.relative_to(root)
            if SKIP_PARTS & set(rel.parts):
                continue
            if path.name in SKIP_NAMES or path.name.endswith(".draft.yaml"):
                continue
            found.append(path)
    return sorted(found)


def templates_in(data):
    if isinstance(data, str):
        if "{{" in data or "{%" in data:
            yield data
    elif isinstance(data, dict):
        for value in data.values():
            yield from templates_in(value)
    elif isinstance(data, list):
        for item in data:
            yield from templates_in(item)


def compile_errors(path, root=ROOT):
    """Return (template count, error strings) for one YAML file."""
    try:
        label = str(Path(path).relative_to(root))
    except ValueError:
        label = str(path)
    try:
        with open(path) as f:
            data = yaml.load(f, Loader=TolerantLoader)
    except yaml.YAMLError as e:
        # The YAMLError message can quote file contents; name the type only.
        return 0, [f"{label}: YAML error: {type(e).__name__}"]
    env = make_env({})
    count = 0
    errors = []
    for source in templates_in(data):
        count += 1
        try:
            env.from_string(source)
        except jinja2.TemplateError as e:
            errors.append(f"{label}: {type(e).__name__}: {e}")
    return count, errors


def scan():
    """Return (template count per file, error strings) for the repo."""
    per_file = {}
    errors = []
    for path in yaml_files():
        count, errs = compile_errors(path)
        per_file[path] = count
        errors.extend(errs)
    return per_file, errors


class TemplateCompileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.per_file, cls.errors = scan()
        cls.files = list(cls.per_file)
        cls.total = sum(cls.per_file.values())

    def test_every_template_compiles(self):
        if self.errors:
            self.fail(
                f"{len(self.errors)} template(s) do not compile:\n"
                + "\n".join(self.errors)
            )

    def test_walk_is_not_vacuous(self):
        self.assertGreater(len(self.files), 0)
        self.assertGreater(self.total, 50)

    def test_blueprints_with_input_tags_are_compiled(self):
        blueprints = [
            p
            for p in self.files
            if p.relative_to(ROOT).parts[0] == "blueprints"
        ]
        self.assertTrue(blueprints)
        self.assertTrue(any(self.per_file[p] > 0 for p in blueprints))


class YamlFilesTest(unittest.TestCase):
    def test_wip_drafts_and_secrets_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "scripts/ok.yaml": "a: 1\n",
                "scripts/_wip/x.yaml": "a: 1\n",
                "scripts/y.draft.yaml": "a: 1\n",
                "scripts/broken.draft.yaml": "a: [unclosed\n",
                "scripts/notes.yml": "a: 1\n",
                "config/secrets.yaml": "token: hunter2\n",
            }
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            self.assertEqual(yaml_files(root=root), [root / "scripts/ok.yaml"])


class CompileErrorsTest(unittest.TestCase):
    def write(self, text, name="sample.yaml"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        path = root / name
        path.write_text(text)
        return root, path

    def test_unknown_filter_is_reported_with_file_name(self):
        root, path = self.write('x: "{{ y | no_such_filter }}"\n')
        count, errors = compile_errors(path, root=root)
        self.assertEqual(count, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("sample.yaml", errors[0])
        self.assertIn("TemplateAssertionError", errors[0])

    def test_input_tag_loads_and_valid_template_passes(self):
        root, path = self.write(
            "a: !input foo\nb: \"{{ states('sensor.x') | float(0) }}\"\n"
        )
        count, errors = compile_errors(path, root=root)
        self.assertEqual(count, 1)
        self.assertEqual(errors, [])

    def test_invalid_yaml_is_one_error_without_contents(self):
        root, path = self.write("secret_value: [unclosed\n", name="bad.yaml")
        count, errors = compile_errors(path, root=root)
        self.assertEqual(count, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("bad.yaml", errors[0])
        self.assertIn("YAML error", errors[0])
        self.assertNotIn("secret_value", errors[0])

    def test_invalid_yaml_does_not_stop_the_scan(self):
        root, bad = self.write("a: [unclosed\n", name="bad.yaml")
        good = root / "good.yaml"
        good.write_text('x: "{{ y | no_such_filter }}"\n')
        results = {p.name: compile_errors(p, root=root) for p in (bad, good)}
        self.assertEqual(len(results["bad.yaml"][1]), 1)
        self.assertEqual(results["good.yaml"][0], 1)
        self.assertEqual(len(results["good.yaml"][1]), 1)


if __name__ == "__main__":
    unittest.main()
