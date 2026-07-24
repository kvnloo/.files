import type {
	ExtensionAPI,
	ExtensionCommandContext,
	ExtensionContext,
	SessionEntry,
	SessionHeader,
	UsageStatistics,
} from "@oh-my-pi/pi-coding-agent";
import { matchesKey, ScrollView, Text, truncateToWidth, wrapTextWithAnsi } from "@oh-my-pi/pi-tui";

const STATE_TYPE = "session-recap-state";
const STATE_VERSION = 1;
const WIDGET_KEY = "session-recap";
const MAX_TIMELINE_ITEMS = 48;
const MAX_FILES = 16;
const MAX_ARTIFACTS = 12;

interface PersistedState {
	version: 1;
	visible: boolean;
	scrollOffset: number;
}

export interface RecapSnapshot {
	title: string;
	cwd: string;
	startedAt: string;
	updatedAt: string;
	entryCount: number;
	userPrompts: number;
	assistantMessages: number;
	toolCalls: number;
	toolErrors: number;
	compactions: number;
	model?: string;
	toolCounts: Array<{ name: string; count: number }>;
	files: Array<{ path: string; actions: string[] }>;
	artifacts: string[];
	timeline: Array<{ kind: "user" | "assistant" | "tool" | "error" | "compact"; text: string }>;
	usage?: Pick<UsageStatistics, "input" | "output" | "cacheRead" | "totalTokens" | "cost">;
}

type SessionSource = {
	getHeader(): SessionHeader;
	getBranch(): SessionEntry[];
	getUsageStatistics(): UsageStatistics;
};
type TodoSnapshot = {
	phases: Array<{
		name: string;
		tasks: Array<{ content: string; status: "pending" | "in_progress" | "completed" | "abandoned" }>;
	}>;
};
type TaskNarrative = {
	objective: string;
	decisions: string[];
};

function projectName(cwd: string): string {
	const segments = cwd.split("/").filter(Boolean);
	return segments.at(-1) ?? cwd;
}

function activeTask(phases: TodoSnapshot["phases"]): string {
	for (const phase of phases) {
		const active = phase.tasks.find(task => task.status === "in_progress");
		if (active) return active.content;
	}
	for (const phase of phases) {
		const pending = phase.tasks.find(task => task.status === "pending");
		if (pending) return pending.content;
	}
	return "All tracked tasks complete";
}

function taskNarrative(source: SessionSource): TaskNarrative {
	const prompts: string[] = [];
	const decisions: string[] = [];
	for (const entry of source.getBranch()) {
		if (entry.type !== "message") continue;
		const message = record(entry.message);
		if (!message || typeof message.role !== "string") continue;
		const text = contentText(message.content);
		if (!text) continue;
		if (message.role === "user") {
			const clean = text
				.replace(/<\/?user_interjection>/g, "")
				.replace(/^The user sent this message as an interjection.*?<message>/, "")
				.replace(/<\/message>$/, "")
				.trim();
			if (
				clean.length >= 24 &&
				!clean.startsWith("You are resuming a prior conversation") &&
				!clean.startsWith("<system-")
			) {
				prompts.push(inlineText(clean, 320));
			}
			continue;
		}
		if (
			message.role === "assistant" &&
			text.length >= 24 &&
			/\b(?:chose|configured|decided|disabled|enabled|fixed|implemented|kept|moved|replaced|selected|using|will use)\b/i.test(
				text,
			)
		) {
			decisions.push(inlineText(text, 240));
		}
	}
	const header = source.getHeader();
	return {
		objective: prompts[0] || inlineText(header.title, 320) || "Complete the tracked session work.",
		decisions: decisions.slice(-4),
	};
}

async function runWorkspaceCopilot(args: string[], payload?: string): Promise<void> {
	try {
		const process = Bun.spawn(["workspace-copilot", ...args], {
			stdin: payload === undefined ? "ignore" : new Blob([payload]),
			stdout: "ignore",
			stderr: "ignore",
		});
		await process.exited;
	} catch {
		// Workspace telemetry is optional and must never interrupt the agent.
	}
}


function record(value: unknown): Record<string, unknown> | undefined {
	return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : undefined;
}

function inlineText(value: unknown, max = 180): string {
	if (typeof value !== "string") return "";
	const text = value.replace(/\s+/g, " ").trim();
	return text.length <= max ? text : `${text.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
}

function contentText(content: unknown): string {
	if (typeof content === "string") return inlineText(content);
	if (!Array.isArray(content)) return "";
	return inlineText(
		content
			.map(item => {
				const part = record(item);
				return part?.type === "text" && typeof part.text === "string" ? part.text : "";
			})
			.filter(Boolean)
			.join(" "),
	);
}

function collectStrings(value: unknown, visit: (value: string, key: string) => void, key = "", depth = 0): void {
	if (depth > 5) return;
	if (typeof value === "string") {
		visit(value, key);
		return;
	}
	if (Array.isArray(value)) {
		for (const item of value) collectStrings(item, visit, key, depth + 1);
		return;
	}
	const object = record(value);
	if (!object) return;
	for (const [childKey, child] of Object.entries(object)) collectStrings(child, visit, childKey, depth + 1);
}

function targetFromArguments(args: unknown): string | undefined {
	let target: string | undefined;
	collectStrings(args, (value, key) => {
		if (target || !/(?:^|_)(?:paths?|files?|cwd|query)$/i.test(key)) return;
		const clean = inlineText(value, 100);
		if (clean) target = clean;
	});
	return target;
}

function artifactUris(value: unknown): string[] {
	const found = new Set<string>();
	collectStrings(value, text => {
		for (const match of text.matchAll(/\b(?:artifact|local|agent):\/\/[^\s`'"<>]+/g)) {
			found.add(match[0]!.replace(/[),.;:]+$/, ""));
		}
	});
	return [...found];
}

function fileTargets(toolName: string, args: unknown): Array<{ path: string; action: string }> {
	const action = toolName === "write" || toolName === "edit" || toolName === "ast_edit" ? "write" : "read";
	const files = new Set<string>();
	collectStrings(args, (value, key) => {
		if (!/(?:^|_)(?:paths?|files?)$/i.test(key)) return;
		const clean = inlineText(value, 200);
		if (clean && !clean.includes("://")) files.add(clean);
	});
	return [...files].map(path => ({ path, action }));
}

function toolCalls(message: Record<string, unknown>): Array<Record<string, unknown>> {
	if (!Array.isArray(message.content)) return [];
	return message.content
		.map(record)
		.filter((item): item is Record<string, unknown> => item?.type === "toolCall" && typeof item.name === "string");
}

function timestampMs(timestamp: string): number {
	const parsed = Date.parse(timestamp);
	return Number.isFinite(parsed) ? parsed : 0;
}

export function summarizeSession(source: SessionSource): RecapSnapshot {
	const header = source.getHeader();
	const entries = source.getBranch();
	const counts = new Map<string, number>();
	const files = new Map<string, Set<string>>();
	const artifacts = new Set<string>();
	const timeline: RecapSnapshot["timeline"] = [];
	let userPrompts = 0;
	let assistantMessages = 0;
	let toolCallsTotal = 0;
	let toolErrors = 0;
	let compactions = 0;
	let model: string | undefined;

	for (const entry of entries) {
		for (const uri of artifactUris(entry)) artifacts.add(uri);
		if (entry.type === "model_change") {
			model = entry.model;
			continue;
		}
		if (entry.type === "compaction") {
			compactions += 1;
			timeline.push({ kind: "compact", text: inlineText(entry.shortSummary ?? entry.summary, 160) || "Context compacted" });
			continue;
		}
		if (entry.type !== "message") continue;
		const message = record(entry.message);
		if (!message || typeof message.role !== "string") continue;

		if (message.role === "user") {
			userPrompts += 1;
			const text = contentText(message.content);
			if (text) timeline.push({ kind: "user", text });
			continue;
		}
		if (message.role === "assistant") {
			assistantMessages += 1;
			const text = contentText(message.content);
			if (text) timeline.push({ kind: "assistant", text });
			for (const call of toolCalls(message)) {
				const name = call.name as string;
				toolCallsTotal += 1;
				counts.set(name, (counts.get(name) ?? 0) + 1);
				for (const file of fileTargets(name, call.arguments)) {
					const actions = files.get(file.path) ?? new Set<string>();
					actions.add(file.action);
					files.set(file.path, actions);
				}
				const args = record(call.arguments);
				const intent = inlineText(args?.i, 120);
				const target = targetFromArguments(call.arguments);
				const detail = intent || target;
				timeline.push({ kind: "tool", text: detail ? `${name} — ${detail}` : name });
			}
			continue;
		}
		if (message.role === "toolResult" && message.isError === true) {
			toolErrors += 1;
			const name = typeof message.toolName === "string" ? message.toolName : "tool";
			const text = contentText(message.content);
			timeline.push({ kind: "error", text: `${name} — ${text || "failed"}` });
		}
	}

	const usage = source.getUsageStatistics();
	const updatedAt = entries.reduce(
		(latest, entry) => (timestampMs(entry.timestamp) > timestampMs(latest) ? entry.timestamp : latest),
		header.timestamp,
	);
	return {
		title: header.title?.trim() || "Untitled session",
		cwd: header.cwd,
		startedAt: header.timestamp,
		updatedAt,
		entryCount: entries.length,
		userPrompts,
		assistantMessages,
		toolCalls: toolCallsTotal,
		toolErrors,
		compactions,
		model,
		toolCounts: [...counts.entries()]
			.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
			.map(([name, count]) => ({ name, count })),
		files: [...files.entries()]
			.slice(-MAX_FILES)
			.map(([path, actions]) => ({ path, actions: [...actions].sort() })),
		artifacts: [...artifacts].slice(-MAX_ARTIFACTS),
		timeline: timeline.slice(-MAX_TIMELINE_ITEMS),
		usage: usage
			? {
					input: usage.input,
					output: usage.output,
					cacheRead: usage.cacheRead,
					totalTokens: usage.totalTokens,
					cost: usage.cost,
				}
			: undefined,
	};
}

export function reconstructState(entries: readonly SessionEntry[]): PersistedState {
	for (let index = entries.length - 1; index >= 0; index -= 1) {
		const entry = entries[index];
		if (entry?.type !== "custom" || entry.customType !== STATE_TYPE) continue;
		const data = record(entry.data);
		if (data?.version !== STATE_VERSION || typeof data.visible !== "boolean") continue;
		return {
			version: STATE_VERSION,
			visible: data.visible,
			scrollOffset:
				typeof data.scrollOffset === "number" && Number.isFinite(data.scrollOffset)
					? Math.max(0, Math.floor(data.scrollOffset))
					: 0,
		};
	}
	return { version: STATE_VERSION, visible: true, scrollOffset: 0 };
}

function number(value: number): string {
	return new Intl.NumberFormat("en-US").format(value);
}

function duration(start: string, end: string): string {
	const milliseconds = Math.max(0, timestampMs(end) - timestampMs(start));
	const minutes = Math.floor(milliseconds / 60_000);
	if (minutes < 1) return "<1m";
	if (minutes < 60) return `${minutes}m`;
	const hours = Math.floor(minutes / 60);
	const remainder = minutes % 60;
	return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function renderLines(snapshot: RecapSnapshot, width: number, theme: ExtensionContext["ui"]["theme"]): string[] {
	const contentWidth = Math.max(20, width - 2);
	const line = (text: string) => truncateToWidth(text, contentWidth);
	const section = (label: string) => theme.fg("accent", theme.bold(label));
	const dim = (text: string) => theme.fg("dim", text);
	const lines: string[] = [
		line(`${section("Session recap")}  ${theme.fg("text", snapshot.title)}`),
		line(dim(`${snapshot.cwd}  ·  ${duration(snapshot.startedAt, snapshot.updatedAt)}  ·  ${snapshot.entryCount} entries`)),
	];
	if (snapshot.model) lines.push(line(`${dim("Model")}  ${snapshot.model}`));
	lines.push(
		line(
			`${section("Activity")}  ${snapshot.userPrompts} prompts  ·  ${snapshot.assistantMessages} responses  ·  ${snapshot.toolCalls} tools${snapshot.toolErrors ? `  ·  ${theme.fg("error", `${snapshot.toolErrors} errors`)}` : ""}${snapshot.compactions ? `  ·  ${snapshot.compactions} compactions` : ""}`,
		),
	);
	if (snapshot.usage) {
		lines.push(
			line(
				`${dim("Tokens")}  ${number(snapshot.usage.totalTokens)} total  ·  ${number(snapshot.usage.input)} in  ·  ${number(snapshot.usage.output)} out  ·  ${number(snapshot.usage.cacheRead)} cached${snapshot.usage.cost ? `  ·  $${snapshot.usage.cost.toFixed(4)}` : ""}`,
			),
		);
	}
	if (snapshot.toolCounts.length > 0) {
		lines.push("", section("Tools"));
		lines.push(
			...wrapTextWithAnsi(
				snapshot.toolCounts.map(tool => `${tool.name} ${tool.count}`).join("  ·  "),
				contentWidth,
			),
		);
	}
	if (snapshot.files.length > 0) {
		lines.push("", section("Files surfaced"));
		for (const file of snapshot.files) {
			const badge = file.actions.includes("write") ? theme.fg("warning", "W") : theme.fg("success", "R");
			lines.push(line(`${badge}  ${file.path}`));
		}
	}
	if (snapshot.artifacts.length > 0) {
		lines.push("", section("Artifacts"));
		for (const artifact of snapshot.artifacts) lines.push(line(`• ${artifact}`));
	}
	lines.push("", section("Recent timeline"));
	if (snapshot.timeline.length === 0) {
		lines.push(dim("No conversational entries yet."));
	} else {
		for (const item of snapshot.timeline) {
			const [label, color] =
				item.kind === "user"
					? ["YOU", "accent"]
					: item.kind === "assistant"
						? ["OMP", "success"]
						: item.kind === "error"
							? ["ERR", "error"]
							: item.kind === "compact"
								? ["ZIP", "warning"]
								: ["TOOL", "muted"];
			const prefix = `${theme.fg(color as Parameters<typeof theme.fg>[0], label.padEnd(4))} `;
			const wrapped = wrapTextWithAnsi(item.text, Math.max(10, contentWidth - 5));
			for (let index = 0; index < wrapped.length; index += 1) {
				lines.push(line(`${index === 0 ? prefix : "     "}${wrapped[index]}`));
			}
		}
	}
	return lines;
}

export default function sessionRecap(api: ExtensionAPI): void {
	const states = new Map<string, PersistedState>();
	let cache: { key: string; snapshot: RecapSnapshot } | undefined;
	const taskLabels = new Map<string, string>();

	const sessionKey = (ctx: ExtensionContext) => ctx.sessionManager.getSessionId();
	const stateFor = (ctx: ExtensionContext): PersistedState => {
		const key = sessionKey(ctx);
		let state = states.get(key);
		if (!state) {
			state = reconstructState(ctx.sessionManager.getBranch());
			states.set(key, state);
		}
		return state;
	};
	const snapshotFor = (ctx: ExtensionContext): RecapSnapshot => {
		const branch = ctx.sessionManager.getBranch();
		const key = `${sessionKey(ctx)}:${ctx.sessionManager.getLeafId() ?? "empty"}:${branch.length}`;
		if (cache?.key === key) return cache.snapshot;
		const snapshot = summarizeSession(ctx.sessionManager);
		cache = { key, snapshot };
		return snapshot;
	};
	const persist = (state: PersistedState): void => {
		api.appendEntry(STATE_TYPE, state);
		cache = undefined;
	};
	const publishHarness = async (
		ctx: ExtensionContext,
		state: "started" | "working" | "waiting" | "completed" | "failed" | "stopped",
		label?: string,
	): Promise<void> => {
		const key = sessionKey(ctx);
		const header = ctx.sessionManager.getHeader();
		await runWorkspaceCopilot([
			"harness-event",
			state,
			"--harness",
			"omp",
			"--label",
			label ?? taskLabels.get(key) ?? header.title ?? "OMP session",
			"--project",
			projectName(header.cwd),
			"--pane",
			`external:omp:${key}`,
			"--session",
			process.env.TMUX_PANE ?? "",
		]);
	};
	const publishTasks = async (ctx: ExtensionContext, phases: TodoSnapshot["phases"]): Promise<void> => {
		const key = sessionKey(ctx);
		const header = ctx.sessionManager.getHeader();
		const narrative = taskNarrative(ctx.sessionManager);
		taskLabels.set(key, activeTask(phases));
		await runWorkspaceCopilot(
			["task-sync", "--session", key, "--project", projectName(header.cwd)],
			JSON.stringify({ phases, ...narrative }),
		);
	};
	const updateWidget = (ctx: ExtensionContext): void => {
		if (!ctx.hasUI || !stateFor(ctx).visible) {
			ctx.ui.setWidget(WIDGET_KEY, undefined);
			return;
		}
		const snapshot = snapshotFor(ctx);
		ctx.ui.setWidget(WIDGET_KEY, (_tui, theme) => {
			const error = snapshot.toolErrors ? theme.fg("error", ` · ${snapshot.toolErrors} errors`) : "";
			const text = `${theme.fg("accent", theme.bold("recap"))} ${theme.fg("muted", "·")} ${snapshot.userPrompts} prompts · ${snapshot.toolCalls} tools${error} ${theme.fg("dim", "· /recap")}`;
			return new Text(text, 0, 0);
		});
	};
	const rehydrate = (ctx: ExtensionContext): void => {
		cache = undefined;
		states.set(sessionKey(ctx), reconstructState(ctx.sessionManager.getBranch()));
		updateWidget(ctx);
	};
	const showOverlay = async (ctx: ExtensionCommandContext, reset = false): Promise<void> => {
		if (!ctx.hasUI) {
			ctx.ui.notify("Session recap requires interactive mode.", "warning");
			return;
		}
		const state = stateFor(ctx);
		const snapshot = snapshotFor(ctx);
		let scrollOffset = reset ? 0 : state.scrollOffset;
		const originalOffset = state.scrollOffset;
		await ctx.ui.custom<void>(
			(tui, theme, _keybindings, done) => ({
				render(width: number): readonly string[] {
					const body = renderLines(snapshot, width, theme);
					const viewportRows = Math.max(4, (process.stdout.rows ?? 40) - 3);
					const maxScroll = Math.max(0, body.length - viewportRows);
					scrollOffset = Math.min(scrollOffset, maxScroll);
					const view = new ScrollView(body.slice(scrollOffset, scrollOffset + viewportRows), {
						height: viewportRows,
						scrollbar: "auto",
						totalRows: body.length,
						theme: { track: text => theme.fg("dim", text), thumb: text => theme.fg("accent", text) },
					});
					view.setScrollOffset(scrollOffset);
					return [
						...view.render(width),
						truncateToWidth(theme.fg("dim", "↑/↓ or j/k scroll  ·  PgUp/PgDn page  ·  g/G ends  ·  Esc/q close"), width),
					];
				},
				handleInput(data: string): void {
					const bodyLength = renderLines(snapshot, process.stdout.columns ?? 120, theme).length;
					const viewportRows = Math.max(4, (process.stdout.rows ?? 40) - 3);
					const maxScroll = Math.max(0, bodyLength - viewportRows);
					if (matchesKey(data, "escape") || matchesKey(data, "esc") || data === "q") {
						done(undefined);
						return;
					}
					if (matchesKey(data, "up") || data === "k") scrollOffset = Math.max(0, scrollOffset - 1);
					else if (matchesKey(data, "down") || data === "j") scrollOffset = Math.min(maxScroll, scrollOffset + 1);
					else if (matchesKey(data, "pageUp")) scrollOffset = Math.max(0, scrollOffset - viewportRows);
					else if (matchesKey(data, "pageDown")) scrollOffset = Math.min(maxScroll, scrollOffset + viewportRows);
					else if (data === "g") scrollOffset = 0;
					else if (data === "G") scrollOffset = maxScroll;
					tui.requestRender();
				},
				invalidate(): void {},
			}),
			{ overlay: true },
		);
		if (scrollOffset !== originalOffset) {
			state.scrollOffset = scrollOffset;
			persist(state);
		}
	};

	api.registerCommand("recap", {
		description: "Open the scrollable current-session recap (show, hide, toggle, or top)",
		getArgumentCompletions: prefix =>
			["show", "hide", "toggle", "top"].filter(value => value.startsWith(prefix)).map(value => ({ value, label: value })),
		handler: async (args, ctx) => {
			const action = args.trim().toLowerCase();
			const state = stateFor(ctx);
			if (action === "show" || action === "hide" || action === "toggle") {
				state.visible = action === "show" ? true : action === "hide" ? false : !state.visible;
				persist(state);
				updateWidget(ctx);
				ctx.ui.notify(`Recap widget ${state.visible ? "shown" : "hidden"}.`, "info");
				return;
			}
			if (action && action !== "top") {
				ctx.ui.notify("Usage: /recap [show|hide|toggle|top]", "warning");
				return;
			}
			await showOverlay(ctx, action === "top");
		},
	});

	api.on("tool_result", async (event, ctx) => {
		if (event.toolName !== "todo" || event.isError) return;
		const details = record(event.details);
		if (!details || !Array.isArray(details.phases)) return;
		const phases = details.phases as TodoSnapshot["phases"];
		await publishTasks(ctx, phases);
		await publishHarness(ctx, "working", activeTask(phases));
	});
	api.on("agent_start", async (_event, ctx) => {
		await publishHarness(ctx, "working");
	});
	api.on("agent_end", async (event, ctx) => {
		if (event.willContinue) return;
		await publishHarness(ctx, "waiting");
	});
	api.on("session_start", (_event, ctx) => rehydrate(ctx));
	api.on("session_start", async (_event, ctx) => {
		await publishHarness(ctx, "started");
	});
	api.on("session_switch", (_event, ctx) => rehydrate(ctx));
	api.on("session_branch", (_event, ctx) => rehydrate(ctx));
	api.on("session_tree", (_event, ctx) => rehydrate(ctx));
	api.on("message_end", (_event, ctx) => {
		cache = undefined;
		updateWidget(ctx);
	});
	api.on("session_shutdown", (_event, ctx) => {
		void publishHarness(ctx, "stopped");
		if (ctx.hasUI) ctx.ui.setWidget(WIDGET_KEY, undefined);
		states.delete(sessionKey(ctx));
		cache = undefined;
	});
}
