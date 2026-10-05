from .types import Subtitle


def _split_text(text: str, max_chars: int, max_lines: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    if max_lines <= 1:
        return lines

    groups: list[str] = []
    for i in range(0, len(lines), max_lines):
        groups.append("\\n".join(lines[i:i + max_lines]))
    return groups


def segments_to_subtitles(segments, max_chars: int = 42, max_lines: int = 2) -> list[Subtitle]:
    subtitles: list[Subtitle] = []
    for segment in segments:
        text = segment.text.strip()
        if not text or segment.end <= segment.start:
            continue

        chunks = _split_text(text, max_chars, max_lines)
        if not chunks:
            continue

        if len(chunks) == 1:
            subtitles.append(Subtitle(segment.start, segment.end, chunks[0]))
            continue

        duration = segment.end - segment.start
        step = duration / len(chunks)
        for index, chunk in enumerate(chunks):
            start = segment.start + step * index
            end = segment.end if index == len(chunks) - 1 else start + step
            subtitles.append(Subtitle(start, end, chunk))

    return subtitles
