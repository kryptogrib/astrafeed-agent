from __future__ import annotations

from datetime import UTC, datetime, timedelta

from astrafeed.domain import Item
from astrafeed.report.dedup import MergedItem
from astrafeed.report.events import (
    ComponentJudgment,
    EventGroup,
    EventJudgeResult,
    assemble_components,
    merge_events,
)

BASE = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)


def _item(ch: str, ext: str, text: str, ts: datetime) -> Item:
    handle = ch.lstrip("@")
    return Item(
        channel_ref=ch,
        external_id=ext,
        text=text,
        link=f"https://t.me/{handle}/{ext}",
        timestamp=ts,
    )


def _merged(
    ch: str,
    ext: str,
    text: str,
    *,
    ts: datetime = BASE,
    imp: int = 3,
    gist: str | None = None,
    event_key: str = "",
) -> MergedItem:
    it = _item(ch, ext, text, ts)
    return MergedItem(
        event_key=event_key,
        gist=gist if gist is not None else text,
        importance=imp,
        interests=("AI",),
        sources=((ch.lstrip("@"), it.link),),
        cluster_id=f"{ch}{ext}",  # unique: never collide via the cluster_id route
        representative_item=it,
        first_ts=ts,
        anchor_link=it.link,
        member_item_ids=((ch, ext),),
    )


def _all_in_one(components, *, confidence: float = 0.9) -> EventJudgeResult:
    """Judge that fuses every member of every component into a single group."""
    return EventJudgeResult(
        components=tuple(
            ComponentJudgment(
                groups=(
                    EventGroup(
                        ids=tuple(str(i) for i in range(len(comp))),
                        confidence=confidence,
                        framing={str(i): "distinct" for i in range(len(comp))},
                    ),
                ),
                rejected_ids=(),
            )
            for comp in components
        )
    )


# --- positive merge ----------------------------------------------------------


def _fable_core() -> list[MergedItem]:
    # The proven Fable-shutdown core: four DIFFERENT channels, same concrete event,
    # all within entity_proximity. Shared entity "Fable" + shared action "закрыл".
    return [
        _merged("@source_alpha", "3710", "Fable закрыл проект, команда расходится"),
        _merged("@source_beta", "285", "Стартап Fable закрыл сервис", ts=BASE + timedelta(hours=2)),
        _merged(
            "@source_gamma", "15904", "Fable закрыл доступ, shutdown", ts=BASE + timedelta(hours=4)
        ),
        _merged(
            "@source_delta", "10319", "Проект Fable закрыл двери", ts=BASE + timedelta(hours=6)
        ),
    ]


def test_fable_shutdown_core_merges_into_one_event():
    items = _fable_core()
    components = assemble_components(items)
    assert len(components) == 1
    assert {m.representative_item.channel_ref for m in components[0]} == {
        "@source_alpha",
        "@source_beta",
        "@source_gamma",
        "@source_delta",
    }
    blocks, consumed = merge_events(components, _all_in_one(components))
    assert len(blocks) == 1
    assert len(consumed) == 4
    assert set(blocks[0].member_item_ids) == {
        ("@source_alpha", "3710"),
        ("@source_beta", "285"),
        ("@source_gamma", "15904"),
        ("@source_delta", "10319"),
    }


def test_headline_member_excluded_from_subfacts():
    # The headline member is rendered verbatim as the headline, so it must NOT also
    # appear as a subfact — otherwise it duplicates and eats a slot from
    # event_subfacts_max. With 4 fused members, exactly 3 subfacts remain.
    items = _fable_core()
    components = assemble_components(items)
    blocks, _consumed = merge_events(components, _all_in_one(components))
    block = blocks[0]
    assert len(block.subfacts) == 3  # 4 members − 1 headline
    headline_pair = (block.headline_gist, block.headline_link)
    assert headline_pair not in block.subfacts
    assert block.headline_gist not in {gist for gist, _ in block.subfacts}


def test_reversibility_reconstructs_original_set_from_member_ids():
    items = _fable_core()
    components = assemble_components(items)
    blocks, _consumed = merge_events(components, _all_in_one(components))
    block = blocks[0]
    # From the block's stable member keys alone, recover the exact MergedItem set.
    by_key = {it.member_item_ids[0]: it for it in items}
    recovered = [by_key[k] for k in block.member_item_ids]
    assert recovered == items


# --- adversarial NON-merges --------------------------------------------------


def test_same_channel_fable_3d_is_not_even_a_candidate():
    # Increment 1 is cross-channel only: two posts from the SAME channel never
    # form a candidate edge, no matter how similar.
    items = [
        _merged("@fable", "100", "Fable выпустил 3D режим закрыл бету"),
        _merged("@fable", "101", "Fable закрыл доступ к 3D", ts=BASE + timedelta(hours=1)),
    ]
    assert assemble_components(items) == []


def test_grok_hack_orthogonal_to_fable_cad():
    # Different entities (Grok vs Fable) ⇒ no shared significant entity ⇒ no edge.
    items = [
        _merged("@a", "1", "Grok взлом jailbreak hack обнаружен"),
        _merged("@b", "2", "Fable CAD выпустил закрыл фичу", ts=BASE + timedelta(hours=1)),
    ]
    assert assemble_components(items) == []


def test_export_orthogonal_to_shutdown():
    # Same vague action family but no shared entity ⇒ not a candidate.
    items = [
        _merged("@a", "1", "Nvidia экспорт чипов в Китай"),
        _merged("@b", "2", "Fable закрыл проект", ts=BASE + timedelta(hours=1)),
    ]
    assert assemble_components(items) == []


def test_distinct_same_channel_stories_do_not_merge():
    # @source_delta/10325 ⟂ 10326: same channel ⇒ never candidates even if both mention
    # an entity+action.
    items = [
        _merged("@source_delta", "10325", "OpenAI закрыл доступ к API"),
        _merged("@source_delta", "10326", "OpenAI закрыл офис", ts=BASE + timedelta(hours=1)),
    ]
    assert assemble_components(items) == []


def test_outside_window_is_not_a_candidate():
    items = [
        _merged("@a", "1", "Fable закрыл проект"),
        _merged("@b", "2", "Fable закрыл проект", ts=BASE + timedelta(hours=72)),
    ]
    assert assemble_components(items, window_h=48) == []


# --- malformed judge degradation ---------------------------------------------


def test_length_mismatch_degrades_all_to_bullets():
    items = _fable_core()
    components = assemble_components(items)
    bad = EventJudgeResult(components=())  # 0 != 1 input component
    blocks, consumed = merge_events(components, bad)
    assert blocks == [] and consumed == []


def test_per_component_duplicate_id_keeps_only_that_component_as_bullets():
    # Two independent components; component B's judgment duplicates an id. Only B
    # degrades to bullets; component A still merges.
    items = [
        _merged("@a", "1", "Fable закрыл проект"),
        _merged("@b", "2", "Fable закрыл сервис", ts=BASE + timedelta(hours=1)),
        _merged("@c", "3", "Grok hack jailbreak взлом"),
        _merged("@d", "4", "Grok hack jailbreak найден", ts=BASE + timedelta(hours=1)),
    ]
    components = assemble_components(items)
    assert len(components) == 2
    result = EventJudgeResult(
        components=(
            ComponentJudgment(
                groups=(EventGroup(ids=("0", "1"), confidence=0.9, framing={}),),
                rejected_ids=(),
            ),
            ComponentJudgment(  # malformed: id "0" appears twice
                groups=(EventGroup(ids=("0", "0"), confidence=0.9, framing={}),),
                rejected_ids=(),
            ),
        )
    )
    blocks, consumed = merge_events(components, result)
    assert len(blocks) == 1
    assert {m.representative_item.channel_ref for m in consumed} == {"@a", "@b"}


def test_low_confidence_group_falls_back_to_bullets():
    items = _fable_core()
    components = assemble_components(items)
    weak = _all_in_one(components, confidence=0.3)
    blocks, consumed = merge_events(components, weak, min_confidence=0.6)
    assert blocks == [] and consumed == []


def test_missing_id_stays_bullet_rest_still_merge():
    items = _fable_core()  # one component of 4
    components = assemble_components(items)
    # Group only ids 0,1,2 (id 3 missing → its own bullet); coverage allows it.
    result = EventJudgeResult(
        components=(
            ComponentJudgment(
                groups=(EventGroup(ids=("0", "1", "2"), confidence=0.9, framing={}),),
                rejected_ids=(),
            ),
        )
    )
    blocks, consumed = merge_events(components, result)
    assert len(blocks) == 1
    assert len(consumed) == 3


# --- cost caps ---------------------------------------------------------------


def test_dense_component_size_cap():
    # Eight cross-channel posts all about the same event would form one huge
    # component; the size cap bounds the judged set.
    items = [
        _merged(f"@c{i}", str(i), "Fable закрыл проект", ts=BASE + timedelta(hours=i))
        for i in range(8)
    ]
    components = assemble_components(items, max_component_size=4)
    assert len(components) == 1
    assert len(components[0]) == 4


def test_max_components_per_report_cap():
    # Three independent 2-channel events, capped to 2 components.
    items = []
    details = {
        "Fable": ("команда расходится навсегда", "доступ пользователям прекращён"),
        "Grok": ("регуляторы потребовали остановки", "инвесторы вывели финансирование"),
        "Mistral": ("европейский офис ликвидирован", "облачный сервис недоступен утром"),
    }
    for k, (ent, (a, b)) in enumerate(details.items()):
        items.append(_merged(f"@x{k}", f"{k}0", f"{ent} закрыл {a}"))
        items.append(_merged(f"@y{k}", f"{k}1", f"{ent} закрыл {b}", ts=BASE + timedelta(hours=1)))
    components = assemble_components(items, max_components=2)
    assert len(components) == 2


def test_non_sequential_group_ids_map_framing_to_right_member():
    # Component of 3; the judge merges ids 0 and 2 (NOT 1), with per-id framing.
    # Framing must be attributed by component-local id, never by member position —
    # member at position 1 in the built block is comp[2], whose framing is "0.4"...
    # C is the highest-importance member ⇒ it is the headline (excluded from
    # subfacts), leaving A as the sole DISTINCT non-headline subfact. This keeps the
    # framing-attribution assertion meaningful under build-time headline exclusion.
    items = [
        _merged("@a", "1", "Fable закрыл проект alpha", gist="A gist"),
        _merged("@b", "2", "Unrelated middle post", gist="B gist", ts=BASE + timedelta(hours=1)),
        _merged(
            "@c",
            "3",
            "Fable закрыл проект beta",
            gist="C gist",
            imp=5,
            ts=BASE + timedelta(hours=2),
        ),
    ]
    components = [items]  # hand-built single component
    result = EventJudgeResult(
        components=(
            ComponentJudgment(
                groups=(
                    EventGroup(
                        ids=("0", "2"),
                        confidence=0.9,
                        framing={"0": "distinct", "2": "redundant"},
                    ),
                ),
                rejected_ids=("1",),
            ),
        )
    )
    blocks, consumed = merge_events(components, result)
    assert len(blocks) == 1
    # Only id 0 (A gist) is "distinct" ⇒ exactly one subfact, and it is A's gist —
    # NOT C's. A position-based lookup would have mis-tagged comp[2] as distinct.
    assert blocks[0].subfacts == (("A gist", items[0].anchor_link),)
    assert {m.representative_item.channel_ref for m in consumed} == {"@a", "@c"}


def test_jaccard_is_sole_recall_route():
    # No shared named entity, no shared action term — only ≥50% token overlap.
    # Route 3 alone must still propose the cross-channel candidate edge.
    items = [
        _merged("@a", "1", "квартальная выручка значительно превысила прогнозы аналитиков"),
        _merged(
            "@b",
            "2",
            "выручка значительно превысила прогнозы рыночных аналитиков снова",
            ts=BASE + timedelta(hours=3),
        ),
    ]
    components = assemble_components(items)
    assert len(components) == 1
    assert len(components[0]) == 2


def test_empty_input_is_safe():
    assert assemble_components([]) == []
    assert merge_events([], EventJudgeResult()) == ([], [])


def test_recall_uses_gists_when_source_action_words_differ():
    members = [
        _merged(
            "@a",
            "1",
            "OpenAI выложили блогпост о доказательстве.",
            gist="OpenAI опубликовала решение задачи Навье-Стокса.",
        ),
        _merged(
            "@b",
            "2",
            "Мы дождались! Задача решена десятью тысячами агентов.",
            gist="OpenAI решила задачу Навье-Стокса с помощью агентов.",
        ),
        _merged("@c", "3", "OpenAI обновили тарифы.", gist="OpenAI обновила цены на API."),
    ]
    components = assemble_components(members)
    assert any(members[0] in c and members[1] in c for c in components)


def test_event_subfacts_preserve_grounded_details_including_headline_source():
    members = [
        _merged("@a", "1", "Release. Costs $10.", gist="Release"),
        _merged("@b", "2", "Release. Twice as fast.", gist="Release"),
    ]
    group = EventGroup(
        ids=("0", "1"),
        confidence=0.9,
        framing={"0": "redundant", "1": "redundant"},
        subfacts={"0": ("Costs $10.",), "1": ("Twice as fast.", "Invented fact")},
    )
    blocks, _ = merge_events(
        [members], EventJudgeResult(components=(ComponentJudgment(groups=(group,)),))
    )
    assert [text for text, _ in blocks[0].subfacts] == ["Costs $10.", "Twice as fast."]


def test_recall_matches_summary_event_terms_against_original_context():
    a = _merged(
        "@a",
        "1",
        "Acme scientists celebrate their breakthrough.",
        gist="Researchers discuss quantum teleportation",
    )
    b = _merged(
        "@b",
        "2",
        "Acme published a quantum teleportation experiment with new error correction.",
        gist="Acme publishes a breakthrough",
    )
    assert assemble_components([a, b]) == [[a, b]]


def test_extra_quote_does_not_replace_distinct_member_gist():
    a = _merged("@a", "1", "Acme releases X", gist="Acme releases X", imp=5)
    b = _merged(
        "@b",
        "2",
        "X halves inference cost. Available in 20 countries.",
        gist="X halves inference cost",
    )
    group = EventGroup(
        ids=("0", "1"),
        confidence=0.9,
        framing={"1": "distinct"},
        subfacts={"1": ("Available in 20 countries.",)},
    )
    blocks, _ = merge_events(
        [[a, b]], EventJudgeResult(components=(ComponentJudgment(groups=(group,)),))
    )
    assert {text for text, _ in blocks[0].subfacts} == {
        "X halves inference cost",
        "Available in 20 countries.",
    }


def test_shared_generic_image_editing_terms_do_not_nominate_a_merge():
    a = _merged(
        "@a",
        "1",
        "ChatGPT выпустил генератор изображений с поддержкой редактирования.",
        gist="ChatGPT выпустил продукт",
    )
    b = _merged(
        "@b",
        "2",
        "ChatGPT переводит скриншоты.",
        gist="Модель редактирования изображений ChatGPT переводит скриншоты",
    )
    assert assemble_components([a, b]) == []


def test_shared_company_does_not_merge_distinct_product_announcements():
    audio = _merged(
        "@audio",
        "1",
        "A company released an audio model for speech generation and editing.",
        gist="A company released an audio model",
    )
    cli = _merged(
        "@agents",
        "2",
        "A company released a CLI for sharing agent configuration in git.",
        gist="A company released a team agent CLI",
    )

    blocks, consumed = merge_events([[audio, cli]], _all_in_one([[audio, cli]]))

    assert blocks == []
    assert consumed == []


def test_live_regression_audio_model_and_team_cli_stay_separate():
    audio = _merged(
        "@ai_newz",
        "4755",
        "Tencent выкатили AuK для генерации и редактирования речи.",
        gist="Tencent выпустила аудиомодель AuK для генерации и редактирования речи",
    )
    cli = _merged(
        "@ai_machinelearning_big_data",
        "10908",
        "Tencent TeamAI CLI складывает навыки и настройки агентов в git-репозиторий.",
        gist="Tencent выпустил TeamAI CLI для централизованного конфига AI-агентов",
    )

    blocks, consumed = merge_events([[audio, cli]], _all_in_one([[audio, cli]]))

    assert blocks == []
    assert consumed == []


def test_distinct_project_urls_on_same_host_do_not_merge_product_announcements():
    audio = _merged(
        "@audio",
        "1",
        "Tencent released AuK. https://github.com/Tencent/AuK",
        gist="Tencent released the AuK audio model",
    )
    cli = _merged(
        "@agents",
        "2",
        "Tencent released TeamAI CLI. https://github.com/Tencent/TeamAI",
        gist="Tencent released the TeamAI agent CLI",
    )

    blocks, consumed = merge_events([[audio, cli]], _all_in_one([[audio, cli]]))

    assert blocks == []
    assert consumed == []


def test_one_shared_ordinary_word_does_not_merge_product_announcements():
    audio = _merged(
        "@audio",
        "1",
        "Сегодня Tencent выпустила AuK для обработки речи.",
        gist="Tencent выпустила аудиомодель AuK сегодня",
    )
    cli = _merged(
        "@agents",
        "2",
        "Сегодня Tencent выпустила TeamAI CLI для команд агентов.",
        gist="Tencent выпустила TeamAI CLI сегодня",
    )

    blocks, consumed = merge_events([[audio, cli]], _all_in_one([[audio, cli]]))

    assert blocks == []
    assert consumed == []


def test_two_shared_ordinary_words_do_not_merge_product_announcements():
    audio = _merged(
        "@audio",
        "1",
        "Сегодня также Tencent выпустила AuK для обработки речи.",
        gist="Tencent выпустила удобную аудиомодель AuK",
    )
    cli = _merged(
        "@agents",
        "2",
        "Сегодня также Tencent выпустила TeamAI CLI для агентов.",
        gist="Tencent выпустила удобный TeamAI CLI",
    )

    blocks, consumed = merge_events([[audio, cli]], _all_in_one([[audio, cli]]))

    assert blocks == []
    assert consumed == []


def test_exact_nonroot_source_url_can_corroborate_same_event():
    first = _merged(
        "@a",
        "1",
        "Acme announced a release. https://example.com/news/releases/42?utm_source=feed",
        gist="Acme announced a new release",
    )
    second = _merged(
        "@b",
        "2",
        "Details are available at https://example.com/news/releases/42#benchmarks",
        gist="Release benchmarks are available",
    )

    blocks, consumed = merge_events([[first, second]], _all_in_one([[first, second]]))

    assert len(blocks) == 1
    assert consumed == [first, second]


def test_same_url_path_with_different_identity_query_does_not_merge():
    first = _merged(
        "@a",
        "1",
        "Acme announced Alpha. https://example.com/article?id=1",
        gist="Acme announced Alpha",
    )
    second = _merged(
        "@b",
        "2",
        "Acme announced Beta. https://example.com/article?id=2",
        gist="Acme announced Beta",
    )

    blocks, consumed = merge_events([[first, second]], _all_in_one([[first, second]]))

    assert blocks == []
    assert consumed == []


def test_shared_product_merges_same_release_with_different_details():
    release = _merged(
        "@models",
        "1",
        "Acme released Orion, a speech generation model.",
        gist="Acme released Orion",
    )
    benchmark = _merged(
        "@benchmarks",
        "2",
        "The new Acme Orion model runs four times faster.",
        gist="Acme Orion runs faster",
    )

    blocks, consumed = merge_events([[release, benchmark]], _all_in_one([[release, benchmark]]))

    assert len(blocks) == 1
    assert consumed == [release, benchmark]


# --- recall precision --------------------------------------------------------


def test_shared_topic_vocabulary_alone_is_not_a_candidate_pair():
    """Two different events worded alike ("компания объявила … модели") must not
    become one component: every false candidate spends judge budget inside the
    200-pair cap and is one bad judgement away from a wrong merge."""
    comps = assemble_components(
        [
            _merged("@a", "1", "Компания Anthropic объявила о запуске новой модели."),
            _merged("@b", "2", "Компания Google объявила о закрытии старой модели."),
        ],
    )
    assert comps == []


def test_same_event_key_within_the_proximity_window_is_a_candidate_pair():
    """A rewrite shares no wording with its original — different verbs, different
    framing, no link. The scorer read both and named the same event, which is the
    only signal left. The judge still has to confirm it."""
    comps = assemble_components(
        [
            _merged(
                "@a",
                "1",
                "Крупнейшая площадка добавила в оборот новый токен.",
                event_key="binance|listing|foo",
            ),
            _merged(
                "@b",
                "2",
                "Теперь FOO можно купить у одного из ведущих обменников.",
                event_key="binance|listing|foo",
            ),
        ],
    )
    assert [sorted(m.representative_item.external_id for m in c) for c in comps] == [["1", "2"]]


def test_same_event_key_outside_the_proximity_window_is_not_a_candidate_pair():
    """Two days apart the same key names a recurring story, not one event; the
    user's rule is a 24-hour candidate window."""
    comps = assemble_components(
        [
            _merged("@a", "1", "Площадка добавила токен.", event_key="binance|listing|foo"),
            _merged(
                "@b",
                "2",
                "FOO теперь торгуется.",
                ts=BASE + timedelta(hours=30),
                event_key="binance|listing|foo",
            ),
        ],
    )
    assert comps == []
