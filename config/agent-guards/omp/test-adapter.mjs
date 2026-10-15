import assert from "node:assert/strict";
import credentialGuard from "./credential-guard.mjs";

let handler;
credentialGuard({ on(event, callback) { assert.equal(event, "tool_call"); handler = callback; } });
const cases = [
  ["bash", { command: "env -i pass-cli --help" }, true],
  ["read", { path: "~/.gnupg/key" }, true],
  ["eval", { code: 'import subprocess; subprocess.run(["pass-cli"])' }, true],
  ["eval", { code: 'Bun.spawn(["pass-cli"])' }, true],
  ["eval", { code: 'process.env' }, true],
  ["mcp__exec", { command: "secret-tool lookup x y" }, true],
  ["edit", { path: "README.md", new_text: "pass-cli" }, false],
  ["bash", { command: 'git commit -m "mention pass-cli"' }, false],
  ["bash", { command: "echo $PATH" }, false],
  ["eval", { code: "1 + 1" }, false],
];
for (const [toolName, input, denied] of cases) {
  const result = await handler({ toolName, input }, { cwd: process.cwd() });
  assert.equal(result?.block === true, denied, toolName);
}
const oldPath = process.env.PATH;
try {
  process.env.PATH = "/nonexistent-credential-guard-test";
  assert.equal((await handler({ toolName: "bash", input: { command: "pwd" } }, { cwd: process.cwd() })).block, true);
} finally { process.env.PATH = oldPath; }
console.log(`${cases.length + 1} OMP adapter checks passed`);
