"""Structured run output for the CSL engine.

The engine's string algebra (`String`/`MixedString`) already keeps formatting
objects apart until someone calls `str()`. This formatter uses that: wrappers
carry their format and their inner value, and `to_segments` flattens the tree
into `(text, format)` runs. No HTML is produced or parsed on this path.
"""

from __future__ import annotations

from ..string import MixedString


def preformat(text):
    return str(text)


class Styled(str):
    style: dict = {}

    def __new__(cls, text):
        obj = str.__new__(cls, str(text))
        obj.inner = text
        return obj


class Italic(Styled):
    style = {'italic': True}


class Oblique(Italic):
    pass


class Bold(Styled):
    style = {'bold': True}


class Superscript(Styled):
    style = {'superscript': True}


class Subscript(Styled):
    style = {'subscript': True}


# These exist because the CSL model names them; the Word writer has no
# corresponding run property for small-caps/light, so they pass through plain.
class Light(Styled):
    style = {}


class Underline(Styled):
    style = {}


class SmallCaps(Styled):
    style = {}


def merge_segments(segments):
    """Merge adjacent runs with the same format; drop empties."""
    output = []
    for text, fmt in segments:
        if not text:
            continue
        if output and output[-1][1] == fmt:
            output[-1] = (output[-1][0] + text, fmt)
        else:
            output.append((text, dict(fmt)))
    return output


def to_segments(value):
    """Flatten a rendered value into `(text, format)` runs."""
    runs = []

    def walk(node, fmt):
        if node is None:
            return
        if isinstance(node, (MixedString, list, tuple)):
            for child in node:
                walk(child, fmt)
        elif isinstance(node, Styled):
            walk(node.inner, {**fmt, **node.style})
        else:
            text = str(node)
            if text:
                runs.append((text, dict(fmt)))

    walk(value, {})
    return merge_segments(runs)


def segments_text(segments):
    return ''.join(text for text, _fmt in segments)


def slice_segments(segments, start, end):
    """Text slice that keeps each character's format."""
    if start >= end:
        return []
    cursor = 0
    output = []
    for text, fmt in segments:
        run_end = cursor + len(text)
        if run_end <= start:
            cursor = run_end
            continue
        if cursor >= end:
            break
        left = max(start, cursor) - cursor
        right = min(end, run_end) - cursor
        output.append((text[left:right], fmt))
        cursor = run_end
    return merge_segments(output)


def style_at(segments, index):
    cursor = 0
    for text, fmt in segments:
        cursor += len(text)
        if index < cursor:
            return fmt
    return {}


def strip_prefix(segments, prefix):
    if not prefix:
        return segments
    text = segments_text(segments)
    if not text.startswith(prefix):
        return segments
    return slice_segments(segments, len(prefix), len(text))


def strip_suffix(segments, suffix):
    if not suffix:
        return segments
    text = segments_text(segments)
    if not text.endswith(suffix):
        return segments
    return slice_segments(segments, 0, len(text) - len(suffix))


def replace_first(segments, old, new):
    """Replace the first occurrence, keeping the format at the match start."""
    text = segments_text(segments)
    index = text.find(old)
    if index < 0:
        return segments
    fmt = style_at(segments, index)
    return merge_segments(
        slice_segments(segments, 0, index)
        + [(new, fmt)]
        + slice_segments(segments, index + len(old), len(text))
    )


def join_segments(pieces, delimiter):
    output = []
    for index, piece in enumerate(pieces):
        if index:
            output.append((delimiter, {}))
        output.extend(piece)
    return merge_segments(output)
