import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const guard = fileURLToPath(new URL("../claude/credential-guard.py", import.meta.url));
const failure = { block: true, reason: "Credential guard unavailable; tool call blocked." };

function inspect(input) {
  return new Promise((resolve) => {
    const child = spawn("python3", [guard], { stdio: ["pipe", "pipe", "ignore"] });
    let output = "";
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(failure);
    }, 5000);
    child.on("error", () => finish(failure));
    child.stdin.on("error", () => finish(failure));
    child.stdout.on("data", (chunk) => {
      output += chunk;
      if (output.length > 65536) {
        child.kill("SIGKILL");
        finish(failure);
      }
    });
    child.on("close", (code) => {
      if (code !== 0) return finish(failure);
      if (!output.trim()) return finish(undefined);
      try {
        const decision = JSON.parse(output)?.hookSpecificOutput;
        if (decision?.permissionDecision === "deny") {
          return finish({ block: true, reason: "Credential access blocked; request a passd capability." });
        }
      } catch { /* Invalid output blocks the call. */ }
      finish(failure);
    });
    child.stdin.end(input);
  });
}

/** OMP wraps built-in, extension and MCP tools with this event. */
export default function credentialGuard(pi) {
  pi.on("tool_call", async (event, ctx) => {
    try {
      return await inspect(JSON.stringify({ tool_name: event.toolName, tool_input: event.input, cwd: ctx.cwd }));
    } catch {
      return failure;
    }
  });
}
