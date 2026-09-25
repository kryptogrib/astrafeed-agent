"""HTML agenda and story pages rendered from a JSON payload; no scripts, inline CSS."""

from __future__ import annotations

from html import escape
from urllib.parse import quote, urlsplit, urlunsplit

from astrafeed.application.agenda_changes import comparison_lines
from astrafeed.application.agenda_text import (
    AGENDA_LEAD,
    CARD_QUOTES,
    EMPTY_AGENDA,
    channel_count,
    channel_links,
    comment_facts,
    count_text,
    coverage_text,
    duration_text,
    english_text,
    evidence_lines,
    growth_text,
    head_start,
    limitation_notes,
    meta_text,
    short_time,
    source_group,
    trust_line,
    utc_clock,
)

_PAGE_CSS = """
:root{--bg:#f7f6f2;--card:#fff;--ink:#1d1d1b;--muted:#6b6a64;--line:#e4e2da;--accent:#0b6bcb;
--up:#1a7f37;--warn:#fff4d6}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;
--muted:#a3a29b;--line:#34332f;--accent:#6cb2ff;--up:#56d17a;--warn:#3a3217}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 4px}.lead,.meta,footer{color:var(--muted)}
.lead{margin:0 0 12px}.meta{font-size:.9rem}
.note{background:var(--warn);border-radius:8px;padding:8px 12px;margin:12px 0}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;margin:16px 0}
article h2{font-size:1.2rem;margin:0 0 6px}h2 a{color:inherit;text-decoration:none}
h2 a:hover{text-decoration:underline}
.stat{font-weight:600}.up{color:var(--up)}a{color:var(--accent)}
blockquote{margin:10px 0;padding:2px 0 2px 12px;border-left:3px solid var(--line)}
blockquote cite{display:block;font-style:normal;color:var(--muted);font-size:.9rem}
ul{padding-left:20px}footer{font-size:.85rem;margin-top:24px}
.talk{border-top:1px dashed var(--line);margin-top:12px;padding-top:8px}
.talk ul{margin:4px 0}
details{color:var(--muted);font-size:.85rem}summary{cursor:pointer}
.sig{font-size:.92rem;margin:8px 0;padding:0;list-style:none}.sig li{margin:2px 0}
.conflict{background:var(--warn);border-radius:6px;padding:2px 6px}
.tl{position:relative;height:30px;margin:10px 4px 2px;border-top:2px solid var(--line)}
.tl a{position:absolute;top:-7px;width:12px;height:12px;margin-left:-6px;border-radius:50%;
background:var(--accent)}.tl a.echo{background:var(--card);border:2px solid var(--muted)}
.tl span{position:absolute;top:8px;font-size:.75rem;color:var(--muted);white-space:nowrap}
.src .echo{color:var(--muted)}
.source-group{display:flex;gap:10px;margin:4px 0}.source-group>span{min-width:85px;
color:var(--muted);font-weight:600}.source-group>div{flex:1}
"""


def _url(link: str) -> str:
    return escape(link) if link.startswith(("https://", "http://")) else "#"


def _html_original(item: dict, key: str = "quote") -> str:
    if not item.get("translation"):
        return ""
    return f"<details><summary>original</summary>{escape(item[key])}</details>"


def _html_quote(item: dict) -> str:
    return (
        f"<blockquote>“{escape(english_text(item))}”<cite>— "
        f'<a href="{_url(item["link"])}">{escape(item["channel"])}</a></cite>'
        f"{_html_original(item)}</blockquote>"
    )


def _html_timeline(card: dict) -> str:
    """Dots along the spread window: filled for originals, hollow for copies."""
    signals = card.get("signals")
    if not signals or len(signals["sources"]) < 2 or not signals["spread_minutes"]:
        return ""
    span = signals["spread_minutes"]
    dots = "".join(
        f'<a class="{"echo" if node["echo_of"] else ""}" '
        f'style="left:{node["minutes_after_first"] / span * 100:.1f}%" '
        f'href="{_url(node["link"])}" title="{escape(node["channel"])} '
        f'{escape(utc_clock(node["published_at"]))}"></a>'
        for node in signals["sources"]
    )
    first = signals["sources"][0]
    labels = (
        f'<span style="left:0">{escape(utc_clock(first["published_at"]))}</span>'
        f'<span style="right:0">+{escape(duration_text(span))}</span>'
    )
    return f'<div class="tl" aria-label="spread timeline">{dots}{labels}</div>'


def _html_card_head(card: dict, title_html: str) -> str:
    growth_class = ' class="up"' if isinstance(card["growth"], int) and card["growth"] > 0 else ""
    parts = [
        title_html,
        f'<p><span class="stat">{escape(count_text(card))}</span> · '
        f"<span{growth_class}>{escape(growth_text(card))}</span><br>"
        f'<span class="meta">{escape(meta_text(card))}</span></p>',
        f"<p>{escape(card['explanation'])}</p>",
    ]
    signal_lines = evidence_lines(card)
    if signal_lines:
        items = "".join(
            f"<li{' class=conflict' if line.startswith('⚠️') else ''}>{escape(line)}</li>"
            for line in signal_lines
        )
        parts.append(f'<ul class="sig">{items}</ul>')
    caveat = (card.get("signals") or {}).get("caveat_drop")
    if caveat:
        parts.append(
            '<div class="talk"><p><b>⚠️ Qualifier dropped in later wording</b> '
            f"(+{escape(duration_text(caveat['minutes_later']))})</p>"
            f"<blockquote>“{escape(caveat['before_quote'])}” <cite>— "
            f'<a href="{_url(caveat["before_link"])}">{escape(caveat["before_channel"])}</a>'
            "</cite></blockquote>"
            f"<blockquote>“{escape(caveat['after_quote'])}” <cite>— "
            f'<a href="{_url(caveat["after_link"])}">{escape(caveat["after_channel"])}</a>'
            "</cite></blockquote></div>"
        )
    parts.append(_html_timeline(card))
    sources = channel_links(card)
    if sources:
        groups: dict[str, list[str]] = {}
        for name, link, note in sources:
            item = f'<a href="{_url(link)}">{escape(name)}</a>'
            if note:
                item += (
                    f' <span class="{"echo" if "copy" in note else "meta"}">({escape(note)})</span>'
                )
            groups.setdefault(source_group(name, link), []).append(item)
        sections = "".join(
            f'<div class="source-group"><span>{label}</span><div>{" · ".join(group)}</div></div>'
            for label in ("Telegram", "X", "Reddit", "News sites", "Other sources")
            if (group := groups.get(label))
        )
        parts.append(f'<div class="src"><b>Sources</b>{sections}</div>')
    return "".join(parts)


def _html_discussion(card: dict, *, full: bool) -> str:
    discussion = card.get("discussion")
    if not discussion:
        return ""
    facts = comment_facts(discussion)
    if not facts and not discussion["points"]:
        return ""
    items = "".join(f"<li>{escape(point)}</li>" for point in discussion["points"])
    for fact, comment in facts:
        source = quote_html = ""
        if comment:
            source = (
                f' — <a href="{_url(comment["link"])}">'
                f"comments under {escape(comment['channel'])} post</a>"
            )
            if full:
                quote_html = (
                    f"<blockquote>“{escape(english_text(comment, 'text'))}”"
                    f"{_html_original(comment, 'text')}</blockquote>"
                )
        items += f"<li>{escape(fact)}{source}{quote_html}</li>"
    return (
        f'<div class="talk"><p><b>💬 From reader comments</b> '
        f"({discussion['comment_count']} comments, unverified)</p><ul>{items}</ul></div>"
    )


def _html_page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="description" content="Live crypto agenda with source links.">'
        f'<meta property="og:title" content="{escape(title)}">'
        '<meta property="og:description" content="Crypto stories with source quotes and links.">'
        '<link rel="icon" href="/favicon.ico" type="image/x-icon">'
        f"<title>{escape(title)}</title><style>{_PAGE_CSS}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def _html_status(payload: dict) -> str:
    notes = limitation_notes(payload)
    note = f'<p class="note">⚠️ {escape("; ".join(notes))}.</p>' if notes else ""
    published = payload.get("published_at")
    snapshot_time = (
        f"Last published snapshot: {short_time(published)}. "
        if published and payload["stale"]
        else ""
    )
    excluded = "Newer collection is not included in these counts. " if payload["stale"] else ""
    return (
        f'<p class="meta">Coverage in this snapshot: {escape(coverage_text(payload))}. '
        f"{escape(snapshot_time + excluded)}</p>{note}"
    )


def _html_source_posts(payload: dict) -> str:
    posts = payload.get("source_posts") or {}
    if not any(posts.values()):
        return ""
    groups = []
    for source, label in (("x", "X"), ("reddit", "Reddit")):
        if not (group := posts.get(source)):
            continue
        items = "".join(
            f'<li><a href="{_url(post["link"])}">{escape(post["channel"])}</a> '
            f'<span class="meta">{escape(short_time(post["published_at"]))}</span>: '
            f"<b>{escape(post['title'])}</b>"
            + (f" — {escape(post['text'])}" if post["text"] != post["title"] else "")
            + "</li>"
            for post in group
        )
        groups.append(f"<h3>{label}</h3><ul>{items}</ul>")
    return (
        "<section><h2>Fresh posts from X and Reddit</h2>"
        '<p class="meta">Single-source posts; not independent confirmation.</p>'
        + "".join(groups)
        + "</section>"
    )


def _html_feed_directory(rss_feeds: list[str], reddit_feeds: list[str]) -> str:
    if not rss_feeds and not reddit_feeds:
        return ""
    news_links = ""
    for feed in rss_feeds:
        parsed = urlsplit(feed)
        host = parsed.hostname or ""
        if host == "feeds.bloomberg.com":
            site = "https://www.bloomberg.com/crypto"
            label = "bloomberg.com"
        else:
            path = "/crypto" if host in {"ft.com", "www.ft.com"} else "/"
            site = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
            label = host.removeprefix("www.")
        news_links += (
            f'<li><a href="{_url(site)}">{escape(label)}</a> '
            f'<a class="meta" href="{_url(feed)}">RSS</a></li>'
        )
    reddit_links = ""
    for feed in reddit_feeds:
        parsed = urlsplit(feed)
        subreddit = parsed.path.split("/")[2] if parsed.path.startswith("/r/") else feed
        path = parsed.path.removesuffix(".rss")
        link = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
        reddit_links += f'<li><a href="{_url(link)}">r/{escape(subreddit)}</a></li>'
    news = f"<h3>News RSS</h3><ul>{news_links}</ul>" if news_links else ""
    reddit = f"<h3>Reddit</h3><ul>{reddit_links}</ul>" if reddit_links else ""
    return (
        f'<details class="feed-directory"><summary>Monitored feeds · '
        f"{len(rss_feeds)} news RSS · {len(reddit_feeds)} Reddit</summary>"
        "<p>These feeds are not evidence for the stories above. "
        "Story links point to the specific posts and articles used there.</p>"
        f"{news}{reddit}</details>"
    )


def render_agenda_html(
    payload: dict, *, rss_feeds: list[str] | None = None, reddit_feeds: list[str] | None = None
) -> str:
    snapshot = quote(payload["snapshot_id"])
    delta = payload.get("response_mode") == "delta"
    lead = "New and updated cards relative to the requested snapshot." if delta else AGENDA_LEAD
    body = [
        f"<h1>AstraFeed · Crypto agenda · {escape(short_time(payload['t']))}</h1>",
        f'<p class="lead">{lead} Same snapshot: <code>POST /a2mcp/astrafeed</code>.</p>',
        _html_status(payload),
        _html_feed_directory(rss_feeds or [], reddit_feeds or []),
        _html_source_posts(payload),
    ]
    body.extend(f'<p class="note">{escape(line)}</p>' for line in comparison_lines(payload))
    if not payload["stories"] and not delta:
        body.append(f"<p>{EMPTY_AGENDA}</p>")
    for index, card in enumerate(payload["stories"], 1):
        href = f"/stories/{quote(card['story_id'])}?format=html&amp;snapshot_id={snapshot}"
        title = f'<h2><a href="{href}">{index}. {escape(card["title"])}</a></h2>'
        quotes = "".join(_html_quote(claim) for claim in card["claims"][:CARD_QUOTES])
        talk = _html_discussion(card, full=False)
        body.append(f"<article>{_html_card_head(card, title)}{quotes}{talk}</article>")
    leads = payload.get("lead_channels") or []
    if leads:
        items = "".join(
            f"<li><b>{escape(lead['channel'])}</b> — first on {lead['stories_first']} "
            f"{'story' if lead['stories_first'] == 1 else 'stories'}, "
            f"{escape(head_start(lead))}</li>"
            for lead in leads
        )
        body.append(f"<h2>⚡ First to report</h2><ul>{items}</ul>")
    upcoming = payload.get("upcoming") or []
    if upcoming:
        items = "".join(
            f"<li>{escape(card['title'])} ({channel_count(card['current_channels'])})</li>"
            for card in upcoming
        )
        body.append(f"<h2>📅 On the calendar</h2><ul>{items}</ul>")
    baseline_query = (
        f"&amp;since_snapshot_id={quote(payload['since_snapshot_id'], safe='')}"
        if "since_snapshot_id" in payload
        else ""
    )
    trust = trust_line(payload)
    trust_html = f"<br>{escape(trust)}" if trust else ""
    body.append(
        "<footer>Copies repeat an earlier source's text near-verbatim: reach, not confirmation. "
        "Prices are OKX spot context, not cause. "
        "Quotes from non-English posts and comments are machine-translated. "
        f"Snapshot {escape(payload['snapshot_id'])} · "
        f'<a href="/agenda?format=md&amp;snapshot_id={snapshot}{baseline_query}">Markdown</a> · '
        f'<a href="/agenda?snapshot_id={snapshot}{baseline_query}">JSON</a>'
        f"{trust_html}</footer>"
    )
    return _html_page("AstraFeed · Crypto agenda", "".join(body))


def render_story_html(payload: dict) -> str:
    card = payload["story"]
    snapshot = quote(payload["snapshot_id"])
    body = [
        f'<p class="meta"><a href="/agenda?format=html&amp;snapshot_id={snapshot}">'
        "← Agenda</a></p>",
        f"<article>{_html_card_head(card, f'<h1>{escape(card["title"])}</h1>')}</article>",
    ]
    if card["claims"]:
        body.append("<h2>What sources say</h2>" + "".join(_html_quote(c) for c in card["claims"]))
    body.append(_html_discussion(card, full=True))
    if card.get("positions"):
        body.append("<h2>Author opinions</h2>" + "".join(_html_quote(p) for p in card["positions"]))
    if card.get("publications"):
        items = "".join(
            f"<li>{escape(short_time(pub['published_at']))} "
            f'<a href="{_url(pub["link"])}">{escape(pub["channel"])}</a></li>'
            for pub in card["publications"]
        )
        body.append(f"<h2>Posts</h2><ul>{items}</ul>")
    body.append(
        f"<footer>{_html_status(payload)}Snapshot {escape(payload['snapshot_id'])}</footer>"
    )
    return _html_page(card["title"], "".join(body))
