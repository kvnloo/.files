import type { DspStageId } from '@aural/shared';

export interface AudioPluginParam {
  name: string;
  value: string;
  explanation: string;
}

export interface AudioPlugin {
  id: DspStageId;
  pluginName: string;
  pluginType: 'lv2' | 'ladspa' | 'builtin';
  pluginUri?: string;
  developer: string;
  whyChosen: string;
  keyParameters: AudioPluginParam[];
  technicalNote?: string;
}

export interface AudioStackInfo {
  server: { name: 'PipeWire'; description: string; whyChosen: string };
  sinkArchitecture: string;
  plugins: Record<DspStageId, AudioPlugin>;
}

export const audioStack: AudioStackInfo = {
  server: {
    name: 'PipeWire',
    description: 'Low-level multimedia framework that unifies audio (and video) under one graph-based processing engine, replacing both PulseAudio and JACK.',
    whyChosen: 'PipeWire\'s native filter-chain module runs DSP in-process with zero additional IPC latency. It sample-rate-matches automatically — the same config works at 44.1k, 48k, 96k, and 384k without resampling. No separate plugin host process, no extra buffering. The filter graph is part of the audio server itself.',
  },

  sinkArchitecture: 'Three virtual sinks (clean / crossfeed / room) run as independent PipeWire filter chains. Switching spatial mode changes the default sink via wpctl — the transition is instantaneous because all three chains are always loaded and processing. This avoids the latency spike of tearing down and rebuilding a filter graph on every mode switch, enabling true real-time A/B/C comparison.',

  plugins: {
    autoeq: {
      id: 'autoeq',
      pluginName: 'PipeWire Convolver',
      pluginType: 'builtin',
      developer: 'PipeWire / AutoEQ Project',
      whyChosen: 'Convolution with minimum-phase FIR filters preserves the headphone\'s original phase response while correcting magnitude. Parametric EQ would need 10+ bands per headphone and still leave residual ripple. The AutoEQ project provides pre-computed corrections for thousands of headphones, matched to perceptual target curves. Five sample rate variants (44.1k–384k) ensure native processing at any rate.',
      keyParameters: [
        { name: 'Block size', value: '256 samples', explanation: 'Processing granularity — small enough for low latency, large enough for efficient FFT' },
        { name: 'Tail size', value: '16,384 samples', explanation: 'FIR filter length — captures the full correction impulse without truncation artifacts' },
        { name: 'Gain', value: '1.0 (unity)', explanation: 'No additional gain applied — the FIR itself contains the correction curve' },
        { name: 'Sample rates', value: '44.1k / 48k / 96k / 192k / 384k', explanation: 'Rate-matched FIR files — PipeWire selects the correct one automatically' },
      ],
      technicalNote: 'Each channel (L/R) has its own convolver instance. The FIR files are generated from AutoEQ\'s compensation data using minimum-phase reconstruction, which concentrates the filter\'s energy at the start of the impulse — minimizing pre-ringing that plagues linear-phase alternatives.',
    },

    crossfeed: {
      id: 'crossfeed',
      pluginName: 'bs2b',
      pluginType: 'ladspa',
      pluginUri: 'bs2b',
      developer: 'Boris Mikhaylov',
      whyChosen: 'The Bauer stereophonic-to-binaural DSP is the gold standard for headphone crossfeed. It uses a simple but psychoacoustically accurate model: a low-pass filtered blend with inter-aural time delay. The Jan Meier 700 Hz / 4.5 dB preset strikes the best balance between spatial naturalness and stereo separation — aggressive enough to externalize the image, gentle enough to preserve detail.',
      keyParameters: [
        { name: 'Cutoff frequency', value: '700 Hz', explanation: 'Low-pass crossover for the blended signal — frequencies below this cross between channels' },
        { name: 'Feeding level', value: '4.5 dB', explanation: 'How much of the opposite channel is mixed in — the Jan Meier "natural" preset' },
      ],
      technicalNote: 'bs2b applies a 1st-order low-pass shelving filter and a ~300μs inter-aural delay, mimicking the acoustic shadow of the human head. Unlike HRTF-based crossfeed, it doesn\'t try to model pinnae — it just restores the basic crosstalk that speakers in a room naturally produce.',
    },

    brir: {
      id: 'brir',
      pluginName: 'PipeWire Convolver (True Stereo)',
      pluginType: 'builtin',
      developer: 'PipeWire / Audio Spatialisation for Headphones (ASH)',
      whyChosen: 'True stereo BRIR convolution uses 4 convolvers in a fan-out topology: each source channel (FL, FR) is convolved with both the ipsilateral and contralateral impulse responses, then summed per ear. This captures the full spatial signature of a real room — early reflections, late reverb, and the listener\'s head-related transfer function — in a single convolution pass per source.',
      keyParameters: [
        { name: 'Tail size', value: '65,536 samples', explanation: 'Long impulse response captures the full room reverb tail (RT60)' },
        { name: 'Gain', value: '0.5 per convolver', explanation: 'Four convolvers sum to unity — prevents clipping at the mix stage' },
        { name: 'Topology', value: '4-convolver fan-out', explanation: 'FL→L + FL→R + FR→L + FR→R, mixed to stereo output' },
        { name: 'Room (default)', value: 'R02 — WDR Control Room', explanation: 'Professional broadcast monitoring room with tight, accurate acoustics (RT60 0.235s)' },
      ],
      technicalNote: 'The ASH dataset was captured using a Neumann KU 100 dummy head in calibrated rooms. The "true stereo" approach (4 IRs per configuration) is critical — simple stereo convolution would collapse the spatial image because it ignores the cross-ear path. The copy→convolve→mix topology handles this correctly within PipeWire\'s native graph.',
    },

    loudness: {
      id: 'loudness',
      pluginName: 'LSP Loud Comp Stereo',
      pluginType: 'lv2',
      pluginUri: 'http://lsp-plug.in/plugins/lv2/loud_comp_stereo',
      developer: 'Linux Studio Plugins (Vladimir Sadovnikov)',
      whyChosen: 'The LSP loudness compensator implements ISO 226:2003 equal-loudness contours with real-time FFT analysis. At low listening volumes, human hearing loses sensitivity to bass and treble (the Fletcher-Munson effect). This plugin dynamically adjusts the frequency response to maintain perceived tonal balance regardless of volume — essential for late-night or quiet listening.',
      keyParameters: [
        { name: 'Standard', value: 'Fletcher-Munson', explanation: 'Classic equal-loudness contour model — well-validated for headphone listening' },
        { name: 'FFT size', value: '4096 samples', explanation: 'Analysis window for frequency-dependent gain computation' },
        { name: 'Input gain', value: '1.0 (unity)', explanation: 'No pre-amplification — compensation is purely subtractive/additive based on contours' },
        { name: 'Hard clip', value: 'Off', explanation: 'Relies on downstream limiter for peak protection instead' },
      ],
      technicalNote: 'The plugin uses the ISO 226:2003 revision of the original Fletcher-Munson curves, which corrected significant errors in the bass region of the 1933 data. The FFT-based approach allows frequency-dependent gain with minimal phase distortion compared to parametric EQ approximations.',
    },

    mbc: {
      id: 'mbc',
      pluginName: 'LSP MB Compressor Stereo',
      pluginType: 'lv2',
      pluginUri: 'http://lsp-plug.in/plugins/lv2/mb_compressor_stereo',
      developer: 'Linux Studio Plugins (Vladimir Sadovnikov)',
      whyChosen: 'The LSP multiband compressor splits the signal into 8 bands aligned to the Bark perceptual scale — each band maps to a critical band of human hearing. This means compression acts where your ears are actually sensitive, not at arbitrary frequency boundaries. The mix of upward compression (bands 0, 6, 7) and downward compression (bands 1–5) simultaneously tames harsh peaks and lifts buried detail.',
      keyParameters: [
        { name: 'Bands', value: '8 (Bark scale)', explanation: '20–100, 100–200, 200–400, 400–800, 800–1.6k, 1.6k–3.2k, 3.2k–8k, 8k–20k Hz' },
        { name: 'Mode mix', value: 'Upward + Downward', explanation: 'Bands 0,6,7 lift quiet detail; bands 1–5 tame fatiguing peaks' },
        { name: 'Ratios', value: '1.04–1.85:1', explanation: 'Gentle ratios throughout — this is fatigue reduction, not mastering compression' },
        { name: 'Attack range', value: '5–100 ms', explanation: 'Fast in treble (transient-aware), slow in bass (preserves punch)' },
      ],
      technicalNote: 'The Bark scale alignment is key: critical bands represent frequency regions the cochlea processes as a unit. Compressing within these bands means the dynamics processing matches human perception — a 3 dB reduction in the 1.6–3.2 kHz presence band has a much larger perceptual effect than the same reduction at 200 Hz.',
    },

    limiter: {
      id: 'limiter',
      pluginName: 'ZaMaximX2',
      pluginType: 'lv2',
      pluginUri: 'urn:zamaudio:ZaMaximX2',
      developer: 'Zam Audio (Damien Zammit)',
      whyChosen: 'ZaMaximX2 is a look-ahead brick-wall stereo limiter. It catches any peak that would exceed the ceiling — essential as a safety net at the end of a complex DSP chain where multiple stages of gain could compound. The -0.3 dBFS ceiling leaves headroom for inter-sample peaks that would cause clipping in the DAC\'s reconstruction filter.',
      keyParameters: [
        { name: 'Ceiling', value: '-0.3 dBFS', explanation: 'Maximum output level — 0.3 dB below full scale to prevent inter-sample clipping' },
        { name: 'Threshold', value: '-0.3 dBFS', explanation: 'Matched to ceiling — limiter engages the moment signal reaches the ceiling' },
        { name: 'Release', value: '25 ms', explanation: 'Fast release minimizes audible gain reduction artifacts' },
      ],
      technicalNote: 'The look-ahead buffer (typically ~1ms) allows the limiter to see peaks before they arrive and apply gain reduction smoothly rather than hard-clipping. At -0.3 dBFS, the ceiling accounts for the worst-case inter-sample peak overshoot (+0.3 dB for a full-scale sine between samples), ensuring the DAC never clips.',
    },
  },
};
