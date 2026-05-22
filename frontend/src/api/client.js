import axios from 'axios';

// ── Base URL ──────────────────────────────────────────────────────────────────
const RAW_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
export const API_URL = RAW_URL || 'http://localhost:8000';

if (!RAW_URL) {
  console.warn('[client] VITE_API_URL not set — falling back to localhost:8000');
}

// ── Axios instance ────────────────────────────────────────────────────────────
const api = axios.create({
  baseURL: API_URL,
  timeout: 8000,
});

// ── REST helpers ──────────────────────────────────────────────────────────────
export const getInspections = (skip = 0, limit = 50) =>
  api.get(`/inspections/?skip=${skip}&limit=${limit}`).then(r => r.data);

export const getStats = () =>
  api.get('/inspections/stats').then(r => r.data);

export const getHealth = () =>
  api.get('/health').then(r => r.data);

export const exportCSV = () =>
  window.open(`${API_URL}/export/csv`, '_blank');

export const exportPDF = () =>
  window.open(`${API_URL}/export/pdf`, '_blank');


// ── WebSocket factory ─────────────────────────────────────────────────────────
// Returns a raw WebSocket. The caller (LiveFeed) owns reconnection logic.
// onFrame(objectURL: string) — called with every annotated JPEG blob URL.
// onMetadata(obj)            — called with every JSON metadata message.
export const createStreamSocket = (onFrame, onMetadata) => {
  const wsBase = API_URL
    .replace(/^https:/, 'wss:')
    .replace(/^http:/, 'ws:');

  const socket = new WebSocket(`${wsBase}/ws/stream`);
  socket.binaryType = 'blob';

  socket.onmessage = async (event) => {
    if (typeof event.data === 'string') {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed?.type === 'ping') return;
        onMetadata(parsed);
      } catch { /* ignore malformed text */ }
    } else {
      try {
        const blob = event.data instanceof Blob
          ? event.data
          : new Blob([event.data], { type: 'image/jpeg' });
        onFrame(URL.createObjectURL(blob));
      } catch { /* ignore bad binary */ }
    }
  };

  return socket;
};