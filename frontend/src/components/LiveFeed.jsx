import React, { useEffect, useState, useRef, useCallback } from 'react';
import { createStreamSocket } from '../api/client';

// Cap outgoing resolution — backend only needs ~640px for YOLO inference.
// Full 1080p adds bytes with zero accuracy gain and bloats latency.
const MAX_W = 640;
const MAX_H = 480;

// Adaptive send interval: loosens when RTT is high, tightens when fast.
const MIN_INTERVAL_MS = 100;
const MAX_INTERVAL_MS = 450;

const LiveFeed = ({ onMetadata }) => {
  const [frameSrc, setFrameSrc] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [connState, setConnState] = useState('connecting');
  const [cameraReady, setCameraReady] = useState(false);
  const [fallbackImage, setFallbackImage] = useState(null);
  const [fps, setFps] = useState(null);
  const [latency, setLatency] = useState(null);
  const [camError, setCamError] = useState(null);

  const socketRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const timerRef = useRef(null);
  const sendTsRef = useRef(null);
  const waitingRef = useRef(false);
  const intervalRef = useRef(200);
  const fpsFrames = useRef([]);
  const reconnTimer = useRef(null);
  const mountedRef = useRef(true);

  const updateFps = useCallback(() => {
    const now = Date.now();
    fpsFrames.current.push(now);
    fpsFrames.current = fpsFrames.current.filter(t => now - t < 2000);
    setFps(Math.round(fpsFrames.current.length / 2));
  }, []);

  const resizeFrame = useCallback((sw, sh) => {
    const scale = Math.min(MAX_W / sw, MAX_H / sh, 1);
    return { w: Math.round(sw * scale), h: Math.round(sh * scale) };
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    setConnState('connecting');

    const ws = createStreamSocket(
      (url) => {
        if (!mountedRef.current) return;
        if (sendTsRef.current) {
          const rtt = Date.now() - sendTsRef.current;
          setLatency(rtt);
          const target = Math.min(MAX_INTERVAL_MS, Math.max(MIN_INTERVAL_MS, rtt * 0.6));
          intervalRef.current = intervalRef.current * 0.8 + target * 0.2;
        }
        waitingRef.current = false;
        updateFps();
        setFrameSrc(prev => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      },
      (meta) => {
        if (!mountedRef.current || meta?.type === 'ping') return;
        setMetadata(meta);
        if (onMetadata) onMetadata(meta);
      }
    );

    ws.onopen = () => { if (mountedRef.current) setConnState('open'); };
    ws.onerror = () => { if (mountedRef.current) setConnState('error'); };
    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnState('closed');
      waitingRef.current = false;
      reconnTimer.current = setTimeout(() => { if (mountedRef.current) connect(); }, 3000);
    };

    socketRef.current = ws;
  }, [updateFps]); // eslint-disable-line react-hooks/exhaustive-deps

  const setupCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: MAX_W }, height: { ideal: MAX_H }, facingMode: 'environment' },
      });
      if (!mountedRef.current) { stream.getTracks().forEach(t => t.stop()); return; }
      const video = videoRef.current;
      if (!video) return;
      video.srcObject = stream;
      video.onloadedmetadata = () => {
        video.play().catch(() => { }).then(() => {
          const check = () => {
            if (!mountedRef.current) return;
            if (video.videoWidth > 0) setCameraReady(true);
            else requestAnimationFrame(check);
          };
          check();
        });
      };
    } catch (err) {
      setCamError(err.name === 'NotAllowedError' ? 'Camera permission denied' : 'Camera unavailable');
      const img = new Image();
      img.src = '/test.jpg';
      img.onload = () => { if (mountedRef.current) setFallbackImage(img); };
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    setupCamera();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnTimer.current);
      clearTimeout(timerRef.current);
      socketRef.current?.close();
      if (videoRef.current?.srcObject)
        videoRef.current.srcObject.getTracks().forEach(t => t.stop());
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Adaptive send loop
  useEffect(() => {
    const send = () => {
      timerRef.current = setTimeout(() => {
        requestAnimationFrame(send);
        const ws = socketRef.current;
        const canvas = canvasRef.current;
        const video = videoRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN || !canvas || waitingRef.current) return;
        const ctx = canvas.getContext('2d');
        let ready = false;

        if (video && video.videoWidth > 0 && !camError) {
          const { w, h } = resizeFrame(video.videoWidth, video.videoHeight);
          if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
          ctx.drawImage(video, 0, 0, w, h);
          ready = true;
        } else if (fallbackImage) {
          const { w, h } = resizeFrame(fallbackImage.width, fallbackImage.height);
          if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
          ctx.clearRect(0, 0, w, h);
          ctx.drawImage(fallbackImage, Math.sin(Date.now() / 700) * 2, 0, w, h);
          ready = true;
        }

        if (!ready) return;

        canvas.toBlob((blob) => {
          if (!blob || blob.size < 500 || ws.readyState !== WebSocket.OPEN) return;
          waitingRef.current = true;
          sendTsRef.current = Date.now();
          ws.send(blob);
        }, 'image/jpeg', 0.65);
      }, intervalRef.current);
    };

    if (cameraReady || fallbackImage) {
      timerRef.current = setTimeout(() => requestAnimationFrame(send), 500);
    }
    return () => clearTimeout(timerRef.current);
  }, [cameraReady, fallbackImage, camError, resizeFrame]);

  // Safety valve: unblock if no response in 4s
  useEffect(() => {
    const id = setInterval(() => { waitingRef.current = false; }, 4000);
    return () => clearInterval(id);
  }, []);

  const isPass = metadata?.pass_fail === 'Pass';
  const hasLens = metadata?.lens_detected || metadata?.is_lens_found;
  const segAge = metadata?.seg_age_s;
  const dets = metadata?.detections ?? [];

  const connDot = { connecting: 'bg-yellow-400', open: 'bg-emerald-400', closed: 'bg-slate-500', error: 'bg-rose-400' }[connState];
  const connLabel = { connecting: 'Connecting…', open: 'Live', closed: 'Reconnecting…', error: 'Connection error' }[connState];

  return (
    <div className="bg-slate-800 p-3 sm:p-4 rounded-xl shadow-lg border border-slate-700 h-full flex flex-col">
      {/* Header */}
      <div className="flex justify-between items-center mb-2 sm:mb-3 shrink-0">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full shrink-0 ${connDot}`}
            style={{ boxShadow: connState === 'open' ? '0 0 6px #34d399' : 'none' }} />
          <h2 className="text-base sm:text-lg font-bold text-slate-100">Live Camera Feed</h2>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {fps !== null && connState === 'open' && <span className="hidden sm:inline font-mono">{fps} fps</span>}
          {latency !== null && connState === 'open' && (
            <span className={`hidden sm:inline font-mono ${latency > 400 ? 'text-amber-400' : 'text-slate-500'}`}>
              {latency}ms
            </span>
          )}
          {hasLens && segAge !== undefined && <span className="hidden sm:inline">seg {segAge}s ago</span>}
          {metadata && (
            <span className={`px-2 sm:px-3 py-1 rounded-full text-xs sm:text-sm font-bold transition-colors ${!hasLens ? 'bg-slate-600 text-slate-300'
              : isPass ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50'
                : 'bg-rose-500/20 text-rose-400 border border-rose-500/50'
              }`}>
              {!hasLens ? 'Scanning…' : metadata.pass_fail}
            </span>
          )}
        </div>
      </div>

      {/* Feed + sidebar */}
      <div className="flex-1 flex flex-col lg:flex-row gap-3 min-h-0">
        <div className="flex-1 min-h-0 min-w-0">
          <div className="relative w-full bg-black rounded-lg overflow-hidden" style={{ aspectRatio: '4/3', minHeight: '200px' }}>
            <video ref={videoRef} autoPlay playsInline muted className="hidden" />
            <canvas ref={canvasRef} className="hidden" />

            {frameSrc ? (
              <img src={frameSrc} alt="Live annotated feed" className="absolute inset-0 w-full h-full object-contain" />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 px-4">
                <div className="w-10 h-10 border-2 border-slate-600 border-t-indigo-400 rounded-full mb-3"
                  style={{ animation: 'spin 1s linear infinite' }} />
                <span className="text-xs sm:text-sm">{connLabel}</span>
                {camError && <span className="text-xs text-amber-400 mt-1 text-center">{camError} — using test image</span>}
              </div>
            )}

            {/* LIVE / status badge */}
            {frameSrc && (
              <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 rounded-full px-2 py-0.5 backdrop-blur-sm">
                <div className={`w-1.5 h-1.5 rounded-full ${connState === 'open' ? 'bg-rose-500' : 'bg-slate-500'}`}
                  style={connState === 'open' ? { animation: 'pulse 1.5s ease-in-out infinite' } : {}} />
                <span className="text-[10px] sm:text-xs font-medium text-white tracking-wide">
                  {connState === 'open' ? 'LIVE' : connLabel.toUpperCase()}
                </span>
              </div>
            )}

            {/* Reconnecting overlay */}
            {connState === 'closed' && (
              <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                <div className="text-center">
                  <div className="w-8 h-8 border-2 border-slate-600 border-t-amber-400 rounded-full mx-auto mb-2"
                    style={{ animation: 'spin 1s linear infinite' }} />
                  <span className="text-xs text-slate-400">Reconnecting…</span>
                </div>
              </div>
            )}

            {hasLens && frameSrc && (
              <div className="absolute bottom-2 right-2 bg-black/60 rounded px-1.5 py-0.5 backdrop-blur-sm hidden sm:block">
                <span className="text-[10px] text-teal-400 font-mono">SEG ✓</span>
              </div>
            )}
            {fallbackImage && !cameraReady && (
              <div className="absolute bottom-2 left-2 bg-amber-500/20 border border-amber-500/40 rounded px-1.5 py-0.5 hidden sm:block">
                <span className="text-[10px] text-amber-400">Test image mode</span>
              </div>
            )}
          </div>
        </div>

        {/* Detections sidebar */}
        <div className="lg:w-44 shrink-0 bg-slate-900 rounded-lg p-2 sm:p-3 overflow-y-auto max-h-32 sm:max-h-40 lg:max-h-none">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5 sm:mb-2">Detections</h3>
          {dets.length > 0 ? (
            <div className="flex lg:flex-col gap-1.5 overflow-x-auto lg:overflow-x-visible pb-1 lg:pb-0">
              {dets.map((det, i) => (
                <div key={i} className="bg-slate-800 p-2 rounded text-sm border border-slate-700 shrink-0 min-w-[120px] lg:min-w-0">
                  <div className="flex justify-between items-center gap-2">
                    <span className="font-medium text-amber-400 text-xs capitalize">{det.label || det.class}</span>
                    <span className="text-slate-400 text-xs">{(det.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="mt-1.5 h-1 bg-slate-700 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-300" style={{
                      width: `${(det.confidence * 100).toFixed(0)}%`,
                      background: det.confidence > 0.7 ? 'linear-gradient(90deg,#f59e0b,#ef4444)' : 'linear-gradient(90deg,#6366f1,#8b5cf6)',
                    }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-500 text-center mt-2 sm:mt-3">
              {hasLens ? '✓ No defects' : 'No lens detected'}
            </div>
          )}
          {metadata && (
            <div className="mt-3 pt-3 border-t border-slate-800 hidden lg:block">
              <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Session</div>
              <div className={`text-xs font-bold ${isPass ? 'text-emerald-400' : 'text-rose-400'}`}>{metadata.pass_fail}</div>
              {latency !== null && (
                <div className={`text-xs mt-1 font-mono ${latency > 400 ? 'text-amber-400' : 'text-slate-600'}`}>RTT {latency}ms</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LiveFeed;