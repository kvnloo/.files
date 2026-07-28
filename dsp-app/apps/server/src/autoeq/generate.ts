import type { InstalledProfile } from '@aural/shared';
import { addProfile } from './profiles';

const AUTOEQ_DIR = '/home/kvn/workspace/.files/config/autoeq';
const VENV_PYTHON = '/home/kvn/workspace/.files/dsp-app/.venv/autoeq/bin/python';
const TARGET_CSV = `${AUTOEQ_DIR}/targets/IEF_Preference_2025.csv`;
const GITHUB_RAW = 'https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/measurements';

/** Slugify a model name into a filesystem-safe profile ID */
function toProfileId(model: string): string {
  return model
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

/** Check that the AutoEQ venv exists */
export async function ensureVenv(): Promise<void> {
  const file = Bun.file(VENV_PYTHON);
  if (!(await file.exists())) {
    throw new Error(
      'AutoEQ venv not found. Run: bash dsp-app/scripts/setup-autoeq.sh',
    );
  }
}

/**
 * Generate FIR convolution filters for a headphone.
 * Downloads measurement from GitHub, runs AutoEQ, saves WAVs.
 */
export async function generateFirFilters(
  source: string,
  rig: string,
  model: string,
): Promise<InstalledProfile> {
  await ensureVenv();

  const profileId = toProfileId(model);
  const outputDir = `${AUTOEQ_DIR}/${profileId}`;
  const csvUrl = `${GITHUB_RAW}/${encodeURIComponent(source)}/${encodeURIComponent(rig)}/${encodeURIComponent(model)}/${encodeURIComponent(model)}.csv`;

  // 1. Download measurement CSV
  const csvRes = await fetch(csvUrl);
  if (!csvRes.ok) {
    throw new Error(`Failed to download measurement: ${csvRes.status} ${csvRes.statusText}`);
  }
  const csvText = await csvRes.text();

  // Ensure output directory exists
  const mkdirProc = Bun.spawn(['mkdir', '-p', outputDir], { stdout: 'pipe', stderr: 'pipe' });
  await mkdirProc.exited;

  // Save measurement CSV locally
  const localCsv = `${outputDir}/${model}.csv`;
  await Bun.write(localCsv, csvText);

  // 2. Run AutoEQ
  const proc = Bun.spawn(
    [
      VENV_PYTHON,
      '-m',
      'autoeq',
      '--input-file', localCsv,
      '--output-dir', outputDir,
      '--target', TARGET_CSV,
      '--convolution-eq',
      '--fs', '44100,48000,96000,192000,384000',
      '--bit-depth', '32',
      '--phase', 'minimum',
      '--f-res', '10',
      '--bass-boost', '0',
    ],
    {
      stdout: 'pipe',
      stderr: 'pipe',
      cwd: outputDir,
    },
  );

  const stderr = await new Response(proc.stderr).text();
  const exitCode = await proc.exited;

  if (exitCode !== 0) {
    throw new Error(`AutoEQ failed (exit ${exitCode}): ${stderr}`);
  }

  // 3. Rename generated WAVs to our naming convention
  // AutoEQ outputs: "{model} minimum phase {rate}Hz.wav"
  // We want them inside the profileId directory with the profileId prefix
  for (const rate of [44100, 48000, 96000, 192000, 384000]) {
    const autoEqName = `${model} minimum phase ${rate}Hz.wav`;
    const ourName = `${profileId} minimum phase ${rate}Hz.wav`;
    const srcPath = `${outputDir}/${autoEqName}`;
    const dstPath = `${outputDir}/${ourName}`;

    // AutoEQ may already produce files with the model name — rename if needed
    const srcFile = Bun.file(srcPath);
    if (await srcFile.exists()) {
      if (srcPath !== dstPath) {
        const mvProc = Bun.spawn(['mv', srcPath, dstPath], { stdout: 'pipe', stderr: 'pipe' });
        await mvProc.exited;
      }
    }
  }

  // 4. Create profile entry
  const profile: InstalledProfile = {
    id: profileId,
    name: model,
    fullName: model,
    target: 'IEF Preference 2025',
    character: `AutoEQ correction (${source}/${rig})`,
    builtin: false,
    source,
    rig,
  };

  await addProfile(profile);

  return profile;
}
