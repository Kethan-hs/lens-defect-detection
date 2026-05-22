"""
Step 1: Lens Segmentation — dual-lens, all bugs fixed.

Bugs fixed:
  1. candidates.sort(reverse=True) crashed when areas were equal — Python
     compared the np.ndarray second element. Fix: key=lambda x: x[0].
  2. CV fallback merged adjacent lenses (e.g. glasses) into one contour
     after GaussianBlur. Fix: watershed distance-transform split.
"""
import os
import cv2
import numpy as np
import torch
from ultralytics import YOLO

LENS_SEG_MODEL_PATH = os.getenv("LENS_SEG_MODEL_PATH", "models/lens_seg.pt")
SEG_CONF            = float(os.getenv("SEG_CONF",       "0.25"))
SEG_IMGSZ           = int(os.getenv("SEG_IMGSZ",        "320"))
MAX_LENSES          = int(os.getenv("MAX_LENSES",        "2"))

_model = None

def _load_model():
    global _model
    if _model is None:
        try:
            _model = YOLO(LENS_SEG_MODEL_PATH)
            print(f"[LensSeg] Loaded: {LENS_SEG_MODEL_PATH}  imgsz={SEG_IMGSZ}  max_lenses={MAX_LENSES}")
        except Exception as e:
            print(f"[LensSeg] Warning: Could not load seg model: {e}")
            _model = None
    return _model


def _mask_to_lens(mask_raw, frame_h, frame_w, pad_pct=0.04):
    msk = cv2.resize(mask_raw, (frame_w, frame_h), interpolation=cv2.INTER_NEAREST)
    msk = (msk > 0.5).astype(np.uint8) * 255
    contours, _ = cv2.findContours(msk, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    x, y, cw, ch = cv2.boundingRect(c)
    px, py = int(cw * pad_pct), int(ch * pad_pct)
    x  = max(0, x - px);         y  = max(0, y - py)
    cw = min(frame_w - x, cw + 2*px)
    ch = min(frame_h - y, ch + 2*py)
    return {"bbox": [x, y, cw, ch], "mask": msk, "polygon": c.reshape(-1, 2).tolist()}


def _split_wide_contour(contour, thresh_mask, h, w):
    """
    Watershed-based split for a single wide contour that may contain two
    adjacent lenses (e.g. glasses with no gap between frames).
    Returns list of sub-contours (1 or 2).
    """
    # Build a mask just for this contour
    single_mask = np.zeros((h, w), np.uint8)
    cv2.drawContours(single_mask, [contour], -1, 255, -1)

    # Distance transform — peaks are the centres of each lens
    dist  = cv2.distanceTransform(single_mask, cv2.DIST_L2, 5)
    dist8 = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Local maxima via dilation
    peak_k  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (30, 30))
    dilated = cv2.dilate(dist8, peak_k)
    peak_mask = ((dist8 == dilated) & (dist8 > int(dist8.max() * 0.4))).astype(np.uint8)

    n_labels, markers = cv2.connectedComponents(peak_mask)
    if n_labels < 3:          # only background + one peak → can't split
        return [contour]

    # Watershed
    bgr = cv2.cvtColor(single_mask, cv2.COLOR_GRAY2BGR)
    cv2.watershed(bgr, markers)

    # Extract a contour per region
    sub_contours = []
    for label in range(1, n_labels):
        region = np.where(markers == label, 255, 0).astype(np.uint8)
        cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            sub_contours.append(max(cnts, key=cv2.contourArea))

    return sub_contours if sub_contours else [contour]


def _cv_segment(frame: np.ndarray):
    """
    Pure-CV fallback — finds up to MAX_LENSES lenses including adjacent ones.
    """
    h, w = frame.shape[:2]
    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur  = cv2.GaussianBlur(gray, (5, 5), 0)    # smaller kernel: less merging
    k5    = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    raw_candidates = []   # (area:float, uid:int, contour)
    for thresh_val in [30, 40, 60, 80]:
        _, binary = cv2.threshold(blur, thresh_val, 255, cv2.THRESH_BINARY)
        binary    = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k5)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = float(cv2.contourArea(c))
            if area < 4000:
                continue
            peri = float(cv2.arcLength(c, True))
            circ = 4.0 * np.pi * area / (peri * peri + 1e-6)

            x, y, cw, ch = cv2.boundingRect(c)
            aspect = cw / max(ch, 1)

            # Wide contour (aspect > 1.8) and circular enough → likely two merged lenses
            if aspect > 1.8 and circ > 0.15 and MAX_LENSES > 1:
                sub = _split_wide_contour(c, binary, h, w)
                for sc in sub:
                    sa = float(cv2.contourArea(sc))
                    if sa > 3000:
                        raw_candidates.append((sa, id(sc), sc))
            elif circ > 0.25:
                raw_candidates.append((area, id(c), c))

    if not raw_candidates:
        return []

    # Sort by area desc — key= avoids ever comparing np.ndarray
    raw_candidates.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate overlapping / near-identical contours
    kept = []
    for area, _, c in raw_candidates:
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx_ = float(M["m10"] / M["m00"])
        cy_ = float(M["m01"] / M["m00"])
        too_close = False
        for _, _, kc in kept:
            Mk = cv2.moments(kc)
            if Mk["m00"] == 0:
                continue
            kx = float(Mk["m10"] / Mk["m00"])
            ky = float(Mk["m01"] / Mk["m00"])
            if abs(cx_ - kx) < 80 and abs(cy_ - ky) < 60:
                too_close = True
                break
        if not too_close:
            kept.append((area, id(c), c))
        if len(kept) >= MAX_LENSES:
            break

    results = []
    for _, _, c in kept:
        x, y, cw, ch = cv2.boundingRect(c)
        mask = np.zeros((h, w), np.uint8)
        cv2.drawContours(mask, [c], -1, 255, -1)
        results.append({
            "bbox":    [x, y, cw, ch],
            "mask":    mask,
            "polygon": c.reshape(-1, 2).tolist(),
        })
    return results


def segment_lens(frame: np.ndarray):
    """
    Returns list of up to MAX_LENSES dicts: [{"bbox","mask","polygon"}, ...]
    """
    h, w = frame.shape[:2]
    model = _load_model()

    if model is not None:
        try:
            with torch.inference_mode():
                results = model(frame, conf=SEG_CONF, imgsz=SEG_IMGSZ,
                                verbose=False, half=False)
            lenses = []
            for result in results:
                if result.masks is None or len(result.masks) == 0:
                    continue
                masks_np = result.masks.data.cpu().numpy()
                areas    = [float(m.sum()) for m in masks_np]
                idxs     = sorted(range(len(areas)), key=lambda i: areas[i], reverse=True)
                for idx in idxs[:MAX_LENSES]:
                    lens = _mask_to_lens(masks_np[idx], h, w)
                    if lens is not None:
                        lenses.append(lens)
                if lenses:
                    return lenses
        except Exception as e:
            print(f"[LensSeg] YOLO failed, using CV fallback: {e}")

    return _cv_segment(frame)