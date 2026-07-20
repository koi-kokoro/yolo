"""Tests for semantic dashboard proxy metrics."""

from app.services.semantic_dashboard_metrics import (
    CLASS_NAMES,
    LOVEDA_REFERENCE_PIXELS,
    build_semantic_metrics,
    derive_semantic_sample,
)


def _statistics(counts):
    return [
        {"name": name, "pixel_count": count}
        for name, count in zip(CLASS_NAMES, counts)
    ]


def test_reference_distribution_is_in_domain():
    sample = derive_semantic_sample(
        _statistics(LOVEDA_REFERENCE_PIXELS), "reference.png"
    )

    assert sample is not None
    assert sample["anomaly_score"] == 0
    assert sample["domain_status"] == "in_domain"
    assert 0 <= sample["reliability_score"] <= 100
    assert sum(sample["class_ratios"].values()) == 1


def test_single_class_prediction_requires_attention():
    sample = derive_semantic_sample(
        _statistics([0, 1_000_000, 0, 0, 0, 0, 0]), "building.png"
    )

    assert sample is not None
    assert sample["anomaly_score"] >= 45
    assert sample["domain_status"] == "out_of_domain"
    assert sample["review_level"] == "high"


def test_empty_statistics_are_not_persisted():
    assert derive_semantic_sample([], "empty.png") is None
    assert build_semantic_metrics([None]) is None
