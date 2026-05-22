"""
Step 1: Lens Isolation
Uses Classical CV (OpenCV HoughCircles) to isolate the lens from a live camera frame.
"""
import cv2
import numpy as np

def detect_lens(frame: np.ndarray) -> tuple[bool, np.ndarray, list, tuple]:
    """
    Detects the lens in the frame using Hough Circles.
    Returns:
        (is_lens_found, cropped_roi, bbox, circle_coords)
        bbox is [x_min, y_min, width, height]
        circle_coords is (cx, cy, r)
    """
    if frame is None or frame.size == 0:
        return False, frame, [], None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.medianBlur(gray, 5)
    
    # Adjust parameters based on actual lighting and camera setup
    circles = cv2.HoughCircles(
        blurred, 
        cv2.HOUGH_GRADIENT, 
        dp=1, 
        minDist=50,
        param1=100, 
        param2=50, 
        minRadius=50, 
        maxRadius=0
    )
    
    if circles is not None:
        circles = np.around(circles).astype(int)
        # Pick the largest circle if multiple are found
        largest_circle = max(circles[0, :], key=lambda c: c[2])
        cx, cy, r = map(int, largest_circle)
        
        # Ensure bounds are within frame
        h, w = frame.shape[:2]
        x_min = max(0, cx - r)
        y_min = max(0, cy - r)
        x_max = min(w, cx + r)
        y_max = min(h, cy + r)
        
        # Bbox in [x, y, w, h] format
        bbox_w = x_max - x_min
        bbox_h = y_max - y_min
        bbox = [x_min, y_min, bbox_w, bbox_h]
        
        cropped_roi = frame[y_min:y_max, x_min:x_max]
        
        # Additional safety check: if cropped ROI is too small, assume no lens
        if cropped_roi.size == 0 or bbox_w < 10 or bbox_h < 10:
            return False, frame, [], None

        return True, cropped_roi, bbox, (cx, cy, r)
        
    return False, frame, [], None
