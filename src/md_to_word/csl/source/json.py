import re

from .. import DATES, NAMES
from ..formatter.segments import (
    Bold, Italic, SmallCaps, Subscript, Superscript,
)
from ..string import MixedString, NoCase, String
from . import BibliographySource, Date, DateRange, LiteralDate, Name, Reference


class CiteProcJSON(BibliographySource):
    def __init__(self, json_data):
        for ref in json_data:
            ref_data = {}
            for key, value in ref.items():
                python_key = key.replace('-', '_')
                if python_key == 'id':
                    ref_key = str(value).lower()
                    continue
                elif python_key == 'type':
                    ref_type = value
                    continue
                elif python_key == 'key':
                    # conflicts with the ref_key, so ignore
                    continue
                if python_key == 'shortTitle':
                    python_key = 'title_short'

                if python_key in NAMES:
                    value = self.parse_names(value)
                elif python_key in DATES:
                    value = self.parse_date(value)
                elif key not in ('language', ):
                    value = self.parse_string(value)

                ref_data[python_key] = value
            self.add(Reference(ref_key, ref_type, **ref_data))

    # Zotero 把字段里的富文本存成这几个标签（CSL-JSON 的事实约定）。
    # `<i>`/`<b>`/`<sup>`/`<sub>` 要成为格式 run，`nocase` 保护大小写；
    # 不认识的标签原样保留，未闭合/错配的标签按就近原则收口，绝不复制正文。
    tag_re = re.compile(
        r'<(/?)(i|b|sup|sub|sc|span)\b([^<>]*)>', re.IGNORECASE)

    def parse_string(self, string):
        text = str(string)
        if '<' not in text:
            return MixedString([String(text)]) if text else MixedString()

        parts = []
        # 每帧：(标签名, 包装类, 子片段)。标签名用于配对关闭标签—
        # `</span>` 既可以关 nocase，也可以关 small-caps，得看开的是哪个。
        frames = [(None, None, parts)]
        buffer = []
        # 不认识的标签原样留着；它的关闭标签也要留着，不能删一半。
        literal = []

        def flush():
            if buffer:
                frames[-1][2].append(String(''.join(buffer)))
                buffer.clear()

        position = 0
        for match in self.tag_re.finditer(text):
            if match.start() > position:
                buffer.append(text[position:match.start()])
            position = match.end()
            closing, name, attrs = match.groups()
            name = name.lower()
            if not closing:
                wrapper = self._rich_wrapper(name, attrs)
                if wrapper is None:
                    literal.append(name)
                    buffer.append(match.group(0))
                    continue
                flush()
                frames.append((name, wrapper, []))
                continue
            if literal and literal[-1] == name:
                literal.pop()
                buffer.append(match.group(0))
                continue
            flush()
            for index in range(len(frames) - 1, 0, -1):
                if frames[index][0] != name:
                    continue
                while len(frames) - 1 >= index:
                    _name, inner_wrapper, inner_parts = frames.pop()
                    frames[-1][2].append(
                        self._wrap(inner_wrapper, inner_parts))
                break
        if position < len(text):
            buffer.append(text[position:])
        flush()
        while len(frames) > 1:
            _name, inner_wrapper, inner_parts = frames.pop()
            frames[-1][2].append(self._wrap(inner_wrapper, inner_parts))
        return MixedString(parts)

    @staticmethod
    def _rich_wrapper(name, attrs):
        name = name.lower()
        if name in ('i', 'b', 'sup', 'sub'):
            return {'i': Italic, 'b': Bold, 'sup': Superscript,
                    'sub': Subscript}[name]
        if name == 'sc':
            return SmallCaps
        normalized = re.sub(r'\s+', '', (attrs or '').lower()).replace("'", '"')
        if 'class="nocase"' in normalized or 'class="nodecor"' in normalized:
            return NoCase
        if 'font-variant:small-caps' in normalized:
            return SmallCaps
        return None

    @staticmethod
    def _wrap(wrapper, parts):
        if not parts:
            return wrapper('')
        inner = parts[0] if len(parts) == 1 else MixedString(parts)
        return wrapper(inner)

    def parse_names(self, json_data):
        names = []
        for name_data in json_data:
            name = Name(**name_data)
            names.append(name)
        return names

    def parse_date(self, json_data):
        def parse_single_date(json_date):
            date_data = {}
            try:
                for i, part in enumerate(('year', 'month', 'day')):
                    date_data[part] = json_date[i]
            except IndexError:
                pass
            return date_data

        dates = []
        for json_date in json_data.get('date-parts', []):
            date = parse_single_date(json_date)
            if 'season' in json_data:
                date['season'] = json_data['season']
            dates.append(date)

        circa = json_data.get('circa', 0) != 0

        if len(dates) == 1:
            return Date(circa=circa, **dates[0])
        elif len(dates) > 1:
            return DateRange(begin=Date(**dates[0]), end=Date(**dates[1]),
                             circa=circa)
        elif 'literal' in json_data:
            return LiteralDate(json_data['literal'], circa=circa)
        else:
            return None
