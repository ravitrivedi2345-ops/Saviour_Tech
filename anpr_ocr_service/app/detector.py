"""
detector.py — Stage 1: Vehicle License Plate Detection (YOLOv8 architecture).

Locates license plate bounding boxes in full high-resolution video frames or images.
Includes pre-filtering (CLAHE adaptive histogram equalization for low-light/glare)
and crop normalization. Supports GPU CUDA acceleration with CPU fallback.
"""

import os
import sys
import time
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings


class PlateDetector:
    """Stage 1 Plate Detection Model."""

    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None):
        self.device = device or settings.DEVICE
        self.conf_threshold = settings.DETECTION_CONF_THRESHOLD
        self.iou_threshold = settings.DETECTION_IOU_THRESHOLD
        self.model_path = model_path
        self.session = None

        # Check for CUDA availability
        self._init_backend()

    def _init_backend(self):
        """Initialize inference engine (ONNX Runtime, Torch, or OpenCV DNN)."""
        has_cuda = False
        try:
            import torch
            has_cuda = torch.cuda.is_available()
        except ImportError:
            pass

        if self.device == "auto":
            self.device = "cuda" if has_cuda else "cpu"

        # Check for model weights
        if self.model_path and os.path.exists(self.model_path):
            try:
                import onnxruntime as ort
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if self.device == "cuda" else ["CPUExecutionProvider"]
                self.session = ort.InferenceSession(self.model_path, providers=providers)
            except Exception as e:
                print(f"[Detector] Warning loading ONNX model: {e}. Using fallback detector.")
                self.session = None
        else:
            self.session = None

    def preprocess_frame(self, image: np.ndarray) -> np.ndarray:
        """Apply adaptive contrast enhancement for night/rain glare."""
        if len(image.shape) == 2:
            return image
        # Convert to LAB color space and apply CLAHE to L channel
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_clahe = clahe.apply(l)
        enhanced = cv2.merge((l_clahe, a, b))
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def detect_plates(self, image: np.ndarray) -> List[Dict]:
        """
        Run plate detection on a frame.
        
        Returns:
            List of dicts: [
                {
                    "bbox": [x1, y1, x2, y2],
                    "confidence": float,
                    "crop": np.ndarray (cropped plate image),
                    "class_name": "license_plate"
                }
            ]
        """
        h, w = image.shape[:2]
        enhanced = self.preprocess_frame(image)

        if self.session is not None:
            return self._run_onnx(enhanced, w, h)
        else:
            return self._run_heuristic_detector(enhanced, w, h)

    def _run_onnx(self, image: np.ndarray, orig_w: int, orig_h: int) -> List[Dict]:
        """Inference with YOLOv8 ONNX model."""
        input_size = 640
        blob = cv2.resize(image, (input_size, input_size))
        blob = blob.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))
        blob = np.expand_dims(blob, axis=0)

        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: blob})
        # Parse standard YOLOv8 output [1, 5, 8400]
        preds = np.squeeze(outputs[0]).T  # [8400, 5] (cx, cy, w, h, conf)

        boxes = []
        confidences = []
        for pred in preds:
            conf = pred[4]
            if conf >= self.conf_threshold:
                cx, cy, bw, bh = pred[0], pred[1], pred[2], pred[3]
                x1 = int((cx - bw / 2) * (orig_w / input_size))
                y1 = int((cy - bh / 2) * (orig_h / input_size))
                x2 = int((cx + bw / 2) * (orig_w / input_size))
                y2 = int((cy + bh / 2) * (orig_h / input_size))
                boxes.append([max(0, x1), max(0, y1), min(orig_w, x2), min(orig_h, y2)])
                confidences.append(float(conf))

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.iou_threshold)
        results = []
        if len(indices) > 0:
            for idx in indices.flatten():
                box = boxes[idx]
                crop = image[box[1]:box[3], box[0]:box[2]]
                results.append({
                    "bbox": box,
                    "confidence": confidences[idx],
                    "crop": crop,
                    "class_name": "license_plate"
                })
        return results

    def _run_heuristic_detector(self, image: np.ndarray, w: int, h: int) -> List[Dict]:
        """
        Morphological & contour-based localization fallback.
        Reliably detects high-contrast rectangular plate regions when pre-trained
        deep weights are not loaded.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        candidates = []

        # Method 1: High-contrast rectangular plate detection (bright plate on darker bumper)
        _, plate_thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(plate_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            aspect = bw / float(bh) if bh > 0 else 0
            area = bw * bh
            if 1.8 <= aspect <= 6.0 and (w * h * 0.005) <= area <= (w * h * 0.40):
                candidates.append((x, y, x + bw, y + bh, 0.92))

        # Method 2: Morphological gradient & Sobel vertical character strokes
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 3))
        grad_x = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
        grad_x = np.absolute(grad_x)
        min_v, max_v = np.min(grad_x), np.max(grad_x)
        if max_v > min_v:
            grad_x = 255 * ((grad_x - min_v) / (max_v - min_v))
        grad_x = grad_x.astype("uint8")
        grad_x = cv2.GaussianBlur(grad_x, (5, 5), 0)
        _, thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            aspect = bw / float(bh) if bh > 0 else 0
            area = bw * bh
            if 1.8 <= aspect <= 6.0 and (w * h * 0.005) <= area <= (w * h * 0.40):
                candidates.append((x, y, x + bw, y + bh, 0.88))

        # Filter and deduplicate candidates
        results = []
        if candidates:
            # Sort by area/confidence
            candidates.sort(key=lambda c: (c[4], (c[2] - c[0]) * (c[3] - c[1])), reverse=True)
            chosen = candidates[0]
            crop = image[chosen[1]:chosen[3], chosen[0]:chosen[2]]
            if crop.size > 0:
                results.append({
                    "bbox": [chosen[0], chosen[1], chosen[2], chosen[3]],
                    "confidence": chosen[4],
                    "crop": crop,
                    "class_name": "license_plate"
                })

        # Fallback: if whole image is already a crop or no candidate found
        if not results:
            aspect = w / float(max(1, h))
            if 1.5 <= aspect <= 6.0:
                results.append({
                    "bbox": [0, 0, w, h],
                    "confidence": 0.90,
                    "crop": image.copy(),
                    "class_name": "license_plate"
                })

        return results
