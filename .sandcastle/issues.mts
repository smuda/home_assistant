export type RawComment = {
  author: { login: string };
  authorAssociation: string;
  body: string;
};

export type RawIssue = {
  number: number;
  title: string;
  body: string;
  author: { login: string };
  assignees: { login: string }[];
  comments: RawComment[];
};

// Only these comment authors are shown to the agent; anyone can comment
// on a public repo.
export const TRUSTED_ASSOCIATIONS: readonly string[] = [
  "OWNER",
  "MEMBER",
  "COLLABORATOR",
];

// The lowest-numbered unassigned issue opened by the repo owner. Issues
// from other authors are never picked up.
export function pickIssue(
  issues: RawIssue[],
  owner: string,
): RawIssue | undefined {
  let best: RawIssue | undefined;
  for (const issue of issues) {
    if (issue.author.login !== owner || issue.assignees.length !== 0) continue;
    if (best === undefined || issue.number < best.number) best = issue;
  }
  return best;
}

export function trustedComments(issue: RawIssue): string {
  const kept = issue.comments.filter((c) =>
    TRUSTED_ASSOCIATIONS.includes(c.authorAssociation),
  );
  if (kept.length === 0) return "(no comments)";
  return kept.map((c) => `@${c.author.login}:\n${c.body}`).join("\n\n---\n\n");
}

export const MISSING_FINDINGS =
  "The reviewer did not report findings. See .sandcastle/logs/ on the host.";

// The reviewer's findings: undefined when it reported none, a fixed
// notice when it reported nothing at all, else the trimmed text.
export function parseFindings(raw: string | undefined): string | undefined {
  if (raw === undefined || raw.trim() === "") return MISSING_FINDINGS;
  const text = raw.trim();
  return text.toLowerCase() === "none" ? undefined : text;
}
