from __future__ import annotations

from astrafeed.report.entities import extract_entities


def test_latin_capitalized_tokens_extracted_and_casefolded():
    ents = extract_entities("Fable от Anthropic закрывается")
    assert "fable" in ents
    assert "anthropic" in ents


def test_generic_ai_denylist_removed():
    # The generic AI vocabulary must not become a shared "entity" — two unrelated
    # posts about an "Agent" or a "Model" should not collide on it.
    ents = extract_entities("Agent Model AI LLM Code")
    assert ents == frozenset()


def test_alias_dictionary_normalizes_variants():
    assert "gpt" in extract_entities("ChatGPT и GPT-4 обновились")
    # cyrillic transliteration alias resolves to the canonical Latin token
    assert "claude" in extract_entities("Клод выпустил апдейт")


def test_possessive_morphology_strip_collides():
    a = extract_entities("Fable's shutdown")
    b = extract_entities("the Fable shutdown")
    assert "fable" in a and "fable" in b


def test_empty_text_is_empty_set():
    assert extract_entities("") == frozenset()
    assert extract_entities(None) == frozenset()  # type: ignore[arg-type]
