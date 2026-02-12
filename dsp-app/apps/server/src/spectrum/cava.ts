/** CAVA subprocess manager — streams FFT bars via callback */
import { existsSync, unlinkSync } from 'node:fs';

const FIFO_PATH = '/tmp/aural-cava-fifo';

const CAVA_CONFIG = `
[general]
bars = 48
framerate = 30
autosens = 1
sensitivity = 100

[input]
method = pulse
source = auto

[output]
method = raw
raw_target = ${FIFO_PATH}
data_format = ascii
ascii_max_range = 1000
`;

type SpectrumCallback = (bars: number[]) => void;

let cavaProcess: ReturnType<typeof Bun.spawn> | null = null;
let configPath: string | null = null;
let fifoReader: ReturnType<typeof setTimeout> | null = null;

export async function startCava(onData: SpectrumCallback): Promise<void> {
  configPath = '/tmp/aural-cava.conf';

  // Create FIFO
  if (existsSync(FIFO_PATH)) unlinkSync(FIFO_PATH);
  const mkfifo = Bun.spawnSync(['mkfifo', FIFO_PATH]);
  if (mkfifo.exitCode !== 0) {
    console.warn('Failed to create FIFO for CAVA');
    return;
  }

  await Bun.write(configPath, CAVA_CONFIG);

  try {
    cavaProcess = Bun.spawn(['cava', '-p', configPath], {
      stdout: 'ignore',
      stderr: 'pipe',
    });

    // Log stderr
    const stderrStream = cavaProcess.stderr;
    if (stderrStream && typeof stderrStream !== 'number') {
      (async () => {
        const r = (stderrStream as ReadableStream<Uint8Array>).getReader();
        const d = new TextDecoder();
        try {
          while (true) {
            const { done, value } = await r.read();
            if (done) break;
            const msg = d.decode(value, { stream: true }).trim();
            if (msg) console.warn('[CAVA]', msg);
          }
        } catch { /* ended */ }
      })();
    }

    console.log('CAVA started (pulse → FIFO)');
  } catch {
    console.warn('CAVA not available — spectrum inactive. Install: sudo apt install cava');
    return;
  }

  // Read from FIFO
  readFifo(onData);
}

async function readFifo(onData: SpectrumCallback): Promise<void> {
  try {
    const file = Bun.file(FIFO_PATH);
    const stream = file.stream();
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const bars = trimmed.split(';').filter(Boolean).map((v) => Number(v) / 1000);
        if (bars.length > 0 && bars.every((b) => !isNaN(b))) {
          onData(bars);
        }
      }
    }
  } catch {
    // FIFO closed or CAVA stopped — try reopening after delay
    if (cavaProcess) {
      setTimeout(() => readFifo(onData), 1000);
    }
  }
}

export function stopCava(): void {
  if (cavaProcess) {
    cavaProcess.kill();
    cavaProcess = null;
  }
  try {
    if (existsSync(FIFO_PATH)) unlinkSync(FIFO_PATH);
  } catch { /* cleanup */ }
}
