import { Hono } from 'hono';
import type { DspState, ApiResponse, SpatialMode, EqProfile, BrirRoom } from '@aural/shared';
import {
  getActiveSink,
  setSpatialMode,
  getActiveEqProfile,
  setEqProfile,
  restartPipeWire,
  getActiveBrirRoom,
  setBrirRoom,
  isMbcEnabled,
} from '../pipewire/control';
import { MBC_BAND_DEFAULTS } from '@aural/shared';

const api = new Hono();

// ─── GET /api/state — Full DSP state snapshot ────────────────────
api.get('/state', async (c) => {
  try {
    const [spatialMode, eqProfile, brirRoom, mbcEnabled] = await Promise.all([
      getActiveSink(),
      getActiveEqProfile(),
      getActiveBrirRoom(),
      isMbcEnabled(),
    ]);

    const state: DspState = {
      spatialMode,
      eqProfile,
      brirRoom,
      mbcEnabled,
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
  const profile = c.req.param('profile') as EqProfile;
  if (!['monarch', 'hd800s'].includes(profile)) {
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

export default api;
