from app.subtitles.formatter import segments_to_subtitles
from app.subtitles.srt import write_srt
from app.transcription.engine import TranscriptSegment


def test_segment_formatting(tmp_path):
    segments = [TranscriptSegment("Hello world", 1.2, 3.4, [])]
    subtitles = segments_to_subtitles(segments)
    output = tmp_path / "test.srt"
    write_srt(subtitles, output)
    assert output.read_text(encoding="utf-8") == "1\n00:00:01,200 --> 00:00:03,400\nHello world\n"
