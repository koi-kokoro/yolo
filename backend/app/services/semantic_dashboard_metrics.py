"""Derive transparent dashboard proxies from semantic class statistics.

The deployed ONNX contract returns a class-id mask rather than per-pixel
probabilities. These metrics are heuristics, not model confidence estimates.
"""

from __future__ import annotations

import math
from typing import Any


CLASS_NAMES = (
    "background",
    "building",
    "road",
    "water",
    "barren",
    "forest",
    "agricultural",
)

# Audited converted_label_pixels 0..6 in reports/audit.json.
LOVEDA_REFERENCE_PIXELS = (
    1_525_959_012,
    404_299_316,
    213_710_339,
    362_297_559,
    207_131_990,
    534_690_631,
    1_001_084_037,
)

# Baseline full-validation per-class IoU in artifacts/.../metrics.json.
BASELINE_CLASS_IOU = (
    0.5363012471,
    0.5786635588,
    0.5395743088,
    0.6322480688,
    0.3554091462,
    0.3776383919,
    0.5358200240,
)


def _normalise(values: list[float] | tuple[float, ...]) -> list[float]:
    total = float(sum(values))
    if total <= 0:
        return [0.0 for _ in values]
    return [float(value) / total for value in values]


def _kl_divergence(left: list[float], right: list[float]) -> float:
    return sum(
        p * math.log2(p / q)
        for p, q in zip(left, right)
        if p > 0 and q > 0
    )


def _js_distance(left: list[float], right: list[float]) -> float:
    midpoint = [(p + q) / 2 for p, q in zip(left, right)]
    divergence = 0.5 * _kl_divergence(left, midpoint) + 0.5 * _kl_divergence(
        right, midpoint
    )
    return math.sqrt(max(0.0, min(1.0, divergence)))


def derive_semantic_sample(
    class_statistics: list[dict[str, Any]], sample_name: str
) -> dict[str, Any] | None:
    """Build one serialisable dashboard sample from semantic pixel counts."""
    counts_by_name = {
        str(item.get("name")): max(0, int(item.get("pixel_count") or 0))
        for item in class_statistics
        if item.get("name")
    }
    counts = [counts_by_name.get(name, 0) for name in CLASS_NAMES]
    total_pixels = sum(counts)
    if total_pixels <= 0:
        return None

    ratios = _normalise(counts)
    reference = _normalise(LOVEDA_REFERENCE_PIXELS)
    distance = _js_distance(ratios, reference)
    anomaly_score = round(distance * 100, 1)

    reference_iou = sum(
        ratio * class_iou for ratio, class_iou in zip(ratios, BASELINE_CLASS_IOU)
    )
    reliability_score = round(
        max(0.0, min(1.0, reference_iou * (1.0 - 0.35 * distance))) * 100,
        1,
    )

    if anomaly_score < 25:
        domain_status = "in_domain"
    elif anomaly_score < 45:
        domain_status = "attention"
    else:
        domain_status = "out_of_domain"

    if anomaly_score >= 45 or reliability_score < 40:
        review_level = "high"
    elif anomaly_score >= 25 or reliability_score < 50:
        review_level = "medium"
    else:
        review_level = "low"

    return {
        "name": sample_name,
        "anomaly_score": anomaly_score,
        "reliability_score": reliability_score,
        "domain_status": domain_status,
        "review_level": review_level,
        "total_pixels": total_pixels,
        "class_ratios": {
            name: round(ratio, 6) for name, ratio in zip(CLASS_NAMES, ratios)
        },
    }


def build_semantic_metrics(samples: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    """Wrap valid samples in a versioned payload for DetectionTask storage."""
    valid = [sample for sample in samples if sample]
    if not valid:
        return None
    return {
        "version": 1,
        "method": "loveda_prior_jsd_weighted_iou_proxy",
        "samples": valid,
    }
