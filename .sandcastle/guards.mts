// Pure host-side guards for main.mts: no I/O, so they are easy to test.

// Paths an agent branch must not touch: they act as soon as they are
// pushed (CI workflows, build files) or change how the loop itself runs.
// Matching is on folded paths (see fold), root-only unless noted.
export const PROTECTED_PREFIXES: readonly string[] = [".github/", ".sandcastle/"];
export const PROTECTED_FILES: readonly string[] = [
  "Makefile",
  "GNUmakefile",
  "package.json",
  "package-lock.json",
  ".gitmodules",
];
// Any directory segment at any depth.
export const PROTECTED_DIRS: readonly string[] = [".claude", ".vscode", ".opencode"];
// The last segment, at any depth.
export const PROTECTED_NAMES: readonly string[] = [
  ".gitattributes",
  "CLAUDE.md",
  "AGENTS.md",
  ".npmrc",
  "opencode.json",
  ".mcp.json",
  ".lfsconfig",
  ".pre-commit-config.yaml",
  ".envrc",
  "tsconfig.json",
];

// Only these keys may reach the sandbox: it must never see a GitHub
// credential or any other secret.
export const ALLOWED_ENV_KEYS: readonly string[] = [
  "CLAUDE_CODE_OAUTH_TOKEN",
  "ANTHROPIC_API_KEY",
];

// Compatibility folding as APFS does it: "ſ" is "s" and "ﬁ" is "fi", so
// ".ſandcastle/" is the same directory as ".sandcastle/" on the host. Case
// mapping runs twice because "ẞ" lowercases to "ß" but only upper-cases to
// "SS" on the second pass.
export const fold = (p: string): string =>
  p.normalize("NFKC").toUpperCase().toLowerCase().toUpperCase().toLowerCase();

// The changed paths that are protected, in input order, original case.
export function protectedPaths(changed: string[]): string[] {
  const prefixes = PROTECTED_PREFIXES.map(fold);
  const files = PROTECTED_FILES.map(fold);
  const dirs = PROTECTED_DIRS.map(fold);
  const names = PROTECTED_NAMES.map(fold);
  return changed.filter((p) => {
    const folded = fold(p);
    const segments = folded.split("/");
    const last = segments.at(-1) ?? "";
    return (
      prefixes.some((prefix) => folded.startsWith(prefix)) ||
      files.includes(folded) ||
      segments.slice(0, -1).some((s) => dirs.includes(s)) ||
      names.includes(last)
    );
  });
}

// ---------------------------------------------------------------------------
// .env handling
// ---------------------------------------------------------------------------

const ESCAPES: Record<string, string> = { n: "\n", r: "\r", t: "\t", "\\": "\\" };

// Mirrors `unquote` in @ai-hero/sandcastle 0.14.0 dist/index.js.
const unquote = (value: string): string => {
  const double = value.length >= 2 && value.startsWith('"') && value.endsWith('"');
  const single = value.length >= 2 && value.startsWith("'") && value.endsWith("'");
  if (single) return value.slice(1, -1);
  if (!double) return value;
  return value.slice(1, -1).replaceAll(/\\([nrt\\])/gu, (_, ch: string) => ESCAPES[ch] ?? ch);
};

// Mirrors `parseEnvLine` / `parseEnvFile` in @ai-hero/sandcastle 0.14.0
// dist/index.js, which decide what reaches the sandbox: no `export `
// handling (a literal "export GH_TOKEN" is the key), no inline comments,
// later duplicates win.
const parseEnvEntries = (text: string): [string, string][] => {
  const entries: [string, string][] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    entries.push([trimmed.slice(0, eq).trim(), unquote(trimmed.slice(eq + 1).trim())]);
  }
  return entries;
};

export function parseEnvFile(text: string): Record<string, string> {
  return Object.fromEntries(parseEnvEntries(text));
}

// Keys the env file sets that are not allowed, in file order. Only keys
// are returned, never values. A key can still be a mangled line (the
// parser keeps "export X" or "A: secret" as a key), so never print them.
export function disallowedEnvKeys(text: string): string[] {
  const found: string[] = [];
  for (const [key] of parseEnvEntries(text)) {
    if (!ALLOWED_ENV_KEYS.includes(key) && !found.includes(key)) found.push(key);
  }
  return found;
}

// The secret values the sandbox will get, for the token scan. An empty
// value falls back to process.env, as Sandcastle's resolveEnv does. The
// claudeCode agent provider adds no env of its own.
export function secretValues(
  text: string,
  processEnv: Record<string, string | undefined>,
): string[] {
  const env = parseEnvFile(text);
  const values: string[] = [];
  for (const key of ALLOWED_ENV_KEYS) {
    if (!Object.hasOwn(env, key)) continue;
    const value = env[key] || processEnv[key] || "";
    if (value.length >= 16 && !values.includes(value)) values.push(value);
  }
  return values;
}

// True if any secret appears in text: plain, hex, or base64 / base64url
// at any of the three byte alignments. For an alignment k the secret is
// encoded after k zero bytes; the first group (k > 0) and the last group
// depend on neighbouring bytes, so only the core between them is searched.
// Whitespace is also stripped from the text first, so an encoding wrapped
// across lines (base64 at 76 columns, hex at 60) is still found.
// In `git log -p` output every content line starts with a diff marker, so
// scan patchContent(text) as well: the marker breaks a wrapped encoding.
// Never returns or logs a secret.
export function leakedSecret(text: string, secrets: string[]): boolean {
  const compact = text.replace(/\s+/g, "");
  for (const secret of secrets) {
    if (secret === "") continue;
    const bytes = Buffer.from(secret, "utf8");
    const needles = [secret, bytes.toString("hex"), bytes.toString("hex").toUpperCase()];
    for (let k = 0; k < 3; k++) {
      const b64 = Buffer.concat([Buffer.alloc(k), bytes]).toString("base64").replaceAll("=", "");
      const core = b64.slice(k > 0 ? 4 : 0, -4);
      if (core === "") continue;
      needles.push(core, core.replaceAll("+", "-").replaceAll("/", "_"));
    }
    if (needles.some((needle) => text.includes(needle) || compact.includes(needle))) return true;
  }
  return false;
}

// `git log -p` output without the one-char diff marker ("+", "-" or " ") of
// each hunk content line, so a base64 or hex encoding wrapped across added
// lines becomes contiguous once whitespace is stripped. File headers
// ("+++ ", "--- ") and every other line are kept as they are.
export function patchContent(patch: string): string {
  return patch
    .split("\n")
    .map((line) =>
      /^[-+ ]/.test(line) && !line.startsWith("+++ ") && !line.startsWith("--- ")
        ? line.slice(1)
        : line,
    )
    .join("\n");
}

// ---------------------------------------------------------------------------
// Git output checks
// ---------------------------------------------------------------------------

// Every path in a `git ... --raw -z --no-renames` record stream, in order.
export function rawPaths(rawZ: string): string[] {
  const parts = rawZ.split("\0");
  const found: string[] = [];
  for (let i = 1; i < parts.length; i += 2) found.push(parts[i]);
  return found.filter((p) => p !== "");
}

// Paths added or changed to a symlink (120000) or gitlink (160000) in the
// output of `git diff --raw -z --no-renames --no-abbrev`, whose records
// are ":<srcmode> <dstmode> <srcsha> <dstsha> <status>\0<path>\0".
// Deleting a symlink has dstmode 000000 and is allowed.
export function disallowedModes(rawZ: string): string[] {
  const parts = rawZ.split("\0");
  const found: string[] = [];
  for (let i = 0; i + 1 < parts.length; i += 2) {
    const dstMode = parts[i].split(" ")[1];
    if (dstMode === "120000" || dstMode === "160000") found.push(parts[i + 1]);
  }
  return found;
}

// Full ref names the sandbox would receive that the loop does not expect:
// Sandcastle bundles every ref into the sandbox.
export function unexpectedRefs(refs: string[]): string[] {
  return refs.filter(
    (ref) =>
      ref !== "refs/heads/main" &&
      !ref.startsWith("refs/heads/agent/") &&
      !ref.startsWith("refs/remotes/origin/") &&
      !ref.startsWith("refs/tags/"),
  );
}

// Agent-controlled text printed to the host terminal must not carry
// escape sequences: C0 and C1 controls and DEL become "?", except \n and \t.
export function forConsole(s: string): string {
  return s.replaceAll(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/gu, "?");
}

export type GitState = {
  head: string;
  main: string;
  originMain: string;
  index: string;
};

// Names of the fields that differ, in a fixed order.
export function changedGitState(before: GitState, after: GitState): string[] {
  const fields: (keyof GitState)[] = ["head", "main", "originMain", "index"];
  return fields.filter((f) => before[f] !== after[f]);
}
