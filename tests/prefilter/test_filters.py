from astrafeed.prefilter.filters import PrefilterConfig, prefilter
from tests.conftest import make_item


def test_min_length_drops_short():
    cfg = PrefilterConfig(min_length=5)
    items = [make_item("1", "hi"), make_item("2", "long enough")]
    assert [i.external_id for i in prefilter(items, cfg)] == ["2"]


def test_blacklist_keyword_drops():
    cfg = PrefilterConfig(blacklist_keywords=["spam"])
    items = [make_item("1", "buy spam now"), make_item("2", "real news")]
    assert [i.external_id for i in prefilter(items, cfg)] == ["2"]


def test_regex_drop():
    cfg = PrefilterConfig(drop_regexes=[r"^AD:"])
    items = [make_item("1", "AD: promo"), make_item("2", "news")]
    assert [i.external_id for i in prefilter(items, cfg)] == ["2"]


def test_empty_config_keeps_all():
    items = [make_item("1", "a"), make_item("2", "b")]
    assert len(prefilter(items, PrefilterConfig())) == 2
