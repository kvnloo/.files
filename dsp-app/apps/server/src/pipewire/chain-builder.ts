/**
 * Dynamic filter chain link builder.
 *
 * Rewrites the `links = [ ... ]` section of a PipeWire filter-chain config
 * to route around bypassed stages. The node definitions stay — only the
 * wiring changes. This means PipeWire can hot-reload with minimal disruption.
 */

import type { SpatialMode, BypassableStageId } from '@aural/shared';

/** Port names for each DSP stage */
interface StagePorts {
  inL: string;
  inR: string;
  outL: string;
  outR: string;
}

const STAGE_PORTS: Record<string, StagePorts> = {
  eq: {
    inL: 'eq_l:In', inR: 'eq_r:In',
    outL: 'eq_l:Out', outR: 'eq_r:Out',
  },
  crossfeed: {
    inL: 'bs2b:Input left', inR: 'bs2b:Input right',
    outL: 'bs2b:Output left', outR: 'bs2b:Output right',
  },
  loudness: {
    inL: 'loudness:in_l', inR: 'loudness:in_r',
    outL: 'loudness:out_l', outR: 'loudness:out_r',
  },
  mbc: {
    inL: 'mbc:in_l', inR: 'mbc:in_r',
    outL: 'mbc:out_l', outR: 'mbc:out_r',
  },
  limiter: {
    inL: 'limiter:lv2_audio_in_1', inR: 'limiter:lv2_audio_in_2',
    outL: 'limiter:lv2_audio_out_1', outR: 'limiter:lv2_audio_out_2',
  },
};

// BRIR is special — it has a fan-out/mix topology
const BRIR_CHAIN = `
                    # AutoEQ → BRIR copy nodes
                    { output = "eq_l:Out"       input = "copyFL:In" }
                    { output = "eq_r:Out"       input = "copyFR:In" }

                    # Fan out to True Stereo BRIR convolvers
                    { output = "copyFL:Out"     input = "brir_fl_l:In" }
                    { output = "copyFL:Out"     input = "brir_fl_r:In" }
                    { output = "copyFR:Out"     input = "brir_fr_l:In" }
                    { output = "copyFR:Out"     input = "brir_fr_r:In" }

                    # Mix: Left ear = FL→L + FR→L, Right ear = FL→R + FR→R
                    { output = "brir_fl_l:Out"  input = "mixL:In 1" }
                    { output = "brir_fr_l:Out"  input = "mixL:In 2" }
                    { output = "brir_fl_r:Out"  input = "mixR:In 1" }
                    { output = "brir_fr_r:Out"  input = "mixR:In 2" }`;

const BRIR_OUT = { outL: 'mixL:Out', outR: 'mixR:Out' };

type Link = { output: string; input: string };

function link(outPort: string, inPort: string): Link {
  return { output: outPort, input: inPort };
}

function formatLinks(links: Link[]): string {
  return links.map(l =>
    `                    { output = "${l.output}"  input = "${l.input}" }`
  ).join('\n');
}

/**
 * Build the ordered stage chain for a given spatial mode + bypass set.
 * Returns the links section string to splice into the config.
 */
export function buildLinks(
  spatialMode: SpatialMode,
  bypassed: Set<BypassableStageId>,
): string {
  // For BRIR mode, the topology is different (fan-out/mix before loudness)
  if (spatialMode === 'room' && !bypassed.has('brir')) {
    return buildRoomLinks(bypassed);
  }

  // Linear chain: eq → [crossfeed] → [loudness] → [mbc] → limiter
  const stages: string[] = ['eq'];

  if (spatialMode === 'crossfeed' && !bypassed.has('crossfeed')) {
    stages.push('crossfeed');
  }
  if (!bypassed.has('loudness')) stages.push('loudness');
  if (!bypassed.has('mbc')) stages.push('mbc');
  stages.push('limiter');

  const links: Link[] = [];
  for (let i = 0; i < stages.length - 1; i++) {
    const from = STAGE_PORTS[stages[i]];
    const to = STAGE_PORTS[stages[i + 1]];
    links.push(link(from.outL, to.inL));
    links.push(link(from.outR, to.inR));
  }

  return formatLinks(links);
}

function buildRoomLinks(bypassed: Set<BypassableStageId>): string {
  // BRIR section (eq → copy → convolvers → mix) is fixed
  let result = BRIR_CHAIN + '\n';

  // After BRIR mix, chain: [loudness] → [mbc] → limiter
  const postBrir: string[] = [];
  if (!bypassed.has('loudness')) postBrir.push('loudness');
  if (!bypassed.has('mbc')) postBrir.push('mbc');
  postBrir.push('limiter');

  const links: Link[] = [];
  // First link: BRIR mix output → first post-BRIR stage
  const firstPost = STAGE_PORTS[postBrir[0]];
  links.push(link(BRIR_OUT.outL, firstPost.inL));
  links.push(link(BRIR_OUT.outR, firstPost.inR));

  // Chain the rest
  for (let i = 0; i < postBrir.length - 1; i++) {
    const from = STAGE_PORTS[postBrir[i]];
    const to = STAGE_PORTS[postBrir[i + 1]];
    links.push(link(from.outL, to.inL));
    links.push(link(from.outR, to.inR));
  }

  result += '\n' + formatLinks(links);
  return result;
}

/**
 * Rewrite the links section of a specific sink in the PipeWire config.
 * Identifies the sink by its node.description, then replaces its links block.
 */
export function rewriteConfigLinks(
  config: string,
  sinkDescription: string,
  newLinks: string,
): string {
  // Find the section for this sink by its node.description
  // Then find the `links = [` block within it and replace its contents
  const descPattern = `node.description = "${sinkDescription}"`;
  const descIdx = config.indexOf(descPattern);
  if (descIdx === -1) return config;

  // Find `links = [` after the description
  const linksStart = config.indexOf('links = [', descIdx);
  if (linksStart === -1) return config;

  // Find the matching closing bracket
  const contentStart = config.indexOf('[', linksStart) + 1;
  let depth = 1;
  let contentEnd = contentStart;
  while (depth > 0 && contentEnd < config.length) {
    if (config[contentEnd] === '[') depth++;
    if (config[contentEnd] === ']') depth--;
    if (depth > 0) contentEnd++;
  }

  return config.slice(0, contentStart) + '\n' + newLinks + '\n                ' + config.slice(contentEnd);
}
