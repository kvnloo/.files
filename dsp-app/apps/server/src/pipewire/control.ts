import { type SpatialMode, type EqProfile, type BrirRoom, type BypassableStageId, SPATIAL_SINK_NAMES, EQ_PROFILES, SAMPLE_RATES, BRIR_ROOMS } from '@aural/shared';
import { buildLinks, rewriteConfigLinks } from './chain-builder';

const AUTOEQ_DIR = '/home/kvn/workspace/.files/config/autoeq';
const BRIR_DIR = '/home/kvn/workspace/.files/config/brir';
const DSP_CONFIG = '/home/kvn/workspace/.files/config/pipewire/pipewire.conf.d/10-headphone-dsp.conf';

/** In-memory bypass state (persists across requests, reset on server restart) */
const bypassedStages = new Set<BypassableStageId>();

export function getBypassed(): BypassableStageId[] {
  return [...bypassedStages];
}

const SINK_DESCRIPTIONS: Record<SpatialMode, string> = {
  clean: 'Headphone DSP',
  crossfeed: 'Headphone DSP + Crossfeed',
  room: 'Headphone DSP + Room',
};

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

async function run(cmd: string[]): Promise<{ stdout: string; stderr: string; exitCode: number }> {
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
    if (block.includes(nodeName)) {
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
  const settingsMatch = stdout.match(/Audio\/Sink\s+(\S+)/);
  if (settingsMatch) {
    const defaultName = settingsMatch[1];
    for (const [mode, sinkName] of Object.entries(SPATIAL_SINK_NAMES)) {
      if (defaultName === sinkName) return mode as SpatialMode;
    }
  }

  // Fallback: look for the * marker in Filters section next to the node name
  // Lines look like: │  *   42. effect_input.headphone_dsp_room   [Audio/Sink]
  for (const [mode, sinkName] of Object.entries(SPATIAL_SINK_NAMES)) {
    const escaped = sinkName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (new RegExp(`\\*.*${escaped}`).test(stdout)) {
      return mode as SpatialMode;
    }
  }

  return 'clean';
}

/** Switch the active PipeWire sink to a spatial mode */
export async function setSpatialMode(mode: SpatialMode): Promise<void> {
  const nodeName = SPATIAL_SINK_NAMES[mode];
  const sinkId = await findSinkId(nodeName);
  if (sinkId === null) {
    throw new Error(`Sink not found: ${nodeName}`);
  }
  const { exitCode, stderr } = await run(['wpctl', 'set-default', String(sinkId)]);
  if (exitCode !== 0) {
    throw new Error(`wpctl set-default failed: ${stderr}`);
  }
}

/** Get the current EQ profile by reading the symlink target */
export async function getActiveEqProfile(): Promise<EqProfile> {
  const link = `${AUTOEQ_DIR}/active_44100Hz.wav`;
  try {
    const target = await Bun.file(link).text().catch(() => '');
    // Actually read the symlink
    const { stdout } = await run(['readlink', link]);
    const resolved = stdout.trim();
    if (resolved.includes('Monarch')) return 'monarch';
    if (resolved.includes('HD800')) return 'hd800s';
  } catch {
    // fallback
  }
  return 'monarch';
}

/** Switch EQ profile by updating symlinks */
export async function setEqProfile(profile: EqProfile): Promise<void> {
  const info = EQ_PROFILES[profile];
  for (const rate of SAMPLE_RATES) {
    const linkPath = `${AUTOEQ_DIR}/active_${rate}Hz.wav`;
    const target = info.filePattern(rate);
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

/** Detect if MBC is currently bypassed by checking the filter chain links */
export async function isMbcEnabled(): Promise<boolean> {
  const config = await Bun.file(DSP_CONFIG).text();
  // MBC is enabled if loudness routes through mbc before limiter
  // It's bypassed if loudness goes directly to limiter
  return config.includes('"loudness:out_l"  input = "mbc:in_l"') ||
         config.includes('"loudness:out_l" input = "mbc:in_l"');
}
