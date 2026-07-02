import {
  type SpatialMode,
  type EqProfile,
  type BrirRoom,
  type BypassableStageId,
  type AudioFormat,
  type AppAudioStream,
  type PipeWireSink,
  type SinkRole,
  SPATIAL_SINK_NAMES,
  MOVIE_SINK_NAME,
  SAMPLE_RATES,
  BRIR_ROOMS,
} from '@aural/shared';
import { buildLinks, rewriteConfigLinks } from './chain-builder';
import { getProfileFilePattern } from '../autoeq/profiles';

const AUTOEQ_DIR = '/home/kvn/workspace/.files/config/autoeq';
const BRIR_DIR = '/home/kvn/workspace/.files/config/brir';
const DSP_CONFIG = '/home/kvn/workspace/.files/config/pipewire/pipewire.conf.d/10-headphone-dsp.conf';

/** In-memory bypass state (persists across requests, reset on server restart) */
const bypassedStages = new Set<BypassableStageId>();

/** Timestamp of last sink switch — used by the format poller to avoid
 *  broadcasting transient DAC rates during PipeWire renegotiation. */
let lastSinkSwitchAt = 0;
export function getLastSinkSwitchTime(): number { return lastSinkSwitchAt; }

export function getBypassed(): BypassableStageId[] {
  return [...bypassedStages];
}

const SINK_DESCRIPTIONS: Record<SpatialMode, string> = {
  clean: 'Headphone DSP',
  crossfeed: 'Headphone DSP + Crossfeed',
  room: 'Headphone DSP + Room',
};

function parseSampleSpec(spec: string | null): Pick<PipeWireSink, 'format' | 'channels' | 'sampleRate'> {
  if (!spec) return { format: null, channels: null, sampleRate: null };
  const match = spec.match(/(\S+)\s+(\d+)ch\s+(\d+)Hz/);
  if (!match) return { format: null, channels: null, sampleRate: null };
  return {
    format: match[1],
    channels: parseInt(match[2], 10),
    sampleRate: parseInt(match[3], 10),
  };
}

function readField(block: string, label: string): string | null {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = block.match(new RegExp(`^\\s*${escaped}:\\s*(.+)$`, 'm'));
  return match?.[1]?.trim() ?? null;
}

function readPulseProperty(block: string, key: string): string | null {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = block.match(new RegExp(`${escaped}\\s*=\\s*"([^"]*)"`));
  return match?.[1] ?? null;
}

function sinkRole(name: string): SinkRole {
  if (name === MOVIE_SINK_NAME) return 'movie';
  if (Object.values(SPATIAL_SINK_NAMES).includes(name)) return 'music';
  if (name.startsWith('alsa_output.')) return 'hardware';
  return 'other';
}

function getDefaultSinkName(statusOutput: string): string | null {
  const settingsMatch = statusOutput.match(/Audio\/Sink\s+(\S+)/);
  if (settingsMatch) return settingsMatch[1];

  const starredMatch = statusOutput.match(/\*\s+\d+\.\s+(\S+)\s+\[Audio\/Sink\]/);
  return starredMatch?.[1] ?? null;
}

/** Toggle a stage bypass and rewrite the active sink's filter chain */
export async function toggleStageBypass(
  stageId: BypassableStageId,
  spatialMode: SpatialMode,
): Promise<void> {
  if (bypassedStages.has(stageId)) {
    bypassedStages.delete(stageId);
  } else {
    bypassedStages.add(stageId);
  }

  const newLinks = buildLinks(spatialMode, bypassedStages);
  let config = await Bun.file(DSP_CONFIG).text();
  const desc = SINK_DESCRIPTIONS[spatialMode];
  config = rewriteConfigLinks(config, desc, newLinks);
  await Bun.write(DSP_CONFIG, config);
  await restartPipeWire();

  // Re-set the default sink after restart (IDs change)
  await setSpatialMode(spatialMode);
}

export async function run(cmd: string[]): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const proc = Bun.spawn(cmd, { stdout: 'pipe', stderr: 'pipe' });
  const stdout = await new Response(proc.stdout).text();
  const stderr = await new Response(proc.stderr).text();
  const exitCode = await proc.exited;
  return { stdout, stderr, exitCode };
}

/** Find a PipeWire node ID by its node.name */
async function findSinkId(nodeName: string): Promise<number | null> {
  const { stdout } = await run(['pw-cli', 'ls', 'Node']);
  // Parse pw-cli output: look for blocks containing the node name
  const blocks = stdout.split(/(?=\tid \d+)/);
  for (const block of blocks) {
    if (new RegExp(`node\\.name\\s*=\\s*"${nodeName}"`).test(block)) {
      const match = block.match(/id (\d+)/);
      if (match) return parseInt(match[1], 10);
    }
  }
  return null;
}

/** Get the currently active (default) sink */
export async function getActiveSink(): Promise<SpatialMode> {
  const { stdout } = await run(['wpctl', 'status']);

  // The Settings section at the bottom shows:
  //   0. Audio/Sink    effect_input.headphone_dsp_room
  const defaultName = getDefaultSinkName(stdout);
  if (defaultName) {
    for (const [mode, sinkName] of Object.entries(SPATIAL_SINK_NAMES)) {
      if (defaultName === sinkName) return mode as SpatialMode;
    }
  }

  // Fallback: look for the * marker in Filters section next to the node name
  // Lines look like: │  *   42. effect_input.headphone_dsp_room   [Audio/Sink]
  for (const [mode, sinkName] of Object.entries(SPATIAL_SINK_NAMES)) {
    const escaped = sinkName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (new RegExp(`\\*.*${escaped}(?![\\w])`).test(stdout)) {
      return mode as SpatialMode;
    }
  }

  return 'clean';
}

/** Snapshot live app routes and PipeWire sinks. */
export async function getPipeWireSystem(): Promise<{
  defaultSinkName: string | null;
  sinks: PipeWireSink[];
  streams: AppAudioStream[];
}> {
  const [{ stdout: statusOut }, { stdout: sinksOut }, { stdout: inputsOut }] = await Promise.all([
    run(['wpctl', 'status']),
    run(['pactl', 'list', 'sinks']),
    run(['pactl', 'list', 'sink-inputs']),
  ]);

  const defaultSinkName = getDefaultSinkName(statusOut);

  const sinks: PipeWireSink[] = sinksOut
    .split(/(?=Sink #\d+)/)
    .filter((block) => block.trim().startsWith('Sink #'))
    .map((block) => {
      const id = parseInt(block.match(/^Sink #(\d+)/)?.[1] ?? '-1', 10);
      const name = readField(block, 'Name') ?? 'unknown';
      const sample = parseSampleSpec(readField(block, 'Sample Specification'));
      return {
        id,
        name,
        description: readField(block, 'Description') ?? name,
        role: sinkRole(name),
        state: readField(block, 'State') ?? 'UNKNOWN',
        sampleRate: sample.sampleRate,
        channels: sample.channels,
        format: sample.format,
        isDefault: name === defaultSinkName,
        activeStreams: 0,
      };
    });

  const sinkById = new Map(sinks.map((sink) => [sink.id, sink]));

  const streams: AppAudioStream[] = inputsOut
    .split(/(?=Sink Input #\d+)/)
    .filter((block) => block.trim().startsWith('Sink Input #'))
    .map((block) => {
      const applicationName = readPulseProperty(block, 'application.name');
      if (!applicationName) return null;

      const id = parseInt(block.match(/^Sink Input #(\d+)/)?.[1] ?? '-1', 10);
      const sinkIdText = readField(block, 'Sink');
      const sinkId = sinkIdText ? parseInt(sinkIdText, 10) : null;
      const sink = sinkId === null ? undefined : sinkById.get(sinkId);
      const sample = parseSampleSpec(readField(block, 'Sample Specification'));
      const corked = readField(block, 'Corked') === 'yes';

      return {
        id,
        applicationName,
        binary: readPulseProperty(block, 'application.process.binary'),
        mediaName: readPulseProperty(block, 'media.name'),
        sinkId,
        sinkName: sink?.name ?? null,
        sinkDescription: sink?.description ?? null,
        sampleRate: sample.sampleRate,
        channels: sample.channels,
        format: sample.format,
        channelMap: readField(block, 'Channel Map'),
        state: corked ? 'paused' : 'active',
      } satisfies AppAudioStream;
    })
    .filter((stream): stream is AppAudioStream => stream !== null);

  for (const sink of sinks) {
    sink.activeStreams = streams.filter((stream) => stream.sinkId === sink.id && stream.state === 'active').length;
  }

  return { defaultSinkName, sinks, streams };
}

/** Switch the active PipeWire sink to a spatial mode.
 *  Locks the graph clock rate during the switch so the DAC doesn't fall back
 *  to 48 kHz while streams migrate between filter-chain sinks. */
export async function setSpatialMode(mode: SpatialMode): Promise<void> {
  // Snapshot current DAC rate before switching — if audio is playing, we lock it
  const currentFormat = await getAudioFormat();
  const lockRate = currentFormat?.sampleRate ?? 0;

  try {
    if (lockRate > 0) {
      await run(['pw-metadata', '-n', 'settings', '0', 'clock.force-rate', String(lockRate)]);
    }

    const nodeName = SPATIAL_SINK_NAMES[mode];
    const sinkId = await findSinkId(nodeName);
    if (sinkId === null) {
      throw new Error(`Sink not found: ${nodeName}`);
    }
    const { exitCode, stderr } = await run(['wpctl', 'set-default', String(sinkId)]);
    if (exitCode !== 0) {
      throw new Error(`wpctl set-default failed: ${stderr}`);
    }

    // Let streams migrate while the rate is locked
    await Bun.sleep(500);
  } finally {
    // Always release the rate lock (0 = no forced rate)
    if (lockRate > 0) {
      await run(['pw-metadata', '-n', 'settings', '0', 'clock.force-rate', '0']);
    }
    lastSinkSwitchAt = Date.now();
  }
}

/** Get the current EQ profile by reading the symlink target */
export async function getActiveEqProfile(): Promise<EqProfile> {
  const link = `${AUTOEQ_DIR}/active_44100Hz.wav`;
  try {
    const { stdout } = await run(['readlink', link]);
    const resolved = stdout.trim();
    if (resolved.includes('Monarch')) return 'monarch';
    if (resolved.includes('HD800')) return 'hd800s';
    // Custom profile: symlink target is "{id}/{id} minimum phase {rate}Hz.wav"
    const match = resolved.match(/^([^/]+)\//);
    if (match) return match[1];
  } catch {
    // fallback
  }
  return 'monarch';
}

/** Switch EQ profile by updating symlinks */
export async function setEqProfile(profile: EqProfile): Promise<void> {
  const filePattern = await getProfileFilePattern(profile);
  if (!filePattern) {
    throw new Error(`Unknown profile: ${profile}`);
  }
  for (const rate of SAMPLE_RATES) {
    const linkPath = `${AUTOEQ_DIR}/active_${rate}Hz.wav`;
    const target = filePattern(rate);
    const { exitCode } = await run(['ln', '-sf', target, linkPath]);
    if (exitCode !== 0) {
      throw new Error(`Failed to create symlink for ${rate}Hz`);
    }
  }
}

/** Restart PipeWire to pick up config/symlink changes */
export async function restartPipeWire(): Promise<void> {
  await run(['systemctl', '--user', 'restart', 'pipewire']);
  // Wait for PipeWire to stabilize
  await Bun.sleep(1500);
}

/** Get current BRIR room from the config file */
export async function getActiveBrirRoom(): Promise<BrirRoom> {
  const config = await Bun.file(DSP_CONFIG).text();
  if (config.includes('BRIR_R32')) return 'R32';
  return 'R02';
}

/** Switch BRIR room in the config file */
export async function setBrirRoom(room: BrirRoom): Promise<void> {
  const info = BRIR_ROOMS[room];
  let config = await Bun.file(DSP_CONFIG).text();
  // Replace all BRIR filename references
  config = config.replace(/BRIR_R\d{2}_C1_True_Stereo\.wav/g, info.filename);
  await Bun.write(DSP_CONFIG, config);
}

/** Get current audio format from PipeWire (sample rate, bit depth, format).
 *  Reads the negotiated Format from the hardware ALSA sink the DSP chain
 *  feeds into, which reflects the actual rate the DAC is running at. */
export async function getAudioFormat(): Promise<AudioFormat | null> {
  try {
    // pw-link shows what the active DSP output connects to (the hardware sink)
    const { stdout: linkOut } = await run(['pw-link', '-l']);
    // Find: effect_output.headphone_dsp*:output_FL\n  |-> alsa_output.*:playback_FL
    const hwSinkMatch = linkOut.match(
      /effect_output\.headphone_dsp\S*:output_FL\n\s+\|->\s+(alsa_output\.\S+):playback_FL/
    );
    const hwSinkName = hwSinkMatch?.[1];
    if (!hwSinkName) return null;

    // pw-dump includes the negotiated Format params with the actual running rate
    const { stdout: dumpOut } = await run(['pw-dump']);
    const nodes = JSON.parse(dumpOut) as any[];
    for (const node of nodes) {
      const props = node?.info?.props;
      if (props?.['node.name'] !== hwSinkName) continue;
      const formats = node?.info?.params?.Format;
      if (!Array.isArray(formats)) continue;
      for (const fmt of formats) {
        if (fmt?.rate) {
          const format = fmt.format ?? 'S32LE';
          const bitsMatch = format.match(/\d+/);
          return {
            sampleRate: fmt.rate,
            bitDepth: bitsMatch ? parseInt(bitsMatch[0], 10) : 32,
            format,
          };
        }
      }
    }
    return null;
  } catch {
    return null;
  }
}

/** Detect if MBC is currently bypassed by checking the filter chain links */
export async function isMbcEnabled(): Promise<boolean> {
  const config = await Bun.file(DSP_CONFIG).text();
  // MBC is enabled if loudness routes through mbc before limiter
  // It's bypassed if loudness goes directly to limiter
  return config.includes('"loudness:out_l"  input = "mbc:in_l"') ||
         config.includes('"loudness:out_l" input = "mbc:in_l"');
}
