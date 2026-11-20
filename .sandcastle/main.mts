// Sequential Reviewer -- implement-then-review loop over GitHub issues
//
// All GitHub and git-push work happens here on the host, using your own
// gh login. The sandbox gets no GitHub access and no token; issue text
// reaches the agent only as prompt arguments, and comments only from
// trusted authors.
//
// Per iteration (run from main, one issue each):
//   1. Pick the lowest-numbered open ready-for-agent issue that you
//      opened and that nobody is assigned to, and claim it (drop the
//      label, assign yourself).
//   2. Phase 1 (Implement): an Opus agent works on the issue on branch
//      agent/issue-<n> and commits. No commits -> the issue is labelled
//      ready-for-human with a comment, and the loop moves on.
//   3. Phase 2 (Review): a second Opus agent reviews the branch diff and
//      either approves it or corrects it directly on the branch.
//   4. Push the branch and open a PR against main. Nothing is deployed.
//      If the reviewer reported problems it could not fix, the PR is a
//      draft and the host posts the findings as a PR comment.
//
// Both phases share one sandbox created via createSandbox(), so they work
// on the same named branch. The loop stops after MAX_ITERATIONS issues or
// when no eligible issue is left.
//
// Isolation: the agent runs in an OpenShell sandbox with a git-bundle copy
// of the repo and no access to the host .git; its commits come back as
// patches into a host worktree. Build the image once with
//   docker build -t sandcastle-openshell:latest .sandcastle/openshell
// and keep the OpenShell gateway running.
//
// Run it from a dedicated clone that has only main (plus origin/* refs and
// tags): Sandcastle bundles every ref into the sandbox, so any other local
// branch would be readable by the agent. Startup refuses otherwise.
//
// Host-side guards stay as defence in depth: every host git call disables
// hooks and pins the credential helper; the git dir is checked for a
// planted commondir; HEAD, refs and the index must be unchanged after the
// sandbox; the branch must build on origin/main, touch no protected path
// and add no symlink or submodule before it is pushed (explicit refspec,
// recorded push URL), in every pushed commit, not just the net diff; the
// content and metadata of every pushed commit and the reviewer output are
// scanned for the .env credential; and a .env that sets anything but
// the Claude credential is refused.
//
// Usage:
//   npm run sandcastle

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { join, resolve } from "node:path";
import * as sandcastle from "@ai-hero/sandcastle";
import {
  changedGitState,
  disallowedEnvKeys,
  disallowedModes,
  patchContent,
  forConsole,
  leakedSecret,
  protectedPaths,
  rawPaths,
  secretValues,
  unexpectedRefs,
  type GitState,
} from "./guards.mts";
import { deleteLeftoverSandboxes, openshell } from "./openshell/provider.mts";
import {
  parseFindings,
  pickIssue,
  trustedComments,
  type RawIssue,
} from "./issues.mts";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Each cycle works on one issue. Raise this to process more issues per run.
const MAX_ITERATIONS = 2;
const MODEL = "claude-opus-5-5";

// ---------------------------------------------------------------------------
// Host helpers
// ---------------------------------------------------------------------------

// execFileSync with an argument array: no shell, so issue titles and other
// untrusted text can never be interpreted as commands.
// The large buffer is for whole-branch diffs scanned for secrets.
// A failure is rethrown with only the command, subcommand and exit status:
// the original error carries stdout and argv, which can hold agent output
// or a token.
const run = (cmd: string, args: string[], input?: string): string => {
  try {
    return execFileSync(cmd, args, {
      encoding: "utf8",
      input,
      maxBuffer: 256 * 1024 * 1024,
      stdio: ["pipe", "pipe", "ignore"],
    });
  } catch (e) {
    const status = (e as { status?: number | null }).status;
    const code = (e as { code?: string }).code;
    throw new Error(
      `${cmd} ${args.find((a) => !a.startsWith("-") && !a.includes("=")) ?? ""} failed (${status != null ? `exit ${status}` : (code ?? "no exit status")})`,
    );
  }
};
// Defence in depth: the agent cannot reach the host .git under OpenShell,
// but anything else that touched the repo (the host worktree Sandcastle
// syncs patches into) must not make git run hooks or a foreign credential
// helper.
const GIT_HARDENING = [
  "-c",
  "core.hooksPath=/dev/null",
  "-c",
  "credential.helper=",
  "-c",
  "credential.helper=!gh auth git-credential",
];
const git = (...args: string[]): string => run("git", [...GIT_HARDENING, ...args]);
const gh = (...args: string[]): string => run("gh", args);

const abort = (message: string): never => {
  console.error(message);
  process.exit(1);
  throw new Error(message);
};

const repoRoot = resolve(process.cwd());
const gitDir = join(repoRoot, ".git");

// Defence in depth: a planted .git/commondir would point git at a dir with
// its own config and hooks. Abort if the git dir is not the plain one.
const assertGitDir = (): void => {
  if (existsSync(join(gitDir, "commondir"))) {
    abort("Aborting: .git/commondir exists; the git dir may have been tampered with.");
  }
  const common = realpathSync(
    git("rev-parse", "--path-format=absolute", "--git-common-dir").trim(),
  );
  if (common !== realpathSync(gitDir)) {
    abort(`Aborting: git common dir is ${common}, not the repo's own .git.`);
  }
};

const sha256 = (path: string): string =>
  existsSync(path)
    ? createHash("sha256").update(readFileSync(path)).digest("hex")
    : "";

const recordGitState = (): GitState => ({
  head: readFileSync(join(gitDir, "HEAD"), "utf8").trim(),
  main: git("rev-parse", "refs/heads/main").trim(),
  originMain: git("rev-parse", "refs/remotes/origin/main").trim(),
  index: sha256(join(gitDir, "index")),
});

const handBack = (n: string, body: string): void => {
  gh("issue", "edit", n, "--repo", repo, "--add-label", "ready-for-human");
  gh("issue", "comment", n, "--repo", repo, "--body", body);
};

// Sandcastle bundles every ref into the sandbox.
const assertRefs = (): void => {
  const refs = git("for-each-ref", "--format=%(refname)").split("\n").filter((r) => r !== "");
  const unexpected = unexpectedRefs(refs);
  if (unexpected.length > 0) {
    abort(
      `Aborting: the sandbox would receive these refs (Sandcastle bundles every ref): ${forConsole(unexpected.join(", "))}. Run the loop from a dedicated clone with only main.`,
    );
  }
};

// ---------------------------------------------------------------------------
// Preconditions
// ---------------------------------------------------------------------------

assertGitDir();

// Anything but the Claude credential in the sandbox env would reach the agent.
const envPath = join(repoRoot, ".sandcastle", ".env");
let secrets: string[] = [];
if (existsSync(envPath)) {
  const envText = readFileSync(envPath, "utf8");
  const bad = disallowedEnvKeys(envText);
  if (bad.length > 0) {
    abort(
      `${envPath} has ${bad.length} line(s) with keys other than CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY. Only those may reach the sandbox; delete the other lines.`,
    );
  }
  secrets = secretValues(envText, process.env);
}

assertRefs();

// A sandbox that outlived an earlier run still holds the token.
await deleteLeftoverSandboxes();

// Agent branches are created from HEAD and the PR base is main.
const currentBranch = git("rev-parse", "--abbrev-ref", "HEAD").trim();
if (currentBranch !== "main") {
  abort(
    `Run Sandcastle from main (currently on ${currentBranch}): agent branches start from HEAD and PRs target main.`,
  );
}

// The tip checks below compare against origin/main, so local main must be
// the same commit.
git("fetch", "origin", "main");
if (
  git("rev-parse", "refs/heads/main").trim() !==
  git("rev-parse", "refs/remotes/origin/main").trim()
) {
  abort("local main differs from origin/main. Sync them and rerun.");
}

// Pushes go to this URL, not to whatever "origin" resolves to later.
const pushUrl = git("remote", "get-url", "--push", "origin").trim();

// Resolved before any sandbox exists, so gh never infers the repo from
// config the agent could have touched.
const repo = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner").trim();
const owner = gh("api", "user", "--jq", ".login").trim();

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

for (let iteration = 1; iteration <= MAX_ITERATIONS; iteration++) {
  console.log(`\n=== Iteration ${iteration}/${MAX_ITERATIONS} ===\n`);

  assertRefs();

  const issues: RawIssue[] = JSON.parse(
    gh(
      "issue",
      "list",
      "--repo",
      repo,
      "--state",
      "open",
      "--label",
      "ready-for-agent",
      "--limit",
      "100",
      "--json",
      "number,title,body,author,assignees,comments",
    ),
  );
  const issue = pickIssue(issues, owner);
  if (!issue) {
    console.log("No ready-for-agent issues left.");
    break;
  }
  const n = String(issue.number);

  // Claim the issue so a concurrent or later run does not pick it again.
  gh("issue", "edit", n, "--repo", repo, "--remove-label", "ready-for-agent", "--add-assignee", "@me");

  const branch = `agent/issue-${n}`;
  console.log(`Working on #${n}: ${issue.title} (branch ${branch})`);

  assertGitDir();
  const before = recordGitState();

  // Create a single sandbox that both the implementer and reviewer share.
  // This gives both agents a real, named branch that persists across phases.
  const sandbox = await sandcastle.createSandbox({
    branch,
    sandbox: openshell({
      image: "sandcastle-openshell:latest",
      policyPath: resolve(repoRoot, ".sandcastle/openshell/policy.yaml"),
    }),
  });

  let reviewed = false;
  let noCommits = false;
  let findings: string | undefined;
  const issueArgs = {
    ISSUE_NUMBER: n,
    ISSUE_TITLE: issue.title,
    ISSUE_BODY: issue.body || "(empty)",
    ISSUE_COMMENTS: trustedComments(issue),
  };

  try {
    // -----------------------------------------------------------------------
    // Phase 1: Implement
    //
    // An Opus agent works on the issue and commits the result. Issue text
    // arrives only as prompt arguments.
    //
    // The agent signals completion via <promise>COMPLETE</promise> when done.
    // -----------------------------------------------------------------------
    // One iteration so each outer pass implements a single issue on its own
    // branch, then hands it to the reviewer. A higher value lets the agent
    // drain the whole backlog onto this one branch in a single pass, which
    // defeats the per-issue review.
    const implement = await sandbox.run({
      name: "implementer",
      maxIterations: 1,
      agent: sandcastle.claudeCode(MODEL),
      promptFile: "./.sandcastle/implement-prompt.md",
      promptArgs: issueArgs,
    });

    if (!implement.commits.length) {
      // Handled after the sandbox closes and the git dir is re-checked.
      noCommits = true;
    } else {
      console.log(`\nImplementation complete on branch: ${branch}`);
      console.log(`Commits: ${implement.commits.length}`);

      // -----------------------------------------------------------------------
      // Phase 2: Review
      //
      // A second Opus agent reviews the diff of the branch produced by
      // Phase 1. It uses the {{BRANCH}} prompt argument to inspect the right
      // branch, and either approves or makes corrections directly on the branch.
      // -----------------------------------------------------------------------
      // The createSandbox handle's run() has no `output` option in this
      // Sandcastle version (only top-level run() does), so the <findings>
      // tag is extracted from stdout here. The last tag wins.
      const review = await sandbox.run({
        name: "reviewer",
        maxIterations: 1,
        agent: sandcastle.claudeCode(MODEL),
        promptFile: "./.sandcastle/review-prompt.md",
        promptArgs: { BRANCH: branch, ...issueArgs },
      });
      const tags = [...review.stdout.matchAll(/<findings>([\s\S]*?)<\/findings>/g)];
      findings = parseFindings(tags.at(-1)?.[1]);

      console.log("\nReview complete.");
      reviewed = true;
    }
  } finally {
    await sandbox.close();
  }

  assertGitDir();
  const changedState = changedGitState(before, recordGitState());
  if (changedState.length > 0) {
    abort(
      `Aborting: the sandbox changed host git state (${changedState.join(", ")}). Nothing was pushed for #${n}.`,
    );
  }

  if (noCommits) {
    // The agent was blocked or declined. Hand the issue back to a human;
    // agent output is deliberately not posted to GitHub.
    handBack(n, `Sandcastle made no commits on ${branch}. See .sandcastle/logs/ on the host.`);
    console.log(`Implementation agent made no commits on #${n}. Moving on.`);
    continue;
  }

  if (!reviewed) continue;

  // Push only a verified commit: the full ref so a same-named tag cannot
  // interfere, building on origin/main, touching no protected path.
  const tip = git("rev-parse", "--verify", `refs/heads/${branch}^{commit}`).trim();
  let basedOnOrigin: boolean;
  try {
    basedOnOrigin = git("merge-base", tip, before.originMain).trim() === before.originMain;
  } catch {
    basedOnOrigin = false;
  }
  // -z so core.quotePath cannot hide a path behind quoting. Every pushed
  // commit is listed, not just the net diff: a commit that adds a protected
  // file or symlink and a later one that removes it leaves no trace in the
  // net diff but is still pushed. --diff-merges=separate so merge commits are
  // listed too, --root so a root commit is.
  const range = `${before.originMain}..${tip}`;
  const perCommit = git(
    "log", "--diff-merges=separate", "--root", "--raw", "-z", "--no-renames", "--no-abbrev",
    "--format=", range,
  );
  const netRaw = git("diff", "--raw", "-z", "--no-renames", "--no-abbrev", before.originMain, tip);
  const offending = protectedPaths([...rawPaths(perCommit), ...rawPaths(netRaw)]).filter(
    (p, i, all) => all.indexOf(p) === i,
  );
  if (!basedOnOrigin || offending.length > 0) {
    // Paths go to the host console only; they are agent-controlled text.
    console.error(
      `Not pushing ${branch}: ` +
        (basedOnOrigin ? "" : "it does not build on origin/main. ") +
        (offending.length > 0
          ? `protected paths touched: ${forConsole(offending.join(", "))}`
          : ""),
    );
    handBack(
      n,
      `Sandcastle did not push ${branch}: the branch touches protected paths or does not build on origin/main. See the host console output.`,
    );
    continue;
  }

  const links = [...new Set([...disallowedModes(perCommit), ...disallowedModes(netRaw)])];
  if (links.length > 0) {
    console.error(
      `Not pushing ${branch}: symlink or submodule added: ${forConsole(links.join(", "))}`,
    );
    handBack(
      n,
      `Sandcastle did not push ${branch}: the branch adds a symlink or submodule. See the host console output.`,
    );
    continue;
  }

  // Everything that would leave the machine: the content and metadata of
  // every pushed commit, and the reviewer findings posted as a comment.
  const scanText = [
    git(
      "log", "--diff-merges=separate", "--root", "-p", "--text", "--no-textconv", "--no-ext-diff",
      "--format=%an%n%ae%n%B", range,
    ),
    findings ?? "",
  ].join("\n");
  if (leakedSecret(`${scanText}\n${patchContent(scanText)}`, secrets)) {
    console.error(
      `Not pushing ${branch}: it or the reviewer output contains a credential from .sandcastle/.env. Revoke the token, then delete branch ${branch}, .sandcastle/worktrees/ and .sandcastle/patches/.`,
    );
    handBack(
      n,
      `Sandcastle did not push ${branch}: it or the reviewer output contains a credential. See the host console output.`,
    );
    continue;
  }

  git("push", pushUrl, `${tip}:refs/heads/${branch}`);
  const prArgs = [
    "pr",
    "create",
    "--repo",
    repo,
    "--base",
    "main",
    "--head",
    branch,
    "--title",
    issue.title,
    "--body",
    `Closes #${n}\n\nImplemented and reviewed by the Sandcastle agent loop. Not deployed: review it, then run make deploy yourself.` +
      (findings !== undefined
        ? "\n\nDraft: the reviewer reported problems it could not fix. See the comment below."
        : ""),
  ];
  if (findings !== undefined) prArgs.push("--draft");
  const prUrl = gh(...prArgs).trim();
  console.log(`PR opened: ${prUrl}`);

  if (findings !== undefined) {
    // Body goes through stdin, never argv or a shell.
    run(
      "gh",
      ["pr", "comment", prUrl, "--repo", repo, "--body-file", "-"],
      `Sandcastle reviewer findings. This is unverified agent output; check it against the diff.\n\n${findings}`,
    );
  }
}

console.log("\nAll done.");
