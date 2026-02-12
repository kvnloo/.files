import { writable, derived } from 'svelte/store';
import type { DspState, SpatialMode, EqProfile, BrirRoom, ApiResponse } from '@aural/shared';
import { dspStages } from '$lib/content/dsp-stages';
import type { DspStageId } from '@aural/shared';

const API_BASE = '/api';

// ─── Core DSP State ──────────────────────────────────────────────
export const dspState = writable<DspState | null>(null);
export const loading = writable(false);
export const error = writable<string | null>(null);

// ─── Derived stores ──────────────────────────────────────────────
export const spatialMode = derived(dspState, ($s) => $s?.spatialMode ?? 'clean');
export const eqProfile = derived(dspState, ($s) => $s?.eqProfile ?? 'monarch');
export const brirRoom = derived(dspState, ($s) => $s?.brirRoom ?? 'R02');
export const mbcEnabled = derived(dspState, ($s) => $s?.mbcEnabled ?? false);

/** Active signal chain stages for the current spatial mode */
export const activeChain = derived(dspState, ($s): DspStageId[] => {
  if (!$s) return [];
  const chain: DspStageId[] = ['autoeq'];
  if ($s.spatialMode === 'crossfeed') chain.push('crossfeed');
  if ($s.spatialMode === 'room') chain.push('brir');
  chain.push('loudness');
  if ($s.mbcEnabled) chain.push('mbc');
  chain.push('limiter');
  return chain;
});

// ─── API Actions ─────────────────────────────────────────────────
async function apiCall<T = void>(path: string, method = 'POST'): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { method });
    return await res.json();
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Network error' };
  }
}

export async function fetchState(): Promise<void> {
  loading.set(true);
  error.set(null);
  const res = await apiCall<DspState>('/state', 'GET');
  if (res.ok && res.data) {
    dspState.set(res.data);
  } else {
    error.set(res.error ?? 'Failed to fetch state');
  }
  loading.set(false);
}

export async function switchSpatialMode(mode: SpatialMode): Promise<void> {
  loading.set(true);
  error.set(null);
  // Optimistic update
  dspState.update((s) => (s ? { ...s, spatialMode: mode } : s));
  const res = await apiCall(`/spatial/${mode}`);
  if (!res.ok) {
    error.set(res.error ?? 'Failed to switch spatial mode');
    await fetchState(); // revert
  }
  loading.set(false);
}

export async function switchEqProfile(profile: EqProfile): Promise<void> {
  loading.set(true);
  error.set(null);
  dspState.update((s) => (s ? { ...s, eqProfile: profile } : s));
  const res = await apiCall(`/eq/${profile}`);
  if (!res.ok) {
    error.set(res.error ?? 'Failed to switch EQ profile');
    await fetchState();
  }
  loading.set(false);
}

export async function switchBrirRoom(room: BrirRoom): Promise<void> {
  loading.set(true);
  error.set(null);
  dspState.update((s) => (s ? { ...s, brirRoom: room } : s));
  const res = await apiCall(`/brir/${room}`);
  if (!res.ok) {
    error.set(res.error ?? 'Failed to switch BRIR room');
    await fetchState();
  }
  loading.set(false);
}
