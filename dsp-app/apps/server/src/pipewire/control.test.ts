import { describe, test, expect, spyOn, beforeEach } from 'bun:test';
import type { SpatialMode, BypassableStageId } from '@aural/shared';
import * as control from './control';

const mockRun = spyOn(control, 'run');

beforeEach(() => {
  mockRun.mockReset();
  mockRun.mockResolvedValue({ stdout: '', stderr: '', exitCode: 0 });
});

// ─── Shared realistic pw-cli ls Node output ────────────────────────
// All three DSP sinks present simultaneously, as in a real PipeWire session.
// Order intentionally puts crossfeed first so prefix bugs are exercisable.
const PW_CLI_ALL_NODES = [
  '\tid 55, type PipeWire:Interface:Node/3',
  '\t\tobject.serial = "55"',
  '\t\tnode.name = "effect_input.headphone_dsp_crossfeed"',
  '\t\tnode.description = "Headphone DSP + Crossfeed"',
  '\tid 42, type PipeWire:Interface:Node/3',
  '\t\tobject.serial = "42"',
  '\t\tnode.name = "effect_input.headphone_dsp"',
  '\t\tnode.description = "Headphone DSP"',
  '\tid 68, type PipeWire:Interface:Node/3',
  '\t\tobject.serial = "68"',
  '\t\tnode.name = "effect_input.headphone_dsp_room"',
  '\t\tnode.description = "Headphone DSP + Room"',
].join('\n');

// ─── getAudioFormat ─────────────────────────────────────────────────

describe('getAudioFormat', () => {
  const PW_LINK_ROOM = [
    'effect_output.headphone_dsp_room:output_FL',
    '  |-> alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink:playback_FL',
    'effect_output.headphone_dsp_room:output_FR',
    '  |-> alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink:playback_FR',
  ].join('\n');

  function makePwDump(nodeName: string, rate: number, format: string) {
    return JSON.stringify([
      {
        info: {
          props: { 'node.name': nodeName },
          params: { Format: [{ mediaType: 'audio', mediaSubtype: 'raw', format, rate, channels: 2 }] },
        },
      },
    ]);
  }

  test('returns actual DAC rate (44100) not PipeWire default (48000)', async () => {
    // This is the exact bug we fixed: Spotify outputs 44100, the DAC negotiates 44100,
    // but the old code read the static default.clock.rate (48000) from pw-cli info 0.
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_ROOM, stderr: '', exitCode: 0 })  // pw-link
      .mockResolvedValueOnce({                                                     // pw-dump
        stdout: makePwDump('alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink', 44100, 'S32LE'),
        stderr: '', exitCode: 0,
      });

    const fmt = await control.getAudioFormat();
    expect(fmt).toEqual({ sampleRate: 44100, bitDepth: 32, format: 'S32LE' });
  });

  test('returns 48000 when DAC is actually running at 48000', async () => {
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_ROOM, stderr: '', exitCode: 0 })
      .mockResolvedValueOnce({
        stdout: makePwDump('alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink', 48000, 'S32LE'),
        stderr: '', exitCode: 0,
      });

    const fmt = await control.getAudioFormat();
    expect(fmt).toEqual({ sampleRate: 48000, bitDepth: 32, format: 'S32LE' });
  });

  test('returns 96000 for hi-res content', async () => {
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_ROOM, stderr: '', exitCode: 0 })
      .mockResolvedValueOnce({
        stdout: makePwDump('alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink', 96000, 'S32LE'),
        stderr: '', exitCode: 0,
      });

    const fmt = await control.getAudioFormat();
    expect(fmt?.sampleRate).toBe(96000);
  });

  test('parses bit depth from different format strings', async () => {
    for (const [format, expectedBits] of [['S16LE', 16], ['S24LE', 24], ['S32LE', 32]] as const) {
      mockRun
        .mockResolvedValueOnce({ stdout: PW_LINK_ROOM, stderr: '', exitCode: 0 })
        .mockResolvedValueOnce({
          stdout: makePwDump('alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink', 44100, format),
          stderr: '', exitCode: 0,
        });

      const fmt = await control.getAudioFormat();
      expect(fmt?.bitDepth).toBe(expectedBits);
      expect(fmt?.format).toBe(format);
    }
  });

  test('follows DSP output to correct hardware sink (crossfeed mode)', async () => {
    const crossfeedLinks = [
      'effect_output.headphone_dsp_crossfeed:output_FL',
      '  |-> alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink:playback_FL',
    ].join('\n');

    mockRun
      .mockResolvedValueOnce({ stdout: crossfeedLinks, stderr: '', exitCode: 0 })
      .mockResolvedValueOnce({
        stdout: makePwDump('alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink', 44100, 'S32LE'),
        stderr: '', exitCode: 0,
      });

    const fmt = await control.getAudioFormat();
    expect(fmt?.sampleRate).toBe(44100);
  });

  test('follows DSP output to correct hardware sink (clean mode)', async () => {
    const cleanLinks = [
      'effect_output.headphone_dsp:output_FL',
      '  |-> alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink:playback_FL',
    ].join('\n');

    mockRun
      .mockResolvedValueOnce({ stdout: cleanLinks, stderr: '', exitCode: 0 })
      .mockResolvedValueOnce({
        stdout: makePwDump('alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink', 44100, 'S32LE'),
        stderr: '', exitCode: 0,
      });

    const fmt = await control.getAudioFormat();
    expect(fmt?.sampleRate).toBe(44100);
  });

  test('returns null when no DSP output link found', async () => {
    mockRun.mockResolvedValueOnce({ stdout: 'no links here', stderr: '', exitCode: 0 });
    const fmt = await control.getAudioFormat();
    expect(fmt).toBeNull();
  });

  test('returns null when hw sink has no Format params', async () => {
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_ROOM, stderr: '', exitCode: 0 })
      .mockResolvedValueOnce({
        stdout: JSON.stringify([{
          info: {
            props: { 'node.name': 'alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink' },
            params: { Format: [] },
          },
        }]),
        stderr: '', exitCode: 0,
      });

    const fmt = await control.getAudioFormat();
    expect(fmt).toBeNull();
  });

  test('returns null on pw-link failure', async () => {
    mockRun.mockRejectedValueOnce(new Error('pw-link not found'));
    const fmt = await control.getAudioFormat();
    expect(fmt).toBeNull();
  });

  test('returns null on invalid pw-dump JSON', async () => {
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_ROOM, stderr: '', exitCode: 0 })
      .mockResolvedValueOnce({ stdout: 'not json', stderr: '', exitCode: 0 });

    const fmt = await control.getAudioFormat();
    expect(fmt).toBeNull();
  });

  test('handles multiple ALSA sinks in pw-dump, picks the linked one', async () => {
    const dump = JSON.stringify([
      {
        info: {
          props: { 'node.name': 'alsa_output.pci-0000_01_00.1.hdmi-stereo' },
          params: { Format: [{ format: 'S16LE', rate: 48000, channels: 2 }] },
        },
      },
      {
        info: {
          props: { 'node.name': 'alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink' },
          params: { Format: [{ format: 'S32LE', rate: 44100, channels: 2 }] },
        },
      },
    ]);

    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_ROOM, stderr: '', exitCode: 0 })
      .mockResolvedValueOnce({ stdout: dump, stderr: '', exitCode: 0 });

    const fmt = await control.getAudioFormat();
    expect(fmt).toEqual({ sampleRate: 44100, bitDepth: 32, format: 'S32LE' });
  });
});

// ─── setSpatialMode ─────────────────────────────────────────────────

describe('setSpatialMode', () => {
  // Realistic pw-link + pw-dump data for getAudioFormat (DAC at 44100)
  const PW_LINK_OUTPUT = [
    'effect_output.headphone_dsp:output_FL',
    '  |-> alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink:playback_FL',
  ].join('\n');

  const PW_DUMP_44100 = JSON.stringify([{
    info: {
      props: { 'node.name': 'alsa_output.usb-Topping_DX5-00.HiFi__Headphones__sink' },
      params: { Format: [{ format: 'S32LE', rate: 44100, channels: 2 }] },
    },
  }]);

  /** Mock the full call sequence: getAudioFormat → lock → findSinkId → wpctl → unlock */
  function mockFullSequence() {
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_OUTPUT, stderr: '', exitCode: 0 })   // pw-link (getAudioFormat)
      .mockResolvedValueOnce({ stdout: PW_DUMP_44100, stderr: '', exitCode: 0 })     // pw-dump (getAudioFormat)
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 })                // pw-metadata lock
      .mockResolvedValueOnce({ stdout: PW_CLI_ALL_NODES, stderr: '', exitCode: 0 })  // pw-cli ls Node
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 })                // wpctl set-default
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 });               // pw-metadata unlock
  }

  test('locks rate at 44100, switches to clean sink, then unlocks', async () => {
    mockFullSequence();

    await control.setSpatialMode('clean');

    // 6 calls: pw-link, pw-dump, pw-metadata lock, pw-cli ls, wpctl, pw-metadata unlock
    expect(mockRun).toHaveBeenCalledTimes(6);
    expect(mockRun.mock.calls[2]).toEqual([['pw-metadata', '-n', 'settings', '0', 'clock.force-rate', '44100']]);
    expect(mockRun.mock.calls[3][0]).toEqual(['pw-cli', 'ls', 'Node']);
    expect(mockRun.mock.calls[4]).toEqual([['wpctl', 'set-default', '42']]);
    expect(mockRun.mock.calls[5]).toEqual([['pw-metadata', '-n', 'settings', '0', 'clock.force-rate', '0']]);
  });

  test('switches to crossfeed sink with correct ID', async () => {
    mockFullSequence();

    await control.setSpatialMode('crossfeed');
    expect(mockRun.mock.calls[4]).toEqual([['wpctl', 'set-default', '55']]);
  });

  test('switches to room sink with correct ID', async () => {
    mockFullSequence();

    await control.setSpatialMode('room');
    expect(mockRun.mock.calls[4]).toEqual([['wpctl', 'set-default', '68']]);
  });

  test('skips locking when no audio is playing (getAudioFormat → null)', async () => {
    mockRun
      .mockResolvedValueOnce({ stdout: 'no links', stderr: '', exitCode: 0 })       // pw-link → no match
      .mockResolvedValueOnce({ stdout: PW_CLI_ALL_NODES, stderr: '', exitCode: 0 })  // pw-cli ls Node
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 });               // wpctl set-default

    await control.setSpatialMode('clean');

    // 3 calls: pw-link (null result), pw-cli ls, wpctl — no pw-metadata calls
    expect(mockRun).toHaveBeenCalledTimes(3);
    expect(mockRun.mock.calls[1][0]).toEqual(['pw-cli', 'ls', 'Node']);
    expect(mockRun.mock.calls[2]).toEqual([['wpctl', 'set-default', '42']]);
  });

  test('unlocks rate even when sink not found (error path)', async () => {
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_OUTPUT, stderr: '', exitCode: 0 })  // pw-link
      .mockResolvedValueOnce({ stdout: PW_DUMP_44100, stderr: '', exitCode: 0 })    // pw-dump
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 })               // pw-metadata lock
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 })               // pw-cli ls → empty (no sinks)
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 });              // pw-metadata unlock

    await expect(control.setSpatialMode('clean')).rejects.toThrow('Sink not found');
    // Unlock must still fire (finally block)
    expect(mockRun.mock.calls[4]).toEqual([['pw-metadata', '-n', 'settings', '0', 'clock.force-rate', '0']]);
  });

  test('unlocks rate even when wpctl fails (error path)', async () => {
    mockRun
      .mockResolvedValueOnce({ stdout: PW_LINK_OUTPUT, stderr: '', exitCode: 0 })   // pw-link
      .mockResolvedValueOnce({ stdout: PW_DUMP_44100, stderr: '', exitCode: 0 })     // pw-dump
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 })                // pw-metadata lock
      .mockResolvedValueOnce({ stdout: PW_CLI_ALL_NODES, stderr: '', exitCode: 0 })  // pw-cli ls
      .mockResolvedValueOnce({ stdout: '', stderr: 'some error', exitCode: 1 })      // wpctl fails
      .mockResolvedValueOnce({ stdout: '', stderr: '', exitCode: 0 });               // pw-metadata unlock

    await expect(control.setSpatialMode('clean')).rejects.toThrow('wpctl set-default failed');
    // Unlock must still fire
    expect(mockRun.mock.calls[5]).toEqual([['pw-metadata', '-n', 'settings', '0', 'clock.force-rate', '0']]);
  });
});

// ─── getActiveSink ──────────────────────────────────────────────────

describe('getActiveSink', () => {
  test('parses room mode from wpctl status Settings section', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: `
 Settings
  0. Audio/Sink    effect_input.headphone_dsp_room
`,
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveSink()).toBe('room');
  });

  test('parses crossfeed mode', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: `
 Settings
  0. Audio/Sink    effect_input.headphone_dsp_crossfeed
`,
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveSink()).toBe('crossfeed');
  });

  test('parses clean mode', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: `
 Settings
  0. Audio/Sink    effect_input.headphone_dsp
`,
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveSink()).toBe('clean');
  });

  test('fallback * path correctly identifies room mode', async () => {
    // All three sinks listed, room is starred — should NOT prefix-match to clean
    mockRun.mockResolvedValueOnce({
      stdout: [
        ' Sinks:',
        ' │      55. effect_input.headphone_dsp_crossfeed       [vol: 1.00]',
        ' │      42. effect_input.headphone_dsp                 [vol: 1.00]',
        ' │  *   68. effect_input.headphone_dsp_room            [vol: 1.00]',
      ].join('\n'),
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveSink()).toBe('room');
  });

  test('fallback * path correctly identifies clean mode', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: [
        ' Sinks:',
        ' │      55. effect_input.headphone_dsp_crossfeed       [vol: 1.00]',
        ' │  *   42. effect_input.headphone_dsp                 [vol: 1.00]',
        ' │      68. effect_input.headphone_dsp_room            [vol: 1.00]',
      ].join('\n'),
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveSink()).toBe('clean');
  });

  test('fallback * path correctly identifies crossfeed mode', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: [
        ' Sinks:',
        ' │  *   55. effect_input.headphone_dsp_crossfeed       [vol: 1.00]',
        ' │      42. effect_input.headphone_dsp                 [vol: 1.00]',
        ' │      68. effect_input.headphone_dsp_room            [vol: 1.00]',
      ].join('\n'),
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveSink()).toBe('crossfeed');
  });

  test('defaults to clean when no sink found', async () => {
    mockRun.mockResolvedValueOnce({ stdout: 'nothing useful here', stderr: '', exitCode: 0 });
    expect(await control.getActiveSink()).toBe('clean');
  });
});

// ─── getActiveEqProfile ─────────────────────────────────────────────

describe('getActiveEqProfile', () => {
  test('detects HD800S from symlink target', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: 'Sennheiser HD800 minimum phase 44100 Hz.wav\n',
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveEqProfile()).toBe('hd800s');
  });

  test('detects Monarch from symlink target', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: 'ThieAudio Monarch MKII minimum phase 44100Hz.wav\n',
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveEqProfile()).toBe('monarch');
  });

  test('detects custom profile from symlink path', async () => {
    mockRun.mockResolvedValueOnce({
      stdout: 'my-custom-iem/my-custom-iem minimum phase 44100Hz.wav\n',
      stderr: '', exitCode: 0,
    });
    expect(await control.getActiveEqProfile()).toBe('my-custom-iem');
  });

  test('defaults to monarch on readlink failure', async () => {
    mockRun.mockRejectedValueOnce(new Error('readlink failed'));
    expect(await control.getActiveEqProfile()).toBe('monarch');
  });
});
