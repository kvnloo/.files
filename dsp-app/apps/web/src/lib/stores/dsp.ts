import { writable, derived } from 'svelte/store';
import type { DspState, SpatialMode, EqProfile, BrirRoom, ApiResponse, BypassableStageId, InstalledProfile, HeadphoneSearchResult, AudioFormat } from '@aural/shared';
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
export const profiles = derived(dspState, ($s) => $s?.profiles ?? []);

export const bypassed = derived(dspState, ($s) => $s?.bypassed ?? []);
export const audioFormat = derived(dspState, ($s) => $s?.audioFormat ?? null);

/** Active signal chain stages for the current spatial mode (respects bypass) */
export const activeChain = derived(dspState, ($s): DspStageId[] => {
  if (!$s) return [];
  const bp = new Set($s.bypassed ?? []);
  const chain: DspStageId[] = ['autoeq'];
  if ($s.spatialMode === 'crossfeed' && !bp.has('crossfeed')) chain.push('crossfeed');
  if ($s.spatialMode === 'room' && !bp.has('brir')) chain.push('brir');
  if (!bp.has('loudness')) chain.push('loudness');
  if ($s.mbcEnabled && !bp.has('mbc')) chain.push('mbc');
  chain.push('limiter');
  return chain;
});

/** Full chain including bypassed stages (for showing greyed-out nodes) */
export const fullChain = derived(dspState, ($s): DspStageId[] => {
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
async function apiCall<T = void>(path: string, method = 'POST', body?: unknown): Promise<ApiResponse<T>> {
  try {
    const opts: RequestInit = { method };
    if (body !== undefined) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(`${API_BASE}${path}`, opts);
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

export async function toggleBypass(stageId: BypassableStageId): Promise<void> {
  loading.set(true);
  error.set(null);
  // Optimistic update
  dspState.update((s) => {
    if (!s) return s;
    const current = s.bypassed ?? [];
    const next = current.includes(stageId)
      ? current.filter((id) => id !== stageId)
      : [...current, stageId];
    return { ...s, bypassed: next };
  });
  const res = await apiCall<BypassableStageId[]>(`/bypass/${stageId}`);
  if (!res.ok) {
    error.set(res.error ?? 'Failed to toggle bypass');
    await fetchState();
  }
  loading.set(false);
}

// ─── Headphone Search & Install ──────────────────────────────────

export async function searchHeadphones(query: string): Promise<HeadphoneSearchResult[]> {
  const res = await apiCall<HeadphoneSearchResult[]>(`/headphones/search?q=${encodeURIComponent(query)}`, 'GET');
  return res.ok && res.data ? res.data : [];
}

export async function installHeadphone(source: string, rig: string, model: string): Promise<InstalledProfile | null> {
  loading.set(true);
  error.set(null);
  const res = await apiCall<InstalledProfile>('/headphones/install', 'POST', { source, rig, model });
  if (res.ok && res.data) {
    // Refresh state to pick up new profile
    await fetchState();
    loading.set(false);
    return res.data;
  }
  error.set(res.error ?? 'Failed to install headphone profile');
  loading.set(false);
  return null;
}

export async function removeHeadphone(id: string): Promise<void> {
  loading.set(true);
  error.set(null);
  const res = await apiCall(`/headphones/${id}`, 'DELETE');
  if (res.ok) {
    await fetchState();
  } else {
    error.set(res.error ?? 'Failed to remove headphone profile');
  }
  loading.set(false);
}
