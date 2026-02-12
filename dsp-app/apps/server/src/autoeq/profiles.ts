import type { InstalledProfile } from '@aural/shared';
import { BUILTIN_EQ_PROFILES, SAMPLE_RATES } from '@aural/shared';

const AUTOEQ_DIR = '/home/kvn/workspace/.files/config/autoeq';
const PROFILES_PATH = `${AUTOEQ_DIR}/profiles.json`;

/** Built-in profiles derived from the shared constants */
const BUILTIN_PROFILES: InstalledProfile[] = Object.values(BUILTIN_EQ_PROFILES).map((p) => ({
  id: p.id,
  name: p.name,
  fullName: p.fullName,
  target: p.target,
  character: p.character,
  builtin: true,
}));

/** Read custom profiles from disk, merged with builtins */
export async function getProfiles(): Promise<InstalledProfile[]> {
  try {
    const file = Bun.file(PROFILES_PATH);
    if (await file.exists()) {
      const custom: InstalledProfile[] = await file.json();
      return [...BUILTIN_PROFILES, ...custom];
    }
  } catch {
    // Corrupt file — return builtins only
  }
  return [...BUILTIN_PROFILES];
}

/** Check if a profile ID exists (builtin or custom) */
export async function hasProfile(id: string): Promise<boolean> {
  const profiles = await getProfiles();
  return profiles.some((p) => p.id === id);
}

/** Add a custom profile and persist to disk */
export async function addProfile(profile: InstalledProfile): Promise<void> {
  const custom = await getCustomProfiles();
  // Replace if already exists
  const filtered = custom.filter((p) => p.id !== profile.id);
  filtered.push(profile);
  await Bun.write(PROFILES_PATH, JSON.stringify(filtered, null, 2));
}

/** Remove a custom profile, its WAV files, and persist */
export async function removeProfile(id: string): Promise<void> {
  // Never remove builtins
  if (id in BUILTIN_EQ_PROFILES) {
    throw new Error(`Cannot remove built-in profile: ${id}`);
  }

  const custom = await getCustomProfiles();
  const filtered = custom.filter((p) => p.id !== id);
  if (filtered.length === custom.length) {
    throw new Error(`Profile not found: ${id}`);
  }
  await Bun.write(PROFILES_PATH, JSON.stringify(filtered, null, 2));

  // Remove WAV directory
  const profileDir = `${AUTOEQ_DIR}/${id}`;
  try {
    const proc = Bun.spawn(['rm', '-rf', profileDir], { stdout: 'pipe', stderr: 'pipe' });
    await proc.exited;
  } catch {
    // Best-effort cleanup
  }
}

/** Get file pattern function for any installed profile */
export async function getProfileFilePattern(id: string): Promise<((rate: number) => string) | null> {
  // Check builtins first
  if (id in BUILTIN_EQ_PROFILES) {
    return BUILTIN_EQ_PROFILES[id as keyof typeof BUILTIN_EQ_PROFILES].filePattern;
  }

  // Custom profile: WAVs are in config/autoeq/{id}/
  const custom = await getCustomProfiles();
  const profile = custom.find((p) => p.id === id);
  if (!profile) return null;

  return (rate: number) => `${id}/${id} minimum phase ${rate}Hz.wav`;
}

async function getCustomProfiles(): Promise<InstalledProfile[]> {
  try {
    const file = Bun.file(PROFILES_PATH);
    if (await file.exists()) {
      return await file.json();
    }
  } catch {
    // Corrupt or missing
  }
  return [];
}
