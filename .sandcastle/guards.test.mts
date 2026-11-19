import { test } from "node:test";
import assert from "node:assert/strict";
import * as guards from "./guards.mts";
import {
  changedGitState,
  disallowedEnvKeys,
  disallowedModes,
  fold,
  forConsole,
  leakedSecret,
  parseEnvFile,
  patchContent,
  protectedPaths,
  secretValues,
  unexpectedRefs,
  type GitState,
} from "./guards.mts";

const STATE: GitState = { head: "h", main: "m", originMain: "o", index: "i" };

const SECRET = "sk-ant-oat01-Zq9xK2mPvL7wRtYb";

test("protectedPaths returns [] for empty input", () => {
  assert.deepEqual(protectedPaths([]), []);
});

test("protectedPaths passes ordinary paths", () => {
  assert.deepEqual(protectedPaths(["automations/x.yaml", "scripts/y.yaml", "README.md"]), []);
});

test("protectedPaths flags paths under each root protected prefix", () => {
  const paths = [".github/workflows/a.yml", ".sandcastle/guards.mts"];
  assert.deepEqual(protectedPaths(paths), paths);
});

test("protectedPaths flags each root protected file", () => {
  const paths = ["Makefile", "GNUmakefile", "package.json", "package-lock.json", ".gitmodules"];
  assert.deepEqual(protectedPaths(paths), paths);
});

test("protectedPaths flags protected directories at any depth", () => {
  const paths = [
    ".claude/settings.json", "a/.claude/x", "a/b/.claude/skills/s.md",
    ".vscode/tasks.json", "a/.vscode/tasks.json",
    ".opencode/x.json", "deep/er/.opencode/y",
  ];
  assert.deepEqual(protectedPaths(paths), paths);
});

test("protectedPaths flags protected names at any depth", () => {
  const names = [
    ".gitattributes", "CLAUDE.md", "AGENTS.md", ".npmrc", "opencode.json", ".mcp.json",
    ".lfsconfig", ".pre-commit-config.yaml", ".envrc", "tsconfig.json",
  ];
  const paths = names.flatMap((n) => [n, `docs/${n}`, `a/b/${n}`]);
  assert.deepEqual(protectedPaths(paths), paths);
});

test("protectedPaths flags the nested examples", () => {
  const paths = ["docs/CLAUDE.md", "a/.vscode/tasks.json", "x/tsconfig.json", "src/.npmrc"];
  assert.deepEqual(protectedPaths(paths), paths);
});

test("protectedPaths does not flag root-only files in subdirectories", () => {
  assert.deepEqual(
    protectedPaths(["docs/Makefile", "sub/package.json", "a/package-lock.json", "a/.gitmodules", "a/GNUmakefile"]),
    [],
  );
});

test("protectedPaths does not flag root-only prefixes when nested", () => {
  assert.deepEqual(protectedPaths(["a/.github/x.yml", "a/.sandcastle/y"]), []);
});

test("protectedPaths compares case-insensitively and keeps the original case", () => {
  const paths = [
    ".GITHUB/workflows/x.yml", "makefile", "MAKEFILE", "Package.json", ".Sandcastle/main.mts",
    "sub/.GitAttributes", ".Claude/x", "a/.VSCODE/y", "claude.md", "Agents.MD", ".NPMRC", ".GitModules",
    "gnumakefile", "a/TSConfig.JSON", "x/.OpenCode/z",
  ];
  assert.deepEqual(protectedPaths(paths), paths);
});

test("protectedPaths folds Unicode look-alikes (NFKC and case)", () => {
  const fi = "Make\ufb01le"; // "Makeﬁle" -> "Makefile"
  const longS = ".\u017fandcastle/main.mts"; // ".ſandcastle/main.mts"
  const fullwidth = "\uff2d\uff41\uff4b\uff45file"; // "Ｍａｋｅfile"
  assert.deepEqual(protectedPaths([fi, longS, fullwidth]), [fi, longS, fullwidth]);
});

test("protectedPaths does not flag non-protected look-alikes", () => {
  assert.deepEqual(
    protectedPaths([
      "Makefile.bak", "CLAUDE.md.bak", "package.json.orig", ".npmrcx", "x.gitattributes",
      ".gitattributes.bak", ".githubx/a", ".github", ".sandcastle", ".claude", "a/.claudex/y",
      "a/x.vscode/y", "tsconfig.json.bak", "opencode.jsonc",
    ]),
    [],
  );
});

test("protectedPaths keeps input order and only the protected entries", () => {
  assert.deepEqual(
    protectedPaths(["automations/x.yaml", "package.json", "scripts/y.yaml", ".github/a.yml", "Makefile"]),
    ["package.json", ".github/a.yml", "Makefile"],
  );
});

// parseEnvFile mirrors parseEnvLine/unquote/parseEnvFile in
// @ai-hero/sandcastle 0.14.0 dist/index.js.
test("parseEnvFile parses plain KEY=value lines", () => {
  assert.deepEqual(parseEnvFile("A=1\nB=two\n"), { A: "1", B: "two" });
});

test("parseEnvFile returns {} for empty input", () => {
  assert.deepEqual(parseEnvFile(""), {});
});

test("parseEnvFile skips blank lines, comments and lines without =", () => {
  assert.deepEqual(parseEnvFile("# A=1\n\n   \n  # B=2\nNOEQUALS\nC=3\n"), { C: "3" });
});

test("parseEnvFile keeps a literal export as part of the key", () => {
  assert.deepEqual(parseEnvFile("export X=1\n"), { "export X": "1" });
});

test("parseEnvFile trims the line, the key and the value", () => {
  assert.deepEqual(parseEnvFile("  A = x  \n"), { A: "x" });
});

test("parseEnvFile splits on the first = only", () => {
  assert.deepEqual(parseEnvFile("A=b=c=\n"), { A: "b=c=" });
});

test("parseEnvFile handles CRLF line endings", () => {
  assert.deepEqual(parseEnvFile("A=1\r\nB=\"two\"\r\n"), { A: "1", B: "two" });
});

test("parseEnvFile strips single quotes literally, with no escape handling", () => {
  assert.deepEqual(parseEnvFile("A='a\\nb $x'\n"), { A: "a\\nb $x" });
});

test("parseEnvFile strips double quotes and expands \\n \\r \\t \\\\ only", () => {
  assert.deepEqual(parseEnvFile('A="a\\nb\\tc\\rd\\\\e"\n'), { A: "a\nb\tc\rd\\e" });
  assert.deepEqual(parseEnvFile('A="x\\qy\\"z"\n'), { A: 'x\\qy\\"z' });
});

test("parseEnvFile does not unquote unbalanced or lone quotes", () => {
  assert.deepEqual(parseEnvFile("A=\"abc\nB='abc\nC=\"\nD='\nE=\"abc'\n"), {
    A: '"abc', B: "'abc", C: '"', D: "'", E: "\"abc'",
  });
});

test("parseEnvFile unquotes an empty quoted value", () => {
  assert.deepEqual(parseEnvFile('A=""\nB=\'\'\n'), { A: "", B: "" });
});

test("parseEnvFile does not strip inline comments", () => {
  assert.deepEqual(parseEnvFile("A=1 # note\n"), { A: "1 # note" });
});

test("parseEnvFile keeps an empty value", () => {
  assert.deepEqual(parseEnvFile("A=\nB="), { A: "", B: "" });
});

test("parseEnvFile lets the last duplicate win", () => {
  assert.deepEqual(parseEnvFile("A=1\nA=2\n"), { A: "2" });
});

test("disallowedEnvKeys returns [] for empty input and allowed keys", () => {
  assert.deepEqual(disallowedEnvKeys(""), []);
  assert.deepEqual(disallowedEnvKeys("CLAUDE_CODE_OAUTH_TOKEN=a\nANTHROPIC_API_KEY=b\n"), []);
});

test("disallowedEnvKeys lists other keys in file order", () => {
  assert.deepEqual(
    disallowedEnvKeys("GH_TOKEN=a\nCLAUDE_CODE_OAUTH_TOKEN=x\nFOO=1\nGITHUB_TOKEN=c\n"),
    ["GH_TOKEN", "FOO", "GITHUB_TOKEN"],
  );
});

test("disallowedEnvKeys deduplicates", () => {
  assert.deepEqual(disallowedEnvKeys("FOO=1\nBAR=2\nFOO=3\n"), ["FOO", "BAR"]);
});

test("disallowedEnvKeys flags an exported allowed key as disallowed", () => {
  assert.deepEqual(disallowedEnvKeys("export ANTHROPIC_API_KEY=x\n"), ["export ANTHROPIC_API_KEY"]);
});

test("disallowedEnvKeys flags look-alike and lowercase keys", () => {
  assert.deepEqual(
    disallowedEnvKeys("anthropic_api_key=x\nANTHROPIC_API_KEY_2=y\n"),
    ["anthropic_api_key", "ANTHROPIC_API_KEY_2"],
  );
});

test("disallowedEnvKeys ignores comments and flags empty values", () => {
  assert.deepEqual(disallowedEnvKeys("# GH_TOKEN=x\nGH_TOKEN=\n"), ["GH_TOKEN"]);
});

test("disallowedEnvKeys never returns values", () => {
  const out = disallowedEnvKeys(`FOO=${SECRET}\n`);
  assert.ok(!out.join("").includes(SECRET));
});

test("secretValues returns file values of allowed keys", () => {
  assert.deepEqual(secretValues(`CLAUDE_CODE_OAUTH_TOKEN=${SECRET}\n`, {}), [SECRET]);
});

test("secretValues falls back to process env for an empty value", () => {
  const fromEnv = "process-env-secret-0123456789";
  assert.deepEqual(secretValues("ANTHROPIC_API_KEY=\n", { ANTHROPIC_API_KEY: fromEnv }), [fromEnv]);
});

test("secretValues prefers the file value over process env", () => {
  assert.deepEqual(
    secretValues(`ANTHROPIC_API_KEY=${SECRET}\n`, { ANTHROPIC_API_KEY: "process-env-secret-0123456789" }),
    [SECRET],
  );
});

test("secretValues ignores allowed keys absent from the file even if set in process env", () => {
  assert.deepEqual(secretValues("", { ANTHROPIC_API_KEY: "process-env-secret-0123456789" }), []);
});

test("secretValues ignores keys that are not allowed", () => {
  assert.deepEqual(secretValues(`GH_TOKEN=${SECRET}\n`, { GH_TOKEN: SECRET }), []);
});

test("secretValues drops values shorter than 16 chars and keeps 16", () => {
  assert.deepEqual(secretValues("ANTHROPIC_API_KEY=123456789012345\n", {}), []);
  assert.deepEqual(secretValues("ANTHROPIC_API_KEY=1234567890123456\n", {}), ["1234567890123456"]);
});

test("secretValues drops a short or missing process env fallback", () => {
  assert.deepEqual(secretValues("ANTHROPIC_API_KEY=\n", { ANTHROPIC_API_KEY: "short" }), []);
  assert.deepEqual(secretValues("ANTHROPIC_API_KEY=\n", {}), []);
});

test("secretValues returns both allowed keys", () => {
  const other = "another-secret-value-123456";
  const out = secretValues(`CLAUDE_CODE_OAUTH_TOKEN=${SECRET}\nANTHROPIC_API_KEY=${other}\n`, {});
  assert.deepEqual([...out].sort(), [SECRET, other].sort());
});

test("leakedSecret is false with no secrets or unrelated text", () => {
  assert.equal(leakedSecret("anything", []), false);
  assert.equal(leakedSecret("", [SECRET]), false);
  assert.equal(leakedSecret("diff --git a/x b/x\n+hello world\n", [SECRET]), false);
});

test("leakedSecret finds the plain secret", () => {
  assert.equal(leakedSecret(`before ${SECRET} after`, [SECRET]), true);
  assert.equal(leakedSecret(SECRET, [SECRET]), true);
});

test("leakedSecret finds lowercase and uppercase hex", () => {
  const hex = Buffer.from(SECRET).toString("hex");
  assert.equal(leakedSecret(`x=${hex.toLowerCase()};`, [SECRET]), true);
  assert.equal(leakedSecret(`x=${hex.toUpperCase()};`, [SECRET]), true);
});

test("leakedSecret does not match a partial secret", () => {
  assert.equal(leakedSecret(SECRET.slice(0, -4), [SECRET]), false);
});

test("leakedSecret matches any of several secrets", () => {
  assert.equal(leakedSecret(`xx ${SECRET} yy`, ["unrelated-secret-0123456789", SECRET]), true);
});

for (const [label, toUrl] of [
  ["base64", (s: string) => s],
  ["base64url", (s: string) => s.replaceAll("+", "-").replaceAll("/", "_")],
] as const) {
  for (let prefixLen = 0; prefixLen <= 8; prefixLen++) {
    test(`leakedSecret finds ${label} with ${prefixLen} leading bytes (alignment ${prefixLen % 3})`, () => {
      for (const secret of [SECRET, "~~~???>>>~~~???>>>~~~???>>>", "\u00e5\u00e4\u00f6-secret-value-0123456789"]) {
        const bytes = Buffer.concat([
          Buffer.from("PQRSTUVWX".slice(0, prefixLen)),
          Buffer.from(secret),
          Buffer.from("-trailing-bytes"),
        ]);
        const encoded = toUrl(bytes.toString("base64")).replaceAll("=", "");
        assert.equal(leakedSecret(`log line: ${encoded} end`, [secret]), true, secret);
      }
    });
  }
}

test("leakedSecret does not flag base64 of unrelated bytes", () => {
  const encoded = Buffer.from("this is just an ordinary commit message body").toString("base64");
  assert.equal(leakedSecret(encoded, [SECRET]), false);
});

const rec = (src: string, dst: string, status: string, path: string): string =>
  `:${src} ${dst} ${"a".repeat(40)} ${"b".repeat(40)} ${status}\0${path}\0`;

test("disallowedModes returns [] for empty output", () => {
  assert.deepEqual(disallowedModes(""), []);
});

test("disallowedModes allows normal and executable files", () => {
  assert.deepEqual(
    disallowedModes(rec("000000", "100644", "A", "a.yaml") + rec("100644", "100755", "M", "run.sh")),
    [],
  );
});

test("disallowedModes flags an added symlink", () => {
  assert.deepEqual(disallowedModes(rec("000000", "120000", "A", "link")), ["link"]);
});

test("disallowedModes flags an added gitlink", () => {
  assert.deepEqual(disallowedModes(rec("000000", "160000", "A", "vendor/sub")), ["vendor/sub"]);
});

test("disallowedModes flags a file changed into a symlink", () => {
  assert.deepEqual(disallowedModes(rec("100644", "120000", "T", "was-file")), ["was-file"]);
});

test("disallowedModes allows deleting a symlink or gitlink", () => {
  assert.deepEqual(
    disallowedModes(rec("120000", "000000", "D", "old-link") + rec("160000", "000000", "D", "old-sub")),
    [],
  );
});

test("disallowedModes allows modifying a normal file into a normal file", () => {
  assert.deepEqual(disallowedModes(rec("100644", "100644", "M", "x")), []);
});

test("disallowedModes keeps order and only the offenders", () => {
  const raw =
    rec("000000", "120000", "A", "z-link") +
    rec("000000", "100644", "A", "ok.txt") +
    rec("000000", "160000", "A", "a-sub") +
    rec("120000", "000000", "D", "gone");
  assert.deepEqual(disallowedModes(raw), ["z-link", "a-sub"]);
});

test("disallowedModes handles paths with spaces and newlines", () => {
  assert.deepEqual(
    disallowedModes(
      rec("000000", "120000", "A", "my link") +
        rec("000000", "160000", "A", "evil\nname") +
        rec("000000", "100644", "A", "fine file"),
    ),
    ["my link", "evil\nname"],
  );
});

test("unexpectedRefs returns [] for empty input and allowed refs", () => {
  assert.deepEqual(unexpectedRefs([]), []);
  assert.deepEqual(
    unexpectedRefs([
      "refs/heads/main", "refs/heads/agent/issue-3", "refs/remotes/origin/main",
      "refs/remotes/origin/feature", "refs/tags/v1",
    ]),
    [],
  );
});

test("unexpectedRefs returns other branches and refs in order", () => {
  assert.deepEqual(
    unexpectedRefs([
      "refs/heads/wip", "refs/heads/main", "refs/stash", "refs/heads/agent/x", "refs/notes/commits",
    ]),
    ["refs/heads/wip", "refs/stash", "refs/notes/commits"],
  );
});

test("unexpectedRefs is exact on main and prefix-based with the slash", () => {
  assert.deepEqual(
    unexpectedRefs(["refs/heads/main2", "refs/heads/main/x", "refs/heads/agent", "refs/heads/agentx/y", "refs/remotes/upstream/main", "refs/remotes/origin"]),
    ["refs/heads/main2", "refs/heads/main/x", "refs/heads/agent", "refs/heads/agentx/y", "refs/remotes/upstream/main", "refs/remotes/origin"],
  );
});

test("forConsole replaces ESC, BEL, NUL, DEL and C1 controls with ?", () => {
  assert.equal(forConsole("a\x1b[31mb"), "a?[31mb");
  assert.equal(forConsole("a\x07b\x00c\x7fd"), "a?b?c?d");
  assert.equal(forConsole("a\u009bb\u0080c\u009fd"), "a?b?c?d");
  assert.equal(forConsole("\r"), "?");
});

test("forConsole keeps newline, tab and printable text", () => {
  assert.equal(forConsole("a\nb\tc plain"), "a\nb\tc plain");
});

test("forConsole keeps non-ASCII letters", () => {
  assert.equal(forConsole("sk\u00e5p/\u00e4\u00f6.yaml"), "sk\u00e5p/\u00e4\u00f6.yaml");
});

test("changedGitState returns [] for identical states", () => {
  assert.deepEqual(changedGitState(STATE, { ...STATE }), []);
});

test("changedGitState names each single differing field", () => {
  assert.deepEqual(changedGitState(STATE, { ...STATE, head: "x" }), ["head"]);
  assert.deepEqual(changedGitState(STATE, { ...STATE, main: "x" }), ["main"]);
  assert.deepEqual(changedGitState(STATE, { ...STATE, originMain: "x" }), ["originMain"]);
  assert.deepEqual(changedGitState(STATE, { ...STATE, index: "x" }), ["index"]);
});

test("changedGitState returns all four in fixed order when all differ", () => {
  const after: GitState = { head: "1", main: "2", originMain: "3", index: "4" };
  assert.deepEqual(changedGitState(STATE, after), ["head", "main", "originMain", "index"]);
});

test("changedGitState uses fixed order regardless of which fields differ", () => {
  assert.deepEqual(changedGitState(STATE, { ...STATE, index: "x", head: "x" }), ["head", "index"]);
  assert.deepEqual(changedGitState(STATE, { ...STATE, originMain: "x", main: "x" }), ["main", "originMain"]);
});

// W1: line-wrapped encodings
const wrap = (s: string, width: number): string =>
  (s.match(new RegExp(`.{1,${width}}`, "g")) ?? []).join("\n");

// A `git log -p` stream where every added line carries a "+" marker.
const logPatch = (addedLines: string[], eol = "\n"): string =>
  [
    "commit 0123456789abcdef0123456789abcdef01234567",
    "Author: A <a@example.com>",
    "",
    "    add file",
    "",
    "diff --git a/x b/x",
    "new file mode 100644",
    "index 0000000..1111111",
    "--- /dev/null",
    "+++ b/x",
    `@@ -0,0 +1,${addedLines.length} @@`,
    ...addedLines.map((l) => `+${l}`),
  ].join(eol) + eol;

// What main.mts scans: the raw text plus the marker-free copy.
const scan = (text: string, secrets: string[]): boolean =>
  leakedSecret(text + "\n" + patchContent(text), secrets);

test("patchContent strips the first char of +, - and space content lines", () => {
  assert.equal(patchContent("+added\n-removed\n context"), "added\nremoved\ncontext");
});

test("patchContent turns a context line ' abc' into 'abc'", () => {
  assert.equal(patchContent(" abc"), "abc");
});

test("patchContent keeps +++ and --- file headers intact", () => {
  assert.equal(patchContent("--- a/x\n+++ b/x\n+body"), "--- a/x\n+++ b/x\nbody");
  assert.equal(patchContent("--- /dev/null\n+++ b/x"), "--- /dev/null\n+++ b/x");
});

test("patchContent keeps commit, diff, index and hunk header lines unchanged", () => {
  const headers = [
    "commit 0123456789abcdef0123456789abcdef01234567",
    "Author: A <a@example.com>",
    "diff --git a/x b/x",
    "new file mode 100644",
    "index 0000000..1111111",
    "@@ -0,0 +1,2 @@",
  ];
  assert.equal(patchContent(headers.join("\n")), headers.join("\n"));
});

test("patchContent removes only one marker char, even from '++' or '--' content", () => {
  assert.equal(patchContent("+++x\n---y\n++z\n--w\n+ +"), "++x\n--y\n+z\n-w\n +");
});

test("patchContent keeps every line of a full git log -p stream", () => {
  const out = patchContent(logPatch(["one", "two"]));
  assert.deepEqual(out.split("\n").slice(-4), ["@@ -0,0 +1,2 @@", "one", "two", ""]);
  assert.ok(out.includes("--- /dev/null\n+++ b/x\n"));
});

test("patchContent returns '' for empty input", () => {
  assert.equal(patchContent(""), "");
});

test("scan finds base64 wrapped at 76 columns with + on every added line", () => {
  const secret = `${SECRET}-and-a-longer-tail-so-it-wraps-more-than-once-0123456789`;
  const b64 = Buffer.from(secret).toString("base64");
  const lines = wrap(b64, 76).split("\n");
  assert.ok(lines.length > 1);
  const text = logPatch(lines);
  assert.equal(scan(text, [secret]), true);
});

test("scan finds wrapped base64 in CRLF patch text", () => {
  const secret = `${SECRET}-and-a-longer-tail-so-it-wraps-more-than-once-0123456789`;
  const lines = wrap(Buffer.from(secret).toString("base64"), 76).split("\n");
  assert.equal(scan(logPatch(lines, "\r\n"), [secret]), true);
});

test("scan finds hex wrapped at 60 columns with + on every added line", () => {
  const secret = `${SECRET}-and-a-longer-tail-so-it-wraps-more-than-once-0123456789`;
  const lines = wrap(Buffer.from(secret).toString("hex"), 60).split("\n");
  assert.ok(lines.length > 1);
  assert.equal(scan(logPatch(lines), [secret]), true);
});

test("scan finds wrapped base64 split across context lines too", () => {
  const secret = `${SECRET}-and-a-longer-tail-so-it-wraps-more-than-once-0123456789`;
  const lines = wrap(Buffer.from(secret).toString("base64"), 76).split("\n");
  const text = ["@@ -1,3 +1,5 @@", ...lines.map((l) => ` ${l}`)].join("\n");
  assert.equal(scan(text, [secret]), true);
});

test("leakedSecret alone misses wrapped base64 when every line has a + marker", () => {
  const secret = `${SECRET}-and-a-longer-tail-so-it-wraps-more-than-once-0123456789`;
  const lines = wrap(Buffer.from(secret).toString("base64"), 76).split("\n");
  assert.equal(leakedSecret(logPatch(lines), [secret]), false);
});

test("scan does not flag an unrelated wrapped patch", () => {
  const lines = wrap(Buffer.from("an ordinary body of text, nothing secret in here at all, really").toString("base64"), 76).split("\n");
  assert.equal(scan(logPatch(lines), [SECRET]), false);
  assert.equal(scan(logPatch(["hello world"]), [SECRET]), false);
});

test("scan still finds a plain secret on an added line", () => {
  assert.equal(scan(logPatch([`token = ${SECRET}`]), [SECRET]), true);
});

test("leakedSecret does not flag whitespace-only text or unrelated wrapped text", () => {
  assert.equal(leakedSecret(" \n\t\r\n  ", [SECRET]), false);
  assert.equal(leakedSecret(wrap(Buffer.from("an ordinary body of text, nothing secret in here at all").toString("base64"), 76), [SECRET]), false);
});

// N2: fold twice
test("fold maps capital sharp s to ss", () => {
  assert.equal(fold("\u1e9e"), "ss");
});

test("fold maps the ligature to plain letters and lowercases", () => {
  assert.equal(fold("Make\ufb01le"), "makefile");
  assert.equal(fold("MAKEFILE"), "makefile");
});

// C1: rawPaths (exported by the builder; absent export is reported, not guessed)
const rawPaths = guards.rawPaths as ((rawZ: string) => string[]) | undefined;

test("rawPaths returns every path in order, including odd names", () => {
  assert.equal(typeof rawPaths, "function", "guards.mts must export rawPaths");
  const raw = rec("000000", "100644", "A", "a.txt")
    + rec("100644", "100644", "M", "dir/with space.yaml")
    + rec("100644", "000000", "D", "new\nline.txt")
    + rec("000000", "120000", "A", ".github/link");
  assert.deepEqual(rawPaths!(raw), ["a.txt", "dir/with space.yaml", "new\nline.txt", ".github/link"]);
});

test("rawPaths returns [] for empty output", () => {
  assert.equal(typeof rawPaths, "function", "guards.mts must export rawPaths");
  assert.deepEqual(rawPaths!(""), []);
});

test("rawPaths covers multiple concatenated commits and repeated paths", () => {
  assert.equal(typeof rawPaths, "function", "guards.mts must export rawPaths");
  const raw = rec("000000", "100644", "A", "Makefile")
    + rec("100644", "100644", "M", "x.yaml")
    + rec("100644", "000000", "D", "Makefile")
    + rec("100644", "100644", "M", "x.yaml");
  assert.deepEqual(rawPaths!(raw), ["Makefile", "x.yaml", "Makefile", "x.yaml"]);
  // a path added then removed across commits is still visible to protectedPaths
  assert.deepEqual(protectedPaths(rawPaths!(raw)), ["Makefile", "Makefile"]);
});
