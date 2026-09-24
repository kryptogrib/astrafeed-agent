from types import SimpleNamespace as NS

from astrafeed.adapters.source.telegram import public_username


def test_plain_username():
    assert public_username(NS(username="markettwits")) == "markettwits"


def test_collectible_usernames_use_first_active():
    # Telegram leaves `username` empty for channels with several (Fragment) handles.
    entity = NS(
        username=None,
        usernames=[NS(username="old", active=False), NS(username="crypto_hd", active=True)],
    )
    assert public_username(entity) == "crypto_hd"


def test_private_channel_has_no_username():
    assert public_username(NS(username=None, usernames=None)) is None
    assert public_username(NS()) is None
