#!/usr/bin/env node
// Independent producer: compile real Bend, expose its numeric ABI, execute that
// ABI to discover display edges, and bind artifacts to the current source bytes.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdtempSync, rmSync, renameSync, existsSync, accessSync, constants } from 'node:fs';
import { dirname, delimiter, join, resolve, isAbsolute } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const repository = resolve(directory, '../..');
const compilerPin = 'bend 2.0.37';
const runtimeSource = 'import Base\nimport ./Flow.bend as Flow\n\ndef main() -> U32:\n  Flow.step(Flow.initial(), 0, 0)\n';
const artifactNames = ['Flow.bend', 'model.json', 'adapter.mjs', 'build.mjs', 'scenarios.json', 'Flow.generated.mjs', 'projection.json', 'architecture.json'];
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const bytes = (name) => readFileSync(join(directory, name));
const json = (name) => JSON.parse(bytes(name).toString('utf8'));
const hash = (name) => sha256(bytes(name));
const sourcePath = (path) => {
  const absolute = resolve(repository, path);
  if (!absolute.startsWith(`${repository}/`)) throw new Error(`Source outside checkout: ${path}`);
  return absolute;
};

function checkFreshness() {
  const receipt = json('receipt.json');
  const model = json('model.json');
  if (receipt.schema !== 1 || receipt.compiler.version !== compilerPin || receipt.compiler.target !== 'JavaScript') {
    throw new Error('Receipt schema/compiler identity mismatch; rebuild with the pinned compiler');
  }
  for (const name of artifactNames) {
    if (receipt.artifacts[name] !== hash(name)) throw new Error(`Stale artifact: ${name}; rebuild the diagram`);
  }
  if (receipt.modelSha256 !== hash('model.json') || receipt.flowSha256 !== hash('Flow.bend') ||
      receipt.compiledSha256 !== hash('Flow.generated.mjs') || receipt.runtimeSha256 !== sha256(runtimeSource)) {
    throw new Error('Stale source/compiled ABI identity');
  }
  if (JSON.stringify(receipt.provenance) !== JSON.stringify(model.provenance)) throw new Error('Provenance mismatch');
  if (receipt.sources.length !== model.sources.length) throw new Error('Cited source list changed');
  for (const { path, kind } of model.sources) {
    const entry = receipt.sources.find((candidate) => candidate.path === path && candidate.kind === kind);
    if (!entry || entry.sha256 !== sha256(readFileSync(sourcePath(path)))) throw new Error(`Cited source changed: ${path}; rebuild the diagram`);
  }
  return receipt;
}

function compilerPath(command) {
  const candidates = isAbsolute(command) || command.includes('/') ? [resolve(command)] :
    (process.env.PATH ?? '').split(delimiter).map((path) => join(path, command));
  for (const candidate of candidates) {
    try { accessSync(candidate, constants.X_OK); return candidate; } catch { /* try next PATH entry */ }
  }
  throw new Error(`Bend executable not found: ${command}; set BEND explicitly`);
}

function publish(name, content) {
  const temporary = join(directory, `.${name}.${process.pid}.tmp`);
  try {
    writeFileSync(temporary, content);
    renameSync(temporary, join(directory, name));
  } finally {
    if (existsSync(temporary)) rmSync(temporary);
  }
}

if (process.argv.slice(2).some((argument) => argument !== '--check')) throw new Error('Usage: node build.mjs [--check]');
if (process.argv.includes('--check')) {
  checkFreshness();
  console.log('Diagram receipt matches current authored, compiled and cited source bytes. No compiler or runtime host checks executed.');
} else {
  const compiler = compilerPath(process.env.BEND || 'bend');
  const version = execFileSync(compiler, ['version'], { encoding: 'utf8', timeout: 10000 }).trim();
  if (version !== compilerPin) throw new Error(`Expected ${compilerPin}; got ${version}. Hapsland's 2.0.36 artifacts are not consumed.`);
  const model = json('model.json');
  const scenarios = json('scenarios.json');
  const sourceHashes = model.sources.map(({ path, kind }) => ({ path, kind, sha256: sha256(readFileSync(sourcePath(path))) }));
  const sourceHash = hash('Flow.bend');
  const modelHash = hash('model.json');
  const temporary = mkdtempSync(join(tmpdir(), 'dotfiles-spec-bend-'));
  let rawCompiledHash;
  try {
    // Importing this exact copy gives the compiler a stable Flow namespace.
    writeFileSync(join(temporary, 'Flow.bend'), bytes('Flow.bend'));
    writeFileSync(join(temporary, 'Runtime.bend'), runtimeSource);
    const output = join(temporary, 'Flow.js');
    execFileSync(compiler, [join(temporary, 'Runtime.bend'), '-o', output], { encoding: 'utf8', timeout: 180000, stdio: 'pipe' });
    const compiled = readFileSync(output, 'utf8');
    rawCompiledHash = sha256(compiled);
    // Only replace the compiler CLI entrypoint. All generated functions/runtime
    // remain untouched. Fail closed on a changed compiler layout; no fallback.
    const footer = /\ncli\(process\.argv\.slice\(\d+\)\);\nio_exit\(\$main\$, [\s\S]*\);\s*$/;
    if (!footer.test(compiled) || !compiled.includes('function $Flow$058step$(') ||
        !compiled.includes('function $Flow$058initial$(') || !compiled.includes('function run_loop(')) {
      throw new Error('Pinned compiler JavaScript ABI layout was not recognized; inspect emitted output before changing the binding');
    }
    const binding = `\nexport const bendInitial = () => run_loop($Flow$058initial$());\nexport const bendStep = (state, event, facts) => run_loop($Flow$058step$(state, event, facts));\nexport const bendMetadata = ${JSON.stringify(model)};\nexport const bendSourceSha256 = ${JSON.stringify(sourceHash)};\nexport const bendModelSha256 = ${JSON.stringify(modelHash)};\n`;
    publish('Flow.generated.mjs', `// Generated from Flow.bend by ${version}; do not hand-edit.\n${compiled.replace(footer, binding)}`);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }

  const { transition, initialState } = await import(pathToFileURL(join(directory, 'adapter.mjs')).href);
  if (!model.states.some(({ id }) => id === initialState)) throw new Error('Initial state is outside metadata wire domain');
  // Fixtures are facts, not another transition table. Execute the compiled model
  // for every state/event and these meaningful positive/negative combinations.
  const positive = Object.fromEntries(model.facts.map(({ key }) => [key, true]));
  positive.serviceInactive = false;
  const fixtures = [{}, positive, { ...positive, managedExact: false },
    { ...positive, serviceActive: false, serviceInactive: true }];
  for (const { key } of model.facts) fixtures.push({ ...positive, [key]: false }, { [key]: true });
  for (const scenario of scenarios) for (const step of scenario.steps) fixtures.push(step.facts);
  const distinctFixtures = [...new Map(fixtures.map((facts) => [JSON.stringify(Object.fromEntries(Object.entries(facts).sort())), facts])).values()];
  const edges = new Map();
  for (const { id: from } of model.states) {
    for (const { id: event, title: eventTitle } of model.events) {
      for (const facts of distinctFixtures) {
        const result = transition(from, event, facts);
        if (!result.accepted) continue;
        const kind = result.outputs.find(({ kind }) => kind === 'action-requested')?.kind ??
          result.outputs.find(({ kind }) => kind === 'event-established')?.kind ?? 'policy-decided';
        const edge = { from, to: result.state, event, eventTitle, kind };
        edges.set(`${from}:${result.state}:${event}:${kind}`, edge);
      }
    }
  }
  const projection = {
    edges: [...edges.values()].sort((a, b) => a.from - b.from || a.event - b.event || a.to - b.to),
    provenance: {
      ...model.provenance,
      producer: 'Executing the actual compiled Flow.bend through adapter.mjs over every metadata state/event and meaningful synthetic fact fixtures',
      fixtureCount: distinctFixtures.length,
      scope: 'Design-level checked possibilities, not an exhaustive proof over all fact combinations and not a native runtime trace. Selected replay highlights only accepted executed transitions.',
      flowSha256: sourceHash,
      modelSha256: modelHash,
      compiledSha256: hash('Flow.generated.mjs')
    }
  };
  publish('projection.json', `${JSON.stringify(projection, null, 2)}\n`);
  const receipt = {
    schema: 1,
    generatedAt: new Date().toISOString(),
    compiler: { version, executable: compiler, executableSha256: sha256(readFileSync(compiler)), target: 'JavaScript', flags: ['Runtime.bend', '-o', 'Flow.js'], producerPlatform: process.platform, producerArchitecture: process.arch },
    flowSha256: sourceHash,
    modelSha256: modelHash,
    runtimeSha256: sha256(runtimeSource),
    rawCompilerOutputSha256: rawCompiledHash,
    compiledSha256: hash('Flow.generated.mjs'),
    artifacts: Object.fromEntries(artifactNames.map((name) => [name, hash(name)])),
    sources: sourceHashes,
    provenance: model.provenance,
    checks: {
      compilation: 'Actual pinned Bend compiler emitted the included JavaScript; no handwritten transition fallback',
      projection: 'Possible edges enumerated by executing compiled decisions with synthetic fact fixtures',
      theoremProofs: 'Not claimed; ordinary compilation/typechecking is not an invariant proof',
      nativeRuntime: 'Not exercised by this producer; no install, Kubernetes commands or paid calls',
      sourceTrust: 'Hashes bind cited local dirty-checkout bytes, not a Git commit containing them or an external deployment receipt'
    }
  };
  publish('receipt.json', `${JSON.stringify(receipt, null, 2)}\n`);
  // Detect a concurrent source edit during generation; do not publish a success
  // assertion for a receipt that no longer matches this checkout.
  checkFreshness();
  console.log(`Generated Bend JavaScript, ${edges.size} checked possible edges and a current source receipt. This producer does not establish K3s runtime acceptance.`);
}
