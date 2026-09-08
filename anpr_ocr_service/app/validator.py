"""
validator.py — Post-processing and regex format validation for license plates.

Key responsibilities:
1. Normalize plate text (strip noise, uppercase, remove hyphens/spaces).
2. Validate against regional regex standards (defaults to Indian standard, configurable).
3. Apply character confusion heuristics (0 <-> O, 1 <-> I, 8 <-> B) based on expected slot types.
4. Flag detections below threshold or format violations as 'needs_review'.
"""

import re
from typing import Dict, List, Optional, Tuple
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings


# Common OCR substitution confusion sets
ALPHA_TO_NUM = str.maketrans({
    "O": "0", "o": "0", "D": "0", "Q": "0",
    "I": "1", "i": "1", "L": "1", "l": "1",
    "Z": "2", "z": "2",
    "E": "3",
    "A": "4",
    "S": "5", "s": "5",
    "G": "6", "b": "6",
    "T": "7",
    "B": "8",
    "q": "9", "g": "9",
})

NUM_TO_ALPHA = str.maketrans({
    "0": "O",
    "1": "I",
    "2": "Z",
    "3": "E",
    "4": "A",
    "5": "S",
    "6": "G",
    "7": "T",
    "8": "B",
})


class PlateValidator:
    """Validates and rectifies recognized license plate character sequences."""

    def __init__(self, regex_pattern: Optional[str] = None, threshold: Optional[float] = None):
        self.pattern_str = regex_pattern or settings.PLATE_REGEX
        self.regex = re.compile(self.pattern_str)
        self.threshold = threshold if threshold is not None else settings.CONFIDENCE_THRESHOLD

    def clean_text(self, text: str) -> str:
        """Strip non-alphanumeric noise, spaces, and hyphens; uppercase."""
        if not text:
            return ""
        return re.sub(r"[^A-Za-z0-9]", "", text).upper()

    def attempt_slot_heuristic_correction(self, raw_plate: str) -> str:
        """
        For standard Indian plate format (State(2) + District(1-2) + Series(1-3) + Number(4)):
        Attempts slot-wise character correction if exact regex fails.
        """
        plate = self.clean_text(raw_plate)
        if len(plate) < 8 or len(plate) > 11:
            return plate

        # State prefix (first 2 chars must be alphabetic)
        state_part = plate[:2].translate(NUM_TO_ALPHA)
        
        # Suffix (last 4 chars must be digits)
        num_part = plate[-4:].translate(ALPHA_TO_NUM)

        # Middle portion (district + series)
        mid_part = plate[2:-4]
        # District is usually 1-2 digits, followed by 1-3 letters
        # Look for the boundary
        corrected_mid = []
        parsing_digits = True
        for ch in mid_part:
            if parsing_digits:
                if ch.isdigit() or ch in "OIBSZ":
                    corrected_mid.append(ch.translate(ALPHA_TO_NUM))
                else:
                    parsing_digits = False
                    corrected_mid.append(ch.translate(NUM_TO_ALPHA))
            else:
                corrected_mid.append(ch.translate(NUM_TO_ALPHA))

        reconstructed = state_part + "".join(corrected_mid) + num_part
        return reconstructed

    def validate(self, raw_text: str, confidence: float) -> Dict:
        """
        Evaluate recognized text and confidence.
        
        Returns:
            dict containing:
                plate: Final validated/corrected plate string
                raw_plate: Original OCR output
                confidence: Aggregated confidence score
                is_format_valid: Boolean indicating regex match
                needs_review: Boolean flag for human-in-the-loop review
                review_reasons: List of reasons if flagged for review
        """
        cleaned = self.clean_text(raw_text)
        reasons: List[str] = []

        # Check confidence threshold
        if confidence < self.threshold:
            reasons.append(f"Confidence score {confidence:.2f} is below review threshold {self.threshold:.2f}")

        # Check format validity
        is_valid = bool(self.regex.match(cleaned))
        final_plate = cleaned

        if not is_valid:
            # Try slot-based correction
            corrected = self.attempt_slot_heuristic_correction(cleaned)
            if self.regex.match(corrected):
                final_plate = corrected
                is_valid = True
            else:
                reasons.append(f"Plate format '{cleaned}' does not match regex pattern '{self.pattern_str}'")

        needs_review = len(reasons) > 0

        return {
            "plate": final_plate,
            "raw_plate": cleaned,
            "confidence": round(confidence, 4),
            "is_format_valid": is_valid,
            "needs_review": needs_review,
            "review_reasons": reasons,
        }
