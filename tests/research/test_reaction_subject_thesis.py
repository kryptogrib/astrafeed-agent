import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs" / "research"))

from author_thesis_extract import match_gold_to_extracted  # noqa: E402
from reaction_subject_thesis import _specific_ok, gold_author  # noqa: E402


def test_preliminary_gold_quotes_are_unique_slices_of_the_post():
    posts = gold_author(expected_only=False)
    assert posts, "label first"
    # overflow and expected together; every author quote must have been resolved
    assert all(t["quote"] and t["end"] > t["start"] for t in posts)


def test_class_match_without_mapped_id_is_not_a_specific_link():
    gold = {"linkable": True, "expected_gold_id": "gold:x:1"}
    pred = {"target": "author_thesis", "target_id": "th-new"}
    assert _specific_ok(pred, gold, {"gold:x:1": None}) is False
    assert _specific_ok(pred, gold, {"gold:x:1": "th-other"}) is False
    assert _specific_ok(pred, gold, {"gold:x:1": "th-new"}) is True
    assert _specific_ok(pred, {**gold, "linkable": False}, {"gold:x:1": "th-new"}) is False


def test_overlap_match_does_not_use_the_model_id():
    gold = [
        {
            "gold_id": "gold:x:1",
            "thread": "u",
            "quote": "ETH to 3k",
            "start": 2,
            "end": 11,
            "origin": "author",
        }
    ]
    extracted = [
        {
            "thesis_id": "th-stable",
            "quote": "I ETH to 3k now",
            "start": 0,
            "end": 15,
            "thread": "u",
        }
    ]
    assert match_gold_to_extracted(gold, extracted)["gold:x:1"] == "th-stable"
