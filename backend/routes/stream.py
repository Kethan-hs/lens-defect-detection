"""
Dual-loop WebSocket stream — smooth display + async ML.
Bugs fixed vs previous version:
  1. display_loop used run_in_executor which on Python 3.12 Windows returned
     a Future instead of being awaitable in the expected way. Fixed: replaced
     with asyncio.to_thread() for all blocking calls (Python 3.9+ compatible).
  2. ml_loop had the same issue — also switched to asyncio.to_thread().
  3. _write_db task creation used run_in_executor(None,...) inside an already-
     running executor context — fixed to plain asyncio.to_thread().
"""
import asyncio
import json
import os
import time
import uuid
import threading

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from db.database              import SessionLocal
from db.models                import InspectionLog
from pipeline.decision        import make_decision_and_annotate
from pipeline.defect_detector import detect_defects_on_roi
from pipeline.lens_segmentor  import segment_lens

router = APIRouter()

SEG_INTERVAL       = float(os.getenv("SEG_INTERVAL",        "5.0"))
DB_WRITE_INTERVAL  = float(os.getenv("DB_WRITE_INTERVAL",   "5.0"))
WS_PING_INTERVAL   = float(os.getenv("WS_PING_INTERVAL",    "20.0"))
DISPLAY_JPEG_Q     = int(os.getenv("DISPLAY_JPEG_Q",         "72"))
TARGET_DISPLAY_FPS = float(os.getenv("TARGET_DISPLAY_FPS",   "25.0"))
DISPLAY_INTERVAL   = 1.0 / TARGET_DISPLAY_FPS   # 40 ms


def _to_safe(obj):
    if isinstance(obj, dict):           return {k: _to_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):  return [_to_safe(v) for v in obj]
    if isinstance(obj, np.integer):     return int(obj)
    if isinstance(obj, np.floating):    return float(obj)
    if isinstance(obj, np.ndarray):     return obj.tolist()
    return obj


def _write_db(pass_fail: str, detections: list):
    db = SessionLocal()
    try:
        db.add(InspectionLog(
            pass_fail    = pass_fail,
            defects_json = json.dumps(_to_safe(detections)),
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[DB] Write error: {e}")
    finally:
        db.close()


# ── Shared overlay state (display loop reads, ML loop writes) ─────────────────
class MLState:
    def __init__(self):
        self._lock          = threading.Lock()
        self.lenses         = []
        self.detections     = []
        self.pass_fail      = "No Lens"
        self.last_seg_time  = 0.0
        self.ml_fps         = 0.0
        self._ml_times      = []

    def write(self, lenses, detections, pass_fail, elapsed_ms):
        self._ml_times.append(elapsed_ms)
        if len(self._ml_times) > 10:
            self._ml_times.pop(0)
        avg = sum(self._ml_times) / len(self._ml_times)
        with self._lock:
            self.lenses     = lenses
            self.detections = detections
            self.pass_fail  = pass_fail
            self.ml_fps     = round(1000 / avg, 1) if avg > 0 else 0.0

    def read(self):
        with self._lock:
            return self.lenses[:], self.detections[:], self.pass_fail, self.ml_fps


# ── Blocking ML worker — runs via asyncio.to_thread ───────────────────────────
def _ml_worker_sync(frame_bytes: bytes, state: MLState, conn_id: str):
    try:
        arr   = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return
        h, w = frame.shape[:2]
        t0   = time.perf_counter()

        # Seg (cached every SEG_INTERVAL seconds)
        now = time.monotonic()
        with state._lock:
            current_lenses = state.lenses[:]
            last_seg       = state.last_seg_time

        if (now - last_seg) >= SEG_INTERVAL:
            new_lenses = segment_lens(frame)
            if new_lenses:
                current_lenses = new_lenses
            with state._lock:
                state.last_seg_time = now
                if new_lenses:
                    state.lenses = new_lenses

        # Combined ROI detect
        detections = []
        if current_lenses:
            bboxes = [l["bbox"] for l in current_lenses]
            x1 = min(b[0] for b in bboxes);  y1 = min(b[1] for b in bboxes)
            x2 = max(b[0]+b[2] for b in bboxes); y2 = max(b[1]+b[3] for b in bboxes)
            pad = 8
            x1, y1 = max(0, x1-pad), max(0, y1-pad)
            x2, y2 = min(w, x2+pad), min(h, y2+pad)
            roi = frame[y1:y2, x1:x2]
            detections = detect_defects_on_roi(roi, offset_x=x1, offset_y=y1)

        _, pass_fail, _ = make_decision_and_annotate(frame, current_lenses, detections)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        state.write(current_lenses, detections, pass_fail, elapsed_ms)

    except Exception as e:
        import traceback
        print(f"[ML][{conn_id}] Error: {e}")
        traceback.print_exc()


# ── Blocking display worker — runs via asyncio.to_thread ──────────────────────
def _display_worker_sync(frame_bytes: bytes, state: MLState):
    try:
        arr   = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None, None

        lenses, detections, pass_fail, ml_fps = state.read()
        annotated, pass_fail, _ = make_decision_and_annotate(frame, lenses, detections)

        if ml_fps > 0:
            cv2.putText(annotated, f"ML {ml_fps}fps",
                        (10, annotated.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (70, 70, 70), 1)

        _, buf = cv2.imencode(".jpg", annotated,
                              [cv2.IMWRITE_JPEG_QUALITY, DISPLAY_JPEG_Q])

        meta = _to_safe({
            "lens_detected":   bool(lenses),
            "is_lens_found":   bool(lenses),
            "lens_count":      len(lenses),
            "pass_fail":       pass_fail,
            "detections":      detections,
            "defects":         detections,
            "all_lens_bboxes": [l["bbox"] for l in lenses],
            "ml_fps":          ml_fps,
        })
        return buf.tobytes(), meta

    except Exception as e:
        print(f"[Display] Worker error: {e}")
        return None, None


# ── WebSocket endpoint ─────────────────────────────────────────────────────────
@router.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    conn_id    = str(uuid.uuid4())[:8]
    print(f"[WS][{conn_id}] Connected from {websocket.client.host}")

    display_q  = asyncio.Queue(maxsize=1)
    ml_q       = asyncio.Queue(maxsize=1)
    should_run = True
    state      = MLState()
    ml_busy    = False
    frame_count = 0
    last_db_write = 0.0

    def drop_insert(q: asyncio.Queue, item):
        while not q.empty():
            try: q.get_nowait()
            except asyncio.QueueEmpty: break
        try: q.put_nowait(item)
        except asyncio.QueueFull: pass

    # ── receive loop ──────────────────────────────────────────────────────────
    async def receive_loop():
        nonlocal should_run, frame_count
        try:
            while should_run:
                data = await websocket.receive_bytes()
                frame_count += 1
                drop_insert(display_q, data)
                if frame_count % 3 == 0:
                    drop_insert(ml_q, data)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[WS][{conn_id}] Receive error: {e}")
        finally:
            should_run = False
            drop_insert(display_q, b"")
            drop_insert(ml_q, b"")

    # ── display loop: 25fps, no YOLO ─────────────────────────────────────────
    async def display_loop():
        nonlocal should_run, last_db_write
        try:
            while should_run:
                t_start = time.monotonic()

                data = await display_q.get()
                if not data or not should_run:
                    break

                # asyncio.to_thread: clean, works on Python 3.9+ including Windows
                try:
                    out_bytes, meta = await asyncio.to_thread(
                        _display_worker_sync, data, state
                    )
                except Exception as e:
                    print(f"[WS][{conn_id}] Display worker error: {e}")
                    continue

                if out_bytes is None or not should_run:
                    continue

                try:
                    await websocket.send_text(json.dumps(meta))
                    await websocket.send_bytes(out_bytes)
                except Exception as e:
                    print(f"[WS][{conn_id}] Send error: {e}")
                    break

                # Throttled DB write
                now = time.monotonic()
                if state.lenses and (now - last_db_write) >= DB_WRITE_INTERVAL:
                    last_db_write = now
                    pf  = state.pass_fail
                    dts = state.detections[:]
                    asyncio.create_task(asyncio.to_thread(_write_db, pf, dts))

                # Pace to 25fps
                elapsed = time.monotonic() - t_start
                sleep_s = DISPLAY_INTERVAL - elapsed
                if sleep_s > 0.002:
                    await asyncio.sleep(sleep_s)

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[WS][{conn_id}] Display loop error: {e}")
        finally:
            should_run = False

    # ── ML loop: ~8fps YOLO in background ────────────────────────────────────
    async def ml_loop():
        nonlocal should_run, ml_busy
        try:
            while should_run:
                data = await ml_q.get()
                if not data or not should_run:
                    break
                if ml_busy:
                    continue
                ml_busy = True
                try:
                    await asyncio.to_thread(_ml_worker_sync, data, state, conn_id)
                finally:
                    ml_busy = False
        except Exception as e:
            print(f"[WS][{conn_id}] ML loop error: {e}")
        finally:
            should_run = False

    # ── ping loop ─────────────────────────────────────────────────────────────
    async def ping_loop():
        nonlocal should_run
        try:
            while should_run:
                await asyncio.sleep(WS_PING_INTERVAL)
                if should_run:
                    await websocket.send_text(json.dumps({"type": "ping"}))
        except Exception:
            pass

    try:
        tasks = [
            asyncio.create_task(receive_loop()),
            asyncio.create_task(display_loop()),
            asyncio.create_task(ml_loop()),
            asyncio.create_task(ping_loop()),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        for t in tasks:
            t.cancel()
        print(f"[WS][{conn_id}] Disconnected  frames={frame_count}")