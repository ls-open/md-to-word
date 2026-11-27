"""`text-case` 按 CSL 1.0.2 的口径逐条锁住。

以前只做了“把每个词首字母大写”：`state-of-the-art` 变成 `State-of-the-art`、
`eBay` 变成 `EBay`、末位停用词 `on` 不变、`For:` 认不出是停用词。规范和
stop-words.json 都写清楚了，这里按条目验证。
"""

from __future__ import annotations

from md_to_word.csl.model import TextCased
from md_to_word.csl.string import MixedString, NoCase, String, case_text


def _title(text: str) -> str:
    return str(case_text(String(text), "title"))


def test_hyphenated_parts_are_separate_words() -> None:
    assert _title("state-of-the-art methods") == "State-of-the-Art Methods"
    assert _title("the-state-of-the-art review") == "The-State-of-the-Art Review"


def test_first_and_last_words_are_capitalised_even_as_stop_words() -> None:
    assert _title("the war of the worlds") == "The War of the Worlds"
    assert _title("an apple a day, and so on") == "An Apple a Day, and so On"


def test_stop_word_after_a_colon_is_capitalised() -> None:
    assert _title("the end: of the line") == "The End: Of the Line"


def test_stop_word_with_trailing_punctuation_is_still_a_stop_word() -> None:
    assert _title("life, the universe and everything") == "Life, the Universe and Everything"
    assert _title("one, Of, the many") == "One, of, the Many"


def test_words_with_existing_capitalisation_are_untouched() -> None:
    assert _title("eBay and iPhone") == "eBay and iPhone"
    assert _title("mixed CASE title") == "Mixed CASE Title"


def test_all_caps_strings_fold_to_title_case() -> None:
    assert _title("THE WAR OF THE WORLDS") == "The War of the Worlds"


def test_multiword_stop_phrase_stays_lowercase() -> None:
    assert _title("a study according to the rules") == "A Study according to the Rules"


def test_capitalize_first_only_touches_a_lowercase_first_word() -> None:
    assert (str(case_text(String("eBay and iPhone"), "capitalize-first")) ==
            "eBay and iPhone")
    assert (str(case_text(String("mixed CASE title"), "capitalize-first")) ==
            "Mixed CASE title")


def test_capitalize_all_handles_hyphens_and_abbreviations() -> None:
    assert (str(case_text(String("state-of-the-art"), "capitalize-all")) ==
            "State-Of-The-Art")
    assert (str(case_text(String("life in the u.s.a."), "capitalize-all")) ==
            "Life In The U.S.A.")


def test_sentence_case_follows_the_spec() -> None:
    # 小写/混合：只动第一个词，其余保持原样。
    assert (str(case_text(String("eBay and iPhone"), "sentence")) ==
            "eBay and iPhone")
    assert (str(case_text(String("the states of matter"), "sentence")) ==
            "The states of matter")
    # 全大写：首字母保留，其余全部小写。
    assert (str(case_text(String("THE WAR OF THE WORLDS"), "sentence")) ==
            "The war of the worlds")


def test_nocase_spans_are_never_touched() -> None:
    text = MixedString([String("the "), NoCase("iPhone"), String(" CASE of art")])
    for mode in ("title", "lowercase", "uppercase", "capitalize-all"):
        result = case_text(text, mode)
        assert "iPhone" in str(result)
        assert [type(segment).__name__ for segment in result] == [
            "String", "NoCase", "String"]


def test_title_case_is_skipped_for_non_english_items() -> None:
    class _Element(TextCased):
        def __init__(self, value):
            self.value = value

        def get(self, key, default=None):
            return self.value if key == "text-case" else default

    assert _Element("title").case("the war", "zh") == "the war"
    assert _Element("title").case("the war", "en") == "The War"
