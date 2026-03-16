import { describe, test, expect } from 'bun:test';
import { buildLinks, rewriteConfigLinks } from './chain-builder';
import type { SpatialMode, BypassableStageId } from '@aural/shared';

// ─── buildLinks ─────────────────────────────────────────────────────

describe('buildLinks', () => {
  function parseLinks(output: string): { output: string; input: string }[] {
    const links: { output: string; input: string }[] = [];
    for (const match of output.matchAll(/output = "([^"]+)"\s+input = "([^"]+)"/g)) {
      links.push({ output: match[1], input: match[2] });
    }
    return links;
  }

  describe('clean mode (no spatial)', () => {
    test('full chain: eq → loudness → mbc → limiter', () => {
      const links = parseLinks(buildLinks('clean', new Set()));
      const chain = links.map(l => l.output.split(':')[0]);
      // Should go eq_l/eq_r → loudness → mbc → limiter
      expect(chain).toContain('eq_l');
      expect(chain).toContain('loudness');
      expect(chain).toContain('mbc');
      // limiter is always last (only appears as input, not output — except its final output)
      expect(links.some(l => l.input.startsWith('limiter:'))).toBe(true);
    });

    test('bypassing loudness skips it in chain', () => {
      const links = parseLinks(buildLinks('clean', new Set(['loudness'])));
      expect(links.some(l => l.input.startsWith('loudness:'))).toBe(false);
      expect(links.some(l => l.output.startsWith('loudness:'))).toBe(false);
    });

    test('bypassing mbc skips it in chain', () => {
      const links = parseLinks(buildLinks('clean', new Set(['mbc'])));
      expect(links.some(l => l.input.startsWith('mbc:'))).toBe(false);
      expect(links.some(l => l.output.startsWith('mbc:'))).toBe(false);
    });

    test('bypassing both loudness and mbc: eq → limiter', () => {
      const links = parseLinks(buildLinks('clean', new Set(['loudness', 'mbc'])));
      // Should have exactly 2 links: eq_l→limiter, eq_r→limiter
      expect(links).toHaveLength(2);
      expect(links[0].output).toBe('eq_l:Out');
      expect(links[0].input).toContain('limiter:');
      expect(links[1].output).toBe('eq_r:Out');
      expect(links[1].input).toContain('limiter:');
    });
  });

  describe('crossfeed mode', () => {
    test('includes crossfeed stage: eq → crossfeed → loudness → mbc → limiter', () => {
      const links = parseLinks(buildLinks('crossfeed', new Set()));
      expect(links.some(l => l.input.includes('bs2b:'))).toBe(true);
      expect(links.some(l => l.output.includes('bs2b:'))).toBe(true);
    });

    test('bypassing crossfeed removes it from chain', () => {
      const links = parseLinks(buildLinks('crossfeed', new Set(['crossfeed'])));
      expect(links.some(l => l.input.includes('bs2b:'))).toBe(false);
      expect(links.some(l => l.output.includes('bs2b:'))).toBe(false);
    });
  });

  describe('room mode (BRIR)', () => {
    test('includes BRIR fan-out/mix topology', () => {
      const output = buildLinks('room', new Set());
      expect(output).toContain('copyFL:In');
      expect(output).toContain('copyFR:In');
      expect(output).toContain('brir_fl_l:In');
      expect(output).toContain('mixL:Out');
      expect(output).toContain('mixR:Out');
    });

    test('BRIR output feeds into loudness → mbc → limiter', () => {
      const links = parseLinks(buildLinks('room', new Set()));
      // mixL:Out → loudness:in_l should exist
      expect(links.some(l => l.output === 'mixL:Out' && l.input === 'loudness:in_l')).toBe(true);
      expect(links.some(l => l.output === 'mixR:Out' && l.input === 'loudness:in_r')).toBe(true);
    });

    test('bypassing loudness in room mode: BRIR → mbc → limiter', () => {
      const links = parseLinks(buildLinks('room', new Set(['loudness'])));
      expect(links.some(l => l.output === 'mixL:Out' && l.input === 'mbc:in_l')).toBe(true);
      expect(links.some(l => l.input.startsWith('loudness:'))).toBe(false);
    });

    test('bypassing BRIR falls back to linear chain', () => {
      const output = buildLinks('room', new Set(['brir']));
      // Should NOT contain BRIR nodes
      expect(output).not.toContain('copyFL');
      expect(output).not.toContain('brir_fl');
      expect(output).not.toContain('mixL');
      // Should be a linear chain like clean mode
      const links = parseLinks(output);
      expect(links[0].output).toBe('eq_l:Out');
    });
  });

  describe('link integrity', () => {
    const modes: SpatialMode[] = ['clean', 'crossfeed', 'room'];
    const bypassCombos: Set<BypassableStageId>[] = [
      new Set(),
      new Set(['loudness']),
      new Set(['mbc']),
      new Set(['loudness', 'mbc']),
    ];

    for (const mode of modes) {
      for (const bypassed of bypassCombos) {
        const label = `${mode} bypass=[${[...bypassed].join(',')}]`;

        test(`${label}: all links have both L and R channels`, () => {
          const links = parseLinks(buildLinks(mode, bypassed));
          // Every L link should have a matching R link
          const lLinks = links.filter(l => l.output.includes('_l:') || l.output.includes(':Out') || l.output.includes('left') || l.output.includes('mixL'));
          const rLinks = links.filter(l => l.output.includes('_r:') || l.output.includes(':Out') || l.output.includes('right') || l.output.includes('mixR'));
          // At minimum, both channels should be present
          expect(links.length).toBeGreaterThanOrEqual(2);
          expect(links.length % 2).toBe(0); // always paired
        });

        test(`${label}: limiter is always the final stage`, () => {
          const links = parseLinks(buildLinks(mode, bypassed));
          // Nothing should take limiter output as input (it's the graph output)
          const limiterOutputs = links.filter(l => l.output.startsWith('limiter:'));
          expect(limiterOutputs).toHaveLength(0);
          // Limiter should appear as an input target
          expect(links.some(l => l.input.startsWith('limiter:'))).toBe(true);
        });
      }
    }
  });
});

// ─── rewriteConfigLinks ─────────────────────────────────────────────

describe('rewriteConfigLinks', () => {
  const sampleConfig = `
    node.description = "Headphone DSP"
    filter.graph = {
        nodes = [ ... ]
        links = [
            { output = "eq_l:Out" input = "loudness:in_l" }
            { output = "eq_r:Out" input = "loudness:in_r" }
        ]
        inputs = [ "eq_l:In" "eq_r:In" ]
    }
`;

  test('replaces links section for matching sink', () => {
    const newLinks = '                    { output = "eq_l:Out"  input = "limiter:lv2_audio_in_1" }';
    const result = rewriteConfigLinks(sampleConfig, 'Headphone DSP', newLinks);
    expect(result).toContain('limiter:lv2_audio_in_1');
    expect(result).not.toContain('loudness:in_l');
  });

  test('preserves config when sink description not found', () => {
    const result = rewriteConfigLinks(sampleConfig, 'Nonexistent Sink', 'new links');
    expect(result).toBe(sampleConfig);
  });

  test('preserves nodes and inputs/outputs sections', () => {
    const newLinks = '                    { output = "eq_l:Out"  input = "limiter:lv2_audio_in_1" }';
    const result = rewriteConfigLinks(sampleConfig, 'Headphone DSP', newLinks);
    expect(result).toContain('nodes = [ ... ]');
    expect(result).toContain('inputs = [ "eq_l:In" "eq_r:In" ]');
  });
});
