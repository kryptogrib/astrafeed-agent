from __future__ import annotations

from collections.abc import Sequence

from astrafeed.domain.models import (
    Channel,
    Group,
    Interest,
    InterestMode,
)


def resolve_effective_interests(
    global_interests: Sequence[Interest],
    group: Group | None,
    group_interests: Sequence[Interest],
    channel: Channel,
    channel_interests: Sequence[Interest],
) -> list[Interest]:
    """Cascade Global -> Group -> Channel. REPLACE drops everything inherited."""
    inherited = list(global_interests)
    if group is not None:
        if group.interest_mode is InterestMode.REPLACE:
            inherited = list(group_interests)
        else:
            inherited = inherited + list(group_interests)
    if channel.interest_mode is InterestMode.REPLACE:
        return list(channel_interests)
    return inherited + list(channel_interests)
