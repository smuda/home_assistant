import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { envFileBody, leftoverSandboxNames, sandboxName, shq } from "./provider.mts";

const tmp = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), "openshell-test."));
let n = 0;

// Source the body in a real /bin/sh and print one variable.
const sourceAndPrint = (body: string, key: string): string => {
  const file = join(tmp, `env-${n++}`);
  writeFileSync(file, body);
  return execFileSync("/bin/sh", ["-c", `. "$1"; printf %s "$${key}"`, "sh", file], {
    encoding: "utf8",
  });
};

test("shq wraps a plain string in single quotes", () => {
  assert.equal(shq("abc"), "'abc'");
});

test("shq quotes the empty string", () => {
  assert.equal(shq(""), "''");
});

test("shq escapes an embedded single quote", () => {
  assert.equal(shq("it's"), `'it'\\''s'`);
});

test("shq leaves $, backticks and spaces inert inside the quotes", () => {
  assert.equal(shq("$HOME `x` a b"), "'$HOME `x` a b'");
});

test("shq output round-trips through /bin/sh", () => {
  for (const v of ["", "a b", "it's", "'", "''", "$(echo x)", "a\nb", "\\", '"q"']) {
    const out = execFileSync("/bin/sh", ["-c", `printf %s ${shq(v)}`], { encoding: "utf8" });
    assert.equal(out, v);
  }
});

test("envFileBody writes one export line per key with a trailing newline", () => {
  assert.equal(envFileBody({ A: "1", B_2: "two" }), "export A='1'\nexport B_2='two'\n");
});

test("envFileBody of an empty env has no export lines", () => {
  assert.doesNotMatch(envFileBody({}), /export/);
});

test("envFileBody quotes values with shq", () => {
  assert.equal(envFileBody({ K: "it's" }), `export K=${shq("it's")}\n`);
});

test("envFileBody round-trips a value with ', $ and a newline through sh", () => {
  const value = "a'b $HOME $(echo pwned) `id`\nsecond line \\ \"q\"";
  assert.equal(sourceAndPrint(envFileBody({ SECRET: value }), "SECRET"), value);
});

test("envFileBody round-trips an empty value", () => {
  assert.equal(sourceAndPrint(envFileBody({ EMPTY: "" }), "EMPTY"), "");
});

test("envFileBody round-trips several keys independently", () => {
  const body = envFileBody({ _A: "x'y", B1: "$B1", C: "line1\nline2" });
  assert.equal(sourceAndPrint(body, "_A"), "x'y");
  assert.equal(sourceAndPrint(body, "B1"), "$B1");
  assert.equal(sourceAndPrint(body, "C"), "line1\nline2");
});

test("envFileBody rejects invalid keys with the exact message", () => {
  for (const key of ["", "1A", "A-B", "A B", "A;touch x", "A=B", "a.b", "A\nB", "$(x)", "é"]) {
    assert.throws(() => envFileBody({ [key]: "v" }), new Error(`invalid env key: ${key}`));
  }
});

test("envFileBody accepts underscore-led and mixed-case keys", () => {
  assert.doesNotThrow(() => envFileBody({ _x: "1", aB_9: "2" }));
});

test("sandboxName uses the sandcastle- prefix and the first 8 hex chars", () => {
  assert.equal(sandboxName("0123456789abcdef"), "sandcastle-01234567");
});

test("sandboxName stays within the 19 character OpenShell limit", () => {
  assert.equal(sandboxName("f".repeat(64)).length, 19);
  assert.ok(sandboxName("abc").length <= 19);
});

// `openshell sandbox list --names` prints one name per line; the default
// table format was not inspected (no gateway call allowed), so only
// line-based name filtering is tested.
test("leftoverSandboxNames returns [] for empty output", () => {
  assert.deepEqual(leftoverSandboxNames(""), []);
  assert.deepEqual(leftoverSandboxNames("\n\n"), []);
});

test("leftoverSandboxNames keeps sandcastle-<8 hex> names in order", () => {
  assert.deepEqual(
    leftoverSandboxNames("sandcastle-0123abcd\nsandcastle-deadbeef\n"),
    ["sandcastle-0123abcd", "sandcastle-deadbeef"],
  );
});

test("leftoverSandboxNames handles CRLF and surrounding whitespace", () => {
  assert.deepEqual(
    leftoverSandboxNames("  sandcastle-0123abcd  \r\nsandcastle-deadbeef\r\n"),
    ["sandcastle-0123abcd", "sandcastle-deadbeef"],
  );
});

test("leftoverSandboxNames drops other names and look-alikes", () => {
  assert.deepEqual(
    leftoverSandboxNames(
      [
        "my-sandbox",
        "sandcastle-0123abc",
        "sandcastle-0123abcde",
        "sandcastle-0123ABCD",
        "sandcastle-0123abcg",
        "xsandcastle-0123abcd",
        "sandcastle-0123abcd-2",
        "sandcastle-",
        "sandcastle-0123abcd extra",
        "sandcastle-aaaaaaaa",
      ].join("\n"),
    ),
    ["sandcastle-aaaaaaaa"],
  );
});
