from app.subtitles import formats
from app.subtitles.formatter import (
    rewrap_subtitles,
    segments_to_subtitles,
    words_to_subtitles,
    wrap_text,
)
from app.subtitles.srt import parse_srt, read_srt, write_srt
from app.subtitles.types import Subtitle, SubtitleParams, Word
from app.transcription.engine import TranscriptSegment


def test_segment_formatting(tmp_path):
    segments = [TranscriptSegment("Hello world", 1.2, 3.4)]
    subtitles = segments_to_subtitles(segments)
    output = tmp_path / "test.srt"
    write_srt(subtitles, output)
    assert output.read_text(encoding="utf-8") == "1\n00:00:01,200 --> 00:00:03,400\nHello world\n"


def test_long_segment_uses_real_line_breaks():
    text = "Це довге речення, яке точно не влізе в один рядок субтитрів для відео"
    subtitles = segments_to_subtitles([TranscriptSegment(text, 0, 4)])
    assert all("\\n" not in s.text for s in subtitles)
    assert "\n" in subtitles[0].text
    assert all(len(line) <= 42 for s in subtitles for line in s.text.split("\n"))


def test_srt_round_trip_keeps_lines(tmp_path):
    source = tmp_path / "source.srt"
    write_srt([Subtitle(0.5, 2.25, "Hello\nworld")], source)
    subtitles = read_srt(source)
    assert len(subtitles) == 1
    assert subtitles[0].start == 0.5
    assert subtitles[0].end == 2.25
    assert subtitles[0].text == "Hello\nworld"


def test_parse_srt_tolerates_crlf_and_short_fraction():
    text = "1\r\n00:00:01,5 --> 00:00:02,000 X1:0\r\nHi\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nThere\r\n"
    subs = parse_srt(text)
    assert [s.text for s in subs] == ["Hi", "There"]
    assert subs[0].start == 1.5


def test_wrap_text_balances_two_lines():
    lines = wrap_text("one two three four five six seven eight nine ten eleven", 42, 2)
    assert len(lines) == 2
    assert abs(len(lines[0]) - len(lines[1])) <= 8


def test_wrap_text_never_drops_text():
    text = " ".join(["слово"] * 40)
    lines = wrap_text(text, 20, 2)
    assert " ".join(lines) == text


def _words(text, start=0.0, step=0.3):
    words = []
    t = start
    for token in text.split():
        words.append(Word(token, t, t + step * 0.8))
        t += step
    return words


def test_words_split_at_sentences_and_pauses():
    words = _words("Привіт. Як справи?") + _words("Все добре", start=5.0)
    subs = words_to_subtitles(words)
    assert [s.text for s in subs] == ["Привіт.", "Як справи?", "Все добре"]
    assert subs[2].start == 5.0


def test_words_respect_line_limits_and_no_overlap():
    words = _words(" ".join(["дуже", "довгий", "текст"] * 30), step=0.25)
    params = SubtitleParams(max_chars_per_line=30, max_lines=2)
    subs = words_to_subtitles(words, params)
    assert len(subs) > 3
    for sub in subs:
        lines = sub.text.split("\n")
        assert len(lines) <= 2 and all(len(line) <= 30 for line in lines)
    for a, b in zip(subs, subs[1:]):
        assert a.end <= b.start


def test_min_duration_extends_short_subtitle():
    subs = words_to_subtitles([Word("Так.", 1.0, 1.2)], SubtitleParams(min_duration=1.0))
    assert subs[0].end - subs[0].start >= 1.0


def test_rewrap_after_translation():
    subs = rewrap_subtitles([Subtitle(0, 2, "a very long translated line that clearly needs wrapping now")])
    assert "\n" in subs[0].text


def test_other_formats():
    subs = [Subtitle(1.0, 2.5, "Hello\nworld"), Subtitle(10.0, 11.0, "Again")]
    vtt = formats.format_vtt(subs)
    assert vtt.startswith("WEBVTT") and "00:00:01.000 --> 00:00:02.500\nHello\nworld" in vtt
    ass = formats.format_ass(subs)
    assert "Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,Hello\\Nworld" in ass
    txt = formats.format_txt(subs)
    assert txt == "[00:01] Hello world\n\n[00:10] Again\n"
