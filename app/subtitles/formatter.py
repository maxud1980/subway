"""Turn recognized words or segments into readable subtitles."""
from __future__ import annotations

import re
from typing import Iterable, Sequence

from .types import Subtitle, SubtitleParams, Word

_SENTENCE_END = re.compile(r"[.!?…]+[\"'»”’)\]]*$")
_PUNCT_END = re.compile(r"[,;:.!?…]+[\"'»”’)\]]*$")
_CLAUSE_END = re.compile(r"[,;:]+[\"'»”’)\]]*$|^[—–]$")


def _greedy_lines(words: Sequence[str], max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _split_score(lines: list[str]) -> float:
    """Lower is better: short longest line, breaks after punctuation, no dangling short words."""
    score = float(max(len(x) for x in lines))
    for line in lines[:-1]:
        last = line.rsplit(" ", 1)[-1]
        if _PUNCT_END.search(last):
            score -= 6
        elif len(last.strip("«»\"'()")) <= 2:
            score += 5  # "я з / Харкова": a one- or two-letter word should start the next line.
    return score


def _balanced_lines(words: Sequence[str], count: int, max_chars: int) -> list[str] | None:
    """Split words into exactly `count` lines with the shortest longest line."""
    n = len(words)
    if count <= 1 or n < count:
        return None
    best: tuple[int, int, list[str]] | None = None

    def search(start: int, remaining: int, acc: list[str]) -> None:
        nonlocal best
        if remaining == 1:
            line = " ".join(words[start:])
            if len(line) > max_chars and not (n - start == 1):
                return
            lines = acc + [line]
            key = (_split_score(lines), max(len(lines[0]) - len(lines[-1]), 0))
            if best is None or key < best[:2]:
                best = (key[0], key[1], lines)
            return
        for end in range(start + 1, n - remaining + 2):
            line = " ".join(words[start:end])
            if len(line) > max_chars and end - start > 1:
                break
            search(end, remaining - 1, acc + [line])

    search(0, count, [])
    return best[2] if best else None


def wrap_text(text: str, max_chars: int = 42, max_lines: int = 2, allow_overflow: bool = True) -> list[str]:
    """Wrap text into balanced lines.

    When the text does not fit into `max_lines`, extra lines are added if
    `allow_overflow` is true, so no text is ever lost.
    """
    words = text.split()
    if not words:
        return []
    joined = " ".join(words)
    if len(joined) <= max_chars:
        return [joined]
    greedy = _greedy_lines(words, max_chars)
    target = len(greedy)
    if target > max_lines and not allow_overflow:
        target = max_lines
    if target <= 4 and len(words) <= 40:
        balanced = _balanced_lines(words, target, max_chars)
        if balanced:
            return balanced
    return greedy


def fits(text: str, params: SubtitleParams) -> bool:
    words = text.split()
    if len(words) <= 1:
        return True
    return len(_greedy_lines(words, params.max_chars_per_line)) <= params.max_lines


def _char_count(text: str) -> int:
    return len(text.replace("\n", ""))


def _adjust_timing(subtitles: list[Subtitle], params: SubtitleParams) -> list[Subtitle]:
    """Apply minimum duration, reading speed and gap rules without overlaps."""
    result: list[Subtitle] = []
    for index, sub in enumerate(subtitles):
        start, end = sub.start, max(sub.end, sub.start)
        next_start = subtitles[index + 1].start if index + 1 < len(subtitles) else float("inf")
        prev_end = result[-1].end if result else 0.0

        needed = max(params.min_duration, _char_count(sub.text) / params.max_cps)
        desired_end = max(end, min(start + needed, start + params.max_duration))
        limit = next_start - params.min_gap
        new_end = min(desired_end, limit) if limit > start else end

        # Not enough room after the subtitle: borrow a little time before it.
        missing = needed - (new_end - start)
        if missing > 0:
            earliest = max(prev_end + params.min_gap, start - min(missing, 0.5))
            if earliest < start:
                start = earliest

        if new_end <= start:
            new_end = start + 0.1
        result.append(Subtitle(round(start, 3), round(new_end, 3), sub.text))
    return result


def words_to_subtitles(words: Iterable[Word], params: SubtitleParams | None = None) -> list[Subtitle]:
    """Group timed words into subtitles at sentence, clause and pause boundaries."""
    params = (params or SubtitleParams()).normalized()
    items = [w for w in words if w.text and w.text.strip()]
    if not items:
        return []

    capacity = params.max_chars_per_line * params.max_lines
    groups: list[list[Word]] = []
    current: list[Word] = []

    def text_of(group: list[Word]) -> str:
        return " ".join(w.text.strip() for w in group)

    for word in items:
        if current:
            gap = word.start - current[-1].end
            candidate = text_of(current + [word])
            too_long = not fits(candidate, params)
            too_slow = word.end - current[0].start > params.max_duration
            if gap >= params.pause_split or too_long or too_slow:
                groups.append(current)
                current = []
        current.append(word)
        token = word.text.strip()
        length = len(text_of(current))
        if _SENTENCE_END.search(token) and length >= 3:
            groups.append(current)
            current = []
        elif _CLAUSE_END.search(token) and length >= capacity * 0.55:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    subtitles = []
    for group in groups:
        lines = wrap_text(text_of(group), params.max_chars_per_line, params.max_lines)
        subtitles.append(Subtitle(group[0].start, max(group[-1].end, group[0].start), "\n".join(lines)))
    return _adjust_timing(subtitles, params)


def segments_to_subtitles(segments, max_chars: int = 42, max_lines: int = 2,
                          params: SubtitleParams | None = None) -> list[Subtitle]:
    """Fallback for transcripts without word timings.

    Long segments are split into readable chunks and their time is shared in
    proportion to the amount of text in each chunk.
    """
    if params is None:
        params = SubtitleParams(max_chars_per_line=max_chars, max_lines=max_lines)
    params = params.normalized()
    subtitles: list[Subtitle] = []
    for segment in segments:
        text = " ".join(segment.text.split())
        if not text or segment.end <= segment.start:
            continue
        chunks: list[list[str]] = []
        current: list[str] = []
        for word in text.split():
            candidate = " ".join(current + [word])
            if current and not fits(candidate, params):
                chunks.append(current)
                current = []
            current.append(word)
            if _SENTENCE_END.search(word) and len(current) > 1:
                chunks.append(current)
                current = []
        if current:
            chunks.append(current)

        total = sum(len(" ".join(c)) for c in chunks) or 1
        duration = segment.end - segment.start
        position = segment.start
        for index, chunk in enumerate(chunks):
            chunk_text = " ".join(chunk)
            end = segment.end if index == len(chunks) - 1 else position + duration * len(chunk_text) / total
            lines = wrap_text(chunk_text, params.max_chars_per_line, params.max_lines)
            subtitles.append(Subtitle(position, end, "\n".join(lines)))
            position = end
    return _adjust_timing(subtitles, params)


def rewrap_subtitles(subtitles: Iterable[Subtitle], params: SubtitleParams | None = None) -> list[Subtitle]:
    """Re-wrap subtitle text (for example after translation) keeping timings."""
    params = (params or SubtitleParams()).normalized()
    return [
        Subtitle(s.start, s.end, "\n".join(wrap_text(" ".join(s.text.split()), params.max_chars_per_line, params.max_lines)))
        for s in subtitles
    ]
