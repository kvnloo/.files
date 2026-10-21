#!/usr/bin/env node
// Producer for the Bend FSM layers. Compiles the unchanged z0intelligence
// fsm.bend files with the pinned Bend, binds the emitted ES module, replays
// every tape through it, enumerates display edges by executing it, and binds
// all artifacts to their bytes in receipt.json. `--check` recompiles nothing:
// it re-hashes everything, re-verifies the copied sources against their
// upstream git blobs, and re-runs every tape and edge through the committed
// compiled module. Any mismatch fails closed.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdtempSync, rmSync, renameSync, existsSync, accessSync, constants } from 'node:fs';
import { dirname, join, resolve, isAbsolute, delimiter } from 'node:path';
import { tmpdir, homedir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const compilerPin = 'bend 2.0.34';
const compilerIdentity = '66e5faf92d75d6e10a11427c8e4f3df72a4c14b1263a04431fdc015a5aa21317';
const bendInputs = ['Runtime.bend', 'WorkItem.bend', 'WorkerSupervision.bend', 'IntegrationOwner.bend', 'Ops.bend', 'OpsLayer.bend'];
const artifactNames = [...bendInputs, 'model.json', 'scenarios.json', 'adapter.mjs', 'build.mjs', 'extract-tapes.py', 'extract-integration-tapes.py',
  'work-item.mmd', 'worker-supervision.mmd', 'integration-owner.mmd', 'integration-tapes.json', 'ops-tapes.json', 'Runtime.generated.mjs', 'projection.json', 'replay.json'];
const sha256 = (b) => createHash('sha256').update(b).digest('hex');
const gitBlob = (b) => createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${b.length}\0`), b])).digest('hex');
const bytes = (name) => readFileSync(join(directory, name));
const json = (name) => JSON.parse(bytes(name).toString('utf8'));
const loadScenarios = () => {
  const base = json('scenarios.json'), integration = json('integration-tapes.json'), ops = json('ops-tapes.json');
  return { ...base, provenance: { ...base.provenance, integration: integration.provenance, ops: ops.provenance },
    scenarios: [...base.scenarios, ...integration.scenarios, ...ops.scenarios] };
};
const hash = (name) => sha256(bytes(name));
const stable = (v) => JSON.stringify(v, null, 1) + '\n';

function checkSources(model) {
  for (const s of model.sources) {
    const blob = gitBlob(bytes(s.path));
    if (blob !== s.gitBlob) throw new Error(`${s.path} is not byte-identical to ${s.upstream} (blob ${blob} != ${s.gitBlob})`);
  }
}

async function loadAdapter() {
  return import(`${pathToFileURL(join(directory, 'adapter.mjs')).href}?t=${Date.now()}`);
}

/** Run every tape through the compiled Bend; return outcome rows. */
function replayAll(adapter, scenarios) {
  return scenarios.scenarios.map((sc) => {
    let state = adapter.validateState(sc.machine, sc.initial);
    const steps = sc.steps.map((step) => {
      const out = adapter.transition(sc.machine, state, step.event, step.facts);
      state = out.value;
      return { before: out.before, state: out.state, verdict: out.verdict, laws: out.laws, value: out.value };
    });
    return { id: sc.id, machine: sc.machine, steps };
  });
}

// Representative values for edge enumeration (design-level, not exhaustive).
const ROLES = ['Owner', 'Opus', 'Sol', 'Chat', 'Free', 'Jev', 'Slm', 'Ci'];
function samples() {
  const author = [{ id: 1, role: 'Opus' }, { id: 1, role: 'Sol' }];
  const actors = [1, 2].flatMap((id) => ROLES.map((role) => ({ id, role })));
  const owner = { id: 3, role: 'Owner' };
  const wiStates = [{ tag: 'Proposed' }, { tag: 'Abandoned' }];
  for (const au of author) {
    wiStates.push({ tag: 'Claimed', au });
    for (const tag of ['Implementing', 'Verifying', 'DraftPR', 'Blocked', 'Interrupted']) wiStates.push({ tag, au, hd: 1 });
    for (const ig of [1, 2]) {
      wiStates.push({ tag: 'Integrated', au, hd: 1, ig });
      for (const dp of [1, 2]) wiStates.push({ tag: 'Deployed', au, hd: 1, ig, dp });
      wiStates.push({ tag: 'Accepted', au, hd: 1, ig, ap: owner }, { tag: 'Merged', au, hd: 1, ig, ap: owner });
    }
  }
  const receipts = [{ sha: 1, pass: true }, { sha: 2, pass: true }, { sha: 1, pass: false }];
  const wiEvents = [{ tag: 'Interrupt' }, ...[1, 2].map((served) => ({ tag: 'Observe', served }))];
  for (const a of [...actors, owner]) {
    for (const tag of ['Claim', 'Start', 'Submit', 'Accept', 'Merge', 'Block', 'Unblock', 'Resume', 'Abandon']) wiEvents.push({ tag, a });
    for (const sha of [1, 2]) wiEvents.push({ tag: 'Push', a, sha }, { tag: 'Deploy', a, served: sha });
    for (const r of receipts) {
      wiEvents.push({ tag: 'Verify', a, r });
      for (const ish of [1, 2]) wiEvents.push({ tag: 'Integrate', a, ish, r });
    }
  }
  const ws = [];
  const workers = [{ id: 1, wt: 0, load: 'Light', exc: 'NoExc' }, { id: 1, wt: 0, load: 'Heavy', exc: 'NoExc' }, { id: 1, wt: 0, load: 'Heavy', exc: 'Gpu' }];
  for (const w of workers) {
    ws.push({ tag: 'Dispatched', w }, { tag: 'Abandoned', w }, { tag: 'Integrated', w });
    for (const bg of [0, 1]) {
      for (const h of ['Groot', 'Mbp']) ws.push({ tag: 'Running', w, h, hb: 0, bg }, { tag: 'Stalled', w, h, hb: 0, bg });
      ws.push({ tag: 'Interrupted', w, at: 0, bg }, { tag: 'Overdue', w, at: 0, bg }, { tag: 'Completed', w, bg }, { tag: 'Resumed', w, by: 2, bg });
    }
  }
  const wsEvents = [{ tag: 'Spawn' }, { tag: 'Reap' }, { tag: 'Finish' }, { tag: 'Abandon' }, { tag: 'Integrate' },
    { tag: 'Beat', t: 5 }, { tag: 'Interrupt', t: 5 }, ...[10, 200, 300].map((now) => ({ tag: 'Tick', now })),
    ...['Groot', 'Mbp', 'Phone'].map((h) => ({ tag: 'Start', h, t: 0 })), ...[true, false].map((log) => ({ tag: 'Resume', by: 2, log }))];
  const leases = [{ tag: 'Free' }, { tag: 'Held', o: 1 }];
  const leaseEvents = [1, 2].flatMap((a) => [{ tag: 'Acquire', a }, { tag: 'Release', a }, { tag: 'Reclaim', a, dead: true }, { tag: 'Reclaim', a, dead: false }]);
  const devices = leases.flatMap((lk) => [{ tag: 'Unknown' }, { tag: 'Seen', app: 1 }].map((fg) => ({ lk, fg })));
  const deviceEvents = [1, 2].flatMap((a) => [{ tag: 'Lock', a }, { tag: 'Unlock', a }, { tag: 'Install', a }, { tag: 'Peek', app: a }, { tag: 'Input', a: 1, app: a }]);
  return [
    { machine: 'work-item', states: wiStates, events: wiEvents, facts: [{ availability: 'DeepWork' }, { availability: 'Off' }] },
    { machine: 'worker', states: ws, events: wsEvents, facts: [{ limit: 120 }] },
    { machine: 'lease', states: leases, events: leaseEvents, facts: [{}] },
    { machine: 'device', states: devices, events: deviceEvents, facts: [{}] },
    { machine: 'integration', states: ['Branch','DraftPR','Queued','OnIntegrationBranch','Deployed','OwnerAccepted','Merged','Parked','Conflicted'].map(tag => ({tag})),
      events: [ {tag:'Draft'}, {tag:'Queue'}, {tag:'Merge'}, {tag:'Conflict'}, {tag:'Resume'},
        ...[true,false].flatMap(ok => [{tag:'Integrate',lease:ok,stack:ok,independent:ok},{tag:'Deploy',equal:ok},{tag:'Accept',owner:ok},
          {tag:'Park',reason:ok,future:ok},{tag:'Observe',equal:ok},{tag:'Expire',expired:ok}])], facts:[{}] },
    // Ops plane: the gate machine is drawn from its idle state (its verdict ignores the previous one)
    { machine: 'ops-gates', states: [{ tag: 'GIdle' }], events: opsGateEvents(), facts: [{}] },
    { machine: 'node-health', states: [{ tag: 'NHealthy' }, { tag: 'NBad', since: 0 }, { tag: 'NNotified', since: 0 }],
      events: [true, false].flatMap((ok) => [10, 4000].map((now) => ({ ok, now }))), facts: [{ limit: 1800 }] },
    { machine: 'gateway-run', states: [{ tag: 'RActive', gw: 1 }, { tag: 'RInterrupted', gw: 1 }, { tag: 'RFailed' }, { tag: 'RDone' }, { tag: 'RResumed' }, { tag: 'RReported' }],
      events: [{ tag: 'GwRestart', gw: 1 }, { tag: 'GwRestart', gw: 2 }, { tag: 'RunError' }, { tag: 'RunDone' }, { tag: 'ReportRun' },
        { tag: 'ResumeRun', session: true }, { tag: 'ResumeRun', session: false }], facts: [{}] }
  ];
}

function opsGateEvents() {
  const B = [true, false];
  const ev = [];
  for (const c of ['CTest', 'CBundle', 'CGpu', 'CTiny']) for (const mbp of B) for (const phone of B) ev.push({ tag: 'GPlace', c, mbp, phone });
  for (const served of B) for (const op of ['GCommit', 'GMergeFF', 'GRollback']) for (const txn of B) ev.push({ tag: 'GGit', served, op, txn });
  for (const clean of B) for (const call of B) for (const check of B) ev.push({ tag: 'GRoll', q: { clean, ff: true, gated: false, receipt: false, call, idle: true }, check });
  for (const priv of B) for (const vis of ['VPublic', 'VPrivate', 'VUnknown']) ev.push({ tag: 'GPush', private: priv, vis });
  for (const intent of B) for (const fg of B) ev.push({ tag: 'GPhone', a: { tag: 'PTap', intent, fg }, call: true });
  for (const chain of B) for (const call of B) ev.push({ tag: 'GPhone', a: { tag: 'PInstall', chain }, call });
  for (const cancelled of B) for (const sol of B) for (const design of B) ev.push({ tag: 'GRoute', cancelled, sol, design });
  return ev;
}

function enumerate(adapter, model) {
  const edges = new Map();
  const selfLoops = new Map();
  let calls = 0;
  for (const { machine, states, events, facts } of samples()) {
    for (const state of states) for (const event of events) for (const f of facts) {
      calls++;
      const out = adapter.transition(machine, state, event, f);
      if (!out.accepted) continue;
      const key = `${machine}:${out.before}>${out.state}:${out.eventTag}`;
      const target = out.before === out.state ? selfLoops : edges;
      if (!target.has(key)) target.set(key, { machine, from: out.before, to: out.state, event: out.eventTag, laws: out.laws });
    }
  }
  const order = Object.keys(model.machines);
  const sort = (list) => [...list].sort((a, b) => order.indexOf(a.machine) - order.indexOf(b.machine) || a.from - b.from || a.to - b.to || a.event.localeCompare(b.event));
  // Compare with the documented Mermaid statecharts (drawing vs compiled code).
  const documented = [];
  for (const [machine, file] of [['work-item', 'work-item.mmd'], ['worker', 'worker-supervision.mmd'], ['integration', 'integration-owner.mmd']]) {
    const ids = new Map(model.states[machine].map((s) => [s.title, s.id]).concat(model.states[machine].map((s) => [s.tag, s.id])));
    for (const line of bytes(file).toString('utf8').split('\n')) {
      const m = line.match(/^\s*(\w+)\s*-->\s*(\w+)\s*:\s*(.*)$/);
      if (!m || !ids.has(m[1]) || !ids.has(m[2])) continue;
      for (const ev of m[3].split('/').map((x) => x.trim().match(/^(\w+)/)?.[1]).filter(Boolean)) {
        documented.push({ machine, from: ids.get(m[1]), to: ids.get(m[2]), event: ev });
      }
    }
  }
  const has = (list, e) => list.some((x) => x.machine === e.machine && x.from === e.from && x.to === e.to && x.event === e.event);
  const all = [...edges.values()];
  return {
    edges: sort(all), selfLoops: sort([...selfLoops.values()]),
    documentedComparison: {
      documentedEdges: documented.length,
      documentedNotProducedByBend: documented.filter((e) => e.from !== e.to && !has(all, e)),
      producedByBendNotDocumented: sort(all.filter((e) => (e.machine === 'work-item' || e.machine === 'worker' || e.machine === 'integration') && !has(documented, e)))
    },
    provenance: { producer: 'Executing Runtime.generated.mjs through adapter.mjs over representative states, events and facts', calls,
      scope: 'Design-level checked possibilities, not an exhaustive proof. The proofs live in LAWS.bend/PROOF.bend upstream.' }
  };
}

function compilerPath() {
  const command = process.env.BEND || join(homedir(), '.bend/bin/bend');
  const candidates = isAbsolute(command) || command.includes('/') ? [resolve(command)] : (process.env.PATH ?? '').split(delimiter).map((p) => join(p, command));
  for (const c of candidates) { try { accessSync(c, constants.X_OK); return c; } catch { /* next */ } }
  throw new Error(`Bend executable not found: ${command}; set BEND`);
}

function publish(name, content) {
  const tmp = join(directory, `.${name}.${process.pid}.tmp`);
  try { writeFileSync(tmp, content); renameSync(tmp, join(directory, name)); } finally { if (existsSync(tmp)) rmSync(tmp); }
}

async function check() {
  const receipt = json('receipt.json');
  const model = json('model.json');
  if (receipt.schema !== 1 || receipt.compiler.version !== compilerPin || receipt.compiler.executableSha256 !== compilerIdentity) {
    throw new Error('Receipt compiler identity mismatch; rebuild with the pinned compiler');
  }
  for (const name of artifactNames) if (receipt.artifacts[name] !== hash(name)) throw new Error(`Stale artifact: ${name}; rebuild`);
  checkSources(model);
  const adapter = await loadAdapter();
  const replay = replayAll(adapter, loadScenarios());
  if (stable(replay) !== bytes('replay.json').toString('utf8')) throw new Error('Compiled Bend no longer reproduces replay.json');
  const projection = enumerate(adapter, model);
  const committed = json('projection.json');
  if (JSON.stringify(projection.edges) !== JSON.stringify(committed.edges)) throw new Error('Compiled Bend no longer reproduces projection edges');
  return { receipt, replay, projection };
}

if (process.argv.slice(2).some((a) => a !== '--check')) throw new Error('Usage: node build.mjs [--check]');
if (process.argv.includes('--check')) {
  const { replay, projection } = await check();
  const steps = replay.reduce((n, s) => n + s.steps.length, 0);
  console.log(`FSM layer receipt matches: sources == upstream blobs, ${replay.length} tapes / ${steps} steps and ${projection.edges.length} edges re-derived from the committed compiled Bend. No compiler run.`);
} else {
  const model = json('model.json');
  checkSources(model);
  const compiler = compilerPath();
  const version = execFileSync(compiler, ['version'], { encoding: 'utf8', timeout: 10000 }).trim().split('\n')[0];
  const identity = sha256(readFileSync(compiler));
  if (version !== compilerPin || identity !== compilerIdentity) {
    throw new Error(`Expected ${compilerPin} (${compilerIdentity}); got ${version} (${identity}). The proofs were checked with that identity.`);
  }
  const temporary = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'fsm-layers-bend-'));
  let rawHash;
  try {
    for (const name of bendInputs) writeFileSync(join(temporary, name), bytes(name));
    const output = join(temporary, 'Runtime.mjs');
    execFileSync(compiler, [join(temporary, 'Runtime.bend'), '-o', output], { encoding: 'utf8', timeout: 300000, stdio: 'pipe' });
    const compiled = readFileSync(output, 'utf8');
    rawHash = sha256(compiled);
    if (!compiled.includes('export default {') || !compiled.includes('"WorkItem.astep"') || !compiled.includes('"WorkerSupervision.step"') || !compiled.includes('"OpsLayer.gate_step"')) {
      throw new Error('Pinned compiler ES-module layout not recognized; inspect the emitted output before changing the binding');
    }
    const binding = `\nexport const bendMetadata = ${JSON.stringify(model)};\nexport const bendSourceSha256 = ${JSON.stringify(Object.fromEntries(bendInputs.map((n) => [n, hash(n)])))};\n`;
    publish('Runtime.generated.mjs', `// Generated from Runtime.bend (+ WorkItem.bend, WorkerSupervision.bend) by ${version}; do not hand-edit.\n${compiled}${binding}`);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
  const adapter = await loadAdapter();
  const replay = replayAll(adapter, loadScenarios());
  publish('replay.json', stable(replay));
  const projection = enumerate(adapter, model);
  publish('projection.json', `${JSON.stringify(projection, null, 1)}\n`);
  const scenarios = loadScenarios();
  const receipt = {
    schema: 1,
    generatedAt: new Date().toISOString(),
    compiler: { version, executableSha256: identity, target: 'ES module (-o Runtime.mjs)', producerPlatform: process.platform, producerArchitecture: process.arch },
    rawCompilerOutputSha256: rawHash,
    artifacts: Object.fromEntries(artifactNames.map((n) => [n, hash(n)])),
    sources: model.sources.map((s) => ({ ...s, sha256: hash(s.path) })),
    proofs: model.proofs,
    tapes: scenarios.provenance,
    checks: {
      compilation: 'The pinned Bend compiler emitted Runtime.generated.mjs from the unchanged fsm.bend files; no handwritten transition table',
      sources: 'WorkItem.bend, WorkerSupervision.bend and the .mmd drawings are byte-identical to their upstream git blobs',
      replay: `${replay.length} tapes replayed through the compiled module; outcomes in replay.json`,
      projection: `${projection.edges.length} display edges enumerated by executing the compiled module (${projection.provenance.calls} calls)`,
      theoremProofs: 'Upstream PROOF.bend pass receipts (bend-emitted-book scope); not re-run here',
      nativeRuntime: 'None. No host, service, adb or GitHub is contacted'
    }
  };
  publish('receipt.json', `${JSON.stringify(receipt, null, 2)}\n`);
  await check();
  const c = projection.documentedComparison;
  console.log(`Compiled ${version}; ${replay.length} tapes replayed; ${projection.edges.length} edges (${c.documentedNotProducedByBend.length} documented-but-not-produced, ${c.producedByBendNotDocumented.length} produced-but-undocumented).`);
}
