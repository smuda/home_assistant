// OpenShell isolated provider for Sandcastle.
//
// Everything goes through the `openshell` CLI. File transfer uses
// `sandbox exec` with stdin/stdout pipes (cat / tar) instead of
// `sandbox upload|download`: upload applies .gitignore filtering inside a
// git work tree by default and its file-vs-directory DEST semantics are not
// documented, while exec's stdin piping and exit-code propagation are.
//
// Env (CLAUDE_CODE_OAUTH_TOKEN from .sandcastle/.env) is written to a 0600
// file in the sandbox over exec stdin, and every exec sources it. The token
// never appears in any process argv or in the openshell CLI's environment.
// It is still a plain value the agent can read inside the sandbox.

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import {
  createIsolatedSandboxProvider,
  type IsolatedSandboxHandle,
  type IsolatedSandboxProvider,
} from "@ai-hero/sandcastle";
import { forConsole } from "../guards.mts";

const HOME = "/sandbox";
const WORKTREE = `${HOME}/repo`;
const ENV_FILE = `${HOME}/.sandcastle-env`;
const TAIL_CHARS = 200_000;
const MAX_COPY_OUT_BYTES = 64 * 1024 * 1024;

interface CliResult {
  stdout: Buffer;
  stderr: string;
  exitCode: number;
  // Set when maxStdoutBytes was exceeded; the child was killed.
  overflowed: boolean;
}

interface CliOptions {
  stdin?: string | Buffer;
  onLine?: (line: string) => void;
  // Keep all of stdout, up to this many bytes, instead of the last
  // TAIL_CHARS. For binary-safe file reads.
  maxStdoutBytes?: number;
}

const log = (msg: string) => process.stderr.write(`[openshell] ${msg}\n`);

const runCli = (args: string[], opts: CliOptions = {}): Promise<CliResult> =>
  new Promise((resolve, reject) => {
    const child = spawn("openshell", ["--color", "never", ...args], {
      stdio: ["pipe", "pipe", "pipe"],
    });
    const limit = opts.maxStdoutBytes;
    let out: Buffer[] = [];
    let outBytes = 0;
    let overflowed = false;
    let stderr = "";
    let partial = "";
    child.stdout.on("data", (chunk: Buffer) => {
      if (overflowed) return;
      out.push(chunk);
      outBytes += chunk.length;
      if (limit !== undefined && outBytes > limit) {
        overflowed = true;
        out = [];
        child.kill();
        return;
      }
      if (limit === undefined && outBytes > TAIL_CHARS) {
        const tail = Buffer.concat(out).subarray(-TAIL_CHARS);
        out = [tail];
        outBytes = tail.length;
      }
      if (opts.onLine) {
        const lines = (partial + chunk.toString("utf8")).split("\n");
        partial = (lines.pop() ?? "").slice(-TAIL_CHARS);
        for (const line of lines) opts.onLine(line);
      }
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr = (stderr + chunk.toString("utf8")).slice(-TAIL_CHARS);
    });
    child.on("error", reject);
    child.on("close", (code: number | null, signal: string | null) => {
      if (opts.onLine && partial) opts.onLine(partial);
      resolve({
        stdout: Buffer.concat(out),
        stderr,
        exitCode: code ?? (signal ? 128 : 1),
        overflowed,
      });
    });
    child.stdin.on("error", () => {});
    child.stdin.end(opts.stdin ?? "");
  });

// Runs a host command (no shell) and returns its stdout.
const collect = (cmd: string, args: string[]): Promise<Buffer> =>
  new Promise((resolve, reject) => {
    const child = spawn(cmd, args);
    const parts: Buffer[] = [];
    child.stdout.on("data", (d: Buffer) => parts.push(d));
    child.on("error", reject);
    child.on("close", (code: number | null) =>
      code === 0 ? resolve(Buffer.concat(parts)) : reject(new Error(`${cmd} exit ${code}`)),
    );
  });

// POSIX single-quote: safe for any value, including embedded quotes.
export const shq = (s: string): string => `'${s.replaceAll("'", `'\\''`)}'`;

// A key goes into the shell script unquoted, so it must be a plain name.
export const envFileBody = (env: Record<string, string>): string => {
  const lines = Object.entries(env).map(([k, v]) => {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(k)) throw new Error(`invalid env key: ${k}`);
    return `export ${k}=${shq(v)}`;
  });
  return lines.join("\n") + "\n";
};

// OpenShell names are max 19 chars.
export const sandboxName = (hex: string): string => `sandcastle-${hex.slice(0, 8)}`;

// Sandbox names this provider creates, from `openshell sandbox list --names`
// (one name per line).
export const leftoverSandboxNames = (listOutput: string): string[] =>
  listOutput
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^sandcastle-[0-9a-f]{8}$/.test(line));

const must = (what: string, r: CliResult): CliResult => {
  if (r.exitCode !== 0) {
    const text = forConsole(r.stderr.trim() || r.stdout.toString().trim());
    throw new Error(`${what} failed (exit ${r.exitCode}): ${text.slice(-2000)}`);
  }
  return r;
};

const deleteSandbox = (name: string): Promise<CliResult> => runCli(["sandbox", "delete", name]);

// A sandbox that outlived its run still holds the token, so a failure here
// aborts the loop rather than being logged and ignored.
export const deleteLeftoverSandboxes = async (): Promise<void> => {
  const list = must("sandbox list", await runCli(["sandbox", "list", "--names"]));
  for (const name of leftoverSandboxNames(list.stdout.toString("utf8"))) {
    must(`sandbox delete ${name}`, await deleteSandbox(name));
    log(`deleted leftover sandbox ${name}`);
  }
};

export type OpenshellOptions = { image: string; policyPath: string };

export const openshell = (options: OpenshellOptions): IsolatedSandboxProvider =>
  createIsolatedSandboxProvider({
    name: "openshell",
    create: async ({ env }) => {
      const name = sandboxName(randomUUID());
      log(`creating sandbox ${name} from ${options.image}`);
      must(
        "sandbox create",
        await runCli([
          "sandbox", "create",
          "--name", name,
          "--from", options.image,
          "--policy", options.policyPath,
          "--no-auto-providers",
          "--no-tty",
          "--detach",
          "--", "sleep", "infinity",
        ]),
      );

      // Raw exec: argv goes to `openshell sandbox exec`, no env sourcing.
      const rawExec = (script: string, opts: CliOptions & { cwd?: string } = {}) =>
        runCli(
          [
            "sandbox", "exec", "-n", name, "--no-tty", "--no-login-shell",
            ...(opts.cwd ? ["--workdir", opts.cwd] : []),
            "--", "sh", "-c", script,
          ],
          opts,
        );

      const close = async () => {
        log(`deleting sandbox ${name}`);
        const r = await deleteSandbox(name);
        if (r.exitCode !== 0) {
          console.error(
            `[openshell] could not delete sandbox ${name}: ${forConsole(r.stderr.trim())}. Delete it with: openshell sandbox delete ${name}`,
          );
        }
      };

      try {
        const envBody = envFileBody(env);
        must(
          "write env file",
          await rawExec(`umask 077 && mkdir -p ${WORKTREE} && cat > ${ENV_FILE}`, {
            stdin: envBody,
          }),
        );
      } catch (e) {
        await close();
        throw e;
      }

      const handle: IsolatedSandboxHandle = {
        worktreePath: WORKTREE,
        sandboxId: name,
        exec: async (command, opts) => {
          if (opts?.sudo) log(`sudo requested but not supported; running unprivileged: ${command}`);
          const r = await rawExec(`. ${ENV_FILE}\n${command}`, {
            cwd: opts?.cwd ?? WORKTREE,
            stdin: opts?.stdin,
            onLine: opts?.onLine,
          });
          return {
            stdout: r.stdout.toString("utf8").slice(-TAIL_CHARS),
            stderr: r.stderr,
            exitCode: r.exitCode,
          };
        },
        copyIn: async (hostPath, sandboxPath) => {
          const info = await stat(hostPath);
          if (info.isDirectory()) {
            const tar = await collect("tar", ["-cf", "-", "-C", hostPath, "."]);
            must(
              `copyIn dir ${hostPath}`,
              await rawExec(`mkdir -p ${shq(sandboxPath)} && tar -xf - -C ${shq(sandboxPath)}`, {
                stdin: tar,
              }),
            );
          } else {
            must(
              `copyIn file ${hostPath}`,
              await rawExec(
                `mkdir -p "$(dirname ${shq(sandboxPath)})" && cat > ${shq(sandboxPath)}`,
                { stdin: await readFile(hostPath) },
              ),
            );
          }
        },
        copyFileOut: async (sandboxPath, hostPath) => {
          const r = await rawExec(`cat ${shq(sandboxPath)}`, { maxStdoutBytes: MAX_COPY_OUT_BYTES });
          if (r.overflowed) throw new Error(`copyFileOut ${sandboxPath}: file larger than 64 MiB`);
          must(`copyFileOut ${sandboxPath}`, r);
          await mkdir(dirname(hostPath), { recursive: true });
          await writeFile(hostPath, r.stdout);
        },
        close,
      };
      return handle;
    },
  });
