// Local, read-only Fettl review after successful file mutations. No repair tool.
import { execFileSync, spawn } from "node:child_process";
import { readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { isAbsolute, resolve as resolvePath } from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

const directory = join(homedir(), ".config", "fettl");
const policy = JSON.parse(readFileSync(join(directory, "hooks.json"), "utf8"));
const mutatingTools = new Set<string>(policy.omp_tools);

export default function fettl(pi: ExtensionAPI) {
  pi.on("tool_result", async (event, ctx) => {
    if (event.isError || !mutatingTools.has(event.toolName)) return;
    const input = event.input as Record<string, unknown> | undefined;
    const targets = Array.isArray(input?.paths) ? input.paths : [input?.path];
    const paths = targets.filter((target): target is string => typeof target === "string" && !target.includes("://"));
    if (!paths.length) return;
    try {
      const root = realpathSync(execFileSync("/usr/bin/git", ["-C", ctx.cwd, "rev-parse", "--show-toplevel"], {
        encoding: "utf8", stdio: ["ignore", "pipe", "ignore"],
      }).trim());
      if (!paths.some(target => {
        try { return realpathSync(isAbsolute(target) ? target : resolvePath(ctx.cwd, target)).startsWith(root + "/"); }
        catch { return false; }
      })) return;
    } catch { return; }
    const { promise, resolve } = Promise.withResolvers<string>();
    const child = spawn("/usr/bin/python3", [join(directory, "hook.py"), "omp"], {
      cwd: ctx.cwd,
      stdio: ["ignore", "pipe", "pipe"],
      timeout: (policy.wall_seconds + 5) * 1000,
    });
    let output = "";
    let diagnostic = "";
    child.stdout.on("data", (chunk: Buffer) => {
      output = (output + chunk.toString()).slice(0, 8000);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      diagnostic = (diagnostic + chunk.toString()).slice(0, 2000);
    });
    child.on("error", () => resolve("Fettl check could not start; this edit was not checked."));
    child.on("close", (code) => resolve(
      code === 0 || code === 1
        ? `Fettl read-only post-edit check (exit ${code}; no fixes applied):\n${output}${diagnostic}`
        : `Fettl check incomplete (exit ${code}); this edit was not fully checked.\n${diagnostic}`,
    ));
    const summary = await promise;
    let enforce = false;
    try { enforce = JSON.parse(readFileSync(join(directory, "mode.json"), "utf8")).mode === "enforce"; } catch {}
    if (enforce) return { additionalContext: summary };
  });
}
