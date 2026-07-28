import type { SpatialMode } from '@aural/shared';

export interface SpatialModeContent {
  name: string;
  tagline: string;
  description: string;
  listenFor: string[];
  characteristics: {
    soundstage: { width: number; depth: number; label: string };
    detail: { score: number; label: string };
    naturalness: { score: number; label: string };
    fatigue: { score: number; label: string };
  };
  icon: string;
  vocabulary: string[];
}

export const spatialModes: Record<SpatialMode, SpatialModeContent> = {
  clean: {
    name: 'Pure Stereo',
    tagline: 'The recording, unaltered',
    icon: '◎',
    vocabulary: ['Imaging', 'Stereo separation', 'Transient', 'Micro-detail', 'Channel isolation'],
    description:
      'No spatial processing. Each ear receives exactly what the mixing engineer intended. Maximum detail retrieval and transient precision.',
    listenFor: [
      'Pinpoint instrument placement in the stereo field',
      'Maximum perceived detail and micro-dynamics',
      "Sound may feel 'inside your head' — this is normal for headphones",
      'Hard-panned instruments appear at the far edges',
    ],
    characteristics: {
      soundstage: { width: 3, depth: 1, label: 'Narrow, in-head' },
      detail: { score: 5, label: 'Maximum retrieval' },
      naturalness: { score: 2, label: 'Headphone-typical' },
      fatigue: { score: 3, label: 'Moderate (sharp imaging)' },
    },
  },
  crossfeed: {
    name: 'Crossfeed',
    tagline: 'Speaker-like intimacy',
    icon: '◉',
    vocabulary: ['Crossfeed', 'Externalization', 'Inter-aural crosstalk', 'Intimacy'],
    description:
      'bs2b crossfeed blends a touch of each channel into the other, mimicking how speakers naturally mix in a room. The Jan Meier preset (700 Hz, 4.5 dB) is tuned for natural vocal presence.',
    listenFor: [
      'The vocalist moves from inside your head to slightly in front',
      'Instruments gain a sense of physical distance',
      "Bass becomes slightly warmer and more 'present'",
      'Hard-panned tracks feel less extreme, more cohesive',
    ],
    characteristics: {
      soundstage: { width: 4, depth: 3, label: 'Intimate, forward' },
      detail: { score: 4, label: 'Slightly smoothed' },
      naturalness: { score: 4, label: 'Speaker-like' },
      fatigue: { score: 2, label: 'Reduced' },
    },
  },
  room: {
    name: 'Room Simulation',
    tagline: 'A seat in the control room',
    icon: '◈',
    vocabulary: ['BRIR', 'Early reflections', 'RT60', 'Externalization', 'Convolution'],
    description:
      'ASH Binaural Room Impulse Response places you in a real, measured acoustic space. True stereo convolution creates authentic reflections, distance cues, and room ambience.',
    listenFor: [
      'A genuine sense of being IN a room — reflections, air, space',
      'Instruments feel distributed in 3D space around you',
      'Reverb tail adds air but may slightly veil fast transients',
      'Close your eyes — can you sense the walls of the room?',
    ],
    characteristics: {
      soundstage: { width: 5, depth: 5, label: 'Holographic, 3D' },
      detail: { score: 3, label: 'Traded for space' },
      naturalness: { score: 5, label: 'Most realistic' },
      fatigue: { score: 1, label: 'Very low (immersive)' },
    },
  },
};
