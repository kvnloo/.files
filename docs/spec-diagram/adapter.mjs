// Serialization/ABI boundary only. Every permission and next-state decision is
// evaluated by the JavaScript actually compiled from Flow.bend.
import { bendInitial, bendStep, bendMetadata } from './Flow.generated.mjs';

const states = new Set(bendMetadata.states.map(({ id }) => id));
const knownFacts = new Set(bendMetadata.facts.map(({ key }) => key));
const labels = (items) => new Map(items.map(({ id, title }) => [id, title]));
const actionLabels = labels(bendMetadata.actions);
const eventLabels = labels(bendMetadata.events);
const reasonLabels = labels(bendMetadata.reasons);

function u32(value, name) {
  if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
    throw new TypeError(`${name} must be an unsigned 32-bit integer`);
  }
  return value;
}

export const initialState = u32(bendInitial(), 'Bend initial state');

export function transition(stateNumber, eventNumber, factsObjectOfBooleans = {}) {
  u32(stateNumber, 'state');
  u32(eventNumber, 'event');
  if (!states.has(stateNumber)) throw new TypeError('state is not a model wire state');
  if (factsObjectOfBooleans === null || typeof factsObjectOfBooleans !== 'object' || Array.isArray(factsObjectOfBooleans)) {
    throw new TypeError('facts must be an object of booleans');
  }
  for (const [key, value] of Object.entries(factsObjectOfBooleans)) {
    if (!knownFacts.has(key)) throw new TypeError(`unknown wire fact: ${key}`);
    if (typeof value !== 'boolean') throw new TypeError(`fact ${key} must be boolean`);
  }
  let mask = 0;
  for (const { key, bit } of bendMetadata.facts) {
    if (factsObjectOfBooleans[key] === true) mask += 2 ** bit;
  }
  const wire = u32(bendStep(stateNumber, eventNumber, mask), 'Bend outcome');
  const state = wire & 63;
  const accepted = ((wire >>> 6) & 1) === 1;
  const reason = (wire >>> 7) & 63;
  const action = (wire >>> 13) & 31;
  const established = (wire >>> 18) & 63;
  if (!states.has(state) || !reasonLabels.has(reason) || !actionLabels.has(action) ||
      (established !== 0 && !eventLabels.has(established - 1)) || wire >>> 24) {
    throw new Error('Bend outcome does not match the declared wire ABI');
  }
  const outputs = [];
  if (action !== 0) outputs.push({ kind: 'action-requested', code: action, label: actionLabels.get(action) });
  if (established !== 0) outputs.push({ kind: 'event-established', code: established - 1, label: eventLabels.get(established - 1) });
  outputs.push({ kind: 'policy-decided', code: reason, label: reasonLabels.get(reason) });
  return { before: stateNumber, state, event: eventNumber, accepted, reason: reasonLabels.get(reason), outputs };
}
