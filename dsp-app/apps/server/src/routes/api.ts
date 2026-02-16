import { Hono } from 'hono';
import type { DspState, ApiResponse, SpatialMode, EqProfile, BrirRoom, BypassableStageId, InstalledProfile, HeadphoneSearchResult } from '@aural/shared';
import {
  getActiveSink,
  setSpatialMode,
  getActiveEqProfile,
  setEqProfile,
  restartPipeWire,
  getActiveBrirRoom,
  setBrirRoom,
  isMbcEnabled,
  getBypassed,
  toggleStageBypass,
  getAudioFormat,
} from '../pipewire/control';
import { MBC_BAND_DEFAULTS } from '@aural/shared';
import { searchHeadphones } from '../autoeq/index';
import { generateFirFilters } from '../autoeq/generate';
import { getProfiles, hasProfile, removeProfile } from '../autoeq/profiles';

const BYPASSABLE: BypassableStageId[] = ['crossfeed', 'brir', 'loudness', 'mbc'];

const api = new Hono();

// ─── GET /api/state — Full DSP state snapshot ────────────────────
api.get('/state', async (c) => {
  try {
    const [spatialMode, eqProfile, brirRoom, mbcEnabled, profiles, audioFormat] = await Promise.all([
      getActiveSink(),
      getActiveEqProfile(),
      getActiveBrirRoom(),
      isMbcEnabled(),
      getProfiles(),
      getAudioFormat(),
    ]);

    const state: DspState = {
      spatialMode,
      eqProfile,
      brirRoom,
      mbcEnabled,
      audioFormat,
      mbcBands: MBC_BAND_DEFAULTS,
      loudness: {
        enabled: true,
        standard: 1,
        fft: 4,
        volume: 0.0,
        input: 1.0,
        hclip: false,
      },
      limiter: {
        ceiling: -0.3,
        threshold: -0.3,
        release: 25.0,
      },
      bypassed: getBypassed(),
      profiles,
    };

    return c.json({ ok: true, data: state } satisfies ApiResponse<DspState>);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

// ─── POST /api/spatial/:mode — Switch spatial mode ───────────────
api.post('/spatial/:mode', async (c) => {
  const mode = c.req.param('mode') as SpatialMode;
  if (!['clean', 'crossfeed', 'room'].includes(mode)) {
    return c.json({ ok: false, error: `Invalid mode: ${mode}` } satisfies ApiResponse, 400);
  }

  try {
    await setSpatialMode(mode);
    return c.json({ ok: true } satisfies ApiResponse);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

// ─── POST /api/eq/:profile — Switch EQ profile ──────────────────
api.post('/eq/:profile', async (c) => {
  const profile = c.req.param('profile');
  if (!(await hasProfile(profile))) {
    return c.json({ ok: false, error: `Invalid profile: ${profile}` } satisfies ApiResponse, 400);
  }

  try {
    await setEqProfile(profile);
    await restartPipeWire();
    return c.json({ ok: true } satisfies ApiResponse);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

// ─── POST /api/brir/:room — Switch BRIR room ────────────────────
api.post('/brir/:room', async (c) => {
  const room = c.req.param('room') as BrirRoom;
  if (!['R02', 'R32'].includes(room)) {
    return c.json({ ok: false, error: `Invalid room: ${room}` } satisfies ApiResponse, 400);
  }

  try {
    await setBrirRoom(room);
    await restartPipeWire();
    return c.json({ ok: true } satisfies ApiResponse);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

// ─── POST /api/bypass/:stageId — Toggle stage bypass ─────────────
api.post('/bypass/:stageId', async (c) => {
  const stageId = c.req.param('stageId') as BypassableStageId;
  if (!BYPASSABLE.includes(stageId)) {
    return c.json({ ok: false, error: `Invalid stage: ${stageId}` } satisfies ApiResponse, 400);
  }

  try {
    const currentMode = await getActiveSink();
    await toggleStageBypass(stageId, currentMode);
    return c.json({ ok: true, data: getBypassed() } satisfies ApiResponse<BypassableStageId[]>);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

// ─── Headphone Search & Install ──────────────────────────────────

/** GET /api/headphones/search?q=... — Search AutoEQ measurement index */
api.get('/headphones/search', async (c) => {
  const query = c.req.query('q') ?? '';
  if (query.length < 2) {
    return c.json({ ok: true, data: [] } satisfies ApiResponse<HeadphoneSearchResult[]>);
  }

  try {
    const results = await searchHeadphones(query);
    return c.json({ ok: true, data: results } satisfies ApiResponse<HeadphoneSearchResult[]>);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

/** GET /api/headphones/profiles — All installed profiles */
api.get('/headphones/profiles', async (c) => {
  try {
    const profiles = await getProfiles();
    return c.json({ ok: true, data: profiles } satisfies ApiResponse<InstalledProfile[]>);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

/** POST /api/headphones/install — Generate FIR filters and install profile */
api.post('/headphones/install', async (c) => {
  try {
    const body = await c.req.json<{ source: string; rig: string; model: string }>();
    if (!body.source || !body.rig || !body.model) {
      return c.json({ ok: false, error: 'Missing source, rig, or model' } satisfies ApiResponse, 400);
    }

    const profile = await generateFirFilters(body.source, body.rig, body.model);
    return c.json({ ok: true, data: profile } satisfies ApiResponse<InstalledProfile>);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

/** DELETE /api/headphones/:id — Remove a custom profile */
api.delete('/headphones/:id', async (c) => {
  const id = c.req.param('id');

  try {
    await removeProfile(id);
    return c.json({ ok: true } satisfies ApiResponse);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return c.json({ ok: false, error: message } satisfies ApiResponse, 500);
  }
});

export default api;
