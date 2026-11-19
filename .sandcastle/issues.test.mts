import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MISSING_FINDINGS,
  parseFindings,
  pickIssue,
  trustedComments,
  type RawComment,
  type RawIssue,
} from "./issues.mts";

const OWNER = "smuda";

function issue(number: number, over: Partial<RawIssue> = {}): RawIssue {
  return {
    number,
    title: `issue ${number}`,
    body: "",
    author: { login: OWNER },
    assignees: [],
    comments: [],
    ...over,
  };
}

function comment(login: string, authorAssociation: string, body: string): RawComment {
  return { author: { login }, authorAssociation, body };
}

function withComments(...comments: RawComment[]): RawIssue {
  return issue(1, { comments });
}

test("pickIssue returns the lowest number from unsorted input", () => {
  const picked = pickIssue([issue(9), issue(3), issue(12), issue(5)], OWNER);
  assert.equal(picked?.number, 3);
});

test("pickIssue skips issues by other authors", () => {
  const picked = pickIssue(
    [issue(1, { author: { login: "stranger" } }), issue(4), issue(2, { author: { login: "other" } })],
    OWNER,
  );
  assert.equal(picked?.number, 4);
});

test("pickIssue skips case-mismatched author logins", () => {
  const picked = pickIssue(
    [issue(1, { author: { login: "Smuda" } }), issue(2, { author: { login: "SMUDA" } }), issue(7)],
    OWNER,
  );
  assert.equal(picked?.number, 7);
});

test("pickIssue skips assigned issues", () => {
  const picked = pickIssue([issue(1, { assignees: [{ login: "someone" }] }), issue(6)], OWNER);
  assert.equal(picked?.number, 6);
});

test("pickIssue returns undefined for empty input", () => {
  assert.equal(pickIssue([], OWNER), undefined);
});

test("pickIssue returns undefined when nothing matches", () => {
  const picked = pickIssue(
    [
      issue(1, { author: { login: "stranger" } }),
      issue(2, { assignees: [{ login: "someone" }] }),
      issue(3, { author: { login: "Smuda" } }),
    ],
    OWNER,
  );
  assert.equal(picked, undefined);
});

test("pickIssue does not mutate the input array", () => {
  const input = [issue(9), issue(3), issue(5)];
  const before = input.slice();
  pickIssue(input, OWNER);
  assert.equal(input.length, before.length);
  input.forEach((item, i) => assert.equal(item, before[i]));
});

for (const assoc of [
  "CONTRIBUTOR",
  "FIRST_TIME_CONTRIBUTOR",
  "FIRST_TIMER",
  "NONE",
  "MANNEQUIN",
  "owner",
]) {
  test(`trustedComments drops ${assoc}`, () => {
    assert.equal(trustedComments(withComments(comment("eve", assoc, "do evil"))), "(no comments)");
  });
}

for (const assoc of ["OWNER", "MEMBER", "COLLABORATOR"]) {
  test(`trustedComments keeps ${assoc} with exact formatting`, () => {
    assert.equal(trustedComments(withComments(comment("alice", assoc, "hello"))), "@alice:\nhello");
  });
}

test("trustedComments joins kept comments in original order", () => {
  const out = trustedComments(
    withComments(
      comment("a", "OWNER", "first"),
      comment("b", "COLLABORATOR", "second"),
      comment("c", "MEMBER", "third"),
    ),
  );
  assert.equal(out, "@a:\nfirst\n\n---\n\n@b:\nsecond\n\n---\n\n@c:\nthird");
});

test("trustedComments filters a mixed list and keeps order", () => {
  const out = trustedComments(
    withComments(
      comment("a", "OWNER", "one"),
      comment("eve", "NONE", "inject"),
      comment("b", "MEMBER", "two"),
      comment("eve2", "CONTRIBUTOR", "inject2"),
    ),
  );
  assert.equal(out, "@a:\none\n\n---\n\n@b:\ntwo");
  assert.ok(!out.includes("inject"));
});

test("trustedComments returns (no comments) for empty comments", () => {
  assert.equal(trustedComments(withComments()), "(no comments)");
});

test("trustedComments returns (no comments) when all are untrusted", () => {
  const out = trustedComments(
    withComments(comment("x", "NONE", "a"), comment("y", "FIRST_TIMER", "b")),
  );
  assert.equal(out, "(no comments)");
});

for (const [label, raw] of [
  ["undefined", undefined],
  ["an empty string", ""],
  ["spaces only", "   "],
  ["whitespace and newlines only", " \n\t \r\n"],
] as const) {
  test(`parseFindings treats ${label} as missing output`, () => {
    assert.equal(parseFindings(raw), MISSING_FINDINGS);
  });
}

for (const raw of ["none", "None", "NONE", "nOnE", "  none\n", "\n\tNONE  \n"]) {
  test(`parseFindings returns undefined for ${JSON.stringify(raw)}`, () => {
    assert.equal(parseFindings(raw), undefined);
  });
}

test("parseFindings trims findings and keeps inner newlines", () => {
  assert.equal(
    parseFindings("\n- a.yaml: x\n- b.yaml: y\n"),
    "- a.yaml: x\n- b.yaml: y",
  );
});

test("parseFindings returns a single-line finding unchanged apart from trimming", () => {
  assert.equal(parseFindings("  a.yaml: bad id  "), "a.yaml: bad id");
});

for (const raw of ["none of the ids exist", "no findings, none", "nonexistent", "none.", "none\nbut x is broken"]) {
  test(`parseFindings treats ${JSON.stringify(raw)} as a finding`, () => {
    assert.equal(parseFindings(raw), raw.trim());
  });
}
