import { writable } from 'svelte/store';
import type { WsSpectrumData } from '@aural/shared';

export const spectrumBars = writable<number[]>(new Array(48).fill(0));
export const spectrumConnected = writable(false);

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectSpectrum(): void {
  if (ws?.readyState === WebSocket.OPEN) return;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname;
  // In dev, Vite proxies /ws to the backend
  ws = new WebSocket(`${protocol}//${host}:${window.location.port}/ws/spectrum`);

  ws.onopen = () => {
    spectrumConnected.set(true);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = (event) => {
    try {
      const data: WsSpectrumData = JSON.parse(event.data);
      if (data.type === 'spectrum') {
        spectrumBars.set(data.bars);
      }
    } catch {
      // Ignore parse errors
    }
  };

  ws.onclose = () => {
    spectrumConnected.set(false);
    ws = null;
    // Reconnect after 2 seconds
    reconnectTimer = setTimeout(connectSpectrum, 2000);
  };

  ws.onerror = () => {
    ws?.close();
  };
}

export function disconnectSpectrum(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close();
    ws = null;
  }
  spectrumConnected.set(false);
}
