export interface VocabTerm {
  term: string;
  definition: string;
  category: 'spatial' | 'tonal' | 'dynamics' | 'technical';
}

export const vocabulary: VocabTerm[] = [
  {
    term: 'Soundstage',
    definition: 'The perceived spatial extent of the sound. A wide soundstage makes instruments feel spread far apart; a narrow one places everything close together.',
    category: 'spatial',
  },
  {
    term: 'Imaging',
    definition: 'How precisely you can locate individual instruments in space. Good imaging means each instrument has a clear, stable position.',
    category: 'spatial',
  },
  {
    term: 'Externalization',
    definition: 'The perception that sound originates outside your head rather than between your ears. Speakers externalize naturally; headphones require processing to achieve this.',
    category: 'spatial',
  },
  {
    term: 'Timbre',
    definition: "The tonal 'color' of a sound. A violin and a flute playing the same note have different timbre — it's what makes instruments sound unique.",
    category: 'tonal',
  },
  {
    term: 'Tonality',
    definition: 'The overall frequency balance of a headphone or system. Warm tonality emphasizes bass; bright tonality emphasizes treble.',
    category: 'tonal',
  },
  {
    term: 'Warmth',
    definition: "Emphasis in the lower midrange (200-500 Hz). The 'body' of instruments and vocals. Too much warmth sounds muddy; too little sounds thin.",
    category: 'tonal',
  },
  {
    term: 'Sibilance',
    definition: "Harsh 'sss' and 'ttt' sounds in vocals, caused by peaks in the 6-8 kHz region. A common source of listening fatigue.",
    category: 'tonal',
  },
  {
    term: 'Transient Response',
    definition: 'How quickly and accurately the system reproduces sudden sounds — snare hits, plucked strings, consonants. Fast transients sound "snappy" and immediate.',
    category: 'dynamics',
  },
  {
    term: 'Dynamic Range',
    definition: 'The difference between the quietest and loudest parts of the music. More dynamic range means more contrast and expressiveness.',
    category: 'dynamics',
  },
  {
    term: 'Micro-dynamics',
    definition: 'Subtle volume variations within a performance — the difference between a gentle and a firm bow stroke. Reveals the expressiveness of a musician.',
    category: 'dynamics',
  },
  {
    term: 'Frequency Response',
    definition: 'A measurement of how loud each frequency is reproduced. A flat frequency response means all frequencies are at equal volume — the baseline for accuracy.',
    category: 'technical',
  },
  {
    term: 'Convolution',
    definition: 'A mathematical process that applies the acoustic characteristics of one system (like a room or an EQ curve) to an audio signal. The core of BRIR and AutoEQ processing.',
    category: 'technical',
  },
  {
    term: 'Impulse Response',
    definition: 'A recording of how a system (room, headphone, speaker) responds to a perfect instantaneous click. Contains all the information about that system\'s acoustic character.',
    category: 'technical',
  },
  {
    term: 'Crossfeed',
    definition: 'Mixing a portion of the left channel into the right (and vice versa) to simulate how speakers naturally blend in a room. Reduces the hyper-separation of headphones.',
    category: 'spatial',
  },
  {
    term: 'RT60',
    definition: 'The time it takes for sound in a room to decay by 60 dB after the source stops. Short RT60 = dry, controlled room. Long RT60 = reverberant, spacious room.',
    category: 'spatial',
  },
  {
    term: 'Listening Fatigue',
    definition: 'The gradual discomfort or tiredness from extended listening. Caused by harsh peaks, excessive brightness, or poor spatial processing. The enemy of long sessions.',
    category: 'dynamics',
  },
];

export function getTermsByCategory(category: VocabTerm['category']): VocabTerm[] {
  return vocabulary.filter((t) => t.category === category);
}

export function findTerm(term: string): VocabTerm | undefined {
  return vocabulary.find((t) => t.term.toLowerCase() === term.toLowerCase());
}
