import pytest
from hypothesis import given
from hypothesis import strategies as st
from vibechecker_engine.text import Refusal, count_words, prepare, validate

ENGLISH = "Students can bring their books to the library after school. "


def utf16_slice(text, start, end):
    return text.encode("utf-16-le")[start * 2 : end * 2].decode("utf-16-le")


@given(
    st.lists(
        st.sampled_from(["English", "😀", "🇭🇰", "中文", "e\u0301", "“I’m”", "👩🏽‍💻"]),
        min_size=1,
        max_size=18,
    )
)
def test_sentence_offsets_reference_original(parts):
    original = "  " + " ".join(parts) + "!\r\nShe writes.  "
    doc = prepare(original)
    for sentence in doc.sentences:
        assert (
            utf16_slice(original, sentence.start_utf16, sentence.end_utf16)
            == original[sentence.start : sentence.end]
        )
        assert doc.normalized[sentence.norm_start : sentence.norm_end] == sentence.normalized


def test_flags_and_chunks():
    doc = prepare(("We chose an apple for the morning snack. " * 60) + "I took an аpple\u200b.")
    assert doc.flags == ("invisible", "homoglyph")
    assert sum(len(chunk) for chunk in doc.chunks) == len(doc.sentences)
    assert all(sum(sentence.word_count for sentence in chunk) <= 200 for chunk in doc.chunks)


def test_word_count_matches_live_gate():
    assert count_words(" --  I’m well-read; 21,  🐈 and e\u0301!") == 5


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (ENGLISH, "too_short"),
        (
            "Mon voisin prépare une promenade dans les montagnes avec ses enfants. " * 30,
            "not_english",
        ),
        ("今天我要讨论这个非常重要的问题。" * 100, "not_english"),
        ("word " * 5001, "too_long"),
    ],
)
def test_refusal(text, code):
    with pytest.raises(Refusal) as result:
        validate(prepare(text))
    assert result.value.code == code


def test_length_boundaries():
    validate(prepare(ENGLISH * 15))
    with pytest.raises(Refusal, match="too_short"):
        validate(prepare(ENGLISH * 29), mode="deep")
    validate(prepare(ENGLISH * 30), mode="deep")
