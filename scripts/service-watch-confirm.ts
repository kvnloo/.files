#!/usr/bin/env bun
/** One tool-free Luna confirmation through the installed SDK; credentials stay in memory. */
import { Database } from 'bun:sqlite';
import { completeSimple } from '/home/kvn/.bun/install/global/node_modules/@oh-my-pi/pi-ai/src/index.ts';
import { buildModel } from '/home/kvn/.bun/install/global/node_modules/@oh-my-pi/pi-catalog/src/build.ts';

const strings: Record<string, true> = {
  failed: true, restart_loop: true, journal_error_rate: true, journal_gap: true, stale_file: true,
  receipt_error_share: true, error_file_growth: true, timer_stale: true, timer_failed: true,
  silent_noop: true, invariant_unavailable: true, unexpected_state: true, heartbeat_stale: true,
  phone_resource_caps: true,
  js_type_error: true, js_reference_error: true, js_syntax_error: true, module_resolution: true,
  connection_refused: true, connection_reset: true, timeout: true, out_of_memory: true,
  uncaught_exception: true, native_fatal: true, bridge_failure: true,
};
const keys: Record<string, true> = {
  ...strings, evidence: true, signatures: true, lines: true, redaction_counts: true,
  raw_text_transmitted: true, index: true, code: true, metrics: true, count: true,
  total: true, share: true, bytes: true, growth: true, age: true, threshold: true,
  ticks: true, restarts: true, sha256: true, withheld_lines: true, withheld_characters: true,
};
function finite(value: unknown): boolean {
  if (typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'string') return Object.hasOwn(strings, value) || /^[a-f0-9]{64}$/.test(value);
  if (Array.isArray(value)) return value.length <= 64 && value.every(finite);
  if (value && typeof value === 'object') {
    return Object.entries(value).every(([key, child]) => Object.hasOwn(keys, key) && finite(child));
  }
  return false;
}
process.umask(0o077);
const capture = process.argv.find(arg => arg.startsWith('--capture-request='))?.split('=').slice(1).join('=');

let output: Record<string, unknown>;
try {
  const input = await Bun.stdin.text();
  if (input.length > 16000) throw new Error('request_size');
  const request = JSON.parse(input);
  if (!request.facts || !finite(request.facts) || request.facts.raw_text_transmitted !== false) {
    throw new Error('finite_projection_required');
  }
  // Read the existing store, never instantiate AuthStorage (which migrates/refreshes/writes).
  const db = new Database('/home/kvn/.omp/agent/agent.db', { readonly: true, create: false });
  const rows = db.query("SELECT data FROM auth_credentials WHERE provider='openai-codex' AND credential_type='oauth' AND disabled_cause IS NULL ORDER BY updated_at DESC").all() as { data: string }[];
  db.close();
  const credential = rows.map(row => JSON.parse(row.data)).find(value =>
    typeof value.access === 'string' && typeof value.expires === 'number' && value.expires > Date.now() + 30000);
  if (!credential) throw new Error('subscription_credential_unavailable');
  const model = buildModel({
    id: 'gpt-6-luna', name: 'gpt-6-luna', provider: 'openai-codex',
    api: 'openai-codex-responses', baseUrl: 'https://chatgpt.com/backend-api/codex',
    reasoning: true, input: ['text'], contextWindow: 16384, maxTokens: 1000,
    // Subscription transport: not a claim about API-equivalent list pricing.
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  });
  const prompt = 'Confirm service anomaly severity from finite facts only. No tools or actions. ' +
    'Return JSON only: severity (info,warn,severe), cause, fix, evidence (nonempty array of integer evidence indices), confidence (number 0..1). ' +
    'A failed service, restart loop, repeated silent no-op or growing error flood is severe. ' +
    'Do not invent a detailed cause not supported by these facts. Facts: ' + JSON.stringify(request.facts);
  const response = await completeSimple(model, {
    systemPrompt: 'Report-only service incident reviewer. Return only the requested short JSON.',
    messages: [{ role: 'user', content: prompt, timestamp: Date.now() }], tools: [],
  }, {
    apiKey: credential.access,
    ...(credential.accountId ? { headers: { 'ChatGPT-Account-Id': credential.accountId } } : {}),
    maxTokens: 1000, reasoning: 'low', hideThinkingSummary: true,
    signal: AbortSignal.timeout(45000),
    // Explicit privacy-audit capture contains the actual SDK payload, never headers.
    ...(capture ? { onPayload: async (payload: unknown) => { await Bun.write(capture, JSON.stringify(payload, null, 2)); } } : {}),
  });
  if (response.stopReason === 'error' || response.stopReason === 'aborted' || response.model !== 'gpt-6-luna') {
    throw new Error('subscription_request_failed');
  }
  const text = response.content.filter(part => part.type === 'text').map(part => part.text).join('\n');
  if (!text || text.length > 6000) throw new Error('invalid_response');
  output = { ok: true, returned_model: response.model, text };
} catch {
  // Never echo provider exceptions, credential rows, request text or SDK diagnostic stderr.
  output = { ok: false, code: 'subscription_unavailable_or_invalid_response' };
}
console.log(JSON.stringify(output));
