
import re
from functools import wraps

# Punctuation characters that should not be duplicated when two of them end up
# adjacent at a concatenation seam (e.g. a suffix '.' following text that
# already ends in '.').
# `display="block"` 在一条文献里断行。用行分隔符而不是 `\n`：空格合并、rstrip 这些
# 处理不会把它当成普通空白吃掉；写出器见到它落成 `<w:br/>`。
LINE_BREAK = '\u2028'

SEAM_PUNCTUATION = frozenset('.,;:!?')
# Punctuation that already closes a clause or sentence. A period appended after
# one of these is redundant: `2020;` + `. ` must not become `2020;.`.
# 与后处理里的 `_TERMINAL_PUNCT` 不同：这里多一个 `;`，因为它在拼接时就吃掉布局
# 补的句点（MDPI 的 `2020;` + `.`）；后处理只处理输出末尾的句末标点。
TERMINAL_PUNCTUATION = frozenset('.!?:;')


def normalize_seam(left, other):
    """Adjust the leading characters of `other` so that concatenating it onto
    `left` does not introduce a double space or a duplicated punctuation mark.

    `left` is the accumulated string so far and `other` the piece about to be
    appended. Only the boundary between them is considered; the interior of
    either side (e.g. an ellipsis inside a title) is never touched. Markup
    segments start with '<', so they are left alone. Returns `other`, possibly
    with its first character removed."""
    left = str(left)
    other_str = str(other)
    if not left or not other_str:
        return other
    last, first = left[-1], other_str[0]
    # collapse a double space
    if last == ' ' and first == ' ':
        return _strip_first_char(other)
    # drop a duplicated punctuation mark ('..' -> '.', ',,' -> ',', ...)
    if last == first and first in SEAM_PUNCTUATION:
        return _strip_first_char(other)
    # A suffix often carries its own trailing space (`suffix=". "`), so the same
    # check has to look past whitespace: `Things. ` + `. London` -> `Things. London`.
    tail = left.rstrip()
    if tail:
        last = tail[-1]
        if last == first and first in SEAM_PUNCTUATION:
            return _strip_first_char(other)
        if first == '.' and last in TERMINAL_PUNCTUATION:
            return _strip_first_char(other)
    return other


def _strip_first_char(other):
    """Return a copy of `other` with its first character removed, preserving
    the (Mixed)String segment structure."""
    if isinstance(other, MixedString):
        segments = list(other)
        head = segments[0]
        stripped = type(head)(str(head)[1:])
        segments[0:1] = [stripped] if stripped != '' else []
        return MixedString(segments)
    return type(other)(str(other)[1:])


def discard_empty_other(method):
    """Decorator for addition operator methods that returns the object itself if
    `other` is the empty string."""
    @wraps(method)
    def wrapper(obj, other):
        if other == '':
            return obj
        else:
            return method(obj, other)
    return wrapper


class String(str):
    @discard_empty_other
    def __radd__(self, other):
        return MixedString([other]).__add__(self)

    @discard_empty_other
    def __add__(self, other):
        return MixedString([self]).__add__(other)

    def __iadd__(self, other):
        return self.__add__(other)

    def replace(self, *args, **kwargs):
        return self.__class__(super().replace(*args, **kwargs))

    def rstrip(self, *args, **kwargs):
        return self.__class__(super().rstrip(*args, **kwargs))

    def lower(self):
        return self.__class__(super().lower())

    def upper(self):
        return self.__class__(super().upper())


class MixedString(list):
    @discard_empty_other
    def __add__(self, other):
        other = normalize_seam(self, other)
        if other == '' or other == []:
            return self

        try:
            return self.__class__(super().__add__(other))
        except TypeError:
            return self.__class__(super().__add__(MixedString([other])))

    @discard_empty_other
    def __radd__(self, other):
        return self.__class__([other]).__add__(self)

    def __iadd__(self, other):
        return self.__add__(other)

    def __str__(self):
        return ''.join(map(str, self))

    def __getitem__(self, index):
        return str(self)[index]

    def replace(self, *args):
        return self.__class__([string.replace(*args) for string in self])

    def translate(self, table):
        return self.__class__([string.translate(table) for string in self])

    def lower(self):
        return self.__class__([string.lower() for string in self])

    def upper(self):
        return self.__class__([string.upper() for string in self])

    def isupper(self):
        return all(string.isupper() for string in self)

    def split(self, *args, **kwargs):
        return str(self).split(*args, **kwargs)

    def rstrip(self, *args, **kwargs):
        rev_iter = reversed(self)
        output = [next(rev_iter).rstrip(*args, **kwargs)]
        output += [string for string in rev_iter]
        return self.__class__(reversed(output))


class NoCase(String):
    """A segment of CSL-JSON text inside `<span class="nocase">`: text-case
    conversions must leave it exactly as the source has it."""
    def __repr__(self):
        return f'{self.__class__.__name__}({self})'


# --- text-case -------------------------------------------------------------
#
# CSL 1.0.2 “Text Case Conversion”。要点：
#   * 词按标点切开，连字符连接的词段算独立的词（`two-thirds` → `Two-Thirds`）；
#   * title 的停用词取自 schema 的 stop-words.json，包括几个词组；
#   * 全大写的字符串先折成“首字母大写、其余小写”；
#   * 停用词一律小写，除非位于字符串首、末，或紧跟冒号；
#   * `nocase` 片段（Zotero 富文本）原样保留。

# https://resource.citationstyles.org/schema/latest/styles/stop-words.json
_STOP_WORDS = (
    'a', 'across', 'afore', 'after', 'against', 'along', 'alongside',
    'amid', 'amidst', 'among', 'amongst', 'an', 'and', 'anenst',
    'apropos', 'apud', 'around', 'as', 'aside', 'astride', 'at',
    'athwart', 'atop', 'barring', 'before', 'behind', 'below', 'beneath',
    'beside', 'besides', 'between', 'beyond', 'but', 'by', 'c', 'ca',
    'circa', "d'", 'de', 'despite', 'down', 'during', 'et', 'except',
    'for', 'forenenst', 'from', 'given', 'in', 'inside', 'into', 'lest',
    'like', 'modulo', 'near', 'next', 'nor', 'notwithstanding', 'of',
    'off', 'on', 'onto', 'or', 'out', 'over', 'per', 'plus', 'pro', 'qua',
    'sans', 'since', 'so', 'than', 'the', 'through', 'throughout', 'thru',
    'thruout', 'till', 'to', 'toward', 'towards', 'under', 'underneath',
    'until', 'unto', 'up', 'upon', 'v.', 'van', 'versus', 'via',
    'vis-à-vis', 'von', 'vs.', 'with', 'within', 'without', 'yet')
# 词条里的句点被词法切开，比对时按去掉句点的形式（`vs.` 配 `vs`）。
STOP_WORDS = frozenset(word.rstrip('.') for word in _STOP_WORDS)

STOP_PHRASES = ('according to', 'ahead of', 'apart from', 'as regards',
                'back to', 'because of', 'close to', 'due to', 'far from',
                'instead of', 'outside of', 'prior to', 'pursuant to',
                'rather than', 'regardless of', 'such as', 'that of',
                'where as')

# 词：字母/数字串，允许词内撇号（`don't`、`O’Brien`）。连字符、句点、括号、
# 引号、逗号、冒号等都算分隔符。
_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def _capitalise(word):
    first = word[:1]
    if first.isalpha() and first.islower():
        return first.upper() + word[1:]
    return word


def _collect_leaves(node, offset, leaves):
    """把嵌套的 (Mixed)String / 格式对象展开成叶子文本，记录每片的起点。

    格式对象（`formatter.Italic` 等）用 `.inner` 挂着真正的值；这里按值走，
    所以斜体、粗体、`nocase` 无论嵌套几层都能被看见。返回总长度。
    """
    if isinstance(node, (MixedString, list, tuple)):
        for child in node:
            offset = _collect_leaves(child, offset, leaves)
        return offset
    inner = getattr(node, 'inner', None)
    if inner is not None:
        return _collect_leaves(inner, offset, leaves)
    text = str(node)
    leaves.append((node, offset, text))
    return offset + len(text)


def _rebuild_leaves(node, texts):
    """按 `_collect_leaves` 的顺序，用 `texts` 里的新文本重建同样的结构。"""
    if isinstance(node, (MixedString, list, tuple)):
        return node.__class__([_rebuild_leaves(child, texts) for child in node])
    inner = getattr(node, 'inner', None)
    if inner is not None:
        return node.__class__(_rebuild_leaves(inner, texts))
    return node.__class__(next(texts))


def case_text(text, text_case):
    """按 `text_case` 转换文本，保留分段、格式与 `nocase` 片段。"""
    leaves = []
    _collect_leaves(text, 0, leaves)
    flat = ''.join(piece for _node, _start, piece in leaves)
    if not flat:
        return text

    protected = [False] * len(flat)
    for node, start, piece in leaves:
        if isinstance(node, NoCase):
            protected[start:start + len(piece)] = [True] * len(piece)

    matches = list(_WORD_RE.finditer(flat))
    if not matches:
        return text
    words = [match.group() for match in matches]
    lowers = [word.lower() for word in words]

    stop = [lower in STOP_WORDS for lower in lowers]
    for index in range(len(words)):
        for phrase in STOP_PHRASES:
            length = len(phrase.split())
            if (index + length <= len(words) and
                    ' '.join(lowers[index:index + length]) == phrase):
                for offset in range(index, index + length):
                    stop[offset] = True

    upper = flat.isupper()
    edits = []
    for index, match in enumerate(matches):
        start, end = match.start(), match.end()
        if any(protected[start:end]):
            continue
        word = words[index]
        if text_case == 'lowercase':
            new = word.lower()
        elif text_case == 'uppercase':
            new = word.upper()
        elif text_case == 'capitalize-all':
            new = _capitalise(word) if word.islower() else word
        elif text_case == 'capitalize-first':
            new = _capitalise(word) if index == 0 and word.islower() else word
        elif text_case == 'sentence':
            if upper:
                new = (word[:1] + word[1:].lower() if index == 0
                       else word.lower())
            else:
                new = (_capitalise(word)
                       if index == 0 and word.islower() else word)
        else:  # title
            # 首词、末词、紧跟冒号的词不受停用词规则影响。
            special = index in (0, len(words) - 1) or (
                ':' in flat[matches[index - 1].end():start] if index else False)
            if upper:
                new = word[:1] + word[1:].lower()
            elif word.islower():
                new = _capitalise(word)
            else:
                new = word
            if stop[index] and not special:
                new = new.lower()
        if new != word:
            edits.append((start, end, new))

    if not edits:
        return text
    texts = [piece for _node, _start, piece in leaves]
    for start, end, new in reversed(edits):
        for index in range(len(leaves) - 1, -1, -1):
            leaf_start = leaves[index][1]
            if leaf_start <= start and end <= leaf_start + len(texts[index]):
                local = start - leaf_start
                texts[index] = (texts[index][:local] + new +
                                texts[index][local + end - start:])
                break
    return _rebuild_leaves(text, iter(texts))


def join(items, delimiter=''):
    items = iter(items)
    try:
        output = next(items)
    except StopIteration:
        return String('')

    for item in items:
        delimiter_part = normalize_seam(output, delimiter)
        output = output + delimiter_part
        output = output + normalize_seam(output, item)
    return output
