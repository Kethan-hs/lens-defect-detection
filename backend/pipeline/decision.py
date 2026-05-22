"""
Step 3: Decision + Annotation — dual-lens aware
Draws segmentation overlays for ALL detected lenses,
then maps detections (already in full-frame coords) onto the frame.
"""
import cv2
import numpy as np

DEFECT_COLORS = {
    "bubble":  (255, 100,   0),
    "crack":   (0,     0, 255),
    "dots":    (0,   230, 230),
    "scratch": (0,   165, 255),
}
DEFAULT_COLOR = (200, 200, 200)


def make_decision_and_annotate(
    frame: np.ndarray,
    lenses: list,           # list of {"bbox","mask","polygon"} from lens_segmentor
    detections: list,       # already in FULL-FRAME coords from detect_defects_on_roi
) -> tuple:
    """
    Args:
        frame      - original BGR frame
        lenses     - list of lens dicts (1 or 2 for spectacles)
        detections - defect dets with full-frame obb_coords + bbox

    Returns:
        annotated_frame, pass_fail ("Pass"|"Fail"|"No Lens"), mapped_detections
    """
    annotated = frame.copy()

    if not lenses:
        cv2.putText(annotated, "NO LENS DETECTED",
                    (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        return annotated, "No Lens", []

    # ── Draw each lens segmentation overlay ───────────────────────────────────
    for i, lens in enumerate(lenses):
        mask    = lens.get("mask")
        polygon = lens.get("polygon", [])
        bbox    = lens.get("bbox", [])

        # Semi-transparent fill
        if mask is not None:
            overlay      = annotated.copy()
            teal_layer   = np.zeros_like(annotated)
            teal_layer[mask > 0] = (180, 220, 0)
            cv2.addWeighted(teal_layer, 0.15, overlay, 0.85, 0, annotated)

        # Outline polygon
        if polygon and len(polygon) >= 3:
            pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(annotated, [pts], isClosed=True, color=(0, 230, 200), thickness=2)

        # Bounding rect
        if bbox and len(bbox) == 4:
            lx, ly, lw, lh = [int(v) for v in bbox]
            cv2.rectangle(annotated, (lx, ly), (lx + lw, ly + lh),
                          (0, 200, 180), 1)

    # ── Pass / Fail ────────────────────────────────────────────────────────────
    pass_fail = "Fail" if detections else "Pass"

    # ── Draw detections (coords are already full-frame) ───────────────────────
    for det in detections:
        cls_name = det["label"]
        conf     = det["confidence"]
        color    = DEFECT_COLORS.get(cls_name, DEFAULT_COLOR)

        # OBB polygon — obb_coords already in full-frame space
        coords = np.array(det["obb_coords"], dtype=np.int32)
        cv2.polylines(annotated, [coords], isClosed=True, color=color, thickness=2)

        label    = f"{cls_name} {conf:.0%}"
        pt1      = tuple(coords[0])
        label_y  = max(pt1[1] - 6, 18)
        cv2.putText(annotated, label,
                    (pt1[0], label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)

    # ── Result banner ──────────────────────────────────────────────────────────
    result_color = (0, 220, 80) if pass_fail == "Pass" else (0, 60, 255)
    n_lenses     = len(lenses)
    label_text   = f"  {pass_fail.upper()}  ({n_lenses} lens{'es' if n_lenses != 1 else ''})"
    cv2.putText(annotated, label_text,
                (30, 55), cv2.FONT_HERSHEY_SIMPLEX, 1.4, result_color, 3)

    return annotated, pass_fail, detections