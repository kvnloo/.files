import type { DspStageId } from '@aural/shared';

export interface DspStageContent {
  name: string;
  shortName: string;
  whatItDoes: string;
  whyItMatters: string;
  listenFor: string[];
  vocabulary: string[];
  tradeoff: { gain: string; sacrifice: string };
  color: string;
}

export const dspStages: Record<DspStageId, DspStageContent> = {
  autoeq: {
    name: 'AutoEQ Convolver',
    shortName: 'AutoEQ',
    whatItDoes: 'Applies a minimum-phase frequency correction filter to flatten the headphone\'s natural frequency response toward a target curve.',
    whyItMatters: 'Every headphone colors the sound differently. AutoEQ removes those colorations so you hear the music, not the headphone\'s personality.',
    listenFor: [
      'More balanced tonality — no frequency range dominates',
      'Vocals and instruments at their natural volume relative to each other',
      'Peaks and dips in the original headphone response are smoothed out',
    ],
    vocabulary: ['frequency response', 'target curve', 'timbre', 'tonality', 'coloration'],
    tradeoff: {
      gain: 'Accurate tonality matching the target curve',
      sacrifice: 'Slight reduction in the headphone\'s unique character',
    },
    color: 'var(--color-stage-eq)',
  },
  crossfeed: {
    name: 'bs2b Crossfeed',
    shortName: 'Crossfeed',
    whatItDoes: 'Blends a small amount of the left channel into the right (and vice versa), with a low-pass filter and subtle delay — mimicking how speakers sound in a room.',
    whyItMatters: 'Headphones present an unnatural "super-stereo" image. In real life, both ears hear both speakers. Crossfeed restores that natural blending.',
    listenFor: [
      'Vocalist moves from inside your head to slightly in front',
      'Hard-panned instruments feel less extreme',
      'Subtle warmth added to the low end',
      'Reduced "ping-pong" effect on older stereo recordings',
    ],
    vocabulary: ['soundstage', 'imaging', 'crossfeed', 'inter-aural crosstalk', 'externalization'],
    tradeoff: {
      gain: 'Natural, speaker-like spatial presentation',
      sacrifice: 'Slight reduction in stereo separation and extreme detail',
    },
    color: 'var(--color-stage-crossfeed)',
  },
  brir: {
    name: 'BRIR Room Simulation',
    shortName: 'Room',
    whatItDoes: 'Convolves the audio with a measured Binaural Room Impulse Response — the acoustic fingerprint of a real room captured with a dummy head.',
    whyItMatters: 'This is the most immersive spatial processing. It doesn\'t just simulate speakers — it simulates the room those speakers are in, complete with reflections and reverb.',
    listenFor: [
      'A genuine sense of three-dimensional space',
      'Early reflections creating a sense of room size',
      'Instruments at varying distances, not all on the same plane',
      'A reverb tail that adds "air" to the recording',
    ],
    vocabulary: ['BRIR', 'impulse response', 'convolution', 'reverb', 'RT60', 'early reflections', 'externalization'],
    tradeoff: {
      gain: 'Most realistic spatial experience, true 3D imaging',
      sacrifice: 'Some transient smearing, slightly veiled micro-detail',
    },
    color: 'var(--color-stage-brir)',
  },
  loudness: {
    name: 'Loudness Compensator',
    shortName: 'Loudness',
    whatItDoes: 'Applies ISO 226:2003 equal-loudness contours to compensate for the human ear\'s frequency sensitivity changing at different volumes.',
    whyItMatters: 'At low volumes, your ears are less sensitive to bass and treble. Loudness compensation gently boosts those ranges so music sounds balanced even when listening quietly.',
    listenFor: [
      'Bass feels present even at low listening volumes',
      'Treble detail doesn\'t disappear when you turn down the volume',
      'Music retains its "fullness" without cranking the volume',
    ],
    vocabulary: ['equal-loudness contours', 'Fletcher-Munson', 'phon', 'loudness compensation'],
    tradeoff: {
      gain: 'Balanced frequency perception at any volume',
      sacrifice: 'Slight coloration vs flat response at reference levels',
    },
    color: 'var(--color-stage-loudness)',
  },
  mbc: {
    name: 'Multiband Compressor',
    shortName: 'MBC',
    whatItDoes: 'Splits the audio into 8 frequency bands (Bark scale) and applies independent gentle compression to each — taming peaks in some bands while lifting quiet detail in others.',
    whyItMatters: 'Reduces listening fatigue by smoothing harsh peaks without affecting the whole signal. Like an intelligent volume control for each frequency region.',
    listenFor: [
      'Harsh sibilance ("sss" sounds) becomes smoother',
      'Bass transients feel more controlled, less boomy',
      'Quiet ambient details become slightly more audible',
      'Long listening sessions feel less tiring',
    ],
    vocabulary: ['multiband compression', 'Bark scale', 'threshold', 'ratio', 'attack', 'release', 'sibilance', 'fatigue'],
    tradeoff: {
      gain: 'Reduced fatigue, smoother dynamics, revealed detail',
      sacrifice: 'Slightly reduced dynamic range and transient impact',
    },
    color: 'var(--color-stage-mbc)',
  },
  limiter: {
    name: 'Safety Limiter',
    shortName: 'Limiter',
    whatItDoes: 'Prevents the signal from exceeding -0.3 dBFS, protecting your hearing and your headphones from sudden volume spikes.',
    whyItMatters: 'A safety net. When switching profiles or encountering poorly mastered tracks, the limiter catches dangerous peaks before they reach your ears.',
    listenFor: [
      'You shouldn\'t hear this working — that means it\'s doing its job',
      'On very loud passages, the absolute loudest peaks are gently caught',
      'No sudden painful spikes when switching between sources',
    ],
    vocabulary: ['limiter', 'ceiling', 'dBFS', 'true peak', 'clipping'],
    tradeoff: {
      gain: 'Hearing protection, consistent maximum level',
      sacrifice: 'Negligible — only affects extreme peaks above threshold',
    },
    color: 'var(--color-stage-limiter)',
  },
};
