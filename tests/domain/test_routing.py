from astrafeed.domain import (
    Channel,
    Group,
    Interest,
    InterestMode,
)
from astrafeed.domain.routing import resolve_effective_interests

G = [Interest("global topic")]
GR = [Interest("group topic")]
CH = [Interest("channel topic")]


def test_extend_appends_global_group_channel():
    chan = Channel("@c", "C", interest_mode=InterestMode.EXTEND)
    grp = Group("G", interest_mode=InterestMode.EXTEND)
    eff = resolve_effective_interests(G, grp, GR, chan, CH)
    assert [i.text for i in eff] == ["global topic", "group topic", "channel topic"]


def test_group_replace_drops_global():
    chan = Channel("@c", "C", interest_mode=InterestMode.EXTEND)
    grp = Group("G", interest_mode=InterestMode.REPLACE)
    eff = resolve_effective_interests(G, grp, GR, chan, CH)
    assert [i.text for i in eff] == ["group topic", "channel topic"]


def test_channel_replace_drops_inherited():
    chan = Channel("@c", "C", interest_mode=InterestMode.REPLACE)
    grp = Group("G", interest_mode=InterestMode.EXTEND)
    eff = resolve_effective_interests(G, grp, GR, chan, CH)
    assert [i.text for i in eff] == ["channel topic"]


def test_no_group_extends_global_and_channel():
    chan = Channel("@c", "C", interest_mode=InterestMode.EXTEND)
    eff = resolve_effective_interests(G, None, [], chan, CH)
    assert [i.text for i in eff] == ["global topic", "channel topic"]
