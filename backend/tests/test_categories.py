"""Tests for the category taxonomy and rules classifier (Decision 8)."""

from backend.categories import (
    LawCategory,
    all_categories,
    classify,
    normalise_category,
)


def test_vocabulary_is_stable_and_includes_other():
    cats = all_categories()
    assert LawCategory.CRIMINAL in cats
    assert LawCategory.OTHER in cats


def test_classify_returns_other_when_nothing_matches():
    assert classify("the quick brown fox jumped") == [LawCategory.OTHER]


def test_classify_detects_criminal_law():
    result = classify(
        "Whoever commits the offence of homicide is guilty of a felony and subject to sentencing.",
    )
    assert LawCategory.CRIMINAL in result


def test_title_outweighs_body_signal():
    # Body mentions driving once; title screams criminal — criminal should rank first.
    result = classify(
        text="The accused was driving at the time of the offence.",
        title="Criminal Code — Homicide and Assault",
    )
    assert result[0] is LawCategory.CRIMINAL


def test_classify_is_multi_label_and_capped():
    result = classify(
        text=(
            "This motor vehicle traffic statute creates an offence for impaired "
            "driving and sets out the criminal penalty and licence suspension."
        ),
        max_categories=2,
    )
    assert len(result) <= 2
    assert LawCategory.TRAFFIC in result or LawCategory.CRIMINAL in result


def test_hints_contribute_to_classification():
    result = classify(
        text="General provisions apply.",
        hints=["Income Tax Act", "taxation"],
    )
    assert LawCategory.TAX in result


def test_normalise_category_round_trips_and_rejects_unknown():
    assert normalise_category("Criminal") is LawCategory.CRIMINAL
    assert normalise_category(" tax ") is LawCategory.TAX
    assert normalise_category("nonsense") is None
