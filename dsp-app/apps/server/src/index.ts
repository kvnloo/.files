import { Hono } from 'hono';
import { cors } from 'hono/cors';
import api from './routes/api';
import { startCava, stopCava } from './spectrum/cava';
import type { WsSpectrumData } from '@aural/shared';

const app = new Hono();

app.use('/*', cors({ origin: ['http://localhost:5173', 'http://localhost:4173'] }));

// Mount API routes
app.route('/api', api);

// Health check
app.get('/health', (c) => c.json({ status: 'ok', timestamp: Date.now() }));

// ─── WebSocket handling via Bun.serve ────────────────────────────
const spectrumClients = new Set<ServerWebSocket>();

type ServerWebSocket = {
  send: (data: string) => void;
  close: () => void;
};

const server = Bun.serve({
  port: 3001,
  fetch(req, server) {
    const url = new URL(req.url);

    // WebSocket upgrade for spectrum
    if (url.pathname === '/ws/spectrum') {
      const upgraded = server.upgrade(req);
      if (!upgraded) {
        return new Response('WebSocket upgrade failed', { status: 400 });
      }
      return undefined;
    }

    // Delegate to Hono for all other routes
    return app.fetch(req);
  },
  websocket: {
    open(ws) {
      spectrumClients.add(ws as unknown as ServerWebSocket);
    },
    close(ws) {
      spectrumClients.delete(ws as unknown as ServerWebSocket);
    },
    message() {
      // Client doesn't send messages for spectrum
    },
  },
});

// Start CAVA and broadcast spectrum data
startCava((bars) => {
  if (spectrumClients.size === 0) return;
  const msg = JSON.stringify({ type: 'spectrum', bars } satisfies WsSpectrumData);
  for (const client of spectrumClients) {
    try {
      client.send(msg);
    } catch {
      spectrumClients.delete(client);
    }
  }
});

console.log(`🎧 Aural server running at http://localhost:${server.port}`);

// Graceful shutdown
process.on('SIGINT', () => {
  stopCava();
  process.exit(0);
});
