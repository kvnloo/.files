import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { homedir } from "node:os";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { realpathSync, statSync } from "node:fs";

const guardedTools: Record<string, true> = { read: true, grep: true, find: true, glob: true };
const reason = "SQLite lock safety: native file tools must not open the agent.db family or walk an ancestor directory. Narrow the path to a safe subtree (for example sessions/). For database facts use an external sqlite3 -readonly subprocess with mode=ro. See OMP #15586. This temporary guard does not replace the upstream native filesystem fix.";

function canonical(path: string): string {
	try { return realpathSync(path); } catch {
		const parent = dirname(path);
		return parent === path ? path : resolve(canonical(parent), relative(parent, path));
	}
}

function within(path: string, root: string): boolean {
	const rel = relative(root, path);
	return rel === "" || (!rel.startsWith(`..${sep}`) && rel !== ".." && !isAbsolute(rel));
}

/** No content reads: stat/realpath do not create a descriptor for a SQLite inode. */
export function sqliteToolDenial(tool: string, input: Record<string, unknown>, cwd: string,
	agentDir = process.env.PI_CODING_AGENT_DIR || resolve(homedir(), ".omp/agent")): string | undefined {
	if (!guardedTools[tool]) return;
	const root = canonical(resolve(agentDir));
	const protectedFiles = ["agent.db", "agent.db-wal", "agent.db-shm", "agent.db-journal"].map(name => resolve(root, name));
	const heldInodes = protectedFiles.flatMap(path => {
		try { const s = statSync(path); return [`${s.dev}:${s.ino}`]; } catch { return []; }
	});
	const paths = typeof input.path === "string" ? input.path.split(";") : [cwd];
	for (let path of paths) {
		path = path.trim() || cwd;
		// Internal resources do not use the host filesystem. file:// and local:// do.
		const scheme = /^([a-z][a-z0-9+.-]*):\/\//i.exec(path);
		if (scheme) {
			if (scheme[1] === "file") { try { path = decodeURIComponent(new URL(path).pathname); } catch { return reason; } }
			else if (scheme[1] === "local") path = path.slice(scheme[0].length);
			else continue;
		}
		if (path === "~" || path.startsWith("~/")) path = homedir() + path.slice(1);
		// Remove read selectors before interpreting a host path; a colon in a
		// filename is conservatively treated as a selector boundary.
		path = path.split(":", 1)[0];
		const wildcard = path.search(/[?*[{]/);
		if (wildcard >= 0) {
			// Walks can follow an arbitrary match below the literal prefix.
			const prefix = path.slice(0, wildcard);
			path = prefix.endsWith(sep) ? prefix : dirname(prefix || ".");
		}
		const target = canonical(resolve(cwd, path));
		if (within(root, target)) return reason;
		if (dirname(target) === root && target.slice(root.length + 1).startsWith("agent.db")) return reason;
		try { const s = statSync(target); if (heldInodes.includes(`${s.dev}:${s.ino}`)) return reason; } catch { /* Nonexistent safe paths remain tool errors. */ }
	}
}

export default function sqliteToolGuard(pi: ExtensionAPI): void {
	pi.on("tool_call", (event, ctx) => {
		const denial = sqliteToolDenial(event.toolName, event.input as Record<string, unknown>, ctx.cwd);
		if (denial) return { block: true, reason: denial };
	});
}
