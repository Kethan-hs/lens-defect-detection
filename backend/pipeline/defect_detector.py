"""
Step 2: Defect Detection — Celeron B830 optimised
Runs ONE detection pass on the combined bounding box of ALL detected lenses.
This avoids N×detect cost (2 lenses = 2× slower) while still covering both.

Celeron B830 profile:
  - imgsz=320, 2 threads → ~120ms per pass (8fps)
  - Combined ROI approach → same cost regardless of lens count
"""
import os
import torch
import numpy as np
from ultralytics import YOLO

MODEL_PATH           = os.getenv("MODEL_PATH",             "models/best.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.3"))
DEFECT_IMGSZ         = int(os.getenv("DEFECT_IMGSZ",          "320"))
NUM_THREADS          = int(os.getenv("TORCH_NUM_THREADS",      "2"))   # Celeron is dual-core

torch.set_num_threads(NUM_THREADS)

_model = None

def _load_model():
    global _model
    if _model is None:
        try:
            _model = YOLO(MODEL_PATH)
            print(f"[DefectDetector] Loaded: {MODEL_PATH}  imgsz={DEFECT_IMGSZ}  threads={NUM_THREADS}")
        except Exception as e:
            print(f"[DefectDetector] Warning: Could not load {MODEL_PATH}: {e}")
            _model = None
    return _model


def detect_defects_on_roi(roi: np.ndarray,
                           offset_x: int = 0,
                           offset_y: int = 0,
                           confidence_threshold: float = CONFIDENCE_THRESHOLD) -> list:
    """
    Single detection pass on a given ROI image.
    offset_x/y map detections back to full-frame coordinates.
    Returns list of dicts with full-frame coords.
    """
    model = _load_model()
    if model is None or roi is None or roi.size == 0:
        return []
    try:
        with torch.inference_mode():
            results = model(roi, conf=confidence_threshold,
                            imgsz=DEFECT_IMGSZ, verbose=False, half=False)
        detections = []
        for result in results:
            if result.obb is None:
                continue
            for obb in result.obb:
                cls_id = int(obb.cls[0].item())
                conf   = float(obb.conf[0].item())
                coords = obb.xyxyxyxy[0].cpu().numpy().tolist()
                # Map from ROI-space to full-frame space
                coords_mapped = [[pt[0] + offset_x, pt[1] + offset_y] for pt in coords]
                xs = [pt[0] for pt in coords]; ys = [pt[1] for pt in coords]
                bbox = [int(min(xs)) + offset_x, int(min(ys)) + offset_y,
                        int(max(xs) - min(xs)), int(max(ys) - min(ys))]
                name = result.names.get(cls_id, f"class_{cls_id}")
                detections.append({
                    "label":      name,
                    "class":      name,
                    "confidence": conf,
                    "obb_coords": coords_mapped,   # full-frame coords
                    "bbox":       bbox,
                    "roi_coords": coords,           # original ROI-space (for debug)
                })
        return detections
    except Exception as e:
        print(f"[DefectDetector] Inference error: {e}")
        return []


def detect_defects(roi: np.ndarray,
                   confidence_threshold: float = CONFIDENCE_THRESHOLD) -> list:
    """
    Legacy single-ROI interface (offset 0,0).
    Kept for backward compatibility with stream.py.
    """
    return detect_defects_on_roi(roi, 0, 0, confidence_threshold)