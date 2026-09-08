"""
generate_synthetic_data.py — Multi-Condition ANPR Synthetic Benchmark Dataset Generator.

Generates realistic plate images embedded into vehicle bumper backgrounds under 5
controlled environmental conditions:
1. Clear Daytime (High contrast, ideal lighting)
2. Night / Low-Light (Sensor noise, headlight flare, low SNR)
3. Rain / Wet Weather (Refractive water distortion, puddle reflection)
4. Motion Blur (Linear velocity PSF kernel, high-speed vehicle transit)
5. Oblique Angle (Perspective homography skew >35 degrees)
"""

import os
import random
import cv2
import numpy as np
from typing import Dict, List, Tuple

# Sample pool of standard Indian format plates
TEST_PLATES = [
    "DL01AB1234", "MH12XY5678", "UP32CD9999", "KA05EF2222", "RJ14GH7777",
    "HR26QR6789", "TN07JK3333", "WB02LM4444", "GJ01NP5555", "CH01ST8888",
    "DL04CD4567", "MH02EF8901", "UP16AB2345", "KA01MN6789", "RJ45KL1122",
    "HR10XY3344", "TN22OP5566", "WB12QR7788", "GJ06ST9900", "CH03UV1212"
]


def render_base_plate(text: str, w: int = 240, h: int = 60) -> np.ndarray:
    """Render a clean Indian white/yellow license plate patch with border and characters."""
    # White reflective plate background
    plate = np.full((h, w, 3), (245, 245, 245), dtype=np.uint8)
    
    # Outer dark border
    cv2.rectangle(plate, (2, 2), (w - 3, h - 3), (20, 20, 20), 2)
    
    # Left IND blue band (High Security Registration Plate standard)
    cv2.rectangle(plate, (4, 4), (24, h - 4), (160, 50, 20), -1)
    cv2.putText(plate, "IND", (5, h // 2 + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.25, (255, 255, 255), 1, cv2.LINE_AA)

    # Render characters
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.95
    thickness = 2
    
    # Measure text size
    text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
    start_x = 34 + (w - 38 - text_size[0]) // 2
    start_y = (h + text_size[1]) // 2

    cv2.putText(plate, text, (start_x, start_y), font, font_scale, (15, 15, 15), thickness, cv2.LINE_AA)
    return plate


def embed_in_vehicle_frame(plate: np.ndarray, frame_w: int = 640, frame_h: int = 480) -> Tuple[np.ndarray, List[int]]:
    """Embed cropped plate patch into a realistic vehicle rear/front bumper scene."""
    frame = np.full((frame_h, frame_w, 3), (45, 45, 48), dtype=np.uint8) # Dark asphalt/chassis
    
    # Add subtle gradients simulating car bumper curvature
    for y in range(frame_h):
        shade = int(35 + (y / frame_h) * 30)
        frame[y, :] = (shade, shade, shade + 5)

    ph, pw = plate.shape[:2]
    # Place plate near lower center
    px = (frame_w - pw) // 2 + random.randint(-40, 40)
    py = int(frame_h * 0.58) + random.randint(-20, 20)

    frame[py:py + ph, px:px + pw] = plate
    bbox = [px, py, px + pw, py + ph]
    return frame, bbox


# ─── Environmental Noise Operators ─────────────────────────────────────────────

def apply_daytime_clean(image: np.ndarray) -> np.ndarray:
    """Clear daytime: optimal contrast and minor ambient noise."""
    # Slight illumination variation
    noise = np.random.normal(0, 3, image.shape).astype(np.float32)
    res = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return res


def apply_night_low_light(image: np.ndarray) -> np.ndarray:
    """Night conditions: reduced dynamic range, Poisson/Gaussian sensor grain, flare."""
    # Darken overall scene
    dark = (image.astype(np.float32) * 0.38)
    # Add sensor noise
    noise = np.random.normal(0, 18, image.shape).astype(np.float32)
    noisy = np.clip(dark + noise, 0, 255).astype(np.uint8)

    # Add simulated headlight flare/glow at corner
    h, w = image.shape[:2]
    flare = np.zeros((h, w), dtype=np.float32)
    cv2.circle(flare, (int(w * 0.2), int(h * 0.4)), 160, (255, 255, 255), -1)
    flare = cv2.GaussianBlur(flare, (99, 99), 0) / 255.0
    flare_3c = np.stack([flare * 140] * 3, axis=-1)

    result = np.clip(noisy.astype(np.float32) + flare_3c, 0, 255).astype(np.uint8)
    return result


def apply_rain_wet(image: np.ndarray) -> np.ndarray:
    """Rain condition: water droplet blur, refractive distortions, streaks."""
    res = image.copy()
    h, w = res.shape[:2]

    # Blur slightly due to misty air
    res = cv2.GaussianBlur(res, (5, 5), 0)

    # Add random rain streaks
    num_streaks = 250
    for _ in range(num_streaks):
        x = random.randint(0, w - 1)
        y = random.randint(0, h - 25)
        length = random.randint(12, 28)
        color = (210, 210, 220)
        cv2.line(res, (x, y), (x - 3, y + length), color, 1)

    # Lower overall contrast slightly due to water film
    res = cv2.addWeighted(res, 0.85, np.full_like(res, 90), 0.15, 0)
    return res


def apply_motion_blur(image: np.ndarray, kernel_size: int = 15) -> np.ndarray:
    """Motion blur: horizontal PSF point-spread function simulating high velocity."""
    kernel = np.zeros((kernel_size, kernel_size))
    # Horizontal motion
    kernel[int((kernel_size - 1) / 2), :] = np.ones(kernel_size)
    kernel = kernel / kernel_size
    blurred = cv2.filter2D(image, -1, kernel)
    return blurred


def apply_oblique_perspective(image: np.ndarray) -> np.ndarray:
    """Oblique perspective: Camera angled at ~35-45 degrees relative to vehicle lane."""
    h, w = image.shape[:2]
    pts_src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    # Skew top-right and bottom-right inward (trapezoidal perspective)
    pts_dst = np.float32([
        [int(w * 0.08), int(h * 0.12)],
        [int(w * 0.92), int(h * 0.02)],
        [int(w * 0.82), int(h * 0.95)],
        [int(w * 0.02), int(h * 0.88)],
    ])
    matrix = cv2.getPerspectiveTransform(pts_src, pts_dst)
    warped = cv2.warpPerspective(image, matrix, (w, h), borderValue=(30, 30, 32))
    return warped


def generate_benchmark_dataset(num_per_condition: int = 20) -> Dict[str, List[Dict]]:
    """
    Generate dataset grouped by environmental conditions.
    
    Returns:
        dict: {
            "daytime_clear": [ {"plate": "...", "image": np.ndarray, "bbox": [...]}, ... ],
            "night_low_light": [...],
            "rain_wet": [...],
            "motion_blur": [...],
            "oblique_angle": [...]
        }
    """
    dataset = {
        "daytime_clear": [],
        "night_low_light": [],
        "rain_wet": [],
        "motion_blur": [],
        "oblique_angle": [],
    }

    for i in range(num_per_condition):
        plate_str = TEST_PLATES[i % len(TEST_PLATES)]
        base_patch = render_base_plate(plate_str)
        frame, bbox = embed_in_vehicle_frame(base_patch)

        # Generate each condition
        img_day = apply_daytime_clean(frame)
        img_night = apply_night_low_light(frame)
        img_rain = apply_rain_wet(frame)
        img_blur = apply_motion_blur(frame, kernel_size=17)
        img_oblique = apply_oblique_perspective(frame)

        dataset["daytime_clear"].append({"plate": plate_str, "image": img_day, "bbox": bbox})
        dataset["night_low_light"].append({"plate": plate_str, "image": img_night, "bbox": bbox})
        dataset["rain_wet"].append({"plate": plate_str, "image": img_rain, "bbox": bbox})
        dataset["motion_blur"].append({"plate": plate_str, "image": img_blur, "bbox": bbox})
        dataset["oblique_angle"].append({"plate": plate_str, "image": img_oblique, "bbox": bbox})

    return dataset
