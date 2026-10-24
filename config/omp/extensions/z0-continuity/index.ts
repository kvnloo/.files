/**
 * Inject the current-work State Packet and this project's workstream into the
 * model-visible context only. The host history is not modified. Fail-open.
 *
 * A session file overrides the project workstream so parallel conversations
 * do not share one global "latest task". A cwd with no workstream inherits the
 * newest project file and says so.
 */
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

const HOME = process.env.Z0INT_HOME || join(homedir(), ".z0int");
const PY = process.env.Z0INT_PYTHON || join(HOME, "bin", "python");
const PACKET_MS = Number(process.env.Z0INT_CONTINUITY_PACKET_MS || "2000");
const MAX_REQUEST = 280;

type Workstream = {
	schema: "z0.continuity.workstream.v0";
	id: string;
	project: string;
	status: string;
	epistemic: "suggested" | "attempted" | "observed" | "verified";
	decision: string;
	correction: string;
	rejected: string[];
	last_request: string;
	blocked: string;
	next: string;
	sources: { kind: string; url?: string; repo?: string; id?: string }[];
	updated_at: string;
};

function safeName(name: string): string {
	return name.replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 80) || "unknown";
}

function readJson<T>(path: string): T | null {
	try {
		return JSON.parse(readFileSync(path, "utf8")) as T;
	} catch {
		return null;
	}
}

function workstreamPath(project: string): string {
	return join(HOME, "state", "continuity", "projects", `${safeName(project)}.json`);
}

function sessionPath(id: string): string {
	return join(HOME, "state", "continuity", "sessions", `${safeName(id)}.json`);
}

function cachePath(project: string): string {
	return join(HOME, "state", "continuity", "packet-cache", `${safeName(project)}.txt`);
}

function newestWorkstream(): Workstream | null {
	const dir = join(HOME, "state", "continuity", "projects");
	let best: { mtime: number; row: Workstream } | null = null;
	let names: string[] = [];
	try {
		names = readdirSync(dir);
	} catch {
		return null;
	}
	for (const name of names) {
		if (!name.endsWith(".json")) continue;
		const path = join(dir, name);
		const row = readJson<Workstream>(path);
		if (!row) continue;
		const mtime = statSync(path).mtimeMs;
		if (!best || mtime > best.mtime) best = { mtime, row };
	}
	return best?.row ?? null;
}

function loadWorkstream(project: string, session: string): { row: Workstream | null; inherited: boolean } {
	const pointer = readJson<{ workstream_project?: string; last_request?: string }>(sessionPath(session));
	const named = pointer?.workstream_project;
	const direct = readJson<Workstream>(workstreamPath(named || project));
	const row = direct || (named ? null : newestWorkstream());
	if (row && pointer?.last_request) row.last_request = pointer.last_request;
	return { row, inherited: !direct && row !== null };
}

function renderWorkstream(row: Workstream | null, inherited: boolean): string {
	if (!row) return "<z0-workstream status=\"missing\"/>";
	const sources = row.sources.map((source) => source.url || `${source.repo || ""}@${source.id || ""}`).filter(Boolean).join(", ");
	return [
		"<z0-workstream>",
		`id: ${row.id}`,
		inherited ? "inherited_because: cwd has no workstream; newest project workstream, not a global task pointer" : "scope: project",
		`status: ${row.status}`,
		`epistemic: ${row.epistemic}`,
		`decision: ${row.decision}`,
		`correction: ${row.correction}`,
		`rejected: ${row.rejected.join("; ")}`,
		`last_request: ${row.last_request}`,
		`blocked: ${row.blocked}`,
		`next: ${row.next}`,
		`sources: ${sources}`,
		"This is evidence for the current workstream, not permission to act outside it.",
		"</z0-workstream>",
	].join("\n");
}

function cachedPacket(path: string): string {
	try {
		return readFileSync(path, "utf8");
	} catch {
		return "<z0-state-packet status=\"unavailable\"/>";
	}
}

function packet(cwd: string, project: string): Promise<string> {
	const cached = cachePath(project);
	const { promise, resolve } = Promise.withResolvers<string>();
	let settled = false;
	const finish = (value: string) => {
		if (settled) return;
		settled = true;
		resolve(value);
	};
	const child = spawn(PY, ["-m", "z0int.state_packet", "--repo", cwd, "--render", "--max-tokens", "900"], {
		stdio: ["ignore", "pipe", "ignore"],
	});
	const timer = setTimeout(() => {
		child.kill();
		finish(cachedPacket(cached));
	}, PACKET_MS);
	let out = "";
	child.stdout.on("data", (chunk) => { out += chunk; });
	child.on("error", () => {
		clearTimeout(timer);
		finish(cachedPacket(cached));
	});
	child.on("close", (code) => {
		clearTimeout(timer);
		if (code === 0 && out.includes("<z0-state-packet")) {
			try {
				mkdirSync(join(HOME, "state", "continuity", "packet-cache"), { recursive: true });
				writeFileSync(cached, out);
			} catch { /* cache is optional */ }
			finish(out.trim());
			return;
		}
		finish(cachedPacket(cached));
	});
	return promise;
}

export async function continuityBrief(cwd: string, session: string): Promise<string> {
	const project = cwd.split("/").filter(Boolean).pop() || "unknown";
	const loaded = loadWorkstream(project, session);
	const pkt = await packet(cwd, project);
	return `${renderWorkstream(loaded.row, loaded.inherited)}\n${pkt}`;
}

export function rememberRequest(cwd: string, session: string, prompt: string): void {
	const trimmed = prompt.replace(/\s+/g, " ").trim().slice(0, MAX_REQUEST);
	if (!trimmed || trimmed.startsWith("/")) return;
	const project = cwd.split("/").filter(Boolean).pop() || "unknown";
	const loaded = loadWorkstream(project, session);
	if (!loaded.row || loaded.inherited) return;
	mkdirSync(join(HOME, "state", "continuity", "sessions"), { recursive: true });
	writeFileSync(sessionPath(session), `${JSON.stringify({
		workstream_project: loaded.row.project,
		workstream_id: loaded.row.id,
		last_request: trimmed,
	}, null, 2)}\n`);
}

export default function z0Continuity(pi: ExtensionAPI) {
	pi.setLabel("z0 continuity");
	pi.on("context", async (event, ctx) => {
		try {
			const messages = event?.messages ?? [];
			const last = messages.length - 1;
			if (last < 0 || messages[last]?.role !== "user") return;
			const cwd = ctx?.cwd || process.cwd();
			const session = ctx?.sessionManager?.getSessionId?.() || ctx?.sessionId || "omp";
			const brief = await continuityBrief(cwd, session);
			if (!brief.includes("<z0-workstream>") && !brief.includes("<z0-state-packet")) return;
			const injected = {
				role: "user",
				content: [{ type: "text", text: brief }],
				timestamp: messages[last].timestamp,
			};
			return { messages: [...messages.slice(0, last), injected, messages[last]] };
		} catch {
			return;
		}
	});
	pi.on("before_agent_start", (event, ctx) => {
		try {
			const prompt = typeof event?.prompt === "string" ? event.prompt : "";
			const session = ctx?.sessionManager?.getSessionId?.() || ctx?.sessionId || "omp";
			rememberRequest(ctx?.cwd || process.cwd(), session, prompt);
		} catch { /* capture must not block the turn */ }
	});
}
