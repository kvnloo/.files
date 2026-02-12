// ─── Spatial Modes ────────────────────────────────────────────────
export type SpatialMode = 'clean' | 'crossfeed' | 'room';

export const SPATIAL_SINK_NAMES: Record<SpatialMode, string> = {
  clean: 'effect_input.headphone_dsp',
  crossfeed: 'effect_input.headphone_dsp_crossfeed',
  room: 'effect_input.headphone_dsp_room',
};

// ─── EQ Profiles ─────────────────────────────────────────────────
export type EqProfile = 'monarch' | 'hd800s';

export interface EqProfileInfo {
  id: EqProfile;
  name: string;
  fullName: string;
  target: string;
  character: string;
  filePattern: (rate: number) => string;
}

export const EQ_PROFILES: Record<EqProfile, EqProfileInfo> = {
  monarch: {
    id: 'monarch',
    name: 'Monarch MKII',
    fullName: 'ThieAudio Monarch MKII',
    target: 'IEF Preference 2025 + Harman IE 2019',
    character: 'Rich bass, smooth mids, intimate presentation',
    filePattern: (rate) => `ThieAudio Monarch MKII minimum phase ${rate}Hz.wav`,
  },
  hd800s: {
    id: 'hd800s',
    name: 'HD800S',
    fullName: 'Sennheiser HD800S',
    target: 'IEF Preference 2025 + Harman OE 2018',
    character: 'Wide soundstage, analytical detail, bright treble',
    filePattern: (rate) => `Sennheiser HD800 minimum phase ${rate} Hz.wav`,
  },
};

export const SAMPLE_RATES = [44100, 48000, 96000, 192000, 384000] as const;
export type SampleRate = (typeof SAMPLE_RATES)[number];

// ─── BRIR Rooms ──────────────────────────────────────────────────
export type BrirRoom = 'R02' | 'R32';

export interface BrirRoomInfo {
  id: BrirRoom;
  name: string;
  description: string;
  rt60: string;
  filename: string;
}

export const BRIR_ROOMS: Record<BrirRoom, BrirRoomInfo> = {
  R02: {
    id: 'R02',
    name: 'WDR Broadcast Control Room',
    description: 'Professional broadcast monitoring room. Tight, accurate acoustics.',
    rt60: '0.235s',
    filename: 'BRIR_R02_C1_True_Stereo.wav',
  },
  R32: {
    id: 'R32',
    name: 'ASH Listening Room',
    description: 'Residential listening room. More spacious, relaxed ambience.',
    rt60: '0.35s',
    filename: 'BRIR_R32_C1_True_Stereo.wav',
  },
};

// ─── MBC (Multiband Compressor) ──────────────────────────────────
export interface MbcBand {
  index: number;
  freqLow: number;
  freqHigh: number;
  label: string;
  mode: 'upward' | 'downward';
  purpose: string;
  enabled: boolean;       // ce_N
  threshold: number;      // al_N (linear gain)
  ratio: number;          // cr_N
  attack: number;         // at_N (ms)
  release: number;        // rt_N (ms)
  knee: number;           // kn_N (linear)
  makeup: number;         // mk_N (linear gain)
}

export const MBC_BAND_DEFAULTS: MbcBand[] = [
  { index: 0, freqLow: 20,   freqHigh: 100,  label: 'Sub Bass',    mode: 'upward',   purpose: 'Gentle sub-bass lift',      enabled: true, threshold: 0.010, ratio: 1.15, attack: 100, release: 300, knee: 1.000, makeup: 1.0 },
  { index: 1, freqLow: 100,  freqHigh: 200,  label: 'Bass',        mode: 'downward', purpose: 'Tame bass boom',            enabled: true, threshold: 0.100, ratio: 1.85, attack: 60,  release: 200, knee: 0.251, makeup: 1.0 },
  { index: 2, freqLow: 200,  freqHigh: 400,  label: 'Low Mid',     mode: 'downward', purpose: 'Reduce mud',                enabled: true, threshold: 0.126, ratio: 1.65, attack: 40,  release: 160, knee: 0.398, makeup: 1.0 },
  { index: 3, freqLow: 400,  freqHigh: 800,  label: 'Mid',         mode: 'downward', purpose: 'Control honk',              enabled: true, threshold: 0.158, ratio: 1.55, attack: 30,  release: 140, knee: 0.501, makeup: 1.0 },
  { index: 4, freqLow: 800,  freqHigh: 1600, label: 'Upper Mid',   mode: 'downward', purpose: 'Ease presence fatigue',     enabled: true, threshold: 0.178, ratio: 1.45, attack: 25,  release: 120, knee: 0.631, makeup: 1.0 },
  { index: 5, freqLow: 1600, freqHigh: 3200, label: 'Presence',    mode: 'downward', purpose: 'Reduce harshness',          enabled: true, threshold: 0.200, ratio: 1.35, attack: 20,  release: 100, knee: 0.708, makeup: 1.0 },
  { index: 6, freqLow: 3200, freqHigh: 8000, label: 'Brilliance',  mode: 'upward',   purpose: 'Recover air/detail',        enabled: true, threshold: 0.040, ratio: 1.06, attack: 10,  release: 80,  knee: 0.631, makeup: 1.0 },
  { index: 7, freqLow: 8000, freqHigh: 20000,label: 'Air',         mode: 'upward',   purpose: 'Subtle sparkle',            enabled: true, threshold: 0.020, ratio: 1.04, attack: 5,   release: 60,  knee: 1.000, makeup: 1.0 },
];

// ─── Loudness Compensator ────────────────────────────────────────
export interface LoudnessState {
  enabled: boolean;
  standard: number;   // 0=ISO226:2003, 1=Fletcher-Munson
  fft: number;        // FFT window size index
  volume: number;     // dB
  input: number;      // linear gain
  hclip: boolean;
}

// ─── Limiter ─────────────────────────────────────────────────────
export interface LimiterState {
  ceiling: number;    // dB
  threshold: number;  // dB
  release: number;    // ms
}

// ─── Full DSP State ──────────────────────────────────────────────
export interface DspState {
  spatialMode: SpatialMode;
  eqProfile: EqProfile;
  brirRoom: BrirRoom;
  mbcEnabled: boolean;
  mbcBands: MbcBand[];
  loudness: LoudnessState;
  limiter: LimiterState;
}

// ─── Signal Chain Node ───────────────────────────────────────────
export type DspStageId = 'autoeq' | 'crossfeed' | 'brir' | 'loudness' | 'mbc' | 'limiter';

export interface DspStage {
  id: DspStageId;
  name: string;
  shortName: string;
  active: boolean;
  description: string;
}

// ─── API Contracts ───────────────────────────────────────────────
export interface ApiResponse<T = void> {
  ok: boolean;
  data?: T;
  error?: string;
}

export interface StateResponse extends ApiResponse<DspState> {}

// ─── WebSocket Messages ──────────────────────────────────────────
export type WsSpectrumData = {
  type: 'spectrum';
  bars: number[];  // 0-1 normalized amplitude per bar
};

export type WsStateChange = {
  type: 'state';
  state: Partial<DspState>;
};

export type WsMessage = WsSpectrumData | WsStateChange;
