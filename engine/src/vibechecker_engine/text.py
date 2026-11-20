"""Keep offsets into the exact browser string separate from model input coordinates."""

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import regex
from lingua import Language, LanguageDetectorBuilder
from spacy.lang.en import English

WORD = regex.compile(r"[\p{L}\p{N}][\p{L}\p{N}\p{M}]*(?:['’\-][\p{L}\p{N}][\p{L}\p{N}\p{M}]*)*")
GRAPHEME = regex.compile(r"\X")
LATIN = regex.compile(r"\p{Script=Latin}")
CONFUSABLE_SCRIPT = regex.compile(r"[\p{Script=Cyrillic}\p{Script=Greek}]")
INVISIBLE = regex.compile(r"[\p{Cf}\u034f]")
CHUNK_WORDS = 200


class Refusal(ValueError):
    def __init__(self, code: Literal["too_short", "too_long", "not_english"]):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    start_utf16: int
    end_utf16: int
    norm_start: int
    norm_end: int
    normalized: str
    word_count: int


@dataclass(frozen=True)
class Prepared:
    normalized: str
    sentences: tuple[Sentence, ...]
    chunks: tuple[tuple[Sentence, ...], ...]
    words: tuple[str, ...]
    flags: tuple[str, ...]

    @property
    def word_count(self):
        return len(self.words)


@lru_cache(maxsize=1)
def _splitter():
    language = English()
    language.add_pipe("sentencizer")
    return language


@lru_cache(maxsize=1)
def _language_id():
    return LanguageDetectorBuilder.from_all_languages().with_low_accuracy_mode().build()


def count_words(text: str) -> int:
    return sum(1 for _ in WORD.finditer(text))


def _normalize(text: str):
    pieces = []
    # NFC can combine several input code points. Keep the original end boundary
    # for each output grapheme so an emoji or decomposed accent never shifts later spans.
    original = [0]
    utf16 = [0]
    for cluster in GRAPHEME.finditer(text):
        raw = cluster.group()
        norm = unicodedata.normalize("NFC", raw.replace("\r\n", "\n").replace("\r", "\n"))
        pieces.append(norm)
        if raw == norm:
            for index, char in enumerate(raw, cluster.start() + 1):
                original.append(index)
                utf16.append(utf16[-1] + 1 + int(ord(char) > 0xFFFF))
        else:
            original.extend([cluster.start()] * (len(norm) - 1) + [cluster.end()])
            utf16.extend(
                [utf16[-1]] * (len(norm) - 1)
                + [utf16[-1] + sum(1 + int(ord(c) > 0xFFFF) for c in raw)]
            )
    return "".join(pieces), original, utf16


def prepare(text: str) -> Prepared:
    normalized, original, utf16 = _normalize(text)
    words = tuple(WORD.findall(normalized))
    sentences = []
    chunks = []
    chunk: list[Sentence] = []
    chunk_count = 0
    for span in _splitter()(normalized).sents:
        start, end = span.start_char, span.end_char
        while start < end and normalized[start].isspace():
            start += 1
        while end > start and normalized[end - 1].isspace():
            end -= 1
        if start == end:
            continue
        value = normalized[start:end]
        sentence = Sentence(
            original[start],
            original[end],
            utf16[start],
            utf16[end],
            start,
            end,
            value,
            count_words(value),
        )
        sentences.append(sentence)
        if chunk and chunk_count + sentence.word_count > CHUNK_WORDS:
            chunks.append(tuple(chunk))
            chunk, chunk_count = [], 0
        chunk.append(sentence)
        chunk_count += sentence.word_count
    if chunk:
        chunks.append(tuple(chunk))
    flags = []
    if INVISIBLE.search(text):
        flags.append("invisible")
    if any(LATIN.search(word) and CONFUSABLE_SCRIPT.search(word) for word in words):
        flags.append("homoglyph")
    return Prepared(normalized, tuple(sentences), tuple(chunks), words, tuple(flags))


def validate(doc: Prepared, mode: Literal["quick", "deep"] = "quick") -> None:
    minimum, maximum = (150, 5000) if mode == "quick" else (300, 2500)
    if doc.word_count > maximum:
        raise Refusal("too_long")
    # An unsegmented script may count as only a few words despite a full essay.
    letters = regex.findall(r"\p{L}", doc.normalized)
    if len(letters) >= 40 and len(LATIN.findall(doc.normalized)) < len(letters) / 2:
        raise Refusal("not_english")
    if doc.word_count < minimum:
        raise Refusal("too_short")
    if _language_id().detect_language_of(doc.normalized) != Language.ENGLISH:
        raise Refusal("not_english")
