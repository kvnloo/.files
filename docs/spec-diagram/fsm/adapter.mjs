// Serialization/ABI boundary only. Every next state, effect and queue decision
// is computed by the JavaScript the pinned Bend compiler emitted from the
// unchanged fsm.bend files (Runtime.generated.mjs). This file converts plain
// JSON values to Bend constructors and back, rejects anything outside the
// declared types, and labels an unchanged state with the law that guards it.
import Bend, { bendMetadata } from './Runtime.generated.mjs';

const meta = bendMetadata;
const call = (name, ...args) => {
  const fn = Bend[name];
  if (typeof fn !== 'function') throw new Error(`Compiled Bend export missing: ${name}`);
  return fn(...args);
};
if (call('abi_version') !== 1) throw new Error('Bend ABI version mismatch');

const namespaceOf = (typeName) => typeName.slice(0, typeName.indexOf('.'));

/** JSON value -> Bend value. Fails closed on any unknown tag, field or range. */
export function toBend(typeName, value, path = typeName) {
  if (typeName === 'Nat') {
    if (!Number.isSafeInteger(value) || value < 0) throw new TypeError(`${path} must be a non-negative integer`);
    return BigInt(value);
  }
  if (typeName === 'Bool') {
    if (typeof value !== 'boolean') throw new TypeError(`${path} must be boolean`);
    return value;
  }
  const type = meta.types[typeName];
  if (!type) throw new TypeError(`Unknown ABI type ${typeName}`);
  const ns = namespaceOf(typeName);
  if (type.enum) {
    if (!type.enum.includes(value)) throw new TypeError(`${path} must be one of ${type.enum.join(', ')}`);
    return { $: `${ns}.${value}` };
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new TypeError(`${path} must be an object`);
  const tags = Object.keys(type.ctors);
  const tag = value.tag ?? (tags.length === 1 ? tags[0] : undefined);
  const fields = type.ctors[tag];
  if (!fields) throw new TypeError(`${path}: unknown constructor ${String(tag)}`);
  for (const key of Object.keys(value)) {
    if (key !== 'tag' && !(key in fields)) throw new TypeError(`${path}.${key} is not a field of ${tag}`);
  }
  const out = { $: `${ns}.${tag}` };
  for (const [field, fieldType] of Object.entries(fields)) out[field] = toBend(fieldType, value[field], `${path}.${field}`);
  return out;
}

/** Bend value -> JSON value, checking the compiled output against the same types. */
export function fromBend(typeName, value, path = typeName) {
  if (typeName === 'Nat') {
    if (typeof value !== 'bigint' || value < 0n || value > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error(`${path}: Bend returned a non-Nat`);
    return Number(value);
  }
  if (typeName === 'Bool') {
    if (typeof value !== 'boolean') throw new Error(`${path}: Bend returned a non-Bool`);
    return value;
  }
  const type = meta.types[typeName];
  const ns = namespaceOf(typeName);
  const tag = typeof value?.$ === 'string' && value.$.startsWith(`${ns}.`) ? value.$.slice(ns.length + 1) : undefined;
  if (type.enum) {
    if (!type.enum.includes(tag)) throw new Error(`${path}: Bend returned an undeclared ${typeName}`);
    return tag;
  }
  const fields = type.ctors[tag];
  if (!fields) throw new Error(`${path}: Bend returned an undeclared ${typeName} constructor`);
  const out = Object.keys(type.ctors).length === 1 ? {} : { tag };
  for (const [field, fieldType] of Object.entries(fields)) out[field] = fromBend(fieldType, value[field], `${path}.${field}`);
  return out;
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const machineOf = (machine) => {
  const m = meta.machines[machine];
  if (!m) throw new TypeError(`Unknown machine ${machine}`);
  return m;
};
const ctorIndex = (typeName, tag) => Object.keys(meta.types[typeName].ctors).indexOf(tag);

/** Presentation node id for a state value (no decision is made here). */
export function displayState(machine, value) {
  const m = machineOf(machine);
  if (machine === 'device') return (value.lk.tag === 'Held' ? 2 : 0) + (value.fg.tag === 'Seen' ? 1 : 0);
  return ctorIndex(m.stateType, value.tag);
}

export function validateState(machine, value) {
  const m = machineOf(machine);
  return fromBend(m.stateType, toBend(m.stateType, value));
}

const guardFor = (machine, from, event) =>
  meta.guards.find((g) => g.machine === machine && g.from === from && g.event === event) ??
  meta.guards.find((g) => g.machine === machine && g.from === '*' && g.event === event);

const stateTag = (machine, value) => machine === 'device'
  ? `${value.lk.tag === 'Held' ? 'held' : 'free'}-${value.fg.tag === 'Seen' ? 'seen' : 'unknown'}` : value.tag;

export function transition(machine, state, event, facts = {}) {
  const m = machineOf(machine);
  for (const key of Object.keys(facts)) if (!(key in m.facts)) throw new TypeError(`unknown fact ${key} for ${machine}`);
  const before = toBend(m.stateType, state);
  const ev = toBend(m.eventType, event);
  const beforeJson = fromBend(m.stateType, before);
  const eventTag = ev.$.slice(ev.$.indexOf('.') + 1);
  const outputs = [];
  let raw, held = false, effect = null;
  if (machine === 'work-item') {
    const avail = toBend('WorkItem.Avail', facts.availability ?? m.facts.availability.default, 'facts.availability');
    raw = call('WorkItem.astep', avail, before, ev);
    held = call('WorkItem.is_off', avail) && call('WorkItem.owner_event', ev);
  } else if (machine === 'worker') {
    raw = call('WorkerSupervision.step', before, ev, toBend('Nat', facts.limit ?? m.facts.limit.default, 'facts.limit'));
  } else if (machine === 'lease') {
    raw = call('WorkerSupervision.lstep', before, ev);
  } else {
    effect = fromBend('WorkerSupervision.Eff', call('WorkerSupervision.peff', before, ev));
    raw = call('WorkerSupervision.pstep', before, ev);
  }
  const after = fromBend(m.stateType, raw);
  const changed = !same(beforeJson, after);
  const guard = guardFor(machine, stateTag(machine, beforeJson), eventTag);
  let verdict;
  let reason;
  if (held) {
    verdict = 'held';
    reason = 'HELD · L7: Kevin is off, so this owner action waits in the needs-Kevin queue.';
    outputs.push({ kind: 'queued', label: 'needs-Kevin queue (owner off)' });
  } else if (guard?.acceptance === 'effect') {
    verdict = effect.tag === 'NoEff' ? 'refused' : 'accepted';
    reason = verdict === 'accepted' ? `ACCEPTED · ${guard.laws.join(' ')}` : `REFUSED · ${guard.laws.join(' ')}: ${guard.text}`;
  } else if (changed) {
    verdict = 'accepted';
    reason = `ACCEPTED${guard?.laws?.length ? ` · checked ${guard.laws.join(' ')}` : ''}`;
  } else if (meta.states[machine].find((s) => s.tag === stateTag(machine, beforeJson))?.terminal) {
    verdict = 'no-change';
    reason = `FINAL: ${stateTag(machine, beforeJson)} is a terminal state; nothing moves it.`;
  } else if (guard && (guard.kind === 'clock' || guard.kind === 'observation')) {
    verdict = 'no-change';
    reason = `NO CHANGE · ${guard.laws.join(' ')}: ${guard.text}`;
  } else if (guard) {
    verdict = 'refused';
    reason = `REFUSED · ${guard.laws.length ? guard.laws.join(' ') : 'role'}: ${guard.text}`;
  } else {
    verdict = 'refused';
    reason = `REFUSED: no ${eventTag} transition from ${stateTag(machine, beforeJson)}; Bend kept the state.`;
  }
  if (effect) outputs.push({ kind: 'effect', label: effect.tag === 'NoEff' ? 'no effect on the phone'
    : effect.tag === 'Installed' ? `install by worker ${effect.a}` : `input by worker ${effect.a} into app ${effect.app}` });
  if (machine === 'work-item' && call('WorkItem.needs_kevin', raw)) outputs.push({ kind: 'queue', label: 'in the needs-Kevin queue (awaiting owner acceptance)' });
  if (machine === 'worker' && call('WorkerSupervision.needs_kevin', raw)) outputs.push({ kind: 'queue', label: 'Overdue: in the needs-Kevin queue' });
  if (machine === 'lease' && 'a' in event) {
    outputs.push({ kind: 'lease', label: call('WorkerSupervision.holds', raw, BigInt(event.a))
      ? `session ${event.a} holds the lease and may write` : `session ${event.a} may NOT write here` });
  }
  outputs.push({ kind: 'decision', label: reason });
  return {
    machine, before: displayState(machine, beforeJson), state: displayState(machine, after),
    event: ctorIndex(m.eventType, eventTag), eventTag, accepted: verdict === 'accepted', verdict, reason,
    laws: guard?.laws ?? (held ? ['L7'] : []), value: after, outputs
  };
}
