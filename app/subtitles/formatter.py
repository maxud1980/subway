from .types import Subtitle

def segments_to_subtitles(segments) -> list[Subtitle]:
    return [
        Subtitle(start=s.start, end=s.end, text=s.text)
        for s in segments if s.text.strip()
    ]
