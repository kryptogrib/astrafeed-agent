from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, TypeVar

from telethon.errors import (
    FloodWaitError,
    MsgIdInvalidError,
    PeerIdInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import Channel as TelegramChannel
from telethon.tl.types import PeerChannel

from astrafeed.domain import (
    Channel,
    CommentFetch,
    CommentStatus,
    DiscussionComment,
    Item,
    Subscription,
)
from astrafeed.domain.ingestion import SourceUnavailableError, require_public_source_ref
from astrafeed.domain.refs import normalize_channel_ref
from astrafeed.ports.source import PublicChannel, WindowRead

_log = logging.getLogger(__name__)

_T = TypeVar("_T")


class _Access(str, Enum):
    """What discovery learned about an item's linked discussion group."""

    READABLE = "readable"  # a linked megagroup exists (joined / member / visible)
    NONE = "none"  # Telegram exposes no linked discussion
    UNKNOWN = "unknown"  # discovery skipped (budget) or failed softly


# Invalid-peer family: Telegram answers GetRepliesRequest with MSG_ID_INVALID /
# PEER_ID_INVALID when the post has NO linked discussion group to read. That is a
# permanent fact about the post, so it must be TERMINAL (UNAVAILABLE), not a
# retryable ERROR — re-fetching it on every run can only ever fail the same way.
_TERMINAL_FETCH_ERRORS = (MsgIdInvalidError, PeerIdInvalidError)


def _classify_fetch(*, access: _Access, raw_count: int, error: Exception | None) -> CommentStatus:
    """Map a fetch outcome to a cacheable status.

    The whole point is to NOT let a transient failure masquerade as the stable
    truth "no comments": a flood-wait or error is retryable, a missing discussion
    is permanently unavailable, and a reachable thread with no replies is empty.

    An invalid-peer error (no linked discussion) is terminal UNAVAILABLE, not a
    retryable ERROR. Everything but one case is forced by the evidence. The
    judgment call is (UNKNOWN access, zero replies, no error): discovery was
    skipped (budget) or failed softly, yet we read nothing. We treat it as EMPTY —
    matching the legacy "0 replies = no comments" behavior so a fresh cache build
    doesn't re-fetch every quiet post forever. The cost is that a post we couldn't
    actually reach is recorded as having no discussion; acceptable for a debug harness.
    """
    if isinstance(error, FloodWaitError):
        return CommentStatus.FLOOD_WAIT
    if isinstance(error, _TERMINAL_FETCH_ERRORS):
        return CommentStatus.UNAVAILABLE
    if error is not None:
        return CommentStatus.ERROR
    if raw_count > 0:
        return CommentStatus.FETCHED
    if access is _Access.NONE:
        return CommentStatus.UNAVAILABLE
    # READABLE or UNKNOWN with zero replies -> empty (see docstring).
    return CommentStatus.EMPTY


def _reason_for(*, status: CommentStatus, access: _Access, error: Exception | None) -> str:
    """A short, self-explanatory note for why a fetch ended in ``status``.

    Persisted alongside the status so a ``comments.jsonl`` record explains itself
    without cross-referencing ``trace.log``. The Telethon error text carries the
    invalid-peer signature ("The message ID used in the peer was invalid …").
    """
    if error is not None:
        return str(error)
    if status is CommentStatus.UNAVAILABLE:
        return "no linked discussion group"
    return ""


def dialog_to_subscription(dialog: Any) -> Subscription:
    """Map a Telethon dialog to a Subscription. Pure: no network, no Telethon
    import. Public channels get an ``@username`` ref; private ones (no username)
    fall back to an id-based ref so they remain referenceable."""
    entity = dialog.entity
    username = getattr(entity, "username", None)
    entity_id = getattr(entity, "id", None)
    ref = f"@{username}" if username else f"id:{entity_id}"
    title = dialog.name or getattr(entity, "title", "") or ref
    # Broadcast channels have ``broadcast=True``; supergroups (megagroups) carry
    # ``broadcast=False`` while still satisfying Telethon's ``is_channel``.
    kind = "channel" if getattr(entity, "broadcast", False) else "chat"
    return Subscription(telegram_ref=ref, title=title, telegram_id=entity_id, kind=kind)


def message_to_item(
    msg: Any, *, channel_ref: str, channel_username: str, channel_name: str | None = None
) -> Item:
    """Map a Telethon Message to a unified Item. Pure: no network, no Telethon import."""
    # Private channels (id-based ref) have no public @handle, so a
    # ``t.me/<username>/<id>`` link would be malformed. Telegram's canonical
    # private-post link is ``t.me/c/<numeric-id>/<msg.id>``.
    if channel_ref.startswith("id:"):
        link = f"https://t.me/c/{channel_ref.removeprefix('id:')}/{msg.id}"
    else:
        link = f"https://t.me/{channel_username}/{msg.id}"
    forwarded_from_ref, forwarded_from_title = _forward_origin(msg)
    return Item(
        channel_ref=channel_ref,
        external_id=str(msg.id),
        text=msg.message or "",
        link=link,
        timestamp=msg.date,
        has_media=msg.media is not None,
        forwarded_from_ref=forwarded_from_ref,
        forwarded_from_title=forwarded_from_title,
        channel_name=channel_name,
    )


def _forward_origin(msg: Any) -> tuple[str | None, str | None]:
    """Read the forward origin only when it is a public channel.

    Telethon resolves a channel origin into ``forward.chat`` (with a ``title``);
    user/anonymous/named-only forwards leave it ``None`` and carry no title. We
    require both a ``username`` and a ``title`` so forwards from users (which
    expose a username but no channel title) and usernameless channels yield
    ``None`` — leaving the Item without a Source Lead signal.
    """
    forward = getattr(msg, "forward", None)
    if forward is None:
        return None, None
    chat = getattr(forward, "chat", None)
    username = getattr(chat, "username", None)
    title = getattr(chat, "title", None)
    if username and title:
        return normalize_channel_ref(username), title
    return None, None


def _peer_key(peer: Any) -> str | None:
    for kind in ("channel", "chat", "user"):
        value = getattr(peer, f"{kind}_id", None)
        if value is not None:
            return f"{kind}:{value}"
    if getattr(peer, "megagroup", False):
        return f"channel:{peer.id}"
    return None


def message_to_comment(
    msg: Any,
    *,
    channel_username: str,
    peer_id: str | None = None,
    thread_root_id: str | None = None,
) -> DiscussionComment:
    """Map a Telethon discussion Message to a lightweight comment.

    `link` is left empty for now: a comment's `msg.id` lives in the discussion
    *group*, so building `t.me/<channel>/<msg.id>` produced a wrong/404 URL. A
    correct thread URL (`t.me/<channel>/<post>?comment=<id>`) is a future change.

    ``reply_to_id``/``author_key``/``edited_at`` are read defensively via
    ``getattr`` chains since Telethon message shapes vary (a message with no
    reply has ``msg.reply_to is None``; a message from a channel-as-author has
    no ``from_id``). Missing values map to ``None`` rather than raising.
    """
    reply_to = getattr(msg, "reply_to", None)
    reply_to_msg_id = getattr(reply_to, "reply_to_msg_id", None) if reply_to is not None else None
    from_id = getattr(msg, "from_id", None)
    author_user_id = getattr(from_id, "user_id", None) if from_id is not None else None
    return DiscussionComment(
        external_id=str(msg.id),
        text=msg.message or "",
        timestamp=msg.date,
        link="",
        reply_to_id=str(reply_to_msg_id) if reply_to_msg_id is not None else None,
        author_key=str(author_user_id) if author_user_id is not None else None,
        edited_at=getattr(msg, "edit_date", None),
        peer_id=_peer_key(getattr(msg, "peer_id", None)) or peer_id,
        thread_root_id=thread_root_id,
        parent_peer_id=(
            _peer_key(getattr(reply_to, "reply_to_peer_id", None))
            or _peer_key(getattr(msg, "peer_id", None))
            or peer_id
        )
        if reply_to_msg_id is not None
        else None,
        has_media=getattr(msg, "media", None) is not None,
    )


def _discussion_root_id(discussion: Any) -> int | None:
    """The last discovery message is the root (core.telegram.org/api/discussion)."""
    for msg in reversed(getattr(discussion, "messages", None) or []):
        mid = getattr(msg, "id", None)
        if mid is not None:
            return int(mid)
    return None


def _parent_belongs_to_thread(
    parent_msg: Any,
    *,
    discussion_root_id: int | None,
    known_ids: set[str],
) -> bool:
    """Return True when a backfilled parent is part of the current discussion.

    Foreign messages that happen to share the discussion-group peer (wrong
    thread / unrelated id) must not be mixed into the snapshot.
    """
    parent_id = getattr(parent_msg, "id", None)
    if discussion_root_id is not None and parent_id == discussion_root_id:
        return True
    reply_to = getattr(parent_msg, "reply_to", None)
    if reply_to is None:
        return False
    top_id = getattr(reply_to, "reply_to_top_id", None)
    reply_msg_id = getattr(reply_to, "reply_to_msg_id", None)
    if discussion_root_id is not None:
        if top_id is not None and int(top_id) != discussion_root_id:
            return False
        if top_id is not None and int(top_id) == discussion_root_id:
            return True
        if reply_msg_id is not None and int(reply_msg_id) == discussion_root_id:
            return True
    return reply_msg_id is not None and str(reply_msg_id) in known_ids


def _entity_ref(telegram_ref: str) -> str | PeerChannel:
    if telegram_ref.startswith("id:"):
        return PeerChannel(int(telegram_ref.removeprefix("id:")))
    return telegram_ref


class TelegramSource:
    """Telethon userbot Source. The TelegramClient is injected (constructed in
    cli/composition root) so the core test suite never starts a live session."""

    def __init__(
        self,
        client: Any,
        *,
        backfill_window: timedelta = timedelta(hours=24),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        discussion_join_limit_per_run: int = 5,
    ) -> None:
        self._client = client
        self._backfill_window = backfill_window
        self._now = now
        self._joined_discussion_ids: set[int] = set()
        self._discussion_join_limit_per_run = discussion_join_limit_per_run
        self._discussion_joins_left = discussion_join_limit_per_run
        # In serve, one TelegramSource is shared across the poll pipeline, report
        # comment enrichment and the bot's list_subscribed_channels. On a drop they
        # can all see is_connected() == False at once; the lock + double-check
        # below keeps them from racing into concurrent connect() calls.
        self._reconnect_lock = asyncio.Lock()

    async def fetch_item(self, item: Item) -> Item | None:
        """Reread one original post without changing collection watermarks."""

        async def read() -> Item | None:
            entity = await self._client.get_entity(_entity_ref(item.channel_ref))
            message = await self._client.get_messages(entity, ids=int(item.external_id))
            if message is None or getattr(message, "date", None) is None:
                return None
            return message_to_item(
                message,
                channel_ref=item.channel_ref,
                channel_username=item.channel_ref.lstrip("@"),
                channel_name=item.channel_name,
            )

        return await self._with_reconnect(read)

    def reset_discussion_join_budget(self) -> None:
        self._discussion_joins_left = self._discussion_join_limit_per_run

    async def _ensure_connected(self) -> None:
        """Revive a dropped Telethon session before issuing a request.

        Telethon's internal auto-reconnect can exhaust its retries and leave the
        client permanently disconnected — a single network blip then poisons every
        subsequent fetch with `ConnectionError: Cannot send requests while
        disconnected`. `is_connected()` is a cheap local bool, so the fast path is
        free when healthy; reconnect happens under a lock with a re-check so
        concurrent callers connect at most once. The StringSession is already
        authorised, so `connect()` restores the session without a fresh login.
        """
        if self._client.is_connected():
            return
        async with self._reconnect_lock:
            if self._client.is_connected():  # another coroutine reconnected while we waited
                return
            _log.warning("telegram client disconnected; reconnecting")
            await self._client.connect()

    async def _with_reconnect(self, op: Callable[[], Awaitable[_T]]) -> _T:
        """Run a network op, retrying exactly once if the connection drops.

        Guards with `_ensure_connected()` first; if the op raises `ConnectionError`
        mid-flight, reconnect and retry one time. A second failure propagates so the
        orchestrator's per-channel handler logs and skips (next tick retries).
        """
        await self._ensure_connected()
        try:
            return await op()
        except ConnectionError:
            _log.warning("telegram connection lost mid-request; reconnecting and retrying once")
            await self._ensure_connected()
            return await op()

    async def fetch_new_items(self, channel: Channel, since: datetime | None) -> list[Item]:
        username = channel.telegram_ref.lstrip("@")
        floor = since if since is not None else self._now() - self._backfill_window
        _log.debug(
            "telegram fetch: ref=%s since=%s floor=%s backfill_hours=%.2f",
            channel.telegram_ref,
            since.isoformat() if since else None,
            floor.isoformat(),
            self._backfill_window.total_seconds() / 3600,
        )

        async def _run() -> list[Item]:
            entity = await self._client.get_entity(_entity_ref(channel.telegram_ref))
            items: list[Item] = []
            async for msg in self._client.iter_messages(entity, offset_date=floor, reverse=True):
                if msg.date <= floor:
                    continue
                items.append(
                    message_to_item(
                        msg,
                        channel_ref=channel.telegram_ref,
                        channel_username=username,
                        channel_name=channel.name,
                    )
                )
            return items

        items = await self._with_reconnect(_run)
        _log.debug("telegram fetch: ref=%s returned=%d", channel.telegram_ref, len(items))
        return items

    async def resolve_public_ref(self, ref: str) -> int:
        return (await self.resolve_public_channel(ref)).telegram_id

    async def resolve_public_channel(self, ref: str) -> PublicChannel:
        """Resolve public channel identity and verify history access without joining."""
        public = require_public_source_ref(ref)

        async def _run() -> PublicChannel:
            entity = await self._client.get_entity(public)
            if not isinstance(entity, TelegramChannel) or not entity.username:
                raise SourceUnavailableError("channel is not a public source")
            # An entity cache hit alone does not establish history access.
            await self._client.get_messages(entity, limit=1)
            return PublicChannel(int(entity.id), f"@{entity.username}", entity.title)

        try:
            return await self._with_reconnect(_run)
        except SourceUnavailableError:
            raise
        except Exception as exc:
            raise SourceUnavailableError(
                "Cannot read public channel; check the link or retry"
            ) from exc

    async def read_window(
        self,
        telegram_id: int,
        start: datetime,
        end: datetime,
        *,
        max_posts: int,
        channel_ref: str | None = None,
        after_id: int | None = None,
    ) -> WindowRead:
        """Read ``[start, end]`` (inclusive) with a post cap. Never opens a DB txn."""

        async def _run() -> WindowRead:
            try:
                entity = await self._client.get_entity(_entity_ref(f"id:{telegram_id}"))
                username = getattr(entity, "username", None)
                if not username:
                    return WindowRead(
                        items=(),
                        truncated=False,
                        error="channel is not a public source",
                    )
                ref = channel_ref or f"@{username}"
                items: list[Item] = []
                truncated = False
                async for msg in self._client.iter_messages(
                    entity,
                    offset_date=(
                        None
                        if after_id
                        else (start - timedelta(seconds=1) if start.microsecond == 0 else start)
                    ),
                    offset_id=after_id or 0,
                    reverse=True,
                ):
                    if getattr(msg, "date", None) is None:
                        continue
                    if msg.date < start:
                        continue
                    if msg.date > end:
                        break
                    if max_posts > 0 and len(items) >= max_posts:
                        truncated = True
                        break
                    items.append(message_to_item(msg, channel_ref=ref, channel_username=username))
                return WindowRead(items=tuple(items), truncated=truncated)
            except FloodWaitError as e:
                seconds = int(getattr(e, "seconds", 0) or 0)
                return WindowRead(
                    items=(),
                    truncated=False,
                    error=str(e),
                    delayed_until=self._now() + timedelta(seconds=seconds),
                )
            except ConnectionError:
                raise
            except Exception as e:
                return WindowRead(items=(), truncated=False, error=str(e))

        return await self._with_reconnect(_run)

    async def list_subscribed_channels(self) -> list[Subscription]:
        async def _run() -> list[Subscription]:
            subs: list[Subscription] = []
            async for dialog in self._client.iter_dialogs():
                if not getattr(dialog, "is_channel", False):
                    continue
                subs.append(dialog_to_subscription(dialog))
            return subs

        return await self._with_reconnect(_run)

    async def fetch_comments(self, item: Item, *, limit: int) -> list[DiscussionComment]:
        """Fetch Telegram discussion comments for a channel Item (``DiscussionReader``).

        Thin wrapper over :meth:`fetch_comments_detailed` for the production path,
        which only needs the comments. Unavailable/closed discussions return [] so
        Report delivery never depends on this enrichment.
        """
        return list((await self.fetch_comments_detailed(item, limit=limit)).comments)

    async def fetch_comments_detailed(
        self, item: Item, *, limit: int, parent_limit: int = 0
    ) -> CommentFetch:
        """Fetch comments and report *why* the result is what it is.

        Unlike :meth:`fetch_comments`, this distinguishes a genuinely empty thread
        from a transient failure (flood-wait/error) or a missing discussion, so an
        offline cache won't record a rate-limit as the stable truth "no comments".

        ``parent_limit`` bounds an additional budget spent backfilling comments
        that are referenced via ``reply_to_id`` but weren't already among the
        ``limit`` main comments collected. Each backfill fetch addresses the
        resolved *discussion-group* entity (from ``_discover_discussion_access``),
        not the origin channel entity used to resolve ``item`` — ``get_messages``
        is a direct by-ID lookup with no server-side redirect, unlike
        ``iter_messages(..., reply_to=...)``, whose ``GetRepliesRequest`` Telegram
        transparently resolves against the linked group. If the discussion group
        couldn't be resolved (discovery wasn't run, or found nothing), backfill
        isn't attempted at all and every referenced parent is recorded as missing
        rather than guessed at. A parent that fails to fetch (error, or a
        "not found" result) is recorded in ``missing_parent_ids`` with
        ``context_incomplete=True`` — it is never silently treated as absent.
        Parents left unfetched purely because ``parent_limit`` ran out are
        likewise recorded in ``missing_parent_ids``, and additionally flip
        ``possibly_truncated=True`` since we know context is missing but didn't
        even try to get it. ``possibly_truncated`` is also set when the main
        collection hits ``limit`` exactly, since that's not a definitive "that's
        everything" signal.

        Empty messages without media are dropped here — deliberately
        NOT the legacy ``min_chars=40`` filter, which stays a report-composition
        concern (see ``report/service.py``), not an adapter-level one.
        """
        try:
            msg_id = int(item.external_id)
        except ValueError:
            return CommentFetch(
                status=CommentStatus.UNAVAILABLE,
                limit=limit,
                reason="external_id is not a numeric message id",
            )
        channel_username = item.channel_ref.lstrip("@")
        access = _Access.UNKNOWN
        discussion_entity: Any | None = None
        discussion_root_id: int | None = None
        comments: list[DiscussionComment] = []
        error: Exception | None = None
        cancelled: asyncio.CancelledError | None = None
        missing_parent_ids: list[str] = []
        parent_issues: dict[str, str] = {}
        discussion_peer_id: str | None = None
        parent_truncated = False
        raw_count = 0
        pending: dict[str, Any] = {}
        try:
            # Best-effort enrichment: revive a dropped client so comments resume
            # after a reconnect, but no retry/propagation here.
            await self._ensure_connected()
            entity = await self._client.get_entity(_entity_ref(item.channel_ref))
            # Root discovery is required even with no join or parent budget.
            # The join budget gates only JoinChannelRequest inside discovery.
            (
                access,
                discussion_entity,
                discussion_root_id,
            ) = await self._discover_discussion_access(entity, msg_id)
            discussion_peer_id = _peer_key(discussion_entity)
            root_id = str(discussion_root_id) if discussion_root_id is not None else None

            def convert(message: Any) -> DiscussionComment:
                return message_to_comment(
                    message,
                    channel_username=channel_username,
                    peer_id=discussion_peer_id,
                    thread_root_id=root_id,
                )

            async for msg in self._client.iter_messages(entity, reply_to=msg_id, limit=limit):
                raw_count += 1
                if str(msg.id) == root_id:
                    continue
                comment = convert(msg)
                if discussion_peer_id and comment.peer_id != discussion_peer_id:
                    continue
                if not comment.text.strip() and not comment.has_media:
                    continue
                if not comment.text.strip():
                    parent_issues[comment.external_id] = "nontext"
                comments.append(comment)

            if parent_limit > 0:
                known_ids = {c.external_id for c in comments}
                visited = known_ids | ({root_id} if root_id else set())
                queue = sorted(
                    {c.reply_to_id for c in comments if c.reply_to_id} - visited,
                    key=int,
                )
                # Only same-peer links can be resolved with this group's entity.
                foreign_ids = {
                    c.reply_to_id
                    for c in comments
                    if c.reply_to_id and c.parent_peer_id != discussion_peer_id
                }
                budget = parent_limit
                while queue:
                    pid = queue.pop(0)
                    if pid in visited:
                        continue
                    visited.add(pid)
                    if pid in foreign_ids or discussion_entity is None:
                        parent_issues[pid] = "membership_unverified"
                        continue
                    if budget <= 0:
                        parent_issues[pid] = "budget"
                        parent_truncated = True
                        continue
                    budget -= 1
                    try:
                        parent_msg = await self._client.get_messages(
                            discussion_entity, ids=int(pid)
                        )
                    except FloodWaitError:
                        parent_issues[pid] = "fetch_error"
                        raise
                    except Exception:  # per-parent failure must not discard the snapshot
                        parent_issues[pid] = "fetch_error"
                        continue
                    if (
                        parent_msg is None
                        or getattr(parent_msg, "id", None) != int(pid)
                        or getattr(parent_msg, "date", None) is None
                    ):
                        parent_issues[pid] = "not_returned"
                        continue
                    parent = convert(parent_msg)
                    top = getattr(getattr(parent_msg, "reply_to", None), "reply_to_top_id", None)
                    if (
                        parent.peer_id != discussion_peer_id
                        or (
                            top is not None
                            and discussion_root_id is not None
                            and top != discussion_root_id
                        )
                        or (parent.reply_to_id and parent.parent_peer_id != discussion_peer_id)
                    ):
                        parent_issues[pid] = "membership_unverified"
                        continue
                    pending[pid] = parent_msg
                    if parent.reply_to_id and parent.reply_to_id not in visited:
                        queue.append(parent.reply_to_id)
        except asyncio.CancelledError as e:
            cancelled = e
        except FloodWaitError as e:
            _log.warning(
                "telegram discussion flood wait: ref=%s msg=%s seconds=%s",
                item.channel_ref,
                item.external_id,
                getattr(e, "seconds", "?"),
            )
            error = e
        except Exception as e:
            _log.debug(
                "telegram discussion unavailable: ref=%s msg=%s err=%s",
                item.channel_ref,
                item.external_id,
                e,
            )
            error = e
        known_ids = {c.external_id for c in comments}
        # Resolve from proven members/root outwards, never trusting cycles
        # or an arbitrary same-group message as thread membership evidence.
        while pending:
            accepted = [
                pid
                for pid, msg in pending.items()
                if _parent_belongs_to_thread(
                    msg,
                    discussion_root_id=discussion_root_id,
                    known_ids=known_ids,
                )
            ]
            if not accepted:
                break
            for pid in accepted:
                parent = convert(pending.pop(pid))
                comments.append(parent)
                known_ids.add(pid)
                if not parent.text.strip():
                    parent_issues[pid] = "nontext"
        for pid in pending:
            parent_issues[pid] = "membership_unverified"
        interrupted = cancelled is not None or error is not None
        if interrupted:
            known_ids = {c.external_id for c in comments}
            root = str(discussion_root_id) if discussion_root_id is not None else None
            for comment in comments:
                if comment.reply_to_id and comment.reply_to_id not in known_ids | {root}:
                    parent_issues.setdefault(comment.reply_to_id, "fetch_error")
        missing_parent_ids = [pid for pid, why in parent_issues.items() if why != "nontext"]
        status = (
            CommentStatus.ERROR
            if cancelled is not None
            else _classify_fetch(access=access, raw_count=raw_count, error=error)
        )
        possibly_truncated = interrupted or parent_truncated or (raw_count >= limit > 0)
        fetch = CommentFetch(
            status=status,
            comments=tuple(comments),
            raw_count=raw_count,
            limit=limit,
            reason=_reason_for(status=status, access=access, error=error),
            context_incomplete=interrupted or bool(parent_issues),
            possibly_truncated=possibly_truncated,
            missing_parent_ids=tuple(missing_parent_ids),
            discussion_peer_id=discussion_peer_id,
            root_id=str(discussion_root_id) if discussion_root_id is not None else None,
            parent_issues=tuple(parent_issues.items()),
            collection_stop_reason=(
                "timeout"
                if cancelled is not None
                else "fetch_error"
                if error
                else "limit"
                if raw_count >= limit > 0
                else "parent_budget"
                if parent_truncated
                else "exhausted"
            ),
        )
        if cancelled is not None:
            cancelled.partial_fetch = fetch  # type: ignore[attr-defined]
            raise cancelled
        return fetch

    async def _discover_discussion_access(
        self, entity: Any, msg_id: int
    ) -> tuple[_Access, Any | None, int | None]:
        """Best-effort join for the linked discussion group, reporting what was found.

        Returns ``(NONE, None, None)`` when Telegram exposes no linked discussion,
        ``(READABLE, chat, root_id)`` when a linked megagroup exists (joined now,
        already a member, or visible) — ``chat`` is the resolved discussion-group
        entity itself, distinct from the origin channel ``entity`` passed in, and
        is what callers must address directly (e.g. ``get_messages`` for parent-
        comment backfill, which has no server-side channel-to-discussion
        redirect the way ``iter_messages(..., reply_to=...)`` does). ``root_id``
        is the discussion-root message id when present in the discovery response,
        used to reject foreign parents. Returns ``(UNKNOWN, None, None)`` when
        discovery itself failed softly. Join side-effects and budget accounting
        are unchanged.
        """
        try:
            discussion = await self._client(GetDiscussionMessageRequest(peer=entity, msg_id=msg_id))
        except FloodWaitError:
            # Let the caller back off — don't fall through to another Telegram
            # request (iter_messages) while already rate-limited.
            raise
        except Exception:
            return _Access.UNKNOWN, None, None
        root_id = _discussion_root_id(discussion)
        messages = getattr(discussion, "messages", None) or []
        root_peer = _peer_key(getattr(messages[-1], "peer_id", None)) if messages else None
        found_megagroup = False
        for chat in getattr(discussion, "chats", []) or []:
            chat_id = getattr(chat, "id", None)
            if chat_id is None or not getattr(chat, "megagroup", False):
                continue
            if root_peer is not None and _peer_key(chat) != root_peer:
                continue
            found_megagroup = True  # a linked discussion exists, joinable or not
            if chat_id in self._joined_discussion_ids:
                # Already a member (or already attempted): readable without budget.
                return _Access.READABLE, chat, root_id
            if self._discussion_joins_left <= 0:
                _log.info("telegram discussion join budget exhausted")
                return _Access.READABLE, chat, root_id
            try:
                await self._client(JoinChannelRequest(chat))
                self._joined_discussion_ids.add(chat_id)
                self._discussion_joins_left -= 1
                _log.info("joined telegram discussion group: id=%s", chat_id)
            except UserAlreadyParticipantError:
                # Already a member (e.g. joined in a previous process): record it
                # so we don't retry, and don't spend join budget we didn't use.
                self._joined_discussion_ids.add(chat_id)
            except FloodWaitError:
                raise
            except Exception as e:
                # A failed join (private/inaccessible group) still cost a
                # JoinChannelRequest round-trip. Count it against the budget and
                # remember the group so a report full of such posts can't fire an
                # unbounded stream of join attempts past discussion_join_limit_per_run.
                self._joined_discussion_ids.add(chat_id)
                self._discussion_joins_left -= 1
                _log.debug("could not join telegram discussion group id=%s: %s", chat_id, e)
            return _Access.READABLE, chat, root_id
        return (_Access.READABLE if found_megagroup else _Access.NONE), None, None
