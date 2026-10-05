from app.subtitles.formatter import segments_to_subtitles
from app.subtitles.srt import write_srt
from app.transcription.engine import TranscriptSegment


def test_segment_formatting(tmp_path):
    segments = [TranscriptSegment("Hello world", 1.2, 3.4, [])]
    subtitles = segments_to_subtitles(segments)
    output = tmp_path / "test.srt"
    write_srt(subtitles, output)
    assert output.read_text(encoding="utf-8") == "1\n00:00:01,200 --> 00:00:03,400\nHello world\n"


def test_srt_round_trip(tmp_path):
    from app.subtitles.srt import read_srt, write_srt
    from app.subtitles.types import Subtitle
    source = tmp_path / 'source.srt'
    write_srt([Subtitle(0.5, 2.25, 'Hello\nworld')], source)
    subtitles = read_srt(source)
    assert len(subtitles) == 1
    assert subtitles[0].start == 0.5
    assert subtitles[0].end == 2.25
    assert subtitles[0].text == 'Hello world'
